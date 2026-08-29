"""Inqirozli kontentni aniqlash (D2-T6).

⚠️⚠️ BU MODUL BOSHQALARIDAN FARQ QILADI. Bu yerdagi xato — noqulaylik
   emas, odam hayoti. Shuning uchun qarorlar boshqacha muvozanatda:

   **Yolg'on IJOBIY arzon, yolg'on SALBIY qimmat.**
   Noto'g'ri aniqlangan post moderatorning bir daqiqasini oladi va
   muallif yumshoq matn ko'radi. O'tkazib yuborilgan post esa odamni
   yolg'iz qoldiradi. Shuning uchun ro'yxat ATAYLAB KENG va aniqlik
   (precision) ataylab qurbon qilingan.

⚠️ ANIQLASH — TSENZURA EMAS.
   Aniqlangan post O'CHIRILMAYDI, YASHIRILMAYDI va hech qanday
   ogohlantirish olmaydi. Task tavsifi buni ochiq aytadi: "jim
   o'chirish eng yomon variant — u odamni yakkalaydi". Aniqlash faqat
   ikki narsa qiladi: navbatning eng tepasiga chiqaradi va yordam
   ma'lumotini ko'rsatadi.

⚠️ IKKI TILDA VA IKKI ALIFBODA.
   O'zbekistonda odam og'ir paytda o'zbekcha (lotin yoki kirill) ham,
   ruscha ham yozishi mumkin — ko'pincha aralash. Faqat lotin
   o'zbekchani qamrash aholining katta qismini o'tkazib yuborardi.
"""

from __future__ import annotations

import re
import unicodedata

# ⚠️ APOSTROF NORMALLASHTIRISH — o'zbek lotin yozuvi uchun MAJBURIY.
#    "o'zimni", "oʻzimni", "o‘zimni", "o`zimni" — bir xil so'z, to'rt
#    xil belgi. Normallashtirmasak, ro'yxat foydalanuvchi klaviaturasiga
#    bog'liq bo'lib qolardi.
APOSTROFLAR = str.maketrans(
    {
        "‘": "'",  # '
        "’": "'",  # '
        "ʻ": "'",  # ʻ
        "ʼ": "'",  # ʼ
        "`": "'",  # `
        "´": "'",  # ´
    }
)

BOSH_JOYLAR = re.compile(r"\s+")


def normallashtir(matn: str) -> str:
    """Kichik harf + bir xil apostrof + bir xil bo'shliq."""
    matn = unicodedata.normalize("NFKC", matn or "")
    return BOSH_JOYLAR.sub(" ", matn.translate(APOSTROFLAR).casefold()).strip()


# ⚠️ RO'YXAT ATAYLAB KENG (yuqoridagi izohga qarang).
#    Har bir satr NORMALLASHTIRILGAN shaklda yozilgan: kichik harf,
#    oddiy apostrof. Qidiruv — QISMIY MOSLIK, chunki o'zbek tili
#    agglyutinativ: "o'ldirmoqchiman", "o'ldirsammikan", "o'ldiraman"
#    bir o'zakdan.
KALIT_SOZLAR: tuple[str, ...] = (
    # --- o'zbekcha, lotin ---
    "o'zimni o'ldir",
    "o'zini o'ldir",
    "o'ldirmoqchiman",
    "o'lgim kel",
    "o'lsam",
    "o'lib qo'ya qol",
    "yashagim kelmay",
    "yashashdan mazza",
    "yashagim yo'q",
    "o'z joniga qasd",
    "jonimga qasd",
    "suitsid",
    "o'zimga zarar",
    "o'zimni kes",
    "tomirimni kes",
    "bilagimni kes",
    "osilib o'l",
    "osib qo'y",
    "dori ichib o'l",
    "zahar ich",
    "hayotdan bezdim",
    "hayotim tugadi",
    "chidayolmayapman",
    "bardosh berolmayapman",
    "hech kimga keragim yo'q",
    "yo'qolib ketsam",
    # --- o'zbekcha, kirill ---
    "ўзимни ўлдир",
    "ўлгим кел",
    "ўз жонига қасд",
    "суицид",
    "ўзимга зарар",
    "яшагим келма",
    "ҳаётдан бездим",
    # --- ruscha ---
    "покончить с собой",
    "покончу с собой",
    "убить себя",
    "убью себя",
    "не хочу жить",
    "не хочется жить",
    "жить не хочу",
    "суицид",
    "самоубийств",
    "вскрыть вены",
    "вскрыл вены",
    "порезать себя",
    "таблетки выпил",
    "уйти из жизни",
    "нет сил жить",
    "устал жить",
)


def inqiroz_aniqlandimi(*matnlar: str) -> bool:
    """Berilgan matnlarning birortasida inqiroz belgisi bormi.

    ⚠️ Bu funksiya TASHXIS QO'YMAYDI. U faqat "bu postga odam ko'z
       tashlashi kerak" degan signal beradi. Qaror — moderatorda
       (`/moderatsiya/qollanma/`).
    """
    return bool(topilgan_belgilar(*matnlar))


def topilgan_belgilar(*matnlar: str) -> list[str]:
    """Qaysi kalit so'zlar topildi — moderator izohi uchun.

    ⚠️ Moderator NIMA aniqlanganini ko'rishi kerak: "inqiroz signali"
       degan yorliq o'zi hech narsa bermaydi va qarorni tasodifiy
       qiladi. D2-T5 dagi `Baho.sabablar` bilan bir xil mantiq.
    """
    matn = normallashtir(" ".join(matnlar))
    return [soz for soz in KALIT_SOZLAR if soz in matn]


def inqiroz_konteksti() -> dict:
    """Yordam bloki uchun sozlama qiymatlari.

    ⚠️ Kontekst-protsessor EMAS, ochiq chaqiruv: blok faqat ikkita
       sahifada kerak, kontekst-protsessor esa uni HAR BIR render'ga
       qo'shardi (va D1-T14 dagi so'rov-sanog'i testlariga ta'sir
       qilish xavfini olib kelardi).
    """
    from django.conf import settings

    return {
        "inqiroz_raqamlar": settings.SHOSHILINCH_RAQAMLAR,
        "ishonch_telefoni": settings.ISHONCH_TELEFONI,
    }
