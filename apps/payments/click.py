"""Click Merchant API — protokol adapteri (D6-T2).

⚠️ BU MODULDA HECH QANDAY DJANGO KO'RINISHI VA MODELI YO'Q — ataylab
   (`apps/accounts/telegram.py` bilan bir xil qaror). Protokol sof
   funksiyalar bo'lsa, uni tarmoqsiz, bazasiz va so'rovsiz sinash
   mumkin: soxta imzo, noto'g'ri summa, tanish bo'lmagan amal —
   hammasi oddiy chaqiruv bilan tekshiriladi.

   D6-T3 (Payme) shu yerga EMAS, `payme.py` ga tushadi va `services.py`
   dagi to'lov mantiqi ikkalasi uchun bir xil qoladi.

CLICK QANDAY ISHLAYDI (SHOP-API, ikki bosqichli)

    1. Biz `Tolov` qatorini yaratamiz va odamni Click sahifasiga
       yuboramiz: `transaction_param` = bizning `Tolov.pk`.
    2. Click **Prepare** (`action=0`) chaqiradi: "shunday buyurtma
       bormi, summa to'g'rimi?". Biz `merchant_prepare_id` qaytaramiz.
    3. Odam kartani tasdiqlaydi.
    4. Click **Complete** (`action=1`) chaqiradi: "pul yechildi".
       Shundan keyingina xizmat beriladi.

    Ikkala chaqiruv ham TAKRORLANISHI mumkin (Click javobni olmasa
    qayta uriniladi) — idempotentlik `services.py` da.

⚠️⚠️ IMZO XOM SATRLAR USTIDAN HISOBLANADI, QAYTA FORMATLASH YO'Q.
   Click `amount` ni `"10000.00"` shaklida yuboradi. Uni `Decimal` ga
   aylantirib, keyin `str()` bilan qaytarish `"10000"` berishi mumkin
   va MD5 BUTUNLAY boshqa chiqadi — imzo esa "noto'g'ri" deb rad
   etiladi. Xato faqat kasr qismi nol bo'lganda chiqadi, ya'ni
   testda emas, PRODDA ko'rinadi.

   Shuning uchun: imzo uchun `request.POST` dagi SATRLAR, taqqoslash
   uchun esa `Decimal` — ikki xil maqsad, ikki xil shakl.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

# ---------------------------------------------------------------------------
# Amallar
# ---------------------------------------------------------------------------
AMAL_PREPARE = 0
AMAL_COMPLETE = 1


# ---------------------------------------------------------------------------
# Xato kodlari — CLICK BELGILAGAN, o'zimiznikini o'ylab topib bo'lmaydi
# ---------------------------------------------------------------------------
# ⚠️ Bu sonlar Click hujjatidan. Ular javobning `error` maydoniga
#    tushadi va Click ularga QARAB ish ko'radi: masalan `-4` ni ko'rib
#    tranzaksiyani muvaffaqiyatli deb yopadi, boshqa manfiy kodda esa
#    pulni qaytaradi. Ya'ni "yaqinroq" kodni tanlash — pul harakati.
MUVAFFAQIYAT = 0
IMZO_XATO = -1
SUMMA_XATO = -2
AMAL_TOPILMADI = -3
ALLAQACHON_TOLANGAN = -4
BUYURTMA_TOPILMADI = -5
TRANZAKSIYA_TOPILMADI = -6
YANGILASH_XATOSI = -7
SOROV_XATOSI = -8
BEKOR_QILINGAN = -9

IZOHLAR = {
    MUVAFFAQIYAT: "Success",
    IMZO_XATO: "SIGN CHECK FAILED!",
    SUMMA_XATO: "Incorrect parameter amount",
    AMAL_TOPILMADI: "Action not found",
    ALLAQACHON_TOLANGAN: "Already paid",
    BUYURTMA_TOPILMADI: "User does not exist",
    TRANZAKSIYA_TOPILMADI: "Transaction does not exist",
    YANGILASH_XATOSI: "Failed to update user",
    SOROV_XATOSI: "Error in request from click",
    BEKOR_QILINGAN: "Transaction cancelled",
}

# ⚠️ Imzoga kiradigan maydonlar — TARTIB MUHIM va u Click hujjatidan.
#    `merchant_prepare_id` faqat Complete'da bor: Prepare paytida u
#    hali mavjud emas (aynan Prepare uni yaratadi).
IMZO_MAYDONLARI = {
    AMAL_PREPARE: (
        "click_trans_id",
        "service_id",
        "<maxfiy_kalit>",
        "merchant_trans_id",
        "amount",
        "action",
        "sign_time",
    ),
    AMAL_COMPLETE: (
        "click_trans_id",
        "service_id",
        "<maxfiy_kalit>",
        "merchant_trans_id",
        "merchant_prepare_id",
        "amount",
        "action",
        "sign_time",
    ),
}

# ⚠️ `sign_string` JURNALGA TUSHMAYDI. Ro'yxat bu yerda emas,
#    `services.MAXFIY_MAYDONLAR` da: jurnal provayderdan mustaqil va
#    Payme (D6-T3) o'z maxfiy maydonini o'sha ro'yxatga qo'shadi.
#    Sabab o'sha yerda batafsil yozilgan.


class ClickXatosi(Exception):
    """So'rov protokolga mos emas. `kod` javobda qaytariladi.

    ⚠️ Xabar FOYDALANUVCHIGA ko'rsatilmaydi — u Click serveriga va
       jurnalga ketadi. Odam Click sahifasida o'z xatosini ko'radi.
    """

    def __init__(self, kod: int, izoh: str = "") -> None:
        self.kod = kod
        self.izoh = izoh or IZOHLAR.get(kod, "Error")
        super().__init__(f"[{kod}] {self.izoh}")


@dataclass(frozen=True)
class ClickSorovi:
    """Tekshiruvdan O'TGAN so'rov.

    Alohida tip: shundan keyingi kod xom `dict` bilan emas,
    TASDIQLANGAN obyekt bilan ishlaydi va "bu imzo tekshirilganmi?"
    degan savol tug'ilmaydi (`TelegramMalumoti` bilan bir xil qaror).
    """

    click_trans_id: str
    service_id: str
    click_paydoc_id: str
    merchant_trans_id: str
    merchant_prepare_id: str
    amount: Decimal
    action: int
    error: int
    error_note: str
    sign_time: str

    @property
    def tolov_id(self) -> int:
        """`merchant_trans_id` — bizning `Tolov.pk`."""
        return int(self.merchant_trans_id)


def imzo_qatori(post, *, amal: int, maxfiy_kalit: str) -> str:
    """Imzolanadigan satr: maydonlar KETMA-KET, ajratgichsiz.

    ⚠️ Ajratgich YO'Q — Click shunday belgilagan. Bu nazariy jihatdan
       chegara noaniqligini beradi (`"1" + "23"` va `"12" + "3"` bir xil
       satr), lekin protokolni biz tanlamaymiz. Amaliy xavf past:
       maydonlarning ma'nolari va uzunliklari qat'iy.
    """
    qismlar = []
    for nom in IMZO_MAYDONLARI[amal]:
        qismlar.append(maxfiy_kalit if nom == "<maxfiy_kalit>" else post.get(nom, ""))
    return "".join(qismlar)


def imzo_hisoblash(post, *, amal: int, maxfiy_kalit: str) -> str:
    """MD5 — Click protokoli TALAB QILADI.

    ⚠️ MD5 buzilgan hash va uni yangi kodda ishlatish odatda xato.
       Bu yerda tanlov bizda emas: Click imzoni shu algoritm bilan
       hisoblaydi va boshqasini qabul qilmaydi. Zaiflik ta'siri
       cheklangan — imzo AUTENTIFIKATSIYA vositasi, hujjat imzosi emas,
       va har so'rovda `sign_time` bilan birga keladi.
    """
    qator = imzo_qatori(post, amal=amal, maxfiy_kalit=maxfiy_kalit)
    return hashlib.md5(qator.encode()).hexdigest()  # noqa: S324


def imzoni_tekshirish(post, *, amal: int, maxfiy_kalit: str) -> bool:
    """⚠️ `hmac.compare_digest` — DOIMIY VAQTDA taqqoslash.

    Oddiy `==` birinchi farqda to'xtaydi va javob vaqti imzoning necha
    belgisi to'g'ri kelganini oshkor qiladi. Tarmoq shovqini bu
    farqni ko'mib yuboradi degan taxminga tayanish kerak emas: to'lov
    endpoint'i tashqaridan CHEKSIZ chaqirilishi mumkin, ya'ni
    hujumchida o'rtachani aniqlash uchun cheksiz o'lchov bor.
    """
    kutilgan = imzo_hisoblash(post, amal=amal, maxfiy_kalit=maxfiy_kalit)
    berilgan = post.get("sign_string", "")
    return hmac.compare_digest(kutilgan, berilgan.lower())


def _butun(post, nom: str, *, standart: int = 0) -> int:
    xom = (post.get(nom) or "").strip()
    if not xom:
        return standart
    try:
        return int(xom)
    except ValueError as xato:
        raise ClickXatosi(SOROV_XATOSI, f"{nom} butun son emas") from xato


def sorovni_oqish(
    post, *, amal: int, service_id: str, maxfiy_kalit: str
) -> ClickSorovi:
    """Xom POST -> tekshirilgan `ClickSorovi`. Xato bo'lsa `ClickXatosi`.

    ⚠️⚠️ TARTIB MUHIM: IMZO ENG BIRINCHI.
       Agar avval "buyurtma bormi?" deb bazaga borsak, imzosiz so'rov
       ham bazani qidirishga majbur qilardi — ya'ni tekin DoS vositasi.
       Bundan ham yomoni: javob kodi ("topilmadi" / "summa noto'g'ri")
       imzosiz odamga bizning buyurtmalarimiz haqida ma'lumot berardi.

    ⚠️ `service_id` ham tekshiriladi. Usiz bir merchant kabinetidagi
       boshqa xizmatning imzosi bu yerda ham o'tib ketardi.
    """
    if amal not in IMZO_MAYDONLARI:
        raise ClickXatosi(AMAL_TOPILMADI)

    # So'rovdagi `action` bizniki bilan mos kelmasa — Click boshqa
    # manzilga yuborgan yoki kimdir qo'lda so'rov yasagan.
    if _butun(post, "action", standart=-1) != amal:
        raise ClickXatosi(AMAL_TOPILMADI)

    if not imzoni_tekshirish(post, amal=amal, maxfiy_kalit=maxfiy_kalit):
        raise ClickXatosi(IMZO_XATO)

    if (post.get("service_id") or "") != str(service_id):
        raise ClickXatosi(SOROV_XATOSI, "service_id mos emas")

    xom_summa = (post.get("amount") or "").strip()
    try:
        summa = Decimal(xom_summa)
    except (InvalidOperation, ValueError) as xato:
        raise ClickXatosi(SUMMA_XATO) from xato

    merchant_trans_id = (post.get("merchant_trans_id") or "").strip()
    if not merchant_trans_id.isdigit():
        # ⚠️ `-5` («buyurtma topilmadi»), `-8` emas: raqam bo'lmagan
        #    `merchant_trans_id` bizda hech qachon mavjud emas, ya'ni
        #    natija bir xil. Ikki xil kod berish qidiruv oynasi ochardi.
        raise ClickXatosi(BUYURTMA_TOPILMADI)

    return ClickSorovi(
        click_trans_id=(post.get("click_trans_id") or "").strip(),
        service_id=(post.get("service_id") or "").strip(),
        click_paydoc_id=(post.get("click_paydoc_id") or "").strip(),
        merchant_trans_id=merchant_trans_id,
        merchant_prepare_id=(post.get("merchant_prepare_id") or "").strip(),
        amount=summa,
        action=amal,
        error=_butun(post, "error"),
        error_note=(post.get("error_note") or "")[:200],
        sign_time=(post.get("sign_time") or "").strip(),
    )


def javob(
    *,
    kod: int,
    click_trans_id: str = "",
    merchant_trans_id: str = "",
    prepare_id: int | None = None,
    confirm_id: int | None = None,
    izoh: str = "",
) -> dict:
    """Click kutadigan JSON javob.

    ⚠️ `error` MANFIY bo'lsa ham HTTP holati 200 qoladi. Click javob
       tanasini o'qiydi; 4xx/5xx esa u uchun "javob yo'q" degani va u
       so'rovni QAYTA yuboradi — ya'ni bizning "rad etdim" xabarimiz
       cheksiz sikl bo'lib qaytardi.
    """
    natija: dict = {
        "click_trans_id": click_trans_id,
        "merchant_trans_id": merchant_trans_id,
        "error": kod,
        "error_note": izoh or IZOHLAR.get(kod, "Error"),
    }
    if prepare_id is not None:
        natija["merchant_prepare_id"] = prepare_id
    if confirm_id is not None:
        natija["merchant_confirm_id"] = confirm_id
    return natija


def tolov_manzili(
    *,
    asos: str,
    service_id: str,
    merchant_id: str,
    tolov_id: int,
    summa: Decimal,
    qaytish_manzili: str,
) -> str:
    """Odam yuboriladigan Click sahifasi.

    ⚠️ `transaction_param` = bizning `Tolov.pk`. Click uni keyin
       `merchant_trans_id` bo'lib qaytaradi — bog'lovchi halqa shu.
    """
    parametrlar = {
        "service_id": service_id,
        "merchant_id": merchant_id,
        "amount": f"{summa:.2f}",
        "transaction_param": str(tolov_id),
        "return_url": qaytish_manzili,
    }
    return f"{asos}?{urlencode(parametrlar)}"
