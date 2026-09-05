"""Kanonik manzil va mutlaq havolalar (D4-T4).

⚠️ NEGA SHABLON TEGI, KONTEKST-PROTSESSOR EMAS
   Kontekst-protsessor HAR renderga qiymat qo'shadi — jumladan HTMX
   qismlariga va D1-T14 da qotirilgan so'rov-sanog'i testlariga. Bu yerda
   esa qiymat faqat `<head>` da, ya'ni to'liq sahifada kerak.
"""

from __future__ import annotations

from urllib.parse import urlencode

from django import template
from django.http import HttpRequest

register = template.Library()

# ⚠️⚠️ KANONIKDA QOLADIGAN YAGONA PARAMETR.
#
#    Kanonik manzil "bu sahifaning HAQIQIY manzili qaysi?" degan savolga
#    javob beradi. Qoida: manzil MAZMUNNI belgilasa qoladi, faqat
#    KO'RINISHNI o'zgartirsa tashlanadi.
#
#      · `category`  -> QOLADI. "Moliya bo'yicha dardlar" — o'z mazmuni
#        bo'lgan alohida sahifa va u qidiruv tizimida alohida turishi
#        kerak.
#      · `sort`      -> tashlanadi (bir xil kontent, boshqa tartib).
#      · `generation`-> tashlanadi. Qolsa 8 kategoriya × 3 avlod = 24 ta
#        yupqa (thin) sahifa hosil bo'lardi va ular bir-biri bilan
#        raqobatlashardi.
#      · `after`, `sahifa` -> tashlanadi (sahifalash).
#      · `q`         -> qidiruv sahifasi `noindex` (u kanonik umuman
#        bermaydi).
#
# ⚠️⚠️ BU QOIDANING NARXI JONLI LOYIHADA KO'RILGAN: kanonik faqat
#    `request.path` dan qurilsa, `/?category=moliya` sahifasi bosh
#    sahifaga kanoniklashardi va Google Search Console uni "Duplicate,
#    not canonical" deb rad etardi — ya'ni kategoriya sahifalari
#    indeksdan butunlay tushib qolardi.
KANONIK_PARAMETRLAR = ("category",)


def _kanonik_yol(request: HttpRequest) -> str:
    """`/yo'l/?category=moliya` — tartibi barqaror."""
    saqlanadi = [
        (kalit, qiymat)
        for kalit in KANONIK_PARAMETRLAR
        # ⚠️ `getlist` EMAS, `get`: takroriy parametr (`?category=a&category=b`)
        #    faqat bitta qiymatga aylanadi. Aks holda bir xil sahifaga ikki
        #    xil kanonik chiqishi mumkin edi.
        if (qiymat := (request.GET.get(kalit) or "").strip())
    ]
    sorov = urlencode(saqlanadi)
    return f"{request.path}?{sorov}" if sorov else request.path


@register.simple_tag(takes_context=True)
def kanonik(context: dict) -> str:
    """Sahifaning kanonik MUTLAQ manzili.

    ⚠️ Mutlaq bo'lishi SHART: `<link rel="canonical">` da nisbiy manzil
       rasman ruxsat etilgan, lekin ijtimoiy tarmoq skanerlari va ba'zi
       vositalar uni noto'g'ri o'qiydi.

    ⚠️ Sxema `request` dan olinadi. Prod'da nginx ortida bu `https`
       bo'lishi uchun `SECURE_PROXY_SSL_HEADER` sozlangan
       (`config/settings/prod.py`) — usiz kanonik `http://` bo'lib
       chiqardi va Google uni boshqa sahifa deb hisoblardi.
    """
    request: HttpRequest = context["request"]
    return request.build_absolute_uri(_kanonik_yol(request))


@register.simple_tag(takes_context=True)
def mutlaq(context: dict, yol: str) -> str:
    """Nisbiy yo'lni mutlaq manzilga aylantiradi.

    `og:image` va `og:url` da nisbiy manzil ISHLAMAYDI: Telegram va
    Facebook skanerlari uni umuman yuklamaydi va karta rasmsiz qoladi.
    """
    request: HttpRequest = context["request"]
    return request.build_absolute_uri(yol)
