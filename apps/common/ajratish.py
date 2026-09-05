"""Qidiruv natijasida mos so'zlarni ajratib ko'rsatish (D4-T3).

⚠️⚠️ NEGA POSTGRES'NING `SearchHeadline` I ISHLATILMADI

   Bu birinchi va tabiiy tanlov edi, lekin D4-T2 dan keyin u ishlamay
   qoldi. Sabab — indekslanadigan matn asl matndan SEZILARLI farq
   qiladi (`apps/common/matn.py`):

       "Ипотека олиш"  ->  "ipoteka olish"
       "Ko'chmas mulk" ->  "kochmas mulk"

   Ikkala yo'l ham buziq:

     · `SearchHeadline("qidiruv_sarlavha", ...)` — ekranda
       NORMALLASHTIRILGAN matn chiqadi: bosh harflarsiz, apostrofsiz,
       kirillcha post lotinchaga aylangan holda. Foydalanuvchi o'zi
       yozgan matnni tanimaydi.

     · `SearchHeadline("title", ...)` — so'rov normallashtirilgan, matn
       esa xom. Kirillcha postda HECH NARSA ajratilmaydi: natija
       ro'yxatda turadi, lekin nega mos kelgani ko'rinmaydi.

⚠️ SHUNING UCHUN AJRATISH SO'Z DARAJASIDA
   Asl matn so'zlarga bo'linadi, HAR BIR so'z AYNAN o'sha
   `qidiruv_uchun()` bilan normallashtiriladi va so'rov so'zlari bilan
   solishtiriladi. Ekranda esa ASL so'z ko'rsatiladi.

   Muhimi: ikkinchi normallashtirish implementatsiyasi PAYDO
   BO'LMAYDI. Qoidalar o'zgarsa (yangi harf, boshqa apostrof siyosati)
   ajratish avtomatik ergashadi.

⚠️ SO'Z BO'YICHA NORMALLASHTIRISH BUTUN MATNNIKI BILAN BIR XIL
   `qidiruv_uchun()` dagi yagona kontekstli qoidalar — `е` va `ц` —
   faqat OLDINGI belgiga qaraydi va u so'z ichida bir xil qoladi.
   So'z boshidagi holat ham mos: alohida so'zning boshi ham "boshi".
   Buni test qotiradi (`test_ajratish.py`).
"""

from __future__ import annotations

import re
from collections.abc import Collection, Iterator

from django.utils.html import escape
from django.utils.safestring import SafeString, mark_safe

from apps.common.matn import APOSTROF_VARIANTLARI, qidiruv_uchun

# ⚠️ APOSTROF SO'Z BELGISI HISOBLANADI, ajratuvchi EMAS.
#    Aks holda "ko'chmas" ikkita so'zga ("ko" va "chmas") bo'linardi va
#    ularning hech biri "kochmas" ga mos kelmasdi — ya'ni D4-T2 da
#    qilingan ish ekranda yo'qolardi.
SOZ_NAQSHI = re.compile(rf"[\w{re.escape(APOSTROF_VARIANTLARI)}']+")

# Parcha ko'rsatilganda mos so'zdan OLDIN qoldiriladigan ulush.
# Butunlay markazga qo'yish tabiiy ko'rinmaydi: o'qish chapdan boshlanadi
# va gapning boshi kontekst beradi.
OLDINGI_ULUSH = 3


def _sozlar(matn: str) -> Iterator[tuple[int, int, str]]:
    """`(boshi, oxiri, so'z)` — asl matndagi o'rni bilan."""
    for moslik in SOZ_NAQSHI.finditer(matn):
        yield moslik.start(), moslik.end(), moslik.group()


def qidiruv_sozlari(xom: str) -> frozenset[str]:
    """So'rovdagi so'zlarning normal shakllari.

    ⚠️ So'rov AVVAL normallashtiriladi, KEYIN so'zlarga bo'linadi —
       teskarisi emas. Sabab: `websearch` sintaksisi (qo'shtirnoq,
       `-istisno`) so'z bo'lmagan belgilar qoldiradi va ular so'zga
       yopishib qolardi (`"ipoteka` -> hech narsaga mos kelmaydi).
    """
    return frozenset(
        moslik.group() for moslik in SOZ_NAQSHI.finditer(qidiruv_uchun(xom))
    )


def _oyna_chegarasi(matn: str, birinchi_moslik: int, oyna: int) -> tuple[int, int]:
    """Parcha chegaralari — so'z o'rtasidan kesmasdan."""
    boshi = max(0, birinchi_moslik - oyna // OLDINGI_ULUSH)
    oxiri = min(len(matn), boshi + oyna)

    # ⚠️ So'z o'rtasidan kesish matnni "buzuq" qilib ko'rsatadi
    #    ("...oteka olish qiy..."), shuning uchun eng yaqin bo'shliqqa
    #    suriladi. Moslik chegaradan chiqib ketmasligi uchun surish
    #    faqat undan uzoqroqda bo'lsa qo'llanadi.
    if boshi > 0:
        keyingi_joy = matn.find(" ", boshi)
        if 0 <= keyingi_joy < birinchi_moslik:
            boshi = keyingi_joy + 1

    if oxiri < len(matn):
        oldingi_joy = matn.rfind(" ", boshi, oxiri)
        if oldingi_joy > birinchi_moslik:
            oxiri = oldingi_joy

    return boshi, oxiri


def ajratib_korsat(
    matn: str, sozlar: Collection[str], *, oyna: int | None = None
) -> SafeString:
    """Mos kelgan so'zlarni `<mark>` bilan o'raydi.

    `oyna` berilsa — matnning BIRINCHI moslik atrofidagi parchasi
    qaytariladi ("…" bilan). Tavsif 5000 belgigacha bo'lishi mumkin va
    uni to'liq ko'rsatish natijalar ro'yxatini o'qib bo'lmaydigan
    qiladi.

    ⚠️⚠️ XAVFSIZLIK: matn FOYDALANUVCHI YOZGAN. Har bir bo'lak
       `escape()` dan o'tadi va faqat `<mark>` teglari qo'lda
       qo'shiladi. Bu funksiya — XSS uchun eng jozibali joy: u
       ta'rifi bo'yicha HTML qaytaradi.
    """
    matn = matn or ""
    if not matn:
        return mark_safe("")  # bo'sh satr — ekranlanadigan narsa yo'q

    mosliklar = [
        (boshi, oxiri)
        for boshi, oxiri, soz in _sozlar(matn)
        if qidiruv_uchun(soz) in sozlar
    ]

    boshi, oxiri = 0, len(matn)
    if oyna is not None and len(matn) > oyna:
        boshi, oxiri = _oyna_chegarasi(matn, mosliklar[0][0] if mosliklar else 0, oyna)

    qismlar: list[str] = ["…"] if boshi > 0 else []
    kursor = boshi

    for moslik_boshi, moslik_oxiri in mosliklar:
        if moslik_boshi < kursor or moslik_oxiri > oxiri:
            continue
        qismlar.append(escape(matn[kursor:moslik_boshi]))
        qismlar.append(f"<mark>{escape(matn[moslik_boshi:moslik_oxiri])}</mark>")
        kursor = moslik_oxiri

    qismlar.append(escape(matn[kursor:oxiri]))
    if oxiri < len(matn):
        qismlar.append("…")

    # ⚠️ `mark_safe` XAVFSIZ: bo'laklarning HAMMASI `escape()` dan o'tgan
    #    va qo'lda qo'shilgan yagona teg — `<mark>`. U foydalanuvchi
    #    ma'lumotidan emas, shu funksiyadan keladi.
    return mark_safe("".join(qismlar))  # noqa: S308 — yuqoridagi izohga qarang
