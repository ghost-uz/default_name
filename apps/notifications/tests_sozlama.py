"""Bildirishnoma sozlamalari va jim soatlar (D5-T4)."""

from __future__ import annotations

import re
from datetime import datetime
from unittest import mock

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.complaints.factories import ComplaintFactory
from apps.notifications.models import (
    BildirishnomaSozlamasi,
    BildirishnomaTuri,
    Notification,
)
from apps.notifications.services import bildirishnoma_yaratish
from apps.notifications.sozlama import (
    MUHIM_TURLAR,
    jim_oyna_tugashigacha,
    jim_vaqtmi,
    standart_yoqilganmi,
)
from apps.notifications.tasks import telegram_yuborish

pytestmark = pytest.mark.django_db

YUBORISH = "apps.notifications.tasks.xabar_yuborish"
MANZIL = "/bildirishnomalar/sozlama/"


def _telegramli(user):
    user.telegram_id = 42
    user.save(update_fields=["telegram_id"])
    return user


def _bildirishnoma(user, turi=BildirishnomaTuri.YANGI_YECHIM):
    return bildirishnoma_yaratish(
        recipient=user, turi=turi, complaint=ComplaintFactory()
    )


def _belgilangan(html: str) -> set[str]:
    """Sahifadagi BELGILANGAN katakchalar nomlari.

    ⚠️ `html.count("checked")` bilan sanash ZAIF orakul: u noto'g'ri
       sababdan ham o'tardi (boshqa shablondagi tasodifiy so'z). Bu yerda
       aynan QAYSI katakcha belgilangani tekshiriladi.
    """
    return {
        m.group(1)
        for m in re.finditer(r'<input[^>]*name="([^"]+)"[^>]*\schecked', html)
    }


def _kunduz():
    """Jim oynadan tashqaridagi vaqt (mahalliy 12:00)."""
    return timezone.make_aware(datetime(2026, 9, 6, 12, 0))


def _tun():
    """Jim oyna ichidagi vaqt (mahalliy 23:00)."""
    return timezone.make_aware(datetime(2026, 9, 6, 23, 0))


# ===========================================================================
# 1. ⚠️ Standart holat — qabul mezoni
# ===========================================================================
def test_STANDARTDA_faqat_MUHIM_turlar_yoqiq():
    """⚠️⚠️ D5-T4 qabul mezoni.

    Ro'yxat ATAYLAB yopiq: yangi tur qo'shilganda u standart holatda
    O'CHIQ bo'ladi. Bu ehtiyotkor tomonga xato qiladi — unutib qo'yish
    hech kimni bezovta qilmaydi.
    """
    for turi in BildirishnomaTuri:
        assert standart_yoqilganmi(turi.value) is (turi.value in MUHIM_TURLAR)


def test_NOMALUM_tur_standartda_OCHIQ():
    """Yangi tur qo'shilib, `MUHIM_TURLAR` ga kiritilmasa — o'chiq."""
    assert standart_yoqilganmi("hali_yoq_tur") is False


def test_SOZLAMASIZ_foydalanuvchiga_yuboriladi(user):
    """⚠️ Qator har foydalanuvchi uchun yaratilmaydi — sozlamaga
    tegmagan odamda u umuman yo'q va standart xulq ishlaydi."""
    _telegramli(user)
    b = _bildirishnoma(user)

    with (
        mock.patch(YUBORISH) as yuborish,
        mock.patch("apps.notifications.tasks.jim_vaqtmi", return_value=False),
    ):
        assert telegram_yuborish(b.pk) == "yuborildi"

    yuborish.assert_called_once()


# ===========================================================================
# 2. Turlar bo'yicha yoqish/o'chirish
# ===========================================================================
def test_OCHIRILGAN_tur_YUBORILMAYDI(user):
    _telegramli(user)
    BildirishnomaSozlamasi.objects.create(
        user=user, turlar={BildirishnomaTuri.YANGI_YECHIM.value: False}
    )
    b = _bildirishnoma(user)

    with mock.patch(YUBORISH) as yuborish:
        assert telegram_yuborish(b.pk) == "o'chirilgan"

    yuborish.assert_not_called()


def test_OCHIRILGAN_turda_ham_YOZUV_yaratiladi(user):
    """⚠️⚠️ Sozlama YETKAZISHNI boshqaradi, YOZUVNI emas.

    Ichki markaz — ZAXIRA kanal: "Telegram'da bezovta qilmang" degan
    odam "menga umuman aytmang" demagan. U saytga kirganda nima
    bo'lganini ko'rishi kerak.
    """
    _telegramli(user)
    BildirishnomaSozlamasi.objects.create(
        user=user, turlar={BildirishnomaTuri.YANGI_YECHIM.value: False}
    )

    _bildirishnoma(user)

    assert Notification.objects.filter(recipient=user).count() == 1


def test_BOSHQA_tur_tegilmaydi(user):
    _telegramli(user)
    BildirishnomaSozlamasi.objects.create(
        user=user, turlar={BildirishnomaTuri.YANGI_YECHIM.value: False}
    )
    b = _bildirishnoma(user, turi=BildirishnomaTuri.YECHIM_QABUL)

    with (
        mock.patch(YUBORISH) as yuborish,
        mock.patch("apps.notifications.tasks.jim_vaqtmi", return_value=False),
    ):
        assert telegram_yuborish(b.pk) == "yuborildi"

    yuborish.assert_called_once()


def test_NOMALUM_kalit_XATO_bermaydi(user):
    """⚠️ Tur olib tashlangach eski sozlama yiqilmasligi kerak."""
    sozlama = BildirishnomaSozlamasi(user=user, turlar={"eski_tur": False})

    assert sozlama.yoqilganmi(BildirishnomaTuri.YANGI_YECHIM) is True


# ===========================================================================
# 3. ⚠️ Jim soatlar
# ===========================================================================
def test_jim_oyna_YARIM_TUNDAN_otadi():
    """⚠️ Oyna 22:00 -> 08:00, ya'ni oddiy `boshlanish <= hozir < tugash`
    taqqoslash HAR DOIM `False` berardi."""
    assert jim_vaqtmi(hozir=_tun()) is True
    assert jim_vaqtmi(hozir=_kunduz()) is False


def test_jim_oyna_chegaralari(settings):
    from datetime import time

    settings.JIM_SOATLAR_BOSHI = time(22, 0)
    settings.JIM_SOATLAR_OXIRI = time(8, 0)

    assert jim_vaqtmi(hozir=timezone.make_aware(datetime(2026, 9, 6, 22, 0))) is True
    assert jim_vaqtmi(hozir=timezone.make_aware(datetime(2026, 9, 6, 7, 59))) is True
    assert jim_vaqtmi(hozir=timezone.make_aware(datetime(2026, 9, 6, 8, 0))) is False
    assert jim_vaqtmi(hozir=timezone.make_aware(datetime(2026, 9, 6, 21, 59))) is False


def test_kechikish_ERTALABGACHA():
    """23:00 da -> 08:00 gacha 9 soat."""
    assert jim_oyna_tugashigacha(hozir=_tun()) == 9 * 3600


def test_JIM_SOATDA_xabar_KECHIKTIRILADI(user):
    """⚠️⚠️ Xabar TASHLANMAYDI, kechiktiriladi: foydalanuvchi tunda
    bezovta qilinmaslikni so'radi, xabardan voz kechishni emas."""
    _telegramli(user)
    b = _bildirishnoma(user)

    with (
        mock.patch(YUBORISH) as yuborish,
        mock.patch("apps.notifications.tasks.jim_vaqtmi", return_value=True),
        mock.patch("apps.notifications.tasks.jim_oyna_tugashigacha", return_value=1234),
        mock.patch.object(telegram_yuborish, "apply_async") as qayta,
    ):
        assert telegram_yuborish(b.pk) == "jim soat"

    yuborish.assert_not_called()
    assert qayta.call_args.kwargs["countdown"] == 1234
    assert qayta.call_args.kwargs["args"] == [b.pk]


def test_JIM_SOATLAR_OCHIRILGAN_bolsa_darhol_yuboriladi(user):
    _telegramli(user)
    BildirishnomaSozlamasi.objects.create(user=user, jim_soatlar=False)
    b = _bildirishnoma(user)

    with (
        mock.patch(YUBORISH) as yuborish,
        mock.patch("apps.notifications.tasks.jim_vaqtmi", return_value=True),
    ):
        assert telegram_yuborish(b.pk) == "yuborildi"

    yuborish.assert_called_once()


# ===========================================================================
# 4. Sozlamalar sahifasi
# ===========================================================================
def test_sahifa_KIRISH_talab_qiladi(anonymous_client):
    javob = anonymous_client.get(MANZIL)

    assert javob.status_code == 302
    assert "/kirish/" in javob["Location"]


def test_sahifa_STANDART_holatni_korsatadi(user):
    c = Client()
    c.force_login(user)

    sahifa = c.get(MANZIL).content.decode()

    assert "Muammoingizga yechim yozildi" in sahifa
    assert "Jim soatlar" in sahifa
    assert _belgilangan(sahifa) == {
        f"tur_{turi.value}" for turi in BildirishnomaTuri if turi in MUHIM_TURLAR
    } | {"jim_soatlar"}


def test_saqlash_ISHLAYDI(user):
    c = Client()
    c.force_login(user)

    javob = c.post(
        MANZIL,
        {
            f"tur_{BildirishnomaTuri.YECHIM_QABUL.value}": "on",
            # `yangi_yechim` va `jim_soatlar` berilmadi -> o'chiq
        },
        follow=True,
    )

    assert javob.status_code == 200
    sozlama = BildirishnomaSozlamasi.objects.get(user=user)
    assert sozlama.turlar[BildirishnomaTuri.YANGI_YECHIM.value] is False
    assert sozlama.turlar[BildirishnomaTuri.YECHIM_QABUL.value] is True
    assert sozlama.jim_soatlar is False


def test_saqlangan_holat_QAYTA_korsatiladi(user):
    # ⚠️ FAQAT bitta tur o'chiriladi — qolgan HAMMASI yoqiq qoladi.
    #    Ro'yxatni qo'lda sanab yozish yangi tur qo'shilganda testni
    #    sindirardi (D5-T5 da aynan shunday bo'ldi).
    ochiq = {turi.value: True for turi in BildirishnomaTuri}
    ochiq[BildirishnomaTuri.YANGI_YECHIM.value] = False
    BildirishnomaSozlamasi.objects.create(user=user, turlar=ochiq, jim_soatlar=False)
    c = Client()
    c.force_login(user)

    sahifa = c.get(MANZIL).content.decode()

    assert _belgilangan(sahifa) == {
        f"tur_{turi.value}"
        for turi in BildirishnomaTuri
        if turi != BildirishnomaTuri.YANGI_YECHIM
    }


def test_forma_TURLARDAN_avtomatik_quriladi():
    """⚠️ Yangi tur qo'shilganda forma o'zi kengayadi — uni yangilashni
    unutish mumkin emas."""
    from apps.notifications.forms import SozlamaForm

    form = SozlamaForm()

    assert len(form.tur_maydonlari) == len(BildirishnomaTuri)


def test_katakcha_LOYIHA_sinfini_oladi(user):
    """Loyiha konvensiyasi: `mt-0.5 h-4 w-4` (`rozilik.html` bilan bir xil)."""
    from apps.notifications.forms import KATAKCHA_SINFI

    c = Client()
    c.force_login(user)

    sahifa = c.get(MANZIL).content.decode()

    assert sahifa.count(f'class="{KATAKCHA_SINFI}"') == len(BildirishnomaTuri) + 1


def test_sahifa_NOINDEX(user):
    c = Client()
    c.force_login(user)

    assert 'content="noindex, nofollow"' in c.get(MANZIL).content.decode()


def test_markazdan_havola_bor(user):
    c = Client()
    c.force_login(user)

    sahifa = c.get(reverse("bildirishnomalar")).content.decode()

    assert reverse("bildirishnoma_sozlamalari") in sahifa
