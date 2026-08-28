"""Telegram Login Widget ma'lumotini TEKSHIRISH (D1-T1).

⚠️ BU MODULDA HECH QANDAY DJANGO KO'RINISHI YO'Q — ataylab.
   Tekshiruv sof funksiya bo'lsa, uni tarmoqsiz, sessiyasiz va
   so'rovsiz sinash mumkin: soxta imzo, eskirgan sana, o'zgartirilgan
   maydon — hammasi oddiy chaqiruv bilan tekshiriladi.

⚠️ PROVAYDERDAN MUSTAQILLIK (ochiq qaror Q3)
   Telegram'ga xos hamma narsa SHU faylda. Kelajakda email yoki boshqa
   kirish usuli qo'shilsa, u o'z moduliga tushadi va `services.py`
   dagi "foydalanuvchini topish/yaratish" qismi o'zgarmaydi.

Telegram nima yuboradi (https://core.telegram.org/widgets/login):

    id          — Telegram foydalanuvchi ID (har doim)
    first_name  — ism (har doim)
    last_name   — familiya (bo'lmasligi mumkin)
    username    — @nom (bo'lmasligi mumkin, O'ZGARISHI mumkin)
    photo_url   — avatar (bo'lmasligi mumkin)
    auth_date   — Unix vaqt (har doim)
    hash        — HMAC-SHA256 imzo (har doim)
"""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass

# ⚠️ 24 soat — D1-T1 qabul mezoni.
#    Nega umuman chegara kerak: imzo MANGU yaroqli bo'lsa, bir marta
#    qo'lga tushgan havola (masalan brauzer tarixi, server jurnali yoki
#    yelka orqali ko'rilgan ekran) istalgan vaqtda qayta yuborilib,
#    hisobga kirish uchun ishlatilardi (replay hujumi).
AUTH_DATE_MUDDATI = 24 * 60 * 60

# Telegram imzolaydigan maydonlar. Boshqasi kelsa ham imzoga kirmaydi.
KUTILGAN_MAYDONLAR = frozenset(
    {"id", "first_name", "last_name", "username", "photo_url", "auth_date"}
)


class TelegramAuthXatosi(Exception):
    """Tekshiruvdan o'tmadi. Xabar FOYDALANUVCHIGA ko'rsatilmaydi.

    ⚠️ Sabab: "imzo noto'g'ri" va "sana eskirgan" ni ajratib ko'rsatish
       hujumchiga qaysi qadamda to'xtaganini aytadi. Foydalanuvchi
       umumiy xabar ko'radi, aniq sabab esa jurnalga tushadi.
    """


@dataclass(frozen=True)
class TelegramMalumoti:
    """Tekshiruvdan O'TGAN ma'lumot.

    Alohida tip: shundan keyingi kod xom `dict` bilan emas, TASDIQLANGAN
    obyekt bilan ishlaydi va "bu ma'lumot tekshirilganmi?" degan savol
    tug'ilmaydi.
    """

    id: int
    first_name: str
    last_name: str
    username: str
    photo_url: str
    auth_date: int


def _malumot_qatori(malumot: dict[str, str]) -> str:
    """Telegram imzolaydigan satrni yig'adi.

    Format qat'iy: `hash` dan tashqari barcha maydonlar
    `kalit=qiymat` ko'rinishida, ALIFBO tartibida, `\\n` bilan birlashadi.

    ⚠️ Faqat KELGAN maydonlar qatnashadi. Bo'lmagan maydonni bo'sh qiymat
       bilan qo'shish imzoni buzadi — Telegram uni umuman yubormaydi.
    """
    juftlar = [
        f"{kalit}={malumot[kalit]}"
        for kalit in sorted(malumot)
        if kalit != "hash" and kalit in KUTILGAN_MAYDONLAR
    ]
    return "\n".join(juftlar)


def tekshirish(
    malumot: dict[str, str],
    *,
    bot_token: str,
    hozir: int | None = None,
    muddat: int = AUTH_DATE_MUDDATI,
) -> TelegramMalumoti:
    """Imzoni va sanani tekshiradi. Xato bo'lsa `TelegramAuthXatosi`.

    ⚠️ IMZO SXEMASI (Telegram hujjatidan)
           secret_key = SHA256(bot_token)          <- oddiy SHA256, HMAC EMAS
           hash       = HMAC_SHA256(data_check_string, secret_key)
       `secret_key` ni HMAC bilan olish (Mini App'dagi sxema) — boshqa
       algoritm va bu yerda ISHLAMAYDI.

    ⚠️ `hmac.compare_digest` — oddiy `==` EMAS.
       Satrlarni `==` bilan solishtirish birinchi farqda to'xtaydi, ya'ni
       taqqoslash VAQTI to'g'ri belgilar soniga bog'liq bo'ladi. Hujumchi
       imzoni bayt-bayt topib olishi mumkin (timing attack).

    ⚠️ TOKEN BO'LMASA — RAD ETAMIZ, o'tkazib yubormaymiz.
       Bo'sh token bilan `secret_key` baribir hisoblanardi va imzoni
       hujumchi ham hisoblay olardi (token sir emas edi). Sozlanmagan
       integratsiya OCHIQ ESHIK bo'lib qolmasin.
    """
    if not bot_token:
        raise TelegramAuthXatosi("TELEGRAM_BOT_TOKEN sozlanmagan")

    kelgan_hash = malumot.get("hash", "")
    if not kelgan_hash:
        raise TelegramAuthXatosi("hash yo'q")

    for majburiy in ("id", "auth_date"):
        if not malumot.get(majburiy):
            raise TelegramAuthXatosi(f"{majburiy} yo'q")

    sirli_kalit = hashlib.sha256(bot_token.encode()).digest()
    kutilgan_hash = hmac.new(
        sirli_kalit, _malumot_qatori(malumot).encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(kutilgan_hash, kelgan_hash):
        raise TelegramAuthXatosi("imzo mos kelmadi")

    try:
        auth_date = int(malumot["auth_date"])
        telegram_id = int(malumot["id"])
    except (TypeError, ValueError) as exc:
        raise TelegramAuthXatosi("id yoki auth_date raqam emas") from exc

    hozir = int(time.time()) if hozir is None else hozir
    yosh = hozir - auth_date
    if yosh > muddat:
        raise TelegramAuthXatosi(f"auth_date eskirgan ({yosh} sekund)")
    # ⚠️ KELAJAKDAGI sana ham rad etiladi. Server soati biroz orqada
    #    bo'lishi mumkin, shuning uchun kichik bag'rikenglik beriladi;
    #    soatlab oldinga ketgan qiymat esa qalbakilashtirish belgisi.
    if yosh < -300:
        raise TelegramAuthXatosi("auth_date kelajakda")

    return TelegramMalumoti(
        id=telegram_id,
        first_name=(malumot.get("first_name") or "")[:150],
        last_name=(malumot.get("last_name") or "")[:150],
        username=(malumot.get("username") or "")[:64],
        photo_url=(malumot.get("photo_url") or "")[:500],
        auth_date=auth_date,
    )


def imzo_yasash(malumot: dict[str, str], *, bot_token: str) -> str:
    """TESTLAR uchun: berilgan ma'lumotga to'g'ri imzo hisoblaydi.

    ⚠️ Ishlab chiqarish kodida CHAQIRILMAYDI. U shu yerda turadi, chunki
       imzo sxemasi bitta joyda bo'lishi kerak: test o'z nusxasini yozsa,
       ikkalasi bir xil xato bilan "kelishib" qolishi mumkin va test
       buzilgan tekshiruvni ham tasdiqlardi.
    """
    sirli_kalit = hashlib.sha256(bot_token.encode()).digest()
    return hmac.new(
        sirli_kalit, _malumot_qatori(malumot).encode(), hashlib.sha256
    ).hexdigest()
