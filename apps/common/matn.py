"""Matn normallashtirish — ikkala ishlatuvchi uchun BITTA manba (D4-T1).

Bu modulda faqat sof funksiyalar bor: na Django, na baza import qilinadi.
Shu sababli uni migratsiya ichidan ham, boshqaruv buyrug'idan ham,
testdan ham xavfsiz chaqirish mumkin.

⚠️ NEGA ALOHIDA MODUL — `inqiroz.py` DA QOLDIRILMADI
   Apostrof variantlari ro'yxati D2-T6 dan beri `inqiroz.py` da turardi.
   Qidiruvga ham aynan shu ro'yxat kerak bo'lganda ikki yo'l bor edi:

     · qidiruv `inqiroz` ni import qilsin — u holda qidiruv o'z joniga
       qasd aniqlash moduliga bog'lanardi. Bir kuni kimdir "qidiruvga
       inqiroz nega kerak?" deb so'raydi va javob bo'lmaydi;
     · ro'yxatdan ikkinchi nusxa yasalsin — bundan ham yomoni. Yangi
       apostrof belgisi BITTA ro'yxatga qo'shiladi, ikkinchisi esa
       jimgina eskiradi. Buni hech qanday test ushlamaydi, chunki har
       ikkala ro'yxat ham o'zicha "to'g'ri" bo'lib qolaveradi.

   Shuning uchun umumiy primitivlar quyi qatlamga tushdi.

⚠️⚠️ IKKI XIL NORMALLASHTIRISH BOR VA ULAR ATAYLAB BOSHQACHA

   `normallashtir()` — ANIQLASH uchun (D2-T6). Apostrof variantlari
       bitta shaklga (`'`) keltiriladi, lekin YO'QOTILMAYDI: kalit
       so'zlar ro'yxati aynan `o'zimni o'ldir` shaklida yozilgan va
       unda qismiy moslik qidiriladi.

   `qidiruv_uchun()` — INDEKSLASH va QIDIRUV uchun (D4-T1). Bu yerda
       maqsad boshqa: natija PostgreSQL tokenizatoriga tushadi va u
       belgilarni butunlay boshqacha o'qiydi (pastdagi izohga qarang).

   "Ikkalasini birlashtiraylik" degan taklif kelsa: har ikkisining
   testlariga qarang — bitta funksiya ikkala shartni bir vaqtda
   bajara olmaydi.
"""

from __future__ import annotations

import re
import unicodedata

# ⚠️ APOSTROF VARIANTLARI — o'zbek lotin yozuvi uchun MAJBURIY.
#    "o'zimni", "oʻzimni", "o’zimni", "o`zimni" — bitta so'z, to'rt xil
#    Unicode belgisi. Qaysi biri yozilishi foydalanuvchining
#    KLAVIATURASIGA bog'liq: Windows'da odatda `'` (U+0027), telefon
#    klaviaturasi ko'pincha `’` (U+2019) ga aylantiradi, rasmiy imloda
#    esa `ʻ` (U+02BB).
#
#    ASCII `'` bu ro'yxatda YO'Q — u nishon shakl, o'ziga o'zi
#    aylantirilmaydi.
APOSTROF_VARIANTLARI = "‘’ʻʼ`´"

# Aniqlash uchun: hammasi ASCII apostrofga keladi.
APOSTROFLAR = str.maketrans(dict.fromkeys(APOSTROF_VARIANTLARI, "'"))

BOSH_JOYLAR = re.compile(r"\s+")


def normallashtir(matn: str) -> str:
    """Kichik harf + bir xil apostrof + bir xil bo'shliq (D2-T6).

    ⚠️ Xulqi D2-T6 dan beri O'ZGARMAGAN va o'zgarmasligi ham kerak:
       `inqiroz.KALIT_SOZLAR` ro'yxatidagi 46 ta ibora aynan shu
       funksiya chiqaradigan shaklda yozilgan. Bu yerdagi har qanday
       o'zgarish inqiroz aniqlashning qamrovini jimgina toraytiradi —
       eng qimmat turdagi xato (`inqiroz.py` docstring'iga qarang).
       Guard: `apps/common/tests/test_inqiroz.py`.
    """
    matn = unicodedata.normalize("NFKC", matn or "")
    return BOSH_JOYLAR.sub(" ", matn.translate(APOSTROFLAR).casefold()).strip()


# ===========================================================================
# Qidiruv uchun normallashtirish (D4-T1)
# ===========================================================================
def _aksentsiz(matn: str) -> str:
    """Diakritik belgilarni olib tashlaydi: "café" -> "cafe", "ё" -> "е".

    ⚠️⚠️ NEGA POSTGRES'NING `unaccent` KENGAYTMASI ISHLATILMADI

       D4-T1 tavsifida "'simple' konfiguratsiya + unaccent" deb yozilgan
       va birinchi qarashda buni bazada qilish tabiiy ko'rinadi. Lekin
       `unaccent()` PostgreSQL'da IMMUTABLE EMAS — u lug'at faylini
       o'qiydi, ya'ni natijasi server sozlamasiga bog'liq.

       Oqibati aniq: uni GENERATED ustun ifodasiga qo'yib BO'LMAYDI
       (Postgres rad etadi). Odatdagi chetlab o'tish — o'zining
       `IMMUTABLE` o'ram funksiyasini yozish, bu esa yolg'on va'da:
       lug'at almashsa indeks jimgina noto'g'ri bo'lib qoladi.

       Python'da qilish bu tuzoqni butunlay yo'q qiladi va bitta
       qo'shimcha foyda beradi: indekslash va qidiruv AYNAN bir xil
       kod yo'lidan o'tadi. Baza tomonda esa faqat immutable
       `to_tsvector('simple', ...)` qoladi.
    """
    return "".join(
        b for b in unicodedata.normalize("NFKD", matn) if not unicodedata.combining(b)
    )


def qidiruv_uchun(matn: str) -> str:
    """Indekslash va qidiruv uchun yagona normal shakl.

    ⚠️ BU FUNKSIYA IKKI JOYDA ISHLATILADI VA IKKALASI HAM MAJBURIY:
       (1) yozuv saqlanganda — `Complaint.qidiruv_sarlavha` /
           `qidiruv_tavsif` ustunlariga;
       (2) foydalanuvchi so'rovi kelganda.

       Faqat bittasida qo'llansa qidiruv jimgina buziladi: indeksda
       bir shakl, so'rovda boshqasi bo'ladi va natija hech qachon
       topilmaydi — xato ham chiqmaydi.

    ⚠️ O'ZGARTIRILSA INDEKS ESKIRADI. Ustunlar saqlangan qiymat, ya'ni
       eski yozuvlar eski qoidalar bilan normallashtirilgan holda
       qoladi. Shuning uchun:

           python manage.py qidiruvni_yangilash

       (guard testi bu funksiya va ustunlar mosligini tekshiradi).
    """
    matn = unicodedata.normalize("NFKC", matn or "").casefold()
    return BOSH_JOYLAR.sub(" ", _aksentsiz(matn)).strip()
