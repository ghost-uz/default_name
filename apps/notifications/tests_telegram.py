"""Telegram orqali bildirishnoma (D5-T2).

⚠️ HECH BIR TEST TARMOQQA CHIQMAYDI — `conftest.py` uni taqiqlaydi va
   bu ataylab: aks holda CI Telegram'ning ishlashiga bog'liq bo'lardi va
   haqiqiy botga test xabari ketishi mumkin edi.
"""

from __future__ import annotations

import json
import urllib.error
from unittest import mock

import pytest

from apps.complaints.factories import ComplaintFactory
from apps.notifications.models import BildirishnomaTuri
from apps.notifications.services import bildirishnoma_yaratish
from apps.notifications.tasks import telegram_yuborish
from apps.notifications.telegram import (
    TelegramBloklandi,
    TelegramVaqtinchalik,
    TelegramXatosi,
    html_qochirish,
    xabar_yuborish,
)

pytestmark = pytest.mark.django_db

# ⚠️ Patch ISHLATILGAN joyda, e'lon qilingan joyda EMAS.
#    `tasks.py` `from .telegram import xabar_yuborish` qiladi, ya'ni nom
#    import paytida `tasks` fazosiga BOG'LANADI. `telegram` modulidagi
#    nomni almashtirish vazifaga UMUMAN ta'sir qilmaydi — mock jimgina
#    chaqirilmay qolardi va test "yuborilmadi" deb yiqilardi.
YUBORISH = "apps.notifications.tasks.xabar_yuborish"


def _javob(tana: dict):
    """`urlopen` uchun soxta kontekst menejeri."""
    soxta = mock.MagicMock()
    soxta.__enter__.return_value.read.return_value = json.dumps(tana).encode()
    return soxta


def _bildirishnoma(user, **kw):
    muammo = ComplaintFactory(title="Ipoteka olish qiyinmi")
    return bildirishnoma_yaratish(
        recipient=user,
        turi=BildirishnomaTuri.YANGI_YECHIM,
        complaint=muammo,
        **kw,
    )


# ===========================================================================
# 1. Mijoz — xato turlarini ajratish
# ===========================================================================
def test_token_YOQ_bolsa_jim_otadi(settings):
    """⚠️ Dev va testda bot sozlanmagan va bu XATO EMAS. Istisno
    tashlash har testni mock qilishga majburlardi."""
    settings.TELEGRAM_BOT_TOKEN = ""

    with mock.patch("urllib.request.urlopen") as urlopen:
        xabar_yuborish(chat_id=1, matn="salom")

    urlopen.assert_not_called()


def test_muvaffaqiyatli_yuborish(settings):
    settings.TELEGRAM_BOT_TOKEN = "sinov-token"

    with mock.patch("urllib.request.urlopen", return_value=_javob({"ok": True})):
        xabar_yuborish(chat_id=42, matn="salom")


@pytest.mark.parametrize(
    "tana",
    [
        {"ok": False, "error_code": 403, "description": "Forbidden"},
        {"ok": False, "error_code": 400, "description": "Bad Request: chat not found"},
        {"ok": False, "error_code": 400, "description": "user is deactivated"},
    ],
)
def test_BLOKLANGAN_holatlar_ajratiladi(settings, tana):
    """⚠️ Bu holatlar DOIMIY — qayta urinish ma'nosiz va zararli."""
    settings.TELEGRAM_BOT_TOKEN = "sinov-token"

    with (
        mock.patch("urllib.request.urlopen", return_value=_javob(tana)),
        pytest.raises(TelegramBloklandi),
    ):
        xabar_yuborish(chat_id=42, matn="salom")


def test_429_da_retry_after_saqlanadi(settings):
    """⚠️ Telegram qancha kutishni O'ZI aytadi — uni hurmat qilmaslik
    keyingi urinishni ham rad ettiradi va cheklovni uzaytiradi."""
    settings.TELEGRAM_BOT_TOKEN = "sinov-token"
    tana = {"ok": False, "error_code": 429, "parameters": {"retry_after": 37}}

    with (
        mock.patch("urllib.request.urlopen", return_value=_javob(tana)),
        pytest.raises(TelegramVaqtinchalik) as xato,
    ):
        xabar_yuborish(chat_id=42, matn="salom")

    assert xato.value.keyin == 37


def test_TARMOQ_xatosi_VAQTINCHALIK(settings):
    settings.TELEGRAM_BOT_TOKEN = "sinov-token"

    with (
        mock.patch("urllib.request.urlopen", side_effect=TimeoutError()),
        pytest.raises(TelegramVaqtinchalik),
    ):
        xabar_yuborish(chat_id=42, matn="salom")


def test_boshqa_xato_UMUMIY(settings):
    settings.TELEGRAM_BOT_TOKEN = "sinov-token"
    tana = {"ok": False, "error_code": 400, "description": "can't parse entities"}

    with (
        mock.patch("urllib.request.urlopen", return_value=_javob(tana)),
        pytest.raises(TelegramXatosi) as xato,
    ):
        xabar_yuborish(chat_id=42, matn="salom")

    assert not isinstance(xato.value, TelegramBloklandi | TelegramVaqtinchalik)


# ===========================================================================
# 2. ⚠️⚠️ Token hech qayerda oshkor bo'lmasin
# ===========================================================================
@pytest.mark.parametrize(
    "yon_tasir",
    [
        TimeoutError(),
        urllib.error.URLError("https://api.telegram.org/botMAXFIY-TOKEN/sendMessage"),
    ],
)
def test_ISTISNODA_token_va_manzil_YOQ(settings, yon_tasir):
    """⚠️⚠️ Telegram API'da token MANZILNING ICHIDA. Uni istisno
    matniga, jurnalga yoki Sentry'ga qo'shish — bot tokenini oshkor
    qilish. `URLError` manzilni O'ZI qo'shishi mumkin, shuning uchun
    faqat tur nomi yoziladi."""
    settings.TELEGRAM_BOT_TOKEN = "MAXFIY-TOKEN"

    with (
        mock.patch("urllib.request.urlopen", side_effect=yon_tasir),
        pytest.raises(TelegramVaqtinchalik) as xato,
    ):
        xabar_yuborish(chat_id=42, matn="salom")

    matn = str(xato.value)
    assert "MAXFIY-TOKEN" not in matn
    assert "api.telegram.org" not in matn


def test_HTTPError_da_ham_token_YOQ(settings):
    settings.TELEGRAM_BOT_TOKEN = "MAXFIY-TOKEN"
    xato_javobi = urllib.error.HTTPError(
        url="https://api.telegram.org/botMAXFIY-TOKEN/sendMessage",
        code=502,
        msg="Bad Gateway",
        hdrs=None,
        fp=None,
    )

    with (
        mock.patch("urllib.request.urlopen", side_effect=xato_javobi),
        pytest.raises(TelegramVaqtinchalik) as xato,
    ):
        xabar_yuborish(chat_id=42, matn="salom")

    assert "MAXFIY-TOKEN" not in str(xato.value)


# ===========================================================================
# 3. HTML qochirish
# ===========================================================================
def test_HTML_qochiriladi():
    """⚠️ Foydalanuvchi matnida `<b>` bo'lsa Telegram xabarni RAD
    ETADI ("can't parse entities") va bildirishnoma yetib bormasdi."""
    assert html_qochirish("<b>&test</b>") == "&lt;b&gt;&amp;test&lt;/b&gt;"


def test_SARLAVHADAGI_teg_xabarni_buzmaydi(user, settings):
    settings.TELEGRAM_BOT_TOKEN = "sinov-token"
    user.telegram_id = 42
    user.save(update_fields=["telegram_id"])
    muammo = ComplaintFactory(title="<script>alert(1)</script> ipoteka")
    b = bildirishnoma_yaratish(
        recipient=user, turi=BildirishnomaTuri.YANGI_YECHIM, complaint=muammo
    )

    with mock.patch(YUBORISH) as yuborish:
        telegram_yuborish(b.pk)

    matn = yuborish.call_args.kwargs["matn"]
    assert "<script>" not in matn
    assert "&lt;script&gt;" in matn


# ===========================================================================
# 4. Vazifa
# ===========================================================================
def test_telegramsiz_hisobga_yuborilmaydi(user):
    """Staff hisoblarida Telegram bo'lmasligi mumkin — ichki markaz
    yetarli (D5-T1)."""
    user.telegram_id = None
    user.save(update_fields=["telegram_id"])
    b = _bildirishnoma(user)

    with mock.patch(YUBORISH) as yuborish:
        assert telegram_yuborish(b.pk) == "telegram yo'q"

    yuborish.assert_not_called()


def test_BLOKLANGAN_foydalanuvchiga_UMUMAN_urinilmaydi(user):
    """⚠️ D5-T2 qabul mezoni: belgilangandan keyin qayta urinilmaydi."""
    user.telegram_id = 42
    user.telegram_bloklandi = True
    user.save(update_fields=["telegram_id", "telegram_bloklandi"])
    b = _bildirishnoma(user)

    with mock.patch(YUBORISH) as yuborish:
        assert telegram_yuborish(b.pk) == "bloklangan"

    yuborish.assert_not_called()


def test_403_da_foydalanuvchi_BELGILANADI(user):
    """⚠️⚠️ D5-T2 qabul mezoni: "403 bo'lsa foydalanuvchi belgilanadi
    va qayta urinilmaydi"."""
    user.telegram_id = 42
    user.save(update_fields=["telegram_id"])
    b = _bildirishnoma(user)

    with mock.patch(YUBORISH, side_effect=TelegramBloklandi("bloklangan")):
        natija = telegram_yuborish(b.pk)

    user.refresh_from_db()
    assert natija == "bloklandi"
    assert user.telegram_bloklandi is True


def test_VAQTINCHALIK_xatoda_QAYTA_URINILADI(user):
    user.telegram_id = 42
    user.save(update_fields=["telegram_id"])
    b = _bildirishnoma(user)

    with (
        mock.patch(YUBORISH, side_effect=TelegramVaqtinchalik("tarmoq", keyin=12)),
        mock.patch.object(
            telegram_yuborish, "retry", side_effect=RuntimeError
        ) as retry,
        pytest.raises(RuntimeError),
    ):
        telegram_yuborish(b.pk)

    assert retry.call_args.kwargs["countdown"] == 12


def test_DOIMIY_xatoda_qayta_urinilmaydi(user):
    user.telegram_id = 42
    user.save(update_fields=["telegram_id"])
    b = _bildirishnoma(user)

    with (
        mock.patch(YUBORISH, side_effect=TelegramXatosi("buzuq HTML")),
        mock.patch.object(telegram_yuborish, "retry") as retry,
    ):
        assert telegram_yuborish(b.pk) == "xato"

    retry.assert_not_called()


def test_YOQ_bildirishnoma_bilan_yiqilmaydi():
    """⚠️ Kontent o'chirilsa bildirishnoma CASCADE ketadi va vazifa
    navbatda qolishi mumkin."""
    assert telegram_yuborish(999999) == "topilmadi"


def test_xabarda_SAYT_havolasi_bor(user, settings):
    settings.SAYT_MANZILI = "https://dard.uz"
    user.telegram_id = 42
    user.save(update_fields=["telegram_id"])
    b = _bildirishnoma(user)

    with mock.patch(YUBORISH) as yuborish:
        telegram_yuborish(b.pk)

    assert yuborish.call_args.kwargs["tugma_manzili"].startswith(
        "https://dard.uz/dard/"
    )


def test_ANONIM_manbada_ism_XABARGA_tushmaydi(user, other_user):
    """⚠️⚠️ Telegram xabari QAYTARIB OLINMAYDI — anonimlik shu yerda
    buzilsa, uni tuzatib bo'lmaydi."""
    from apps.solutions.services import yechim_yozish

    muammo = ComplaintFactory(author=user)
    user.telegram_id = 42
    user.save(update_fields=["telegram_id"])

    yechim_yozish(
        complaint=muammo,
        author=other_user,
        content="Anonim javob matni.",
        is_anonymous=True,
    )
    from apps.notifications.models import Notification

    b = Notification.objects.get(recipient=user)

    with mock.patch(YUBORISH) as yuborish:
        telegram_yuborish(b.pk)

    matn = yuborish.call_args.kwargs["matn"]
    assert other_user.username not in matn
    assert "Kimdir" in matn


# ===========================================================================
# 5. ⚠️ Navbatga qo'yish — `on_commit`
# ===========================================================================
def test_vazifa_COMMITDAN_KEYIN_navbatga_tushadi(
    user, other_user, django_capture_on_commit_callbacks
):
    """⚠️⚠️ Vazifa `transaction.on_commit()` orqali qo'yiladi.

    To'g'ridan-to'g'ri `delay()` qilinsa, worker uni tranzaksiya COMMIT
    bo'lgunicha olishi mumkin va o'shanda bildirishnoma bazada HALI
    YO'Q — vazifa "topilmadi" deb tugardi. Xato TASODIFIY bo'lardi:
    sekin bazada o'tib ketardi, yuk ostida esa qaytalanardi.

    ⚠️ Bu testning O'ZI ham dalil: `pytest.mark.django_db` tranzaksiya
       ichida ishlaydi, ya'ni `on_commit` odatda UMUMAN chaqirilmaydi.
       Uni ko'rish uchun maxsus fixture kerak — demak vazifa haqiqatan
       ham commitga bog'langan.
    """
    muammo = ComplaintFactory(author=user)

    with (
        mock.patch("apps.notifications.tasks.telegram_yuborish.delay") as vazifa,
        django_capture_on_commit_callbacks(execute=True),
    ):
        from apps.solutions.services import yechim_yozish

        yechim_yozish(complaint=muammo, author=other_user, content="Mana yechim matni.")

    vazifa.assert_called_once()


def test_KIRISHDA_blok_bayrogi_tozalanadi(user):
    """⚠️ Telegram blokdan chiqarilganini XABAR QILMAYDI. Login vidjeti
    o'sha botning nomidan ishlaydi — undan o'tgan odamda bot bilan
    aloqa bor (evristika, sabab `accounts/services.py` da)."""
    from apps.accounts.services import telegram_foydalanuvchisini_olish_yoki_yaratish

    user.telegram_id = 777
    user.telegram_bloklandi = True
    user.save(update_fields=["telegram_id", "telegram_bloklandi"])

    topilgan, yangimi = telegram_foydalanuvchisini_olish_yoki_yaratish(
        {"id": "777", "first_name": user.first_name, "last_name": user.last_name}
    )

    assert yangimi is False
    assert topilgan.telegram_bloklandi is False
