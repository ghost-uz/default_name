"""Payme Merchant API — protokol adapteri (D6-T3).

⚠️ `click.py` BILAN BIR XIL QARORDA: Django ko'rinishi va modeli YO'Q.
   Protokol sof funksiya bo'lsa, uni tarmoqsiz va bazasiz sinash
   mumkin. To'lov MANTIQI esa ikkalasi uchun bitta — `services.py`
   (D6-T1 ogohlantirishi: «ikki to'lov yo'li ikki xil qoida bo'yicha
   ishlardi va farqni faqat mijoz sezardi»).

PAYME CLICK'DAN NIMASI BILAN FARQ QILADI

    | | Click | Payme |
    |---|---|---|
    | Shakl | ikkita form-POST | BITTA JSON-RPC 2.0 endpoint |
    | Autentifikatsiya | MD5 imzo | HTTP Basic (`Paycom:<kalit>`) |
    | Summa birligi | so'm | **TIYIN** (1 so'm = 100 tiyin) |
    | Holat | bizda | **Payme bizdan SO'RAYDI** (`CheckTransaction`) |
    | Pul qaytarish | tushunchasi yo'q | `-2` holati (bajarilgandan keyin bekor) |

⚠️⚠️ SUMMA TIYINDA. Bu integratsiyadagi eng oson qilinadigan xato:
   `19000` so'mlik obuna Payme uchun `1900000` tiyin. Chalkashsa
   mijozdan 100 barobar kam (yoki ko'p) pul yechiladi va buni
   TESTDA payqash qiyin — ikkala son ham "to'g'ri ko'rinadi".
   Shuning uchun aylantirish FAQAT shu modulda, chegarada bo'ladi
   va `services.py` tiyin haqida umuman bilmaydi.

⚠️⚠️ HAR SO'ROV TAKRORLANISHI MUMKIN. Payme javobni olmasa aynan
   o'sha `params.id` bilan qayta so'raydi va javob BIR XIL bo'lishi
   shart — shu jumladan `create_time` va `perform_time` ham.
   Shuning uchun bu vaqtlar HISOBLANMAYDI, bazadan O'QILADI.

Hujjat: https://developer.help.paycom.uz/
"""

from __future__ import annotations

import base64
import binascii
import hmac
from datetime import UTC, datetime
from decimal import Decimal

from django.utils import timezone

# ---------------------------------------------------------------------------
# Metodlar
# ---------------------------------------------------------------------------
CHECK_PERFORM = "CheckPerformTransaction"
CREATE = "CreateTransaction"
PERFORM = "PerformTransaction"
CANCEL = "CancelTransaction"
CHECK = "CheckTransaction"
STATEMENT = "GetStatement"


# ---------------------------------------------------------------------------
# Tranzaksiya holatlari — PAYME BELGILAGAN
# ---------------------------------------------------------------------------
# ⚠️ Bu sonlar bizning `TolovHolati` MIZ EMAS. Payme ularni
#    `CheckTransaction` javobida kutadi va o'z holat mashinasiga
#    solishtiradi. Ikkalasini bir tushuncha deb qarash — xato:
#    bizda «bekor» bitta, Payme'da ikkita (to'lovdan OLDIN va KEYIN).
HOLAT_YARATILDI = 1
HOLAT_BAJARILDI = 2
HOLAT_BEKOR = -1
HOLAT_QAYTARILDI = -2  # bajarilgandan KEYIN bekor = pul qaytarildi


# ---------------------------------------------------------------------------
# Xato kodlari — PAYME BELGILAGAN
# ---------------------------------------------------------------------------
# ⚠️ Muvaffaqiyatda `error` maydoni UMUMAN bo'lmaydi (JSON-RPC
#    qoidasi). Bu son faqat JURNALGA yoziladigan "xato bo'lmadi"
#    belgisi — javobga tushmaydi.
MUVAFFAQIYAT_KODI = 0

USUL_POST_EMAS = -32300
JSON_XATO = -32700
SOROV_NOTOGRI = -32600
METOD_TOPILMADI = -32601
HUQUQ_YETARLI_EMAS = -32504
ICHKI_XATO = -32400

SUMMA_XATO = -31001
TRANZAKSIYA_TOPILMADI = -31003
BEKOR_QILIB_BOLMAYDI = -31007
AMAL_BAJARILMAYDI = -31008

# ⚠️ `-31050..-31099` oralig'ini MERCHANT o'zi belgilaydi va ular
#    `account` maydonlariga tegishli. Javobda `data` MAJBURIY — u
#    qaysi maydon xato ekanini aytadi, Payme esa buni foydalanuvchiga
#    ko'rsatadi ("Buyurtma raqami noto'g'ri" degan aniq xabar).
BUYURTMA_TOPILMADI = -31050
# ⚠️ `CheckPerformTransaction` hujjatida FAQAT `-31001` va
#    `-31050..-31099` sanab o'tilgan — `-31008` u yerda YO'Q. Shuning
#    uchun "buyurtma allaqachon yakunlangan" ham merchant oralig'idan
#    olinadi: kod hujjatga mos qoladi va odam aniq xabar ko'radi.
BUYURTMA_YAKUNLANGAN = -31051

# ⚠️ `account` (buyurtma) xatolari ORALIG'I — bu kodlarda javobga `data`
#    (xato maydon nomi) qo'yish MAJBURIY. D6-T4 da shu oraliqdan ikkinchi
#    kod ham webhook javobiga tushdi va bitta kod bilan taqqoslash
#    yetmay qoldi.
ACCOUNT_XATOLARI = range(-31099, -31049)

# ⚠️ Bekor qilish sababi. Payme yuboradi, biz saqlaymiz va
#    `CheckTransaction` da QAYTARAMIZ. `4` — taymaut bo'yicha bekor.
SABAB_TAYMAUT = 4

# ⚠️⚠️ 12 SOAT — Payme qoidasi: shu vaqt ichida bajarilmagan
#    tranzaksiya bekor qilinadi (`state = -1`, `reason = 4`).
#    Millisekundda, chunki Payme'ning butun vaqt hisobi millisekundda.
MUDDAT_MS = 12 * 60 * 60 * 1000

# ⚠️ `account` ichidagi maydon nomi — Payme kabinetida SOZLANADI va
#    bu yerdagi nom bilan AYNAN mos bo'lishi shart. Mos kelmasa
#    hamma so'rov `-31050` bilan qaytadi va sabab hech qayerda
#    ko'rinmaydi (Payme faqat "hisob topilmadi" deydi).
ACCOUNT_MAYDONI = "order_id"


def _xabar(ru: str, uz: str, en: str) -> dict[str, str]:
    """⚠️ `message` — UCH TILDA obyekt, oddiy satr emas.

    Payme uni foydalanuvchiga O'Z ilovasida ko'rsatadi, ya'ni bu
    matnni o'zbek mijozi o'qiydi. Bitta til yuborish uni rus tilida
    ko'rsatilishiga olib kelardi.
    """
    return {"ru": ru, "uz": uz, "en": en}


XABARLAR = {
    USUL_POST_EMAS: _xabar(
        "Требуется метод POST", "POST usuli talab qilinadi", "POST method required"
    ),
    JSON_XATO: _xabar("Ошибка разбора JSON", "JSON o'qib bo'lmadi", "JSON parse error"),
    SOROV_NOTOGRI: _xabar("Неверный запрос", "So'rov noto'g'ri", "Invalid request"),
    METOD_TOPILMADI: _xabar("Метод не найден", "Metod topilmadi", "Method not found"),
    HUQUQ_YETARLI_EMAS: _xabar(
        "Недостаточно привилегий",
        "Huquq yetarli emas",
        "Insufficient privileges",
    ),
    ICHKI_XATO: _xabar("Внутренняя ошибка", "Ichki xato", "Internal error"),
    SUMMA_XATO: _xabar("Неверная сумма", "Summa noto'g'ri", "Invalid amount"),
    TRANZAKSIYA_TOPILMADI: _xabar(
        "Транзакция не найдена", "Tranzaksiya topilmadi", "Transaction not found"
    ),
    BEKOR_QILIB_BOLMAYDI: _xabar(
        "Заказ выполнен, отмена невозможна",
        "Buyurtma bajarilgan, bekor qilib bo'lmaydi",
        "Order completed, cannot cancel",
    ),
    AMAL_BAJARILMAYDI: _xabar(
        "Невозможно выполнить операцию",
        "Amalni bajarib bo'lmaydi",
        "Unable to perform operation",
    ),
    BUYURTMA_TOPILMADI: _xabar(
        "Заказ не найден", "Buyurtma topilmadi", "Order not found"
    ),
    BUYURTMA_YAKUNLANGAN: _xabar(
        "Заказ уже завершён",
        "Buyurtma allaqachon yakunlangan",
        "Order already completed",
    ),
}


class PaymeXatosi(Exception):
    """JSON-RPC xato javobiga aylanadigan istisno.

    ⚠️ `data` FAQAT `account` xatolarida (`-31050..-31099`) majburiy —
       u qaysi maydon xato ekanini aytadi. Boshqa kodlarda uni
       yuborish Payme tomonida hech narsa qilmaydi.
    """

    def __init__(self, kod: int, data: str | None = None) -> None:
        self.kod = kod
        self.data = data
        super().__init__(f"[{kod}]")


# ---------------------------------------------------------------------------
# Autentifikatsiya
# ---------------------------------------------------------------------------
def avtorizatsiya_togrimi(sarlavha: str, *, kalit: str) -> bool:
    """`Authorization: Basic base64("Paycom:<kalit>")`.

    ⚠️⚠️ `hmac.compare_digest` — DOIMIY VAQTDA (Click'dagi bilan bir
       xil sabab: endpoint tashqaridan cheksiz chaqirilishi mumkin,
       ya'ni hujumchida o'rtacha javob vaqtini o'lchash uchun cheksiz
       imkoniyat bor).

    ⚠️ LOGIN ham tekshiriladi. Payme har doim `Paycom` yuboradi;
       uni e'tiborsiz qoldirish "parol to'g'ri bo'lsa login ahamiyatsiz"
       degani bo'lardi va kalit boshqa joyda ham ishlatilsa
       chalkashlik yasardi.

    ⚠️ Kalit BO'SH bo'lsa (sozlanmagan) HAR DOIM `False`. Aks holda
       sozlanmagan server hamma so'rovni qabul qilardi.
    """
    if not kalit:
        return False
    if not sarlavha.startswith("Basic "):
        return False
    try:
        ochilgan = base64.b64decode(sarlavha[6:].strip(), validate=True).decode()
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return False
    return hmac.compare_digest(ochilgan, f"Paycom:{kalit}")


# ---------------------------------------------------------------------------
# Birlik va vaqt aylantirish — CHEGARADA, faqat shu yerda
# ---------------------------------------------------------------------------
def tiyinga(summa: Decimal) -> int:
    """So'm -> tiyin. ⚠️ Yumaloqlash YO'Q: `Decimal` aniq."""
    return int(summa * 100)


def somga(tiyin: int | str) -> Decimal:
    """Tiyin -> so'm.

    ⚠️ `Decimal(tiyin) / 100`, `float` EMAS: `1900000 / 100` float'da
       aniq chiqadi, lekin boshqa summalarda tiyin yo'qolardi va
       taqqoslash jimgina yiqilardi.
    """
    return Decimal(tiyin) / Decimal(100)


def vaqtga_ms(vaqt: datetime | None) -> int:
    """`datetime` -> Unix millisekund. `None` -> `0` (Payme shunday kutadi)."""
    if vaqt is None:
        return 0
    return int(vaqt.timestamp() * 1000)


def ms_dan_vaqtga(ms: int) -> datetime:
    """Unix millisekund -> `datetime`.

    ⚠️ `datetime.UTC`, `django.utils.timezone.utc` EMAS — ikkinchisi
       Django 5.0 da OLIB TASHLANGAN. Eski kod namunalarida hamon
       uchraydi va `AttributeError` bilan yiqiladi.
    """
    return datetime.fromtimestamp(ms / 1000, tz=UTC)


def muddati_otganmi(*, yaratilgan: datetime | None) -> bool:
    """12 soatlik oyna o'tganmi (Payme qoidasi).

    ⚠️ Vaqt BAZADAN olinadi, so'rovdagi `time` dan emas: so'rovdagi
       vaqtni Payme yuboradi va unga tayanish "tashqi ma'lumotga
       ishonib muddatni hisoblash" bo'lardi.
    """
    if yaratilgan is None:
        return False
    otgan = (timezone.now() - yaratilgan).total_seconds() * 1000
    return otgan > MUDDAT_MS


# ---------------------------------------------------------------------------
# JSON-RPC javoblari
# ---------------------------------------------------------------------------
def javob(natija: dict, *, sorov_id) -> dict:
    return {"jsonrpc": "2.0", "id": sorov_id, "result": natija}


def xato_javobi(kod: int, *, sorov_id=None, data: str | None = None) -> dict:
    """⚠️ HTTP holati HAR DOIM 200 — xato TANADA (Click'dagi bilan bir
    xil qoida: 4xx/5xx provayder uchun «javob yo'q» degani).
    """
    xato: dict = {
        "code": kod,
        "message": XABARLAR.get(kod, XABARLAR[ICHKI_XATO]),
    }
    if data is not None:
        xato["data"] = data
    return {"jsonrpc": "2.0", "id": sorov_id, "error": xato}


# ---------------------------------------------------------------------------
# `account` ni o'qish
# ---------------------------------------------------------------------------
def buyurtma_raqami(account) -> int:
    """`account.order_id` -> `Tolov.pk`.

    ⚠️ Xato bo'lsa `-31050` va `data = "order_id"`: Payme buni
       foydalanuvchiga AYNAN shu maydon xato deb ko'rsatadi. `-32600`
       (umumiy "so'rov noto'g'ri") berish odamga "nimadir buzildi"
       degan foydasiz xabarni ko'rsatardi.
    """
    if not isinstance(account, dict):
        raise PaymeXatosi(BUYURTMA_TOPILMADI, data=ACCOUNT_MAYDONI)
    xom = str(account.get(ACCOUNT_MAYDONI, "")).strip()
    if not xom.isdigit():
        raise PaymeXatosi(BUYURTMA_TOPILMADI, data=ACCOUNT_MAYDONI)
    return int(xom)


def bekor_sababi(xom) -> int:
    """Payme yuborgan `reason` ni butun songa aylantiradi.

    ⚠️ Yaroqsiz qiymat XATOGA olib kelmaydi — `0` bo'ladi. Bekor
       qilish sababini o'qib bo'lmagani uchun BEKOR QILISHNI RAD
       ETISH mijozning pulini muzlatib qo'yardi: Payme pulni
       qaytargan, biz esa "sabab tushunarsiz" deb obunani ochiq
       qoldirardik.
    """
    if isinstance(xom, bool) or xom is None:
        return 0
    if isinstance(xom, int):
        return xom
    matn = str(xom).strip()
    if matn.lstrip("-").isdigit():
        return int(matn)
    return 0


def tolov_manzili(
    *,
    asos: str,
    merchant_id: str,
    tolov_id: int,
    summa: Decimal,
    qaytish_manzili: str,
) -> str:
    """Odam yuboriladigan Payme sahifasi.

    ⚠️ Parametrlar `;` bilan ajratilgan SATR bo'lib, keyin base64
       qilinadi — Click'dagi oddiy query-string EMAS. Format
       Payme hujjatidan: `m=<id>;ac.<maydon>=<qiymat>;a=<tiyin>;c=<url>`.
    """
    qismlar = ";".join(
        [
            f"m={merchant_id}",
            f"ac.{ACCOUNT_MAYDONI}={tolov_id}",
            f"a={tiyinga(summa)}",
            f"c={qaytish_manzili}",
        ]
    )
    kodlangan = base64.b64encode(qismlar.encode()).decode()
    return f"{asos.rstrip('/')}/{kodlangan}"
