"""Ijtimoiy tarmoq uchun rasm yasash — Open Graph kartasi (D4-T4).

⚠️ NEGA UMUMAN KERAK
   Reja virallikni asosiy o'sish kanali deb belgilagan. Telegram yoki
   Facebook'ga tashlangan havola rasmsiz bo'lsa, u lentada kichkina
   kulrang qator bo'lib qoladi; rasm bilan esa u kartaga aylanadi va
   bosilish darajasi sezilarli farq qiladi. Rasm — havolaning "muqovasi".

⚠️ NEGA SERVERDA RASTR, HTML EMAS
   Facebook, Telegram va X `og:image` da FAQAT rastr formatni qabul
   qiladi (SVG ishlamaydi), ya'ni matnni haqiqiy piksellarga aylantirish
   kerak. Buning uchun shrift fayli SHART — brauzersiz boshqa yo'l yo'q.

⚠️ SHRIFT VENDORLANGAN (`assets/fonts/`), tizim shriftidan olinmaydi.
   `python:3.12-slim` da hech qanday shrift yo'q, Windows'dagi shriftlar
   esa tarqatilmaydi. Tizim shriftiga tayanish "lokalda ishlaydi,
   konteynerda quti chizadi" degan holatni yaratardi — Dockerfile'ning
   birinchi izohi aynan shundan ogohlantiradi.

   `htmx.min.js` bilan bir xil qaror: tashqi manbaga bog'lanmaymiz.

⚠️ IKKITA STATIK FAYL, O'ZGARUVCHAN (variable) EMAS
   Birinchi urinishda o'zgaruvchan Inter qo'yilgan edi: bitta fayldan
   `set_variation_by_name()` bilan to'qqizta og'irlik chiqardi va bu
   chiroyli ko'rinardi. Lekin u 876 KB, kerakli belgilarga
   qisqartirilgandan keyin ham 513 KB — chunki o'zgaruvchan shriftda
   `gvar` jadvali (har glif uchun har o'q bo'yicha o'zgarish
   ma'lumotlari) saqlanadi va u qisqarmaydi.

   `check-added-large-files` hooki (500 KB) uni to'g'ri rad etdi.
   Chegarani ko'tarish yoki istisno qo'shish mumkin edi, lekin ikkalasi
   ham qo'riqchini bo'shatardi. To'g'ri yechim — bizga faqat IKKI
   og'irlik kerak ekanini tan olish:

       o'zgaruvchan, qisqartirilgan   513 KB
       ikkita statik, qisqartirilgan  252 KB   <- shu

   Qanday yasalgani: `assets/fonts/README.md`.

⚠️ `assets/`, `static/` EMAS: shrift FAQAT server tomonida ishlatiladi.
   `static/` da tursa `collectstatic` uni yig'ib, nginx uni bekorga
   ommaviy tarqatardi (saytning o'zi Inter'ni Google Fonts'dan oladi va
   u yerda ancha kichik `woff2` beriladi).
"""

from __future__ import annotations

import functools
import io
from pathlib import Path

from django.conf import settings
from PIL import Image, ImageDraw, ImageFont

SHRIFTLAR = Path(settings.BASE_DIR) / "assets" / "fonts"
SHRIFT_FAYLLARI = {
    False: SHRIFTLAR / "Inter-Regular.ttf",
    True: SHRIFTLAR / "Inter-Bold.ttf",
}

# ⚠️ 1200×630 — Open Graph standarti (1.91:1). Boshqa nisbat berilsa
#    platformalar rasmni O'ZI kesadi va matn chetidan qirqilib qoladi.
KENGLIK = 1200
BALANDLIK = 630

CHEKKA = 72
CHIZIQ_KENGLIGI = 14  # chapdagi brend chizig'i

# Ranglar `tailwind/input.css` dagi YORUG' mavzu tokenlaridan olingan.
# ⚠️ Qorong'i variant YO'Q va kerak ham emas: rasm foydalanuvchining
#    mavzusida emas, Telegram/Facebook lentasida ko'rinadi.
FON = "#ffffff"
BRAND = "#2563eb"  # --p-blue-600
MATN = "#0f172a"  # --p-slate-900
SUST = "#64748b"  # --p-slate-500
CHIP_FON = "#f1f5f9"  # --p-slate-100

SARLAVHA_OLCHAMI = 60
SARLAVHA_QATOR_BALANDLIGI = 74
MAKS_QATOR = 4


@functools.lru_cache(maxsize=8)
def shrift(olcham: int, *, qalin: bool = False) -> ImageFont.FreeTypeFont:
    """Shriftni yuklaydi va KESHLAYDI.

    ⚠️ Kesh muhim: shrift faylini har rasm uchun qaytadan o'qish
       vazifani bekorga sekinlashtiradi. Kalit `(olcham, qalin)` —
       Pillow'da o'lcham shrift OBYEKTIGA bog'langan, ya'ni har
       o'lcham uchun alohida nusxa kerak.
    """
    return ImageFont.truetype(SHRIFT_FAYLLARI[qalin], olcham)


def _sozni_boklash(soz: str, f: ImageFont.FreeTypeFont, kenglik: int) -> list[str]:
    """Qatorga sig'maydigan bitta so'zni majburan bo'laklarga ajratadi.

    ⚠️ Busiz uzun so'z (masalan URL yoki tasodifiy belgilar qatori)
       cheksiz siklga yoki rasmdan chiqib ketishga olib kelardi.
    """
    bolaklar: list[str] = []
    joriy = ""
    for belgi in soz:
        if not joriy or f.getlength(joriy + belgi) <= kenglik:
            joriy += belgi
        else:
            bolaklar.append(joriy)
            joriy = belgi
    if joriy:
        bolaklar.append(joriy)
    return bolaklar


def _uch_nuqta(qator: str, f: ImageFont.FreeTypeFont, kenglik: int) -> str:
    """Qatorni "…" sig'adigan qilib qisqartiradi."""
    qator = qator.rstrip()
    while qator and f.getlength(qator + "…") > kenglik:
        qator = qator[:-1].rstrip()
    return qator + "…"


def qatorlarga_bolish(
    matn: str, f: ImageFont.FreeTypeFont, kenglik: int, maks_qator: int
) -> list[str]:
    """Matnni qatorlarga bo'ladi — PIKSEL bo'yicha, belgi soni bo'yicha EMAS.

    ⚠️ Belgi soni bo'yicha o'rash (`textwrap`) bu loyihada NOTO'G'RI
       ishlaydi: kirillcha "Ипотека" va lotincha "Ipoteka" bir xil
       belgi sonida turli kenglik egallaydi, o'zbek lotinidagi "ʻ" esa
       deyarli kengliksiz. Natijada ba'zi sarlavha rasmdan chiqib
       ketardi, ba'zisi esa yarim bo'sh qolardi.
    """
    tokenlar: list[str] = []
    for soz in matn.split():
        if f.getlength(soz) <= kenglik:
            tokenlar.append(soz)
        else:
            tokenlar.extend(_sozni_boklash(soz, f, kenglik))

    qatorlar: list[str] = []
    joriy = ""
    kesildi = False

    for soz in tokenlar:
        nomzod = f"{joriy} {soz}".strip()
        if f.getlength(nomzod) <= kenglik:
            joriy = nomzod
            continue
        qatorlar.append(joriy)
        joriy = soz
        if len(qatorlar) >= maks_qator:
            kesildi = True
            break

    if joriy and not kesildi:
        qatorlar.append(joriy)

    if kesildi or len(qatorlar) > maks_qator:
        qatorlar = qatorlar[:maks_qator]
        qatorlar[-1] = _uch_nuqta(qatorlar[-1], f, kenglik)

    return qatorlar


def og_rasm_yasash(*, sarlavha: str, kategoriya: str = "") -> bytes:
    """Sarlavha va kategoriyadan OG kartasini (PNG baytlari) yasaydi.

    ⚠️ Funksiya BAZAGA BORMAYDI va Django modelini bilmaydi — faqat matn
       oladi. Shu sababli uni testda ham, boshqaruv buyrug'ida ham
       (standart rasm) bir xil chaqirish mumkin.
    """
    rasm = Image.new("RGB", (KENGLIK, BALANDLIK), FON)
    chiz = ImageDraw.Draw(rasm)

    # Chapdagi brend chizig'i — rasm "biznikiligi"ning eng arzon belgisi.
    chiz.rectangle([0, 0, CHIZIQ_KENGLIGI, BALANDLIK], fill=BRAND)

    chap = CHEKKA + CHIZIQ_KENGLIGI

    # --- Brend ------------------------------------------------------------
    brend_shrift = shrift(38, qalin=True)
    chiz.text((chap, CHEKKA), "Dard", font=brend_shrift, fill=MATN)
    chiz.text(
        (chap + brend_shrift.getlength("Dard"), CHEKKA),
        ".uz",
        font=brend_shrift,
        fill=BRAND,
    )
    chiz.text(
        (chap, CHEKKA + 52),
        "Nolima, yechim topamiz",
        font=shrift(22),
        fill=SUST,
    )

    # --- Sarlavha ---------------------------------------------------------
    sarlavha_shrift = shrift(SARLAVHA_OLCHAMI, qalin=True)
    matn_kengligi = KENGLIK - chap - CHEKKA
    qatorlar = qatorlarga_bolish(
        sarlavha.strip() or "Dard.uz", sarlavha_shrift, matn_kengligi, MAKS_QATOR
    )

    # ⚠️ Blok BREND bilan CHIP ORASIDA markazlashtiriladi, butun rasm
    #    bo'yicha EMAS.
    #
    #    Butun rasm bo'yicha markazlashtirilganda kategoriyasiz kartada
    #    (standart rasm) pastda sezilarli bo'sh joy qolardi: matn
    #    yuqoriga tortilib, karta muvozanatsiz ko'rinardi. Jonli
    #    ko'rilgan farq.
    yuqori = CHEKKA + 100  # brend + shior tugagan joy
    pastki = BALANDLIK - CHEKKA - (72 if kategoriya else 0)

    blok = len(qatorlar) * SARLAVHA_QATOR_BALANDLIGI
    y = yuqori + max(0, (pastki - yuqori - blok) // 2)

    for qator in qatorlar:
        chiz.text((chap, y), qator, font=sarlavha_shrift, fill=MATN)
        y += SARLAVHA_QATOR_BALANDLIGI

    # --- Kategoriya chipi -------------------------------------------------
    if kategoriya:
        chip_shrift = shrift(26, qalin=True)
        chip_matn = kategoriya.strip()
        chip_w = chip_shrift.getlength(chip_matn)
        chip_y = BALANDLIK - CHEKKA - 52
        chiz.rounded_rectangle(
            [chap, chip_y, chap + chip_w + 48, chip_y + 52],
            radius=26,
            fill=CHIP_FON,
        )
        chiz.text((chap + 24, chip_y + 11), chip_matn, font=chip_shrift, fill=SUST)

    xotira = io.BytesIO()
    # `optimize=True` — PNG hajmini ~15% kamaytiradi; rasm bir marta
    # yasalib, ko'p marta uzatiladi, ya'ni almashuv foydali.
    rasm.save(xotira, format="PNG", optimize=True)
    return xotira.getvalue()
