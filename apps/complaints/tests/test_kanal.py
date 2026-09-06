"""Telegram kanaliga avto-post (D5-T3)."""

from __future__ import annotations

from datetime import timedelta
from unittest import mock

import pytest
from django.utils import timezone

from apps.common.models import ModerationStatus
from apps.complaints.factories import CategoryFactory, ComplaintFactory
from apps.complaints.kanal import nomzodlar, post_matni
from apps.complaints.models import Complaint
from apps.complaints.tasks import kanalga_post
from apps.notifications.telegram import TelegramXatosi

pytestmark = pytest.mark.django_db

# ⚠️ Patch ISHLATILGAN joyda: `tasks.kanalga_post` funksiya ichida import
#    qiladi, ya'ni nom chaqiruv paytida `telegram` modulidan olinadi.
YUBORISH = "apps.notifications.telegram.xabar_yuborish"


@pytest.fixture(autouse=True)
def _kanal_sozlangan(settings):
    settings.TELEGRAM_CHANNEL_ID = "@sinov_kanal"
    settings.SAYT_MANZILI = "https://dard.uz"


def qaynoq(**kw) -> Complaint:
    """Kanalga tushishi kutiladigan post."""
    kw.setdefault("hot_score", 100.0)
    return ComplaintFactory(**kw)


# ===========================================================================
# 1. ⚠️⚠️ Anonimlik — kanal posti QAYTARIB OLINMAYDI
# ===========================================================================
def test_kanal_postida_MUALLIF_UMUMAN_YOQ(user):
    """⚠️⚠️ Kanalda muallif KO'RSATILMAYDI — na anonimda, na OCHIQDA.

    Kanal posti savolni ko'rsatadi, odamni emas. Yuz minglab odamga
    bir zumda ko'ringan xabarni qaytarib bo'lmaydi: Telegram'da
    o'chirilgan xabar ham allaqachon o'qilgan bo'ladi.
    """
    muammo = qaynoq(author=user, title="Ipoteka olish qiyinmi")

    matn = post_matni(muammo)

    assert user.username not in matn
    assert user.display_name not in matn


def test_ANONIM_postda_ham_muallif_YOQ(user):
    muammo = qaynoq(author=user, is_anonymous=True, title="Anonim savol")

    matn = post_matni(muammo)

    assert user.username not in matn


def test_yuborilgan_xabarda_ham_muallif_YOQ(user):
    """Uchidan-uchiga: vazifa haqiqatan yuborgan matnda ham yo'q."""
    qaynoq(author=user, title="Ipoteka olish qiyinmi")

    with mock.patch(YUBORISH) as yuborish:
        kanalga_post()

    assert user.username not in yuborish.call_args.kwargs["matn"]


# ===========================================================================
# 2. ⚠️ Takror chiqmaslik (qabul mezoni)
# ===========================================================================
def test_BITTA_POST_IKKI_MARTA_chiqmaydi():
    """⚠️⚠️ D5-T3 qabul mezoni.

    `hot_score` har 10 daqiqada qayta hisoblanadi va bitta post kunlar
    davomida eng tepada qolishi mumkin — belgisiz u kanalga HAR KUNI
    qayta chiqardi.
    """
    qaynoq(title="Ipoteka olish qiyinmi")

    with mock.patch(YUBORISH) as yuborish:
        kanalga_post()
        birinchi = yuborish.call_count
        kanalga_post()

    assert birinchi == 1
    assert yuborish.call_count == 1, "post ikkinchi marta chiqdi"


def test_yuborilgandan_keyin_BELGILANADI():
    muammo = qaynoq()

    with mock.patch(YUBORISH):
        kanalga_post()

    muammo.refresh_from_db()
    assert muammo.kanalga_yuborilgan_at is not None


def test_HAR_POST_ALOHIDA_belgilanadi():
    """⚠️⚠️ Hammasi yuborilgandan KEYIN belgilash xavfli: vazifa
    o'rtasida uzilsa (worker o'ldi, Telegram tushdi), yuborilganlar
    belgilanmagan qolardi va keyingi ishga tushishda QAYTA chiqardi."""
    for i in range(3):
        qaynoq(title=f"Post {i}", hot_score=100.0 - i)

    # Ikkinchi yuborishda uziladi.
    with mock.patch(YUBORISH, side_effect=[None, TelegramXatosi("tushdi")]):
        kanalga_post()

    belgilangan = Complaint.objects.exclude(kanalga_yuborilgan_at=None).count()
    assert belgilangan == 1, "uzilishdan oldingi post belgilanmagan"


def test_YUBORISH_YIQILSA_belgilanmaydi():
    """⚠️ Belgi yuborishdan KEYIN qo'yiladi: teskarisida post "chiqqan"
    deb qolib, hech qachon chiqmasdi. Ikki xatodan kamroq zararlisi —
    takror emas, o'tkazib yuborish."""
    muammo = qaynoq()

    with mock.patch(YUBORISH, side_effect=TelegramXatosi("tushdi")):
        kanalga_post()

    muammo.refresh_from_db()
    assert muammo.kanalga_yuborilgan_at is None


# ===========================================================================
# 3. Kim chiqadi, kim chiqmaydi
# ===========================================================================
def test_YASHIRILGAN_post_kanalga_chiqmaydi():
    qaynoq(title="Yashirin", moderation_status=ModerationStatus.HIDDEN)

    assert list(nomzodlar()) == []


def test_TEKSHIRUVDAGI_post_ham_chiqmaydi():
    qaynoq(title="Navbatda", moderation_status=ModerationStatus.PENDING)

    assert list(nomzodlar()) == []


def test_INQIROZ_belgisi_bor_post_KANALGA_CHIQMAYDI():
    """⚠️⚠️ D2-T6 siyosati: aniqlangan post o'chirilmaydi va
    yashirilmaydi — u saytda odatdagidek turadi.

    Lekin uni MINGLAB odamga O'ZIMIZ tarqatish butunlay boshqa narsa:
    bu odamning eng og'ir daqiqasini ommaviy tomoshaga aylantirardi.

    Farq nozik va muhim: biz kontentni CHEKLAMAYMIZ, lekin uni
    KUCHAYTIRMAYMIZ ham.
    """
    muammo = qaynoq(title="Og'ir holat")
    Complaint.objects.filter(pk=muammo.pk).update(inqiroz_aniqlandi=True)

    assert list(nomzodlar()) == []


def test_ESKI_post_chiqmaydi(settings):
    """⚠️ `hot_score` eski postda ham yuqori bo'lishi mumkin, kanal esa
    "bugun nima bo'lyapti" degan lenta."""
    eski = qaynoq(title="Eski post")
    Complaint.objects.filter(pk=eski.pk).update(
        created_at=timezone.now() - timedelta(days=settings.KANAL_OYNA_KUNLARI + 1)
    )

    assert list(nomzodlar()) == []


def test_ochirilgan_post_chiqmaydi():
    muammo = qaynoq()
    muammo.delete()

    assert list(nomzodlar()) == []


# ===========================================================================
# 4. Tartib va chegara
# ===========================================================================
def test_ENG_QAYNOQLARI_birinchi():
    past = qaynoq(title="Past", hot_score=1.0)
    baland = qaynoq(title="Baland", hot_score=999.0)

    assert [m.pk for m in nomzodlar()][:2] == [baland.pk, past.pk]


def test_KUNLIK_soni_chegaralangan(settings):
    settings.KANAL_KUNLIK_SONI = 2
    for i in range(5):
        qaynoq(title=f"Post {i}")

    with mock.patch(YUBORISH) as yuborish:
        kanalga_post()

    assert yuborish.call_count == 2


def test_KANAL_sozlanmagan_bolsa_hech_narsa_qilmaydi(settings):
    settings.TELEGRAM_CHANNEL_ID = ""
    qaynoq()

    with mock.patch(YUBORISH) as yuborish:
        assert kanalga_post() == "kanal sozlanmagan"

    yuborish.assert_not_called()


# ===========================================================================
# 5. Post matni
# ===========================================================================
def test_matnda_sarlavha_va_kategoriya():
    kat = CategoryFactory(name="Uy-joy", slug="uy-joy")
    muammo = qaynoq(title="Ipoteka olish qiyinmi", category=kat)

    matn = post_matni(muammo)

    assert "Ipoteka olish qiyinmi" in matn
    assert "#Uy-joy" in matn


def test_UZUN_tavsif_qisqartiriladi(settings):
    settings.KANAL_PARCHA_UZUNLIGI = 50
    muammo = qaynoq(description="a" * 500)

    matn = post_matni(muammo)

    assert "…" in matn
    assert len(matn) < 300


def test_HTML_qochiriladi():
    """⚠️ Telegram buzuq HTML'da xabarni RAD ETADI — post umuman
    chiqmasdi."""
    muammo = qaynoq(title="<script>alert(1)</script>")

    matn = post_matni(muammo)

    assert "<script>" not in matn
    assert "&lt;script&gt;" in matn


def test_xabarda_sayt_HAVOLASI_bor():
    muammo = qaynoq()

    with mock.patch(YUBORISH) as yuborish:
        kanalga_post()

    manzil = yuborish.call_args.kwargs["tugma_manzili"]
    assert manzil == f"https://dard.uz{muammo.get_absolute_url()}"
