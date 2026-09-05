"""Open Graph rasmini yasash (D4-T4).

⚠️ Bu testlar BAZASIZ: `og_rasm_yasash()` faqat matn oladi.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image, ImageDraw

from apps.common.og import (
    BALANDLIK,
    KENGLIK,
    MAKS_QATOR,
    og_rasm_yasash,
    qatorlarga_bolish,
    shrift,
)


def rasm(baytlar: bytes) -> Image.Image:
    return Image.open(io.BytesIO(baytlar))


# ===========================================================================
# 1. Shrift qamrovi — eng jim buziladigan joy
# ===========================================================================
def _yoq_belgi_bitmapi(f) -> bytes:
    """Aniq mavjud BO'LMAGAN belgining tasviri (xususiy foydalanish sohasi)."""
    im = Image.new("L", (90, 90), 0)
    ImageDraw.Draw(im).text((10, 10), "", font=f, fill=255)
    return im.tobytes()


def _bitmap(f, belgi: str) -> bytes:
    im = Image.new("L", (90, 90), 0)
    ImageDraw.Draw(im).text((10, 10), belgi, font=f, fill=255)
    return im.tobytes()


@pytest.mark.parametrize(
    ("nom", "belgilar"),
    [
        ("lotin", "abcdefghijklmnopqrstuvxyzABCXYZ"),
        # ⚠️ O'zbek lotinidagi `oʻ` va `gʻ` — U+02BB. Ko'p shriftda YO'Q.
        ("ozbek", "oʻgʻOʻGʻʼ"),
        ("apostrof", "'‘’ʻʼ`´"),
        # ⚠️ O'zbek kirilligiga xos: ў қ ғ ҳ. Ular ham ko'p shriftda yo'q.
        ("kiril", "абвгдеёжзийклмнопрстуфхцчшъьэюяўқғҳАБВЎҚҒҲ"),
        ("belgi", "0123456789«»—…?!"),
    ],
)
def test_SHRIFT_kerakli_belgilarni_QAMRAB_oladi(nom, belgilar):
    """⚠️⚠️ Shrift almashtirilsa yoki noto'g'ri fayl qo'yilsa, yo'q
    belgilar o'rniga bo'sh QUTI chiziladi — rasm yasaladi, xato
    chiqmaydi, va buni faqat Telegram'ga havola tashlagan odam ko'radi.

    Tekshiruv usuli: har belgi tasvirini ATAYLAB mavjud bo'lmagan
    belgining tasviri bilan solishtiramiz. Bir xil bo'lsa — glif yo'q.
    """
    f = shrift(48, qalin=True)
    yoq = _yoq_belgi_bitmapi(f)

    yoqolgan = [c for c in belgilar if _bitmap(f, c) == yoq]

    assert yoqolgan == [], f"{nom}: shriftda quyidagi belgilar YO'Q — " + " ".join(
        f"U+{ord(c):04X}" for c in yoqolgan
    )


def test_shrift_KESHLANADI():
    """Shrift faylini har rasm uchun qayta o'qish bekorga sekinlashtiradi."""
    assert shrift(48, qalin=True) is shrift(48, qalin=True)


def test_QALIN_va_ODDIY_boshqa_shrift():
    """⚠️ Tekshiruv NOM bo'yicha ham, O'LCHOV bo'yicha ham.

    Nom yolg'iz yetarli emas: statik nusxa yasalganda nom jadvali
    yangilanmasligi mumkin va IKKALA fayl ham "Regular" deb ko'rinadi
    (aynan shu holat bir marta yuz berdi). Qalin matn esa har doim
    KENGROQ chiziladi — buni metadata yashira olmaydi.
    """
    qalin = shrift(48, qalin=True)
    oddiy = shrift(48, qalin=False)

    assert qalin is not oddiy
    assert qalin.getname()[1] == "Bold"
    assert oddiy.getname()[1] == "Regular"
    assert qalin.getlength("Dard.uz") > oddiy.getlength("Dard.uz")


# ===========================================================================
# 2. Rasmning o'zi
# ===========================================================================
def test_olcham_Open_Graph_standartida():
    """⚠️ 1200×630 (1.91:1). Boshqa nisbatda platformalar rasmni O'ZI
    kesadi va matn chetidan qirqiladi."""
    im = rasm(og_rasm_yasash(sarlavha="Ipoteka olish", kategoriya="Moliya"))

    assert im.size == (KENGLIK, BALANDLIK)
    assert im.format == "PNG"


@pytest.mark.parametrize(
    "sarlavha",
    [
        "Ipoteka olish qiyinmi?",
        "Ипотека олиш қийинми? Банк рад этди",
        "Koʻchmas mulk va oʻzimning huquqlarim",
        "a" * 200,  # bitta juda uzun so'z
        "  ",  # bo'sh
        "🙂 emoji va matn",
    ],
)
def test_HAR_XIL_kiritmada_yiqilmaydi(sarlavha):
    """⚠️ Sarlavha foydalanuvchi yozgan matn: u kirillcha ham, bitta
    uzun so'z ham, bo'sh ham bo'lishi mumkin. Fon vazifasidagi istisno
    jimgina yo'qoladi — shuning uchun chegara holatlari shu yerda."""
    im = rasm(og_rasm_yasash(sarlavha=sarlavha, kategoriya="Boshqa"))

    assert im.size == (KENGLIK, BALANDLIK)


def test_kategoriyasiz_ham_ishlaydi():
    im = rasm(og_rasm_yasash(sarlavha="Sarlavha", kategoriya=""))

    assert im.size == (KENGLIK, BALANDLIK)


def test_matn_HAQIQATAN_chiziladi():
    """⚠️ Bo'sh oq rasm ham "yasalgan" hisoblanardi. Tekshiruv: oq
    bo'lmagan piksellar bormi."""
    im = rasm(og_rasm_yasash(sarlavha="Ipoteka", kategoriya="Moliya")).convert("L")

    # Chapdagi brend chizig'idan tashqaridagi soha
    markaz = im.crop((100, 150, KENGLIK - 100, BALANDLIK - 150))

    assert markaz.getextrema()[0] < 128, "matn chizilmagan — rasm bo'm-bo'sh"


def test_bir_xil_kiritma_bir_xil_natija():
    """⚠️ Vazifa fayl nomini MAZMUN HASHIDAN quradi: natija
    determinlashgan bo'lmasa har saqlashda yangi fayl paydo bo'lardi."""
    a = og_rasm_yasash(sarlavha="Ipoteka", kategoriya="Moliya")
    b = og_rasm_yasash(sarlavha="Ipoteka", kategoriya="Moliya")

    assert a == b


# ===========================================================================
# 3. Qatorlarga bo'lish — piksel bo'yicha
# ===========================================================================
def test_uzun_sarlavha_MAKS_QATORgacha_kesiladi():
    f = shrift(60, qalin=True)

    qatorlar = qatorlarga_bolish("juda uzun sarlavha " * 30, f, 1000, MAKS_QATOR)

    assert len(qatorlar) == MAKS_QATOR
    assert qatorlar[-1].endswith("…")


def test_qisqa_sarlavha_KESILMAYDI():
    f = shrift(60, qalin=True)

    qatorlar = qatorlarga_bolish("Qisqa sarlavha", f, 1000, MAKS_QATOR)

    assert qatorlar == ["Qisqa sarlavha"]


def test_HAR_QATOR_kenglikka_SIGADI():
    """⚠️ Asosiy invariant: bo'lish PIKSEL bo'yicha ishlaydi. Belgi soni
    bo'yicha bo'linganda kirillcha matn kengroq chiqib, rasmdan chetga
    chiqib ketardi."""
    f = shrift(60, qalin=True)
    kenglik = 900

    for matn in (
        "Ипотека олиш қийинми ва банк нима дейди бу ҳолатда",
        "Ipoteka olish qiyinmi va bank nima deydi bu holatda",
        "Koʻchmas mulk va oʻzimning huquqlarim haqida savol",
    ):
        for qator in qatorlarga_bolish(matn, f, kenglik, MAKS_QATOR):
            assert f.getlength(qator) <= kenglik, f"chetga chiqdi: {qator!r}"


def test_bitta_UZUN_soz_majburan_bolinadi():
    """⚠️ Busiz uzun so'z (URL yoki tasodifiy belgilar) cheksiz siklga
    yoki rasmdan chiqib ketishga olib kelardi."""
    f = shrift(60, qalin=True)
    kenglik = 400

    qatorlar = qatorlarga_bolish("a" * 200, f, kenglik, MAKS_QATOR)

    assert len(qatorlar) > 1
    for qator in qatorlar:
        assert f.getlength(qator) <= kenglik
