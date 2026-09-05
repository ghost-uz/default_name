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

# ⚠️⚠️ QIDIRUV UCHUN: apostrof BIR SHAKLGA KELTIRILMAYDI, O'CHIRILADI.
#    ASCII `'` ham shu ro'yxatda — ya'ni hech qanday apostrof qolmaydi.
#
#    IKKI SABAB, ikkalasi ham o'lchangan:
#
#    1. `simple` tokenizatori apostrofda SO'ZNI BO'LADI:
#           to_tsvector('simple', "ko'chmas")  ->  'ko':1 'chmas':2
#           to_tsvector('simple', "kochmas")   ->  'kochmas':1
#       ikkinchisi bilan birinchisini qidirsangiz — TOPILMAYDI.
#
#    2. Foydalanuvchilar apostrofni ko'pincha UMUMAN yozmaydi
#       ("uzbekiston", "kochmas mulk"). O'chirilganda "ko'chmas",
#       "koʻchmas", "kochmas" va "кўчмас" — hammasi bitta lexemaga
#       tushadi.
#
#    ⚠️ NARXI BOR VA U ONGLI QABUL QILINGAN: `o'` va `o` farqi yo'qoladi
#       ("to'y" va "toy" bir xil bo'lib qoladi). Qidiruvda qamrov
#       (recall) aniqlikdan muhimroq — topilmagan natija foydalanuvchi
#       uchun "sayt buzuq" degani, ortiqcha natija esa shunchaki
#       ro'yxatning ikkinchi qatori.
APOSTROFSIZ = str.maketrans(dict.fromkeys(APOSTROF_VARIANTLARI + "'", ""))

BOSH_JOYLAR = re.compile(r"\s+")


def _apostrofni_tekislash(matn: str) -> str:
    """Barcha apostrof variantlarini ASCII `'` ga keltiradi va NFKC qiladi.

    ⚠️⚠️ TARTIB: TEKISLASH NFKC DAN OLDIN — bu jonli sinovda topilgan
       xato (D4-T2 testi ushladi, lekin u D2-T6 ga ham tegishli edi).

       `´` (U+00B4, AKUT) ning MOSLIK dekompozitsiyasi bor:

           NFKC("ko´chmas")  ->  "ko" + " " + U+0301 + "chmas"

       ya'ni NFKC uni BO'SHLIQ + birikuvchi urg'u belgisiga aylantiradi.
       Shundan keyin apostrof jadvali unga yetib bormaydi: belgi
       endi apostrof emas. Natijada "ko´chmas" -> "ko chmas" bo'lib,
       so'z IKKIGA bo'linardi.

       Oqibati ikki joyda ko'rinardi va ikkalasi ham jim: qidiruvda
       natija topilmasdi, inqiroz aniqlashida esa `o´ldirmoqchiman`
       kalit so'zga mos kelmasdi.

       NFKC ni butunlay olib tashlash mumkin emas — u to'liq kenglikdagi
       harflar va ligaturalarni ham tekislaydi. Shuning uchun tartib
       almashtirildi: avval apostrof, keyin NFKC.

    ⚠️ NFKC O'ZI ham apostrof hosil qilishi mumkin (U+FF07 -> U+0027),
       lekin u ALLAQACHON nishon shakl — qo'shimcha o'tish kerak emas.
    """
    return unicodedata.normalize("NFKC", (matn or "").translate(APOSTROFLAR))


def normallashtir(matn: str) -> str:
    """Kichik harf + bir xil apostrof + bir xil bo'shliq (D2-T6).

    ⚠️ Xulqi D2-T6 dan beri O'ZGARMAGAN va o'zgarmasligi ham kerak:
       `inqiroz.KALIT_SOZLAR` ro'yxatidagi 46 ta ibora aynan shu
       funksiya chiqaradigan shaklda yozilgan. Bu yerdagi har qanday
       o'zgarish inqiroz aniqlashning qamrovini jimgina toraytiradi —
       eng qimmat turdagi xato (`inqiroz.py` docstring'iga qarang).
       Guard: `apps/common/tests/test_inqiroz.py`.
    """
    return BOSH_JOYLAR.sub(" ", _apostrofni_tekislash(matn).casefold()).strip()


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


# ---------------------------------------------------------------------------
# Kiril -> lotin (D4-T2)
# ---------------------------------------------------------------------------
# ⚠️⚠️ NEGA UMUMAN KERAK
#    O'zbekistonda bir xil odam bir kuni lotin, ertasiga kirill yozadi —
#    ko'pincha bitta jumla ichida ham. Transliteratsiyasiz "ipoteka" va
#    "ипотека" bir-birini HECH QACHON topmaydi va foydalanuvchi qidiruvni
#    buzuq deb qabul qiladi (D4-T2 `nega` bo'limi aynan shu haqda).
#
# ⚠️ YO'NALISH BITTA: kiril -> lotin. Teskarisi kerak emas — muhimi
#    hamma narsa BITTA shaklga kelishi, qaysi shakl ekani ahamiyatsiz.
#    Lotin tanlandi, chunki kontentning katta qismi shundaydir va
#    transliteratsiya ishi kamroq bo'ladi.
#
# ⚠️ Jadval RASMIY o'zbek transliteratsiyasiga tayanadi: lotin yozuvidagi
#    kontent aynan shu qoidalar bilan yozilgan, ya'ni faqat shunda
#    kirillcha so'rov lotincha yozuvni topadi.
#
# ⚠️ `ў` va `ғ` apostrofli shaklga (`o'`, `g'`) o'tkaziladi, keyin esa
#    apostrof umumiy qoida bilan o'chiriladi. To'g'ridan-to'g'ri `o` / `g`
#    yozish qisqaroq bo'lardi, lekin u holda apostrof siyosati IKKI joyda
#    yashardi va ularning biri bir kuni o'zgarardi.
KIRIL_LOTIN = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "ё": "yo",
    "ж": "j",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "x",
    "ч": "ch",
    "ш": "sh",
    "ъ": "'",  # tutuq belgisi — apostrof qoidasi uni o'chiradi
    "ь": "",  # yumshatish belgisi: lotin yozuvida muqobili yo'q
    "э": "e",
    "ю": "yu",
    "я": "ya",
    # --- o'zbek kirilliga xos harflar ---
    "ў": "o'",
    "қ": "q",
    "ғ": "g'",
    "ҳ": "h",
    # --- faqat ruschada uchraydi ---
    "ы": "i",
    "щ": "shch",
}

# `е` va `ц` dan OLDIN kelgan belgi qoidani o'zgartiradi (pastga qarang).
KIRIL_UNLILAR = frozenset("аеёиоуўэюяъь")


def _transliteratsiya(matn: str) -> str:
    """Kirillcha matnni lotinchaga o'giradi.

    ⚠️ IKKI HARF KONTEKSTGA BOG'LIQ — rasmiy qoida shunday va usiz
       kirillcha kontent lotincha so'rovga mos kelmaydi:

           «Европа» -> "yevropa"   (so'z boshida)
           «берди»  -> "berdi"     (undoshdan keyin)
           «цирк»   -> "sirk"      (so'z boshida)
           «абзац»  -> "abzats"    (aks holda)

       Bu qoidalarsiz «Европа» "evropa" bo'lardi va lotin yozuvidagi
       "Yevropa" bilan hech qachon uchrashmasdi.

    ⚠️ Kirillcha bo'lmagan belgilar TEGILMAYDI: matn aralash bo'lishi
       odatiy hol ("Windows 11 да ишламаяпти").
    """
    natija: list[str] = []
    oldingi = ""

    for belgi in matn:
        if belgi == "е":
            boshimi = not oldingi.isalpha() or oldingi in KIRIL_UNLILAR
            natija.append("ye" if boshimi else "e")
        elif belgi == "ц":
            natija.append("s" if not oldingi.isalpha() else "ts")
        else:
            natija.append(KIRIL_LOTIN.get(belgi, belgi))
        oldingi = belgi

    return "".join(natija)


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
    # ⚠️ Apostrof NFKC DAN OLDIN tekislanadi — sabab
    #    `_apostrofni_tekislash()` da (u yerdagi xato ikkala funksiyaga
    #    ham tegishli edi).
    matn = _apostrofni_tekislash(matn).casefold()

    # ⚠️⚠️ TARTIB AHAMIYATLI — ikkalasi ham jonli sinovda tekshirilgan:
    #
    #    · Transliteratsiya AKSENTDAN OLDIN. Teskarisida `ё` avval `е` ga
    #      aylanardi (diakritika olib tashlanadi) va keyin "e" bo'lardi —
    #      "yo" o'rniga. `й` esa NFKD da `и` + breve ga parchalanib "i"
    #      bo'lib qolardi.
    #
    #    · Apostrof TRANSLITERATSIYADAN KEYIN: `ў` -> `o'` va `ъ` -> `'`
    #      yangi apostrof hosil qiladi va ular ham o'chirilishi kerak.
    matn = _transliteratsiya(matn)
    matn = matn.translate(APOSTROFSIZ)

    return BOSH_JOYLAR.sub(" ", _aksentsiz(matn)).strip()
