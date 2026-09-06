"""Telegram Bot API — xabar yuborish (D5-T2).

⚠️ NEGA YANGI PAKET QO'SHILMADI
   Loyiha qoidasi: "buni stdlib yoki Django bilan qilib bo'ladimi?".
   Bu yerda javob HA — bitta `POST` va bitta JSON javob. `requests`
   qulayroq, lekin u yerda hech qanday murakkab holat yo'q: sessiya
   ham, oqim (streaming) ham, autentifikatsiya sxemasi ham kerak emas.

⚠️ BU MODULDA DJANGO MODELI YO'Q — ataylab (`accounts/telegram.py` bilan
   bir xil qaror). Mijoz sof funksiya bo'lsa, uni bazasiz va so'rovsiz
   sinash mumkin: soxta javob berib, har bir xato yo'lini tekshirish
   oddiy chaqiruvga aylanadi.

⚠️⚠️ TOKEN MANZILNING ICHIDA
   Telegram API'da token URL'ning bir qismi:
   `https://api.telegram.org/bot<TOKEN>/sendMessage`.

   Ya'ni manzilni istisno matniga, jurnalga yoki Sentry'ga qo'shish —
   BOT TOKENINI OSHKOR QILISH. Bu modulda hech bir istisno manzilni
   o'z ichiga OLMAYDI va buni test qo'riqlaydi.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from django.conf import settings

log = logging.getLogger(__name__)

API_ILDIZI = "https://api.telegram.org"

# Telegram xato kodlari (https://core.telegram.org/bots/api).
BLOKLANGAN_TAVSIFLAR = (
    "bot was blocked by the user",
    "user is deactivated",
    "chat not found",
    "bot can't initiate conversation",
)


class TelegramXatosi(Exception):
    """Umumiy xato. ⚠️ Matnda MANZIL bo'lmasligi shart (token!)."""


class TelegramBloklandi(TelegramXatosi):
    """Foydalanuvchi botni bloklagan yoki chat mavjud emas.

    ⚠️ BU DOIMIY XATO — qayta urinish MA'NOSIZ va zararli: navbat
       bitta foydalanuvchi uchun cheksiz aylanardi. D5-T2 qabul
       mezoni aynan shuni talab qiladi.
    """


class TelegramVaqtinchalik(TelegramXatosi):
    """Tarmoq, 5xx yoki 429 — qayta urinish MA'NOLI."""

    def __init__(self, xabar: str, *, keyin: int | None = None) -> None:
        super().__init__(xabar)
        # 429 javobida Telegram `parameters.retry_after` beradi (sekund).
        self.keyin = keyin


def html_qochirish(matn: str) -> str:
    """Telegram `parse_mode=HTML` uchun eng kichik qochirish.

    ⚠️ Telegram HTML rejimida FAQAT bir nechta teg ruxsat etilgan, lekin
       `<`, `>` va `&` baribir maxsus. Foydalanuvchi matnida `<b>` bo'lsa
       Telegram xabarni RAD ETADI ("can't parse entities") va
       bildirishnoma umuman yetib bormasdi.
    """
    return (matn or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _javobni_tekshirish(tana: dict) -> None:
    """Telegram javobini xato turlariga ajratadi."""
    if tana.get("ok"):
        return

    tavsif = str(tana.get("description", "")).lower()
    kod = tana.get("error_code")

    if kod == 403 or any(belgi in tavsif for belgi in BLOKLANGAN_TAVSIFLAR):
        raise TelegramBloklandi(tavsif or "bloklangan")

    if kod == 429:
        keyin = (tana.get("parameters") or {}).get("retry_after")
        raise TelegramVaqtinchalik("tezlik chegarasi", keyin=keyin)

    # ⚠️ 400 — odatda BIZNING xatomiz (noto'g'ri chat_id, buzuq HTML).
    #    Qayta urinish uni tuzatmaydi, shuning uchun doimiy deb
    #    hisoblanadi va jurnalga tushadi.
    raise TelegramXatosi(f"telegram xatosi: {kod} {tavsif}")


def xabar_yuborish(*, chat_id: int, matn: str, tugma_manzili: str = "") -> None:
    """Telegram'ga xabar yuboradi.

    ⚠️ FAQAT SINXRON CHAQIRUV — uni ko'rinishdan TO'G'RIDAN-TO'G'RI
       chaqirmang. Tarmoq so'rovi so'rov-javob siklini Telegram
       serverining javob tezligiga bog'lab qo'yardi (D5-T2 qabul
       mezoni: "yuborish sinxron EMAS"). Chaqiruvchi — Celery vazifasi
       (`apps/notifications/tasks.py`).

    ⚠️ Token bo'sh bo'lsa JIM o'tib ketadi: dev va test muhitida bot
       sozlanmagan va bu XATO EMAS. Istisno tashlash har testni
       mock qilishga majburlardi.
    """
    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        log.debug("telegram: token yo'q, xabar yuborilmadi")
        return

    yuk: dict[str, object] = {
        "chat_id": chat_id,
        "text": matn,
        "parse_mode": "HTML",
        # ⚠️ Havola oldi ko'rinishi O'CHIRILGAN: u xabarni ikki barobar
        #    uzaytiradi va lentada bildirishnoma emas, reklama bo'lib
        #    ko'rinadi.
        "disable_web_page_preview": True,
    }
    if tugma_manzili:
        yuk["reply_markup"] = {
            "inline_keyboard": [[{"text": "Ochish", "url": tugma_manzili}]]
        }

    sorov = urllib.request.Request(  # noqa: S310 — manzil qotirilgan (API_ILDIZI)
        f"{API_ILDIZI}/bot{token}/sendMessage",
        data=json.dumps(yuk).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(  # noqa: S310 — yuqoridagi izohga qarang
            sorov, timeout=settings.TELEGRAM_TIMEOUT
        ) as javob:
            tana = json.loads(javob.read().decode())
    except urllib.error.HTTPError as xato:
        # ⚠️ Telegram xato holatlarida ham JSON tana qaytaradi — undagi
        #    `description` bizga xato TURINI aytadi. Uni o'qimasdan
        #    "HTTP 403" deb qo'yish bloklanganni vaqtinchalik xatodan
        #    ajratib bo'lmaydigan qilardi.
        try:
            tana = json.loads(xato.read().decode())
        except (ValueError, OSError):
            # ⚠️ MANZIL QO'SHILMAYDI — u tokenni o'z ichiga oladi.
            raise TelegramVaqtinchalik(f"HTTP {xato.code}") from None
        _javobni_tekshirish(tana)
        return
    except (urllib.error.URLError, TimeoutError, OSError) as xato:
        # ⚠️ `xato` ning o'zi manzilni o'z ichiga olishi MUMKIN
        #    (`URLError` ba'zan uni qo'shadi) — shuning uchun faqat
        #    tur nomi yoziladi.
        raise TelegramVaqtinchalik(f"tarmoq: {type(xato).__name__}") from None

    _javobni_tekshirish(tana)
