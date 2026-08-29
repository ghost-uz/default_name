"""Spam evristikasi: honeypot + signallar (D2-T5)."""

from __future__ import annotations

import re
import time
from datetime import timedelta
from pathlib import Path

import pytest
from django.conf import settings
from django.core import signing
from django.urls import reverse
from django.utils import timezone

from apps.common.spam import (
    HONEYPOT_MAYDONI,
    MIN_TOLDIRISH_VAQTI,
    SHUBHA_BALLI,
    VAQT_MAYDONI,
    Baho,
    bahola,
)
from apps.complaints.factories import CategoryFactory, ComplaintFactory
from apps.complaints.forms import ComplaintForm
from apps.complaints.models import Complaint, Generation
from apps.moderation.models import Report
from apps.moderation.selectors import navbat

pytestmark = pytest.mark.django_db

YOZISH = "/yozish/"


def vaqt(otgan: int) -> str:
    """`otgan` soniya oldin ochilgan forma uchun imzolangan belgi."""
    return signing.dumps({"t": int(time.time()) - otgan})


def malumot(kategoriya, *, otgan: int = 60, **ozgarish) -> dict:
    d = {
        "title": "Ipoteka olmoqchiman, lekin bank rad etdi",
        "description": (
            "Ikki bankka murojaat qildim va ikkalasi ham rad etdi. "
            "Kredit tarixim toza, daromadim rasmiy. Nima qilish kerak?"
        ),
        "category": kategoriya.pk,
        "generation_tag": Generation.MILLENNIAL,
        VAQT_MAYDONI: vaqt(otgan),
        HONEYPOT_MAYDONI: "",
    }
    d.update(ozgarish)
    return d


# ===========================================================================
# Baholash — signallar
# ===========================================================================
def test_toza_forma_SHUBHALI_EMAS():
    baho = bahola(honeypot="", vaqt=vaqt(60), matn="Oddiy matn, havolasiz.")

    assert baho.ball == 0
    assert baho.shubhalimi is False


def test_HONEYPOT_toldirilsa_BOT_ANIQ():
    """⚠️ Ko'rinmaydigan maydonni odam to'ldira olmaydi — mexanik
    aniqlik. Bu YAGONA holat kontentni rad etadi."""
    baho = bahola(honeypot="http://spam.example", vaqt=vaqt(60), matn="matn")

    assert baho.bot_aniq is True
    assert baho.shubhalimi is True


def test_QABUL_MEZONI_3_soniyadan_tez_forma_SHUBHALI():
    """⭐ Qabul mezoni: "3 sekunddan tez to'ldirilgan forma shubhali
    deb belgilanadi".

    ⚠️ Shuning uchun tez to'ldirish balli YOLG'IZ O'ZI chegaraga
       yetadi — boshqa hech qanday signal talab qilinmaydi.
    """
    baho = bahola(honeypot="", vaqt=vaqt(2), matn="Oddiy matn.")

    assert baho.shubhalimi is True, (
        f"{MIN_TOLDIRISH_VAQTI} soniyadan tez to'ldirilgan forma yolg'iz "
        f"o'zi shubhali bo'lishi kerak (ball={baho.ball}, chegara={SHUBHA_BALLI})"
    )


def test_sekin_toldirilgan_forma_SHUBHALI_EMAS():
    assert bahola(honeypot="", vaqt=vaqt(30), matn="matn").shubhalimi is False
    assert bahola(honeypot="", vaqt=vaqt(3), matn="matn").shubhalimi is False


def test_JUDA_tez_forma_kop_ball_oladi():
    tez = bahola(honeypot="", vaqt=vaqt(0), matn="matn")
    sekinroq = bahola(honeypot="", vaqt=vaqt(2), matn="matn")

    assert tez.ball > sekinroq.ball


def test_VAQT_BELGISI_YOQ_bolsa_shubhali():
    """Formani umuman ochmasdan to'g'ridan-to'g'ri POST yuborilgan."""
    assert bahola(honeypot="", vaqt="", matn="matn").shubhalimi is True


def test_VAQT_BELGISI_BUZILGAN_bolsa_shubhali():
    """⚠️ Belgi imzolangan: skript uni o'tmishga surib, "sekin
    to'ldirdim" deb ko'rsata olmaydi."""
    xom = vaqt(60)
    buzuq = xom[:-3] + "xyz"

    assert bahola(honeypot="", vaqt=buzuq, matn="matn").shubhalimi is True


def test_ESKIRGAN_belgi_SHUBHALI_EMAS():
    """⚠️ Oson o'tkazib yuboriladigan holat: qoralamani saqlab qo'yib,
    ertasiga davom ettirgan odam JAZOLANMASLIGI kerak.

    Eskirgan belgi "juda uzoq to'ldirilgan" degani — bot xulqiga
    umuman o'xshamaydi.
    """
    juda_eski = signing.dumps({"t": int(time.time()) - 30 * 24 * 3600})

    baho = bahola(honeypot="", vaqt=juda_eski, matn="matn")

    assert baho.shubhalimi is False, f"sabablar: {baho.sabablar}"


def test_KELAJAKDAGI_vaqt_shubhali():
    kelajak = signing.dumps({"t": int(time.time()) + 3600})

    assert bahola(honeypot="", vaqt=kelajak, matn="matn").shubhalimi is True


@pytest.mark.parametrize(
    ("soni", "kutilgan_ball"),
    [(0, 0), (1, 0), (2, 1), (3, 2), (5, 3)],
)
def test_HAVOLA_soni_ballga_taasir_qiladi(soni, kutilgan_ball):
    matn = "Yordam kerak. " + " ".join(
        f"https://example{i}.com/sahifa" for i in range(soni)
    )

    baho = bahola(honeypot="", vaqt=vaqt(60), matn=matn)

    assert baho.ball == kutilgan_ball


def test_YALANGOCH_domen_havola_deb_SANALMAYDI():
    """⚠️ "fanfics.uz da o'qigandim" — bu havola emas, oddiy jumla.

    Yalang'och domenni sanash oddiy suhbatni spam qilib ko'rsatardi.
    """
    matn = "Menga fanfics.uz va drama.uz saytlari yoqadi, u yerda o'qiganman."

    assert bahola(honeypot="", vaqt=vaqt(60), matn=matn).ball == 0


def test_YANGI_HISOB_yolgiz_ozi_SHUBHALI_EMAS(user_factory):
    """⚠️⚠️ Eng himoyasiz foydalanuvchi ham YANGI hisob bilan keladi.

    Odam dardini yozish uchun ro'yxatdan o'tadi — ro'yxatdan o'tib,
    keyin dard kutib o'tirmaydi. Yangi hisobni o'zi bilan jazolash
    aynan shu odamni jazolardi, shuning uchun ball ATAYLAB kichik.
    """
    yangi = user_factory()

    baho = bahola(honeypot="", vaqt=vaqt(60), matn="matn", foydalanuvchi=yangi)

    assert baho.ball == 1
    assert baho.shubhalimi is False


def test_ESKI_hisob_ball_olmaydi(user_factory):
    eski = user_factory()
    eski.date_joined = timezone.now() - timedelta(days=30)
    eski.save(update_fields=["date_joined"])

    baho = bahola(honeypot="", vaqt=vaqt(60), matn="matn", foydalanuvchi=eski)

    assert baho.ball == 0


def test_signallar_YIGILADI(user_factory):
    matn = " ".join(f"https://example{i}.com" for i in range(3))

    baho = bahola(honeypot="", vaqt=vaqt(2), matn=matn, foydalanuvchi=user_factory())

    # tez to'ldirish (3) + 3 havola (2) + yangi hisob (1)
    assert baho.ball == 6
    assert len(baho.sabablar) == 3


def test_izoh_MODERATORGA_sabablarni_korsatadi():
    """⚠️ "Shubhali" yorlig'i o'zi hech narsa bermaydi: moderator NEGA
    shubhali ekanini bilmasa, qarorni tasodifiy qabul qiladi."""
    baho = bahola(honeypot="", vaqt=vaqt(1), matn="https://a.com https://b.com")

    assert "Avtomatik filtr" in baho.izoh
    assert "soniyada to'ldirilgan" in baho.izoh
    assert "havola" in baho.izoh


# ===========================================================================
# Forma
# ===========================================================================
def test_forma_honeypot_va_vaqt_maydonlarini_QOSHADI():
    form = ComplaintForm()

    assert HONEYPOT_MAYDONI in form.fields
    assert VAQT_MAYDONI in form.fields


def test_honeypot_ODAMDAN_yashiringan():
    """⚠️ Uch qatlam: CSS (ko'z), `tabindex=-1` (klaviatura),
    `aria-hidden` (ekran o'quvchi). Bittasi yetmaydi."""
    render = str(ComplaintForm()[HONEYPOT_MAYDONI])

    assert 'class="honeypot"' in render
    assert 'tabindex="-1"' in render
    assert 'aria-hidden="true"' in render
    assert 'autocomplete="off"' in render


def test_honeypot_nomi_BRAUZER_AUTOFILL_ga_tushmaydi():
    """⚠️⚠️ Eng nozik joy: brauzer va parol menejerlari `website`,
    `email`, `url`, `phone` nomli maydonlarni AVTOMATIK to'ldiradi —
    ko'rinmasa ham. Bunday nom honeypot'ni haqiqiy odamlarni
    ushlaydigan tuzoqqa aylantirardi.
    """
    xavfli = {"website", "url", "email", "phone", "name", "address", "company"}

    assert HONEYPOT_MAYDONI not in xavfli


def test_vaqt_maydoni_IMZOLANGAN():
    belgi = ComplaintForm().fields[VAQT_MAYDONI].initial()

    malumotlar = signing.loads(belgi)
    assert abs(malumotlar["t"] - int(time.time())) < 5


def test_honeypot_toldirilsa_forma_YAROQSIZ():
    kategoriya = CategoryFactory()

    form = ComplaintForm(
        data=malumot(kategoriya, **{HONEYPOT_MAYDONI: "https://spam.example"})
    )

    assert form.is_valid() is False


def test_xato_xabari_honeypotni_FOSH_QILMAYDI():
    """⚠️ "Yashirin maydonni to'ldirdingiz" deb yozish botni yozgan
    odamga aynan nimani chetlab o'tish kerakligini aytib berardi."""
    kategoriya = CategoryFactory()
    form = ComplaintForm(data=malumot(kategoriya, **{HONEYPOT_MAYDONI: "x"}))
    form.is_valid()

    matn = " ".join(form.errors["__all__"]).lower()

    for soz in ("honeypot", "yashirin", "maydon", "bot"):
        assert soz not in matn, f"xato xabari mexanizmni oshkor qilyapti: {matn!r}"


def test_toza_forma_YAROQLI_va_balli_NOL():
    kategoriya = CategoryFactory()

    form = ComplaintForm(data=malumot(kategoriya))

    assert form.is_valid(), form.errors
    assert form.spam_bahosi.ball == 0


# ===========================================================================
# Ko'rinish — MAHSULOT QARORI: shubhali kontent YASHIRILMAYDI
# ===========================================================================
def test_HONEYPOT_bilan_post_YARATILMAYDI(auth_client):
    kategoriya = CategoryFactory()

    auth_client.post(
        YOZISH, malumot(kategoriya, **{HONEYPOT_MAYDONI: "https://spam.example"})
    )

    assert Complaint.objects.count() == 0


def test_SHUBHALI_post_YARATILADI_va_KORINADI(auth_client):
    """⭐⭐ MAHSULOT QARORI (foydalanuvchi tanlagan, 2026-08-29).

    Shubhali post e'lon qilinadi va odamlar uni KO'RADI. Yolg'on
    ijobiy holatning narxi bu yerda spamnikidan yuqori: spam bir necha
    soat ko'rinib tursa — noqulay; og'ir dardini yozgan odamning posti
    jimgina yo'qolsa — u boshqa qaytmaydi.
    """
    kategoriya = CategoryFactory()

    auth_client.post(YOZISH, malumot(kategoriya, otgan=1))

    muammo = Complaint.objects.get()
    assert muammo.is_publicly_visible is True
    assert muammo in list(Complaint.objects.visible())


def test_SHUBHALI_post_NAVBATGA_tushadi(auth_client):
    kategoriya = CategoryFactory()

    auth_client.post(YOZISH, malumot(kategoriya, otgan=1))

    holatlar = navbat()
    assert len(holatlar) == 1
    assert holatlar[0].avtomatikmi is True
    assert "Avtomatik filtr" in holatlar[0].izohlar[0]


def test_TOZA_post_navbatga_TUSHMAYDI(auth_client):
    kategoriya = CategoryFactory()

    auth_client.post(YOZISH, malumot(kategoriya, otgan=60))

    assert Complaint.objects.count() == 1
    assert navbat() == []


def test_tizim_shikoyati_SHIKOYATCHISIZ(auth_client):
    """`reporter=None` — "o'chirilgan hisob" emas, TIZIM."""
    kategoriya = CategoryFactory()

    auth_client.post(YOZISH, malumot(kategoriya, otgan=1))

    hisobot = Report.objects.get()
    assert hisobot.reporter is None
    assert hisobot.complaint == Complaint.objects.get()


def test_TAHRIRLASH_takroriy_shikoyat_YARATMAYDI(auth_client, user):
    """⚠️ Tahrirlash har safar yangi qator yaratsa, navbat bir xil
    holat bilan to'lib ketardi."""
    muammo = ComplaintFactory(author=user)
    yol = reverse("complaint_edit", args=[muammo.slug])
    kirish = malumot(muammo.category, otgan=1)

    auth_client.post(yol, kirish)
    auth_client.post(yol, kirish)

    assert Report.objects.count() == 1


def test_YECHIM_formasi_ham_himoyalangan(auth_client):
    from apps.solutions.forms import SolutionForm
    from apps.solutions.models import Solution

    muammo = ComplaintFactory()
    yol = reverse("solution_create", args=[muammo.slug])

    assert HONEYPOT_MAYDONI in SolutionForm().fields

    auth_client.post(
        yol,
        {
            "content": "Men ham shunday holatda bo'lganman, menga bu yordam berdi.",
            VAQT_MAYDONI: vaqt(1),
            HONEYPOT_MAYDONI: "",
        },
    )

    assert Solution.objects.count() == 1  # yaratildi
    assert navbat()[0].turi == "yechim"  # va navbatda


# ===========================================================================
# Guardlar — himoyani ULASH unutilmasin
# ===========================================================================
def test_barcha_YOZISH_formalarida_himoya_bor():
    """⚠️ Himoyani ulash unutilsa forma ISHLASHDA DAVOM ETADI — faqat
    himoyasiz. Hech narsa xato bermaydi, ya'ni buni faqat maxsus
    qidirgandagina topish mumkin.
    """
    from apps.common.spam import SpamHimoyaliForm
    from apps.solutions.forms import SolutionForm

    for forma in (ComplaintForm, SolutionForm):
        assert issubclass(forma, SpamHimoyaliForm), (
            f"{forma.__name__} `SpamHimoyaliForm` dan meros olmagan — "
            "foydalanuvchi kontenti himoyasiz yoziladi"
        )


def test_himoya_shabloni_HAR_BIR_yozish_formasiga_ULANGAN():
    """Forma sinfida maydon bo'lsa-yu shablon uni chizmasa, brauzerdan
    kelgan POST'da vaqt belgisi bo'lmaydi — ya'ni HAR BIR haqiqiy
    yuborish "shubhali" bo'lib qolardi."""
    shablonlar = Path(settings.BASE_DIR) / "templates"
    forma_naqshi = re.compile(r"<form[^>]*method=[\"']post[\"']", re.IGNORECASE)

    kutilgan = {
        "complaints/create.html": "form",
        "complaints/detail.html": "solution_form",
    }

    for nisbiy in kutilgan:
        matn = (shablonlar / nisbiy).read_text(encoding="utf-8")
        assert forma_naqshi.search(matn), f"{nisbiy}: POST forma topilmadi"
        assert "components/_spam_himoya.html" in matn, (
            f"{nisbiy}: `_spam_himoya.html` include qilinmagan"
        )


def test_chegara_va_ballar_MOS(user_factory):
    """Sozlash paytida buzilib qolmasin: tez to'ldirish YOLG'IZ O'ZI
    chegaraga yetishi, yangi hisob esa YETMASLIGI shart."""
    tez = bahola(honeypot="", vaqt=vaqt(MIN_TOLDIRISH_VAQTI - 1), matn="matn")
    yangi_hisob = bahola(
        honeypot="", vaqt=vaqt(60), matn="matn", foydalanuvchi=user_factory()
    )

    assert tez.ball >= SHUBHA_BALLI, "qabul mezoni buzildi"
    assert yangi_hisob.ball < SHUBHA_BALLI, "yangi hisob yolg'iz o'zi jazolanmasin"


def test_baho_ozgarmas_holatda_boshlanadi():
    """`Baho.sabablar` — `default_factory`, umumiy ro'yxat emas.

    ⚠️ `sabablar: list = []` deb yozilsa BARCHA bahalar bitta ro'yxatni
       bo'lishardi va sabablar so'rovdan so'rovga to'planib ketardi.
    """
    a, b = Baho(), Baho()
    a.qosh(1, "sinov")

    assert b.sabablar == []
    assert b.ball == 0
