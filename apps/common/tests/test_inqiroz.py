"""Inqirozli kontent siyosati (D2-T6).

⚠️ Bu fayldagi testlarning ko'pi "nima BO'LMASLIGI kerak" ni
   tekshiradi: post o'chirilmasin, yashirilmasin, muallif
   ogohlantirish olmasin. Task tavsifi shuni talab qiladi —
   "jim o'chirish eng yomon variant, u odamni yakkalaydi".
"""

from __future__ import annotations

import pytest
from django.test import override_settings
from django.urls import reverse

from apps.common.inqiroz import (
    KALIT_SOZLAR,
    inqiroz_aniqlandimi,
    normallashtir,
    topilgan_belgilar,
)
from apps.common.models import ModerationStatus
from apps.complaints.factories import CategoryFactory, ComplaintFactory
from apps.complaints.models import Complaint, Generation
from apps.moderation.models import AuditAction, AuditLog, Report, ReportReason
from apps.moderation.selectors import navbat
from apps.moderation.services import inqirozni_belgilash
from apps.solutions.factories import SolutionFactory

pytestmark = pytest.mark.django_db

YOZISH = "/yozish/"
QOLLANMA = reverse("moderatsiya_qollanma")

INQIROZ_MATNI = "Ortiq chidayolmayapman, o'zimni o'ldirmoqchiman."


def malumot(kategoriya, **ozgarish) -> dict:
    """Toza forma ma'lumoti.

    ⚠️ Vaqt belgisi 60 soniya OLDINGI qilib qo'yiladi. `vaqt_belgisi()`
       ni shu yerda chaqirish "0 soniyada to'ldirildi" degani bo'lardi
       va D2-T5 spam evristikasi ishga tushib, har bir postga ortiqcha
       tizim shikoyati yozardi — ya'ni bu fayldagi testlar INQIROZNI
       emas, spamni o'lchab qolardi.
    """
    import time

    from django.core import signing

    from apps.common.spam import HONEYPOT_MAYDONI, VAQT_MAYDONI

    d = {
        "title": "Uzoq vaqtdan beri og'ir holatdaman, nima qilishni bilmayman",
        "description": (
            "Ishdan chiqarishdi, oilada muammo. Kimdan yordam so'rashni "
            "bilmayapman va o'zimni juda yomon his qilyapman."
        ),
        "category": kategoriya.pk,
        "generation_tag": Generation.MILLENNIAL,
        VAQT_MAYDONI: signing.dumps({"t": int(time.time()) - 60}),
        HONEYPOT_MAYDONI: "",
    }
    d.update(ozgarish)
    return d


# ===========================================================================
# Aniqlash — normallashtirish va til qamrovi
# ===========================================================================
@pytest.mark.parametrize(
    "apostrof",
    ["o'zimni o'ldirmoqchiman", "oʻzimni oʻldirmoqchiman", "o‘zimni o‘ldirmoqchiman"],
)
def test_APOSTROF_variantlari_bir_xil_topiladi(apostrof):
    """⚠️⚠️ O'zbek lotin yozuvida apostrof KAMIDA to'rt xil belgi bilan
    yoziladi ('  ʻ  ‘  `). Normallashtirmasak, aniqlash foydalanuvchining
    KLAVIATURASIGA bog'liq bo'lib qolardi — ya'ni ba'zi odamlar uchun
    umuman ishlamasdi."""
    assert inqiroz_aniqlandimi(apostrof) is True


def test_KATTA_HARF_ham_topiladi():
    assert inqiroz_aniqlandimi("O'ZIMNI O'LDIRMOQCHIMAN") is True


@pytest.mark.parametrize(
    "matn",
    [
        "o'zimni o'ldirmoqchiman",  # lotin
        "ўзимни ўлдирмоқчиман",  # kirill
        "не хочу жить больше",  # ruscha
        "покончить с собой",
        "суицид haqida o'ylayapman",
    ],
)
def test_IKKI_TILDA_va_IKKI_ALIFBODA(matn):
    """⚠️ O'zbekistonda odam og'ir paytda o'zbekcha (lotin yoki kirill)
    ham, ruscha ham yozadi — ko'pincha aralash. Faqat lotin o'zbekchani
    qamrash aholining katta qismini o'tkazib yuborardi."""
    assert inqiroz_aniqlandimi(matn) is True


def test_ODDIY_matn_topilmaydi():
    assert (
        inqiroz_aniqlandimi("Ijaraga uy oldim, uy egasi shartnomani buzyapti") is False
    )
    assert inqiroz_aniqlandimi("") is False


def test_bir_nechta_matn_birdan_tekshiriladi():
    """Sarlavha toza, tavsif esa yo'q — ikkalasi ham qaraladi."""
    assert inqiroz_aniqlandimi("Oddiy sarlavha", INQIROZ_MATNI) is True


def test_topilgan_belgilar_MODERATORGA_beriladi():
    """⚠️ "Inqiroz signali" degan yorliq o'zi hech narsa bermaydi:
    moderator NIMA aniqlanganini ko'rmasa, qarorni tasodifiy qabul
    qiladi (D2-T5 dagi `Baho.sabablar` bilan bir xil mantiq)."""
    belgilar = topilgan_belgilar(INQIROZ_MATNI)

    assert belgilar
    assert all(b in KALIT_SOZLAR for b in belgilar)


def test_normallashtirish_boshliqlarni_ham_tekislaydi():
    assert normallashtir("  A\n\tB  ") == "a b"


def test_YOLGON_IJOBIY_qabul_qilingan():
    """⚠️ Bu test XATONI emas, QAROR ni qotiradi.

    "Bu ish meni o'ldirayapti" — keng tarqalgan ibora va u ro'yxatga
    tushishi MUMKIN. Biz buni ataylab qabul qilamiz: yolg'on ijobiy
    moderatorning bir daqiqasini oladi, o'tkazib yuborilgan post esa
    odamni yolg'iz qoldiradi.

    Test ro'yxat kengligini himoya qiladi — kimdir "aniqlikni
    oshiraman" deb signalni torraytirmasin.
    """
    kutilgan = {"o'lgim kel", "o'z joniga qasd", "suitsid", "не хочу жить"}

    assert kutilgan <= set(KALIT_SOZLAR)
    assert len(KALIT_SOZLAR) >= 30, (
        "Ro'yxat qisqartirilgan. Bu modulda yolg'on SALBIY yolg'on "
        "ijobiydan beqiyos qimmat — sabab `inqiroz.py` docstring'ida."
    )


# ===========================================================================
# ⚠️ ENG MUHIMI: kontent O'CHIRILMAYDI va YASHIRILMAYDI
# ===========================================================================
def test_aniqlangan_post_KORINISHDA_QOLADI(auth_client):
    """⭐⭐ Task tavsifi: "jim o'chirish eng yomon variant — u odamni
    yakkalaydi"."""
    kategoriya = CategoryFactory()

    auth_client.post(YOZISH, malumot(kategoriya, description=INQIROZ_MATNI * 2))

    muammo = Complaint.objects.get()
    assert muammo.inqiroz_aniqlandi is True
    assert muammo.moderation_status == ModerationStatus.VISIBLE
    assert muammo.deleted_at is None
    assert muammo in list(Complaint.objects.visible())


def test_muallif_HECH_QANDAY_OGOHLANTIRISH_olmaydi(auth_client):
    """⚠️ Muallifga "postingiz belgilandi" deyish kuzatuv tuyg'usini
    beradi va uyaltiradi — aynan eng himoyasiz paytda."""
    kategoriya = CategoryFactory()

    javob = auth_client.post(
        YOZISH, malumot(kategoriya, description=INQIROZ_MATNI * 2), follow=True
    )
    xabarlar = [str(m) for m in javob.context["messages"]]

    assert xabarlar == ["Dardingiz e'lon qilindi."]
    matn = javob.content.decode()
    for soz in ("belgilandi", "shubhali", "tekshiruvda", "moderator"):
        assert soz not in matn.lower(), f"sahifada «{soz}» so'zi bor"


def test_ODDIY_post_belgilanmaydi(auth_client):
    kategoriya = CategoryFactory()

    auth_client.post(YOZISH, malumot(kategoriya))

    assert Complaint.objects.get().inqiroz_aniqlandi is False
    assert Report.objects.count() == 0


# ===========================================================================
# Navbat — qabul mezoni: "15 daqiqa ichida moderatorga ko'rinadi"
# ===========================================================================
def test_QABUL_MEZONI_aniqlangan_post_navbat_TEPASIDA(auth_client, user_factory):
    """⭐ Qabul mezoni: "aniqlangan post 15 daqiqa ichida moderatorga
    ko'rinadi".

    Amalda DARHOL: aniqlash yozish paytida sinxron ishlaydi va `XAVF`
    sababli tizim shikoyati D2-T2 navbatining eng tepasiga chiqadi.
    """
    from datetime import timedelta

    from django.utils import timezone

    # Navbatda allaqachon eski va ko'p shikoyatli holatlar bor
    eski = ComplaintFactory(title="Uch kun kutgan")
    r = Report.objects.create(
        reporter=user_factory(), complaint=eski, reason=ReportReason.SPAM
    )
    Report.objects.filter(pk=r.pk).update(created_at=timezone.now() - timedelta(days=3))

    kategoriya = CategoryFactory()
    auth_client.post(YOZISH, malumot(kategoriya, description=INQIROZ_MATNI * 2))

    holatlar = navbat()
    assert holatlar[0].target == Complaint.objects.get(inqiroz_aniqlandi=True)
    assert holatlar[0].shoshilinchmi is True


def test_tizim_shikoyati_XAVF_sababi_bilan():
    muammo = ComplaintFactory()

    inqirozni_belgilash(target=muammo, matnlar=[INQIROZ_MATNI])

    hisobot = Report.objects.get()
    assert hisobot.reason == ReportReason.XAVF
    assert hisobot.reporter is None
    assert "Inqiroz belgisi" in hisobot.comment


def test_TAKRORIY_belgilash_ikkinchi_shikoyat_YARATMAYDI():
    muammo = ComplaintFactory()

    inqirozni_belgilash(target=muammo, matnlar=[INQIROZ_MATNI])
    inqirozni_belgilash(target=muammo, matnlar=[INQIROZ_MATNI])

    assert Report.objects.count() == 1


def test_SPAM_va_INQIROZ_shikoyatlari_ARALASHMAYDI():
    """⭐ Ikkalasi ham `reporter=None` bilan yoziladi.

    Sababsiz qidirilsa, spam izohi inqiroz izohining ustiga yozilardi
    va navbatdagi ENG MUHIM signal yo'qolardi.
    """
    from apps.common.spam import bahola
    from apps.moderation.services import avtomatik_belgilash

    muammo = ComplaintFactory()

    inqirozni_belgilash(target=muammo, matnlar=[INQIROZ_MATNI])
    avtomatik_belgilash(target=muammo, baho=bahola(honeypot="", vaqt="", matn="m"))

    sabablar = set(Report.objects.values_list("reason", flat=True))
    assert sabablar == {ReportReason.XAVF, ReportReason.SPAM}
    xavf = Report.objects.get(reason=ReportReason.XAVF)
    assert "Inqiroz belgisi" in xavf.comment


def test_YECHIM_ham_tekshiriladi():
    yechim = SolutionFactory(content=INQIROZ_MATNI)

    inqirozni_belgilash(target=yechim, matnlar=[yechim.content])

    yechim.refresh_from_db()
    assert yechim.inqiroz_aniqlandi is True
    assert navbat()[0].turi == "yechim"


def test_belgilash_AUDIT_jurnaliga_tushadi():
    muammo = ComplaintFactory()

    inqirozni_belgilash(target=muammo, matnlar=[INQIROZ_MATNI])

    yozuv = AuditLog.objects.get(action=AuditAction.INQIROZ_ANIQLANDI)
    assert yozuv.kim == "tizim"
    assert yozuv.malumot["belgilar"]


# ===========================================================================
# Yordam bloki — muallifga ham, o'quvchiga ham
# ===========================================================================
def test_yordam_bloki_OQUVCHIGA_ham_korinadi(anonymous_client):
    """⚠️ Do'stining postini ochgan odamga ham raqam kerak bo'lishi
    mumkin — u yordam so'rashi mumkin bo'lgan yagona odam."""
    muammo = ComplaintFactory(inqiroz_aniqlandi=True)

    matn = anonymous_client.get(muammo.get_absolute_url()).content.decode()

    assert "yolg'iz emassiz" in matn
    assert "103" in matn


def test_yordam_bloki_ODDIY_postda_YOQ(anonymous_client):
    muammo = ComplaintFactory()

    matn = anonymous_client.get(muammo.get_absolute_url()).content.decode()

    assert "data-inqiroz" not in matn


def test_YECHIMDAGI_belgi_ham_blokni_chiqaradi(anonymous_client):
    muammo = ComplaintFactory()
    SolutionFactory(complaint=muammo, inqiroz_aniqlandi=True)

    matn = anonymous_client.get(muammo.get_absolute_url()).content.decode()

    assert "data-inqiroz" in matn


def test_blok_ISHONCH_TELEFONISIZ_ham_ishlaydi(anonymous_client):
    """⚠️ Rasmiy raqam hali tasdiqlanmagan. "Hech narsa yo'q" degan
    holatdan ko'ra 103/112 ancha yaxshi."""
    muammo = ComplaintFactory(inqiroz_aniqlandi=True)

    with override_settings(ISHONCH_TELEFONI=None):
        matn = anonymous_client.get(muammo.get_absolute_url()).content.decode()

    assert "data-inqiroz" in matn
    assert "103" in matn


def test_ISHONCH_TELEFONI_sozlansa_BIRINCHI_chiqadi(anonymous_client):
    muammo = ComplaintFactory(inqiroz_aniqlandi=True)
    liniya = {"nom": "Sinov liniyasi", "raqam": "1146", "vaqt": "24/7"}

    with override_settings(ISHONCH_TELEFONI=liniya):
        matn = anonymous_client.get(muammo.get_absolute_url()).content.decode()

    assert "Sinov liniyasi" in matn
    assert matn.index("1146") < matn.index("Tez tibbiy yordam")


def test_ISHONCH_TELEFONI_sozlamada_BOSH():
    """⚠️⚠️ Task eslatmasi: "noto'g'ri inqiroz raqami raqam yo'qligidan
    XAVFLIROQ".

    Bu test raqam TASDIQLANGUNICHA bo'sh qolishini qotiradi. Rasmiy
    manbadan tasdiqlangan raqam kelganda test yangilanadi — ya'ni
    to'ldirish ONGLI qadam bo'ladi, tasodifiy emas.
    """
    from django.conf import settings

    assert settings.ISHONCH_TELEFONI is None, (
        "Ishonch telefoni to'ldirilgan. Rasmiy manbadan tasdiqlanganini "
        "tekshiring va shu testni yangilang."
    )
    assert settings.SHOSHILINCH_RAQAMLAR, "103/112 hech qachon bo'sh qolmasin"


# ===========================================================================
# Moderator qo'llanmasi (qabul mezoni)
# ===========================================================================
def test_QABUL_MEZONI_qollanma_bor(staff_client):
    matn = staff_client.get(QOLLANMA).content.decode()

    assert "Inqirozli kontent — qo'llanma" in matn
    assert "jim o'chirmang" in matn
    assert "103" in matn


def test_qollanma_ODDIY_foydalanuvchiga_404(auth_client, anonymous_client):
    assert anonymous_client.get(QOLLANMA).status_code == 404
    assert auth_client.get(QOLLANMA).status_code == 404


def test_qollanmaga_NAVBATDAN_havola_bor(staff_client, user_factory):
    """⚠️ Qo'llanma kerak bo'ladigan payt — shoshilinch payt. Uni
    qidirib topish kerak bo'lsa, u ishlatilmaydi."""
    muammo = ComplaintFactory()
    inqirozni_belgilash(target=muammo, matnlar=[INQIROZ_MATNI])

    matn = staff_client.get(reverse("moderatsiya_navbat")).content.decode()

    assert QOLLANMA in matn
