"""Ovoz berish ko'rinishlari uchun umumiy yordamchilar (D1-T8).

Har ilova o'z modelining endpoint'iga EGA (`complaints`, `solutions`) —
shunda `common` hech qaysi ilovani import qilmaydi. Bu yerda esa faqat
ikkalasida bir xil bo'lgan qism turadi: ruxsat, qiymatni o'qish va
qaytish manzili.
"""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from apps.common.models import VoteValue

# POST tanasidagi maydon nomi. Maketdagi tugmalar `name="qiymat"` bilan
# yuboriladi — shunda JavaScript'siz ham ishlaydi.
QIYMAT_MAYDONI = "qiymat"


def htmx_sorovimi(request: HttpRequest) -> bool:
    """HTMX yuborganmi yoki oddiy forma POST'imi.

    Bir xil endpoint ikkalasiga ham javob beradi: HTMX'ga HTML parcha,
    brauzerga esa qayta yo'naltirish. Aks holda JavaScript o'chirilganda
    (yoki yuklanmaganda) ovoz berish umuman ishlamasdi.
    """
    return request.headers.get("HX-Request") == "true"


def ovoz_ruxsati(request: HttpRequest) -> HttpResponse | None:
    """Ovoz berishga ruxsat bormi. Bor bo'lsa `None`, aks holda javob.

    ⚠️ `@login_required` ATAYLAB ISHLATILMAYDI: u 302 bilan login
       sahifasiga yo'naltiradi, HTMX esa yo'naltirishni kuzatib borib
       BUTUN LOGIN SAHIFASINI ovoz blokining o'rniga qo'yardi.
       Kirmagan foydalanuvchiga 401 kerak (D1-T8 qabul mezoni).

    ⚠️ Mehmon xulqi — hal qilingan qaror (C varianti, maket bilan bir xil):
       ovoz TO'XTATILADI va tugma yonida login taklifi chiqadi. Server
       tomoni shu qarorning ikkinchi qatlami: brauzerdan chetlab o'tib
       so'rov yuborilsa ham ovoz hisoblanmaydi.
    """
    user = request.user
    if not user.is_authenticated:
        if htmx_sorovimi(request):
            # Qisqa matn — HTMX standart holatda 2xx bo'lmagan javobni
            # DOM'ga qo'ymaydi, shuning uchun bu asosan tashqi mijozlar
            # va nosozliklarni tekshirish uchun.
            return HttpResponse(
                "Ovoz berish uchun kiring.",
                status=401,
                content_type="text/plain; charset=utf-8",
            )
        return redirect(f"{reverse('login')}?next={request.path}")

    if not user.can_write:
        # Bloklangan foydalanuvchi o'qiy oladi, lekin ta'sir o'tkaza olmaydi
        # (D0-T2: `is_banned` != `is_active`).
        return HttpResponseForbidden("Hisobingiz cheklangan.")

    return None


def ovoz_qiymatini_oqish(request: HttpRequest) -> int:
    """POST tanasidan `+1` / `-1` ni oladi.

    ⚠️ Yo'nalish URL'da EMAS, TANADA — bu D1-T8 tavsifidan farq qiladi.
       Sabab: maketdagi ovoz bloki BITTA `vote_url` bilan ishlaydi va
       ikkala tugma bitta formaga tegishli. Yo'nalishni tugmaning
       `value` atributida yuborish JavaScript'siz ham ishlaydigan yagona
       yo'l (`<button name="qiymat" value="1">`). URL'ga ko'chirilsa
       har tugmaga alohida forma kerak bo'lardi.

    Noto'g'ri qiymatda `ValueError` — chaqiruvchi 400 qaytaradi.
    """
    xom = request.POST.get(QIYMAT_MAYDONI, "")
    try:
        qiymat = int(xom)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Ovoz qiymati raqam emas: {xom!r}") from exc

    if qiymat not in (VoteValue.UP, VoteValue.DOWN):
        raise ValueError(f"Ovoz qiymati faqat +1 yoki -1: {qiymat!r}")
    return qiymat


def ovozdan_keyingi_manzil(request: HttpRequest, zaxira: str) -> str:
    """JavaScript'siz POST'dan keyin qayerga qaytarish.

    ⚠️ `HTTP_REFERER` ga KO'R-KO'RONA ishonilmaydi — u foydalanuvchi
       boshqara oladigan sarlavha. Tekshiruvsiz ishlatilsa ochiq
       yo'naltirish (open redirect) bo'lardi: hujumchi qurbonni o'z
       saytiga olib chiqib, u yerda soxta login ko'rsatishi mumkin.
    """
    referer = request.META.get("HTTP_REFERER", "")
    if referer and url_has_allowed_host_and_scheme(
        referer, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return referer
    return zaxira
