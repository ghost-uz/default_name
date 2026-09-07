"""VAQTINCHALIK: maket sahifalarini brauzerda ko'rish uchun.

⚠️ Bu fayl M1 oxirida O'CHIRILADI. Uning yagona vazifasi — D0-T6 dan keyin
   shablonlar haqiqatan render bo'lishini tekshirish va dizaynni jonli
   ko'rish imkonini berish.

NEGA URL NOMLARI HOZIR QOTIRILADI
   Shablonlarda `{% url 'feed' %}` yozilgan. Shu nomlar M1 da haqiqiy
   ilova `urls.py` fayllariga O'SHA NOMLAR BILAN ko'chadi:

       feed              -> apps/complaints/urls.py
       complaint_detail  -> apps/complaints/urls.py
       complaint_create  -> apps/complaints/urls.py
       category_list     -> apps/complaints/urls.py
       expert_list       -> apps/accounts/urls.py
       profile           -> apps/accounts/urls.py
       login             -> apps/accounts/urls.py
       landing           -> apps/common/urls.py

   Shunda shablonlarga qayta tegish SHART EMAS — faqat bu fayl o'chadi.

   Manzillarning o'zi ham yakuniy (o'zbekcha, SEO uchun — reja 5-bo'lim).
"""

from __future__ import annotations

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import path


def _sahifa(shablon: str, active_nav: str = "", **qoshimcha):
    """Kontekst bilan shablon render qiladigan oddiy ko'rinish yasaydi."""

    def korinish(request: HttpRequest, **kwargs) -> HttpResponse:
        kontekst = {
            "active_nav": active_nav,
            "maket_rejimi": True,
            **qoshimcha,
            **kwargs,
        }
        return render(request, shablon, kontekst)

    return korinish


def ekspertlar(request: HttpRequest) -> HttpResponse:
    """⚠️ EKSPERTLAR SAHIFASI — MAKET, LEKIN NARXI HAQIQIY (D6-T2).

    Sahifadagi PRO bloki maketdan qolgan, endi esa HAQIQIY sotib
    olish sahifasi bor (`/pro/`). Ikkita boshqa narx ko'rsatish —
    jonli sahifadagi yolg'on: odam bu yerda bir sonni ko'rib,
    to'lov sahifasida boshqasini ko'rardi.

    ⚠️ NEGA `_sahifa()` YORDAMCHISI ISHLATILMAYDI
       U kontekstni YOPILMA YARATILGANDA yig'adi, ya'ni sozlama
       URLconf import qilinganda BIR MARTA o'qilardi. Sozlama
       keyin o'zgarsa (test, `.env`) sahifa eski sonni ko'rsatib
       turardi — D6-T1 dagi teskari `OneToOne` keshi bilan bir xil
       turdagi JIM eskirish.
    """
    return render(
        request,
        "accounts/expert_list.html",
        {
            "active_nav": "experts",
            "maket_rejimi": True,
            "narx": settings.OBUNA_NARXI,
            "kun": settings.OBUNA_MUDDATI_KUN,
        },
    )


urlpatterns = [
    # ⚠️ BU YERDAN OLIB TASHLANGANLAR (haqiqiy ko'rinishga o'tdi):
    #      feed, complaint_create, complaint_detail -> apps/complaints/urls.py
    #      login, profile                           -> apps/accounts/urls.py
    #    Ikkalasi qolsa `reverse()` OXIRGISINI olardi va maket haqiqiy
    #    sahifani jimgina bosib qo'yardi.
    path("tanishuv/", _sahifa("pages/landing.html"), name="landing"),
    path(
        "kategoriyalar/",
        _sahifa("complaints/category_list.html", "categories"),
        name="category_list",
    ),
    path("ekspertlar/", ekspertlar, name="expert_list"),
]
