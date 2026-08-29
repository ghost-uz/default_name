"""Huquqiy sahifalar (D2-T10).

⚠️⚠️ MATNLAR YURIST TOMONIDAN KO'RILMAGAN.

   Qabul mezoni buni talab qiladi va u HALI BAJARILMAGAN. Bu yerdagi
   matnlar — yaxshi qoralama: ular platformaning haqiqiy xulqini aniq
   tasvirlaydi (nima yig'iladi, nima o'chadi, moderator nimani ko'radi),
   ya'ni yurist noldan boshlamaydi, tayyor matnni tekshiradi.

   ⚠️ Har bir sahifada shu haqda ochiq belgi turadi. U yuristning
      xulosasi kelgach OLIB TASHLANADI — bir joyda, bitta sozlama
      bilan (`HUQUQIY_KORILDI`).
"""

from __future__ import annotations

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import path


def _kontekst() -> dict:
    return {
        "versiya": settings.HUQUQIY_VERSIYA,
        "yosh": settings.YOSH_CHEGARASI,
        "aloqa_telefon": settings.ALOQA_TELEFONI,
        "aloqa_telegram": settings.ALOQA_TELEGRAM,
        "aloqa_email": settings.ALOQA_EMAIL,
        "korildi": settings.HUQUQIY_KORILDI,
    }


def shartlar(request: HttpRequest) -> HttpResponse:
    return render(request, "huquqiy/shartlar.html", _kontekst())


def maxfiylik(request: HttpRequest) -> HttpResponse:
    return render(request, "huquqiy/maxfiylik.html", _kontekst())


def qoidalar(request: HttpRequest) -> HttpResponse:
    return render(request, "huquqiy/qoidalar.html", _kontekst())


def boglanish(request: HttpRequest) -> HttpResponse:
    return render(request, "huquqiy/boglanish.html", _kontekst())


urlpatterns = [
    path("shartlar/", shartlar, name="shartlar"),
    path("maxfiylik/", maxfiylik, name="maxfiylik"),
    path("qoidalar/", qoidalar, name="qoidalar"),
    path("boglanish/", boglanish, name="boglanish"),
]
