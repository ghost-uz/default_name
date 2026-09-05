"""Matn normallashtirish — lotin/kiril va apostrof (D4-T2).

⚠️ Bu yerdagi testlar BAZASIZ: `qidiruv_uchun()` sof funksiya. Uning
   qidiruv natijalariga ta'siri `apps/complaints/tests/test_qidiruv.py`
   da, uchidan-uchiga tekshiriladi.
"""

from __future__ import annotations

import pytest

from apps.common.matn import (
    KIRIL_LOTIN,
    normallashtir,
    qidiruv_uchun,
)


# ===========================================================================
# 1. D4-T2 qabul mezoni: ikki alifbo bir xil natija beradi
# ===========================================================================
@pytest.mark.parametrize(
    ("lotin", "kiril"),
    [
        ("ipoteka", "ипотека"),
        ("ajrashish", "ажрашиш"),
        ("hujjat", "ҳужжат"),
        ("qarz", "қарз"),
        ("bola", "бола"),
        ("maktab", "мактаб"),
        ("shifokor", "шифокор"),
        ("universitet", "университет"),
    ],
)
def test_LOTIN_va_KIRIL_bir_xil_shaklga_keladi(lotin, kiril):
    """⚠️ D4-T2 ning asosiy qabul mezoni.

    Ikkisi bir shaklga kelmasa, kirillcha yozilgan post lotincha
    so'rovga HECH QACHON javob bermaydi — va foydalanuvchi buni
    "qidiruv ishlamayapti" deb tushunadi.
    """
    assert qidiruv_uchun(kiril) == qidiruv_uchun(lotin)


@pytest.mark.parametrize(
    ("kiril", "kutilgan"),
    [
        # ⚠️ `е` KONTEKSTGA BOG'LIQ — rasmiy qoida.
        ("Европа", "yevropa"),  # so'z boshida -> "ye"
        ("берди", "berdi"),  # undoshdan keyin -> "e"
        ("оева", "oyeva"),  # unlidan keyin -> "ye"
        # ⚠️ `ц` ham kontekstga bog'liq.
        ("цирк", "sirk"),  # so'z boshida -> "s"
        ("абзац", "abzats"),  # aks holda -> "ts"
        # O'zbek kirilliga xos harflar.
        ("ўзбек", "ozbek"),  # ў -> o' -> apostrof o'chadi
        ("ғалаба", "galaba"),  # ғ -> g' -> apostrof o'chadi
        ("маъно", "mano"),  # ъ -> ' -> o'chadi
        # Ikki harfli mosliklar.
        ("ёлка", "yolka"),
        ("юрак", "yurak"),
        ("ялпи", "yalpi"),
        ("чойхона", "choyxona"),
        ("шошилинch", "shoshilinch"),
        # Faqat ruschada uchraydigan harflar.
        ("щётка", "shchyotka"),
        ("мы", "mi"),
    ],
)
def test_transliteratsiya(kiril, kutilgan):
    assert qidiruv_uchun(kiril) == kutilgan


def test_ARALASH_matn_buzilmaydi():
    """⚠️ Aralash yozuv odatiy hol, istisno emas."""
    assert qidiruv_uchun("Windows 11 да ишламаяпти") == "windows 11 da ishlamayapti"


def test_kirilcha_BOLMAGAN_belgilar_tegilmaydi():
    assert qidiruv_uchun("iPhone 15 Pro Max") == "iphone 15 pro max"
    assert qidiruv_uchun("2026-yil 5-sentabr") == "2026-yil 5-sentabr"


# ===========================================================================
# 2. D4-T2 qabul mezoni: apostrof variantlari
# ===========================================================================
@pytest.mark.parametrize(
    "variant",
    [
        "ko'chmas",  # ASCII         U+0027
        "ko‘chmas",  # chap qo'shtirnoq  U+2018
        "ko’chmas",  # o'ng qo'shtirnoq  U+2019 (telefon klaviaturasi)
        "koʻchmas",  # rasmiy imlo   U+02BB
        "koʼchmas",  # U+02BC
        "ko`chmas",  # teskari       U+0060
        "ko´chmas",  # akut          U+00B4
        "kochmas",  # ⚠️ apostrofsiz — eng ko'p uchraydigan yozuv
        "кўчмас",  # ⚠️ kirill
    ],
)
def test_APOSTROFNING_HAR_VARIANTI_bir_shaklga_keladi(variant):
    """⚠️⚠️ D4-T2 ning ikkinchi qabul mezoni.

    To'qqizta yozuv usuli — bitta so'z. Bulardan bittasi ham chetda
    qolsa, qidiruv foydalanuvchining KLAVIATURASIGA bog'liq bo'lib
    qoladi va buni tushuntirib bo'lmaydi.
    """
    assert qidiruv_uchun(variant) == "kochmas"


def test_apostrof_OCHIRILADI_bir_shaklga_KELTIRILMAYDI():
    """⚠️ Bu D2-T6 dagi qaror bilan ATAYLAB boshqacha.

    Sabab `matn.py` da o'lchangan: `simple` tokenizatori apostrofda
    so'zni bo'ladi, ya'ni apostrofni saqlab qolish "ko'chmas" ni ikkita
    lexemaga (`ko` + `chmas`) ajratardi va apostrofsiz yozilgan so'rov
    uni topmasdi.
    """
    assert "'" not in qidiruv_uchun("o'zbekiston va g'alaba")
    assert qidiruv_uchun("o'zbekiston") == "ozbekiston"


def test_tutuq_belgisi_ham_ochadi():
    """`ъ` -> `'` -> o'chadi. Ya'ni "san'at" va "sanat" bir xil."""
    assert qidiruv_uchun("san'at") == qidiruv_uchun("sanat") == "sanat"


# ===========================================================================
# 3. ⚠️ INQIROZ ANIQLASHI TEGILMAGAN (D2-T6)
# ===========================================================================
def test_INQIROZ_normallashtirishi_apostrofni_SAQLAYDI():
    """⚠️⚠️ `normallashtir()` va `qidiruv_uchun()` BIR MODULDA turadi va
    aynan shuning uchun ularni chalkashtirib yuborish oson.

    `inqiroz.KALIT_SOZLAR` ro'yxatidagi 46 ta ibora apostrofli shaklda
    yozilgan (`o'zimni o'ldir`). Agar bu funksiya apostrofni o'chirsa,
    ro'yxatning katta qismi HECH QACHON mos kelmasdi — va buni hech
    narsa bildirmasdi.
    """
    assert normallashtir("o‘zimni o‘ldir") == "o'zimni o'ldir"


def test_INQIROZ_akut_apostrofni_ham_TANIYDI():
    """⚠️⚠️ D4-T2 testi ushlagan HAQIQIY xato — u D2-T6 ga tegishli edi.

    `´` (U+00B4) ning moslik dekompozitsiyasi bor: NFKC uni BO'SHLIQ +
    birikuvchi urg'uga aylantiradi. Tekislash NFKC dan KEYIN turgani
    uchun jadval unga yetib bormasdi va `o´ldirmoqchiman` so'z ichida
    ikkiga bo'linib, kalit so'zga mos kelmasdi.

    Aniqlash o'tkazib yuborilishi bu modulda eng qimmat xato
    (`inqiroz.py` docstring'iga qarang), shuning uchun regressiya
    testi shu yerda.
    """
    from apps.common.inqiroz import inqiroz_aniqlandimi

    assert normallashtir("o´ldirmoqchiman") == "o'ldirmoqchiman"
    assert inqiroz_aniqlandimi("men o´ldirmoqchiman o´zimni")


def test_INQIROZ_normallashtirishi_TRANSLITERATSIYA_QILMAYDI():
    """⚠️ Kalit so'zlar ro'yxatida kirillcha iboralar ALOHIDA yozilgan
    (`ўзимни ўлдир`). Transliteratsiya qo'shilsa, ular endi mos
    kelmasdi va kirillcha yozadigan odam aniqlashdan tushib qolardi."""
    assert normallashtir("ЎЗИМНИ ЎЛДИР") == "ўзимни ўлдир"


# ===========================================================================
# 4. Jadval butunligi
# ===========================================================================
def test_JADVALDA_ozbek_kirilining_HAMMA_harfi_bor():
    """⚠️ Tushib qolgan harf jimgina o'zini o'zi ko'rsatmaydi: u
    transliteratsiyadan o'zgarmasdan o'tadi va lexema ichida kirillcha
    belgi bo'lib qoladi — natija esa shunchaki topilmaydi."""
    ozbek_kirili = "абвгдеёжзийклмнопрстуфхцчшъьэюяўқғҳ"

    tushib_qolgan = [
        harf
        for harf in ozbek_kirili
        if harf not in KIRIL_LOTIN and harf not in ("е", "ц")  # ikkisi kontekstli
    ]

    assert tushib_qolgan == []


def test_HECH_QANDAY_kiril_belgi_natijada_QOLMAYDI():
    """Butun alifbo bo'ylab tekshiruv — yuqoridagi jadval testining
    ish vaqtidagi juftligi."""
    natija = qidiruv_uchun("абвгдеёжзийклмнопрстуфхцчшъьэюяўқғҳ")

    assert natija.isascii(), f"kirillcha belgi qoldi: {natija!r}"
