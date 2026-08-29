"""Huquqiy sahifalar, rozilik va yosh chegarasi (D2-T10)."""

from __future__ import annotations

import pytest
from django.conf import settings
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.factories import RoziliksizUserFactory
from apps.accounts.services import rozilikni_yozish
from apps.complaints.factories import CategoryFactory

pytestmark = pytest.mark.django_db

ROZILIK = reverse("rozilik")
HUQUQIY_YOLLAR = ("shartlar", "maxfiylik", "qoidalar", "boglanish")


@pytest.fixture
def roziliksiz_client(db):
    """Kirgan, LEKIN rozilik bermagan foydalanuvchi."""
    user = RoziliksizUserFactory()
    c = Client()
    c.force_login(user)
    return c, user


# ===========================================================================
# Huquqiy sahifalar
# ===========================================================================
@pytest.mark.parametrize("nom", HUQUQIY_YOLLAR)
def test_sahifa_KIRMAGANLARGA_ham_ochiq(client, nom):
    """⚠️ Shartlarni o'qish uchun kirish talab qilinmasin: odam nimaga
    rozi bo'layotganini KIRISHDAN OLDIN ko'ra olishi kerak."""
    javob = client.get(reverse(nom))

    assert javob.status_code == 200


@pytest.mark.parametrize("nom", HUQUQIY_YOLLAR)
def test_sahifada_VERSIYA_korsatiladi(client, nom):
    assert settings.HUQUQIY_VERSIYA in client.get(reverse(nom)).content.decode()


@pytest.mark.parametrize("nom", HUQUQIY_YOLLAR)
def test_YURIST_KORMAGANI_ochiq_yozilgan(client, nom):
    """⭐ Qabul mezoni "matnlar yurist tomonidan ko'rilgan" HALI
    BAJARILMAGAN.

    Buni yashirish eng yomon variant bo'lardi: foydalanuvchi matnni
    tekshirilgan deb o'ylardi. Belgi `HUQUQIY_KORILDI` bilan
    boshqariladi — xulosa kelgach bitta joyda o'chiriladi.
    """
    matn = client.get(reverse(nom)).content.decode()

    assert settings.HUQUQIY_KORILDI is False
    assert "yurist tomonidan tekshirilmagan" in matn


@pytest.mark.parametrize("nom", HUQUQIY_YOLLAR)
def test_KORILDI_bolsa_ogohlantirish_YOQOLADI(client, nom):
    with override_settings(HUQUQIY_KORILDI=True):
        matn = client.get(reverse(nom)).content.decode()

    assert "yurist tomonidan tekshirilmagan" not in matn


def test_shartlarda_YOSH_chegarasi_bor(client):
    matn = client.get(reverse("shartlar")).content.decode()

    assert str(settings.YOSH_CHEGARASI) in matn


def test_maxfiylikda_ANONIMLIK_CHEGARASI_ochiq_yozilgan(client):
    """⭐⭐ D2-T2 da qabul qilingan qaror foydalanuvchiga AYTILISHI shart.

    Anonim post moderatorga anonim emas. Buni yozmasak, odam noto'g'ri
    kutish bilan yozadi — va bu ishonchni buzishning eng tez yo'li.
    """
    matn = client.get(reverse("maxfiylik")).content.decode()

    assert "moderatorga anonim emas" in matn.lower()
    assert "haqiqiy muallifni" in matn


def test_maxfiylikda_OCHIRISH_oqibati_yozilgan(client):
    """D2-T8 qarori: kontent qoladi. Odam buni oldindan bilsin."""
    matn = client.get(reverse("maxfiylik")).content.decode()

    assert "Qoladi" in matn
    # ⚠️ Matn SHABLONDA yozilgan (o'zgaruvchi emas) — ekranlanmaydi.
    assert "O'chirilgan foydalanuvchi" in matn


def test_maxfiylikda_AVTOMATIK_tekshiruvlar_yozilgan(client):
    """D2-T5 va D2-T6 — foydalanuvchi ko'rmaydigan mexanizmlar, ya'ni
    ular haqida aytish ayniqsa muhim."""
    matn = client.get(reverse("maxfiylik")).content.decode()

    assert "Spam belgilari" in matn
    assert "Inqiroz belgilari" in matn


def test_boglanishda_INQIROZ_LINIYASI_EMASLIGI_yozilgan(client):
    """⚠️⚠️ Aloqa raqami loyiha egasiniki. Uni inqiroz liniyasi deb
    o'ylagan odam noto'g'ri joyga qo'ng'iroq qilardi."""
    matn = client.get(reverse("boglanish")).content.decode()

    assert "ishonch telefoni emas" in matn
    assert "103" in matn and "112" in matn


def test_boglanishda_TELEGRAM_birinchi_chiqadi(client):
    """⚠️ Ochiq saytdagi raqam skraper botlar tomonidan yig'iladi.
    Telegram sozlangan bo'lsa u birinchi turadi."""
    with override_settings(ALOQA_TELEGRAM="dard_uz_admin"):
        matn = client.get(reverse("boglanish")).content.decode()

    assert "dard_uz_admin" in matn
    assert matn.index("dard_uz_admin") < matn.index("Telefon")


# ===========================================================================
# ⭐ Rozilik — qabul mezoni: "rozilik sanasi saqlanadi"
# ===========================================================================
def test_QABUL_MEZONI_rozilik_SANASI_saqlanadi():
    user = RoziliksizUserFactory()

    rozilikni_yozish(user=user, yosh_tasdiqlandi=True)

    user.refresh_from_db()
    assert user.rozilik_at is not None
    assert user.yosh_tasdigi_at is not None


def test_rozilik_VERSIYASI_ham_saqlanadi():
    """⚠️ Faqat sana yetarli emas: "roziman" degan yozuv qaysi MATNGA
    tegishli ekani ma'lum bo'lmasa, jurnal hech narsa isbotlamaydi."""
    user = RoziliksizUserFactory()

    rozilikni_yozish(user=user, yosh_tasdiqlandi=True)

    user.refresh_from_db()
    assert user.rozilik_versiyasi == settings.HUQUQIY_VERSIYA


def test_ESKI_versiyaga_rozilik_YANGISINI_qoplamaydi(user):
    """⭐ Shartlar o'zgarsa foydalanuvchi qayta o'qib, qayta rozilik
    beradi."""
    assert user.rozilik_bormi is True

    with override_settings(HUQUQIY_VERSIYA="2099-01-01"):
        assert user.rozilik_bormi is False
        assert user.can_write is False


def test_rozilik_bermagan_YOZA_OLMAYDI():
    user = RoziliksizUserFactory()

    assert user.rozilik_bormi is False
    assert user.can_write is False


def test_rozilik_bermagan_OQIY_OLADI(roziliksiz_client):
    """⚠️ O'QISH uchun hech narsa talab qilinmaydi — saytni ko'rish
    rozilik bilan cheklanmasin."""
    c, _ = roziliksiz_client

    assert c.get("/").status_code == 200
    assert c.get(reverse("shartlar")).status_code == 200


def test_rozilik_bermagan_POST_YOZA_OLMAYDI(roziliksiz_client):
    from apps.common.spam import HONEYPOT_MAYDONI, VAQT_MAYDONI, vaqt_belgisi
    from apps.complaints.models import Complaint, Generation

    c, _ = roziliksiz_client
    kategoriya = CategoryFactory()

    javob = c.post(
        "/yozish/",
        {
            "title": "Ipoteka olmoqchiman, lekin bank rad etdi",
            "description": "Ikki bankka murojaat qildim va ikkalasi ham rad etdi. Nima qilay?",
            "category": kategoriya.pk,
            "generation_tag": Generation.MILLENNIAL,
            VAQT_MAYDONI: vaqt_belgisi(),
            HONEYPOT_MAYDONI: "",
        },
    )

    assert javob.status_code == 403
    assert Complaint.objects.count() == 0


# ===========================================================================
# Rozilik sahifasi
# ===========================================================================
def test_rozilik_sahifasi_IKKI_katakcha(roziliksiz_client):
    """⚠️ Yosh tasdig'i va shartlarga rozilik BOSHQA-BOSHQA narsalar."""
    c, _ = roziliksiz_client

    matn = c.get(ROZILIK).content.decode()

    assert 'name="yosh"' in matn
    assert 'name="shartlar"' in matn
    assert str(settings.YOSH_CHEGARASI) in matn


@pytest.mark.parametrize(
    "malumot",
    [{}, {"yosh": "1"}, {"shartlar": "1"}],
)
def test_IKKALA_katakcha_shart(roziliksiz_client, malumot):
    c, user = roziliksiz_client

    javob = c.post(ROZILIK, malumot)

    user.refresh_from_db()
    assert javob.status_code == 200
    assert user.rozilik_bormi is False


def test_rozilikdan_keyin_YOZA_OLADI(roziliksiz_client):
    c, user = roziliksiz_client

    c.post(ROZILIK, {"yosh": "1", "shartlar": "1"})

    user.refresh_from_db()
    assert user.rozilik_bormi is True
    assert user.can_write is True


def test_rozilikdan_keyin_NEXT_ga_qaytariladi(roziliksiz_client):
    """⚠️ Odam kirgandan keyin qayerga ketayotganini yo'qotmasin."""
    c, _ = roziliksiz_client

    javob = c.post(ROZILIK, {"yosh": "1", "shartlar": "1", "next": "/saqlanganlar/"})

    assert javob["Location"] == "/saqlanganlar/"


def test_rozilikda_OCHIQ_YONALTIRISH_YOQ(roziliksiz_client):
    """Begona manzil `next` orqali o'tmasin."""
    c, _ = roziliksiz_client

    javob = c.post(
        ROZILIK, {"yosh": "1", "shartlar": "1", "next": "https://yovuz.example/"}
    )

    assert "yovuz.example" not in javob["Location"]


def test_rozilik_sahifasi_KIRMAGANLARGA_YOPIQ(client):
    assert client.get(ROZILIK).status_code == 302


def test_rozilik_sahifasi_ENG_MUHIMINI_takrorlaydi(roziliksiz_client):
    """⚠️ Odam uzun shartlarni o'qimasligi mumkin — eng muhim ikki
    narsa katakcha yonida turadi."""
    c, _ = roziliksiz_client

    matn = c.get(ROZILIK).content.decode()

    assert "moderatorga anonim emas" in matn
    assert "saytda qoladi" in matn


# ===========================================================================
# Sozlama guardlari
# ===========================================================================
def test_HUQUQIY_VERSIYA_sana_shaklida():
    """⚠️ Versiya SANA: "v2" kabi qiymat qachon o'zgarganini
    bildirmasdi."""
    import re

    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", settings.HUQUQIY_VERSIYA)


def test_YOSH_CHEGARASI_rejadagi_qiymat():
    """Reja auditoriyani 16 yoshdan deb belgilagan."""
    assert settings.YOSH_CHEGARASI == 16


def test_ALOQA_TELEFONI_ISHONCH_TELEFONI_EMAS():
    """⭐⭐ Ikkalasi chalkashmasin.

    Aloqa raqami — loyiha egasining shaxsiy raqami (2026-08-29 da
    tasdiqlangan). Inqirozdagi odamga tayyorgarliksiz odam javob
    berishi xavfli, shuning uchun u inqiroz blokiga TUSHMAYDI.
    """
    assert settings.ISHONCH_TELEFONI is None
    assert settings.ALOQA_TELEFONI


def test_inqiroz_blokida_ALOQA_raqami_YOQ(client):
    from apps.complaints.factories import ComplaintFactory

    muammo = ComplaintFactory(inqiroz_aniqlandi=True)

    matn = client.get(muammo.get_absolute_url()).content.decode()

    raqam = settings.ALOQA_TELEFONI.replace(" ", "")
    assert raqam not in matn.replace(" ", "")


def test_rozilik_sanasi_QAYTA_yozilmaydi_yosh_uchun():
    """Yosh bir marta tasdiqlanadi: keyingi rozilikda u qayta
    yozilmaydi (odam yoshi kichraymaydi)."""
    user = RoziliksizUserFactory()
    rozilikni_yozish(user=user, yosh_tasdiqlandi=True)
    user.refresh_from_db()
    birinchi = user.yosh_tasdigi_at

    user.rozilik_at = timezone.now()
    rozilikni_yozish(user=user, yosh_tasdiqlandi=True)
    user.refresh_from_db()

    assert user.yosh_tasdigi_at == birinchi
