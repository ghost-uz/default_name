"""Lenta filtrlari uchun shablon teglari (D1-T7)."""

from __future__ import annotations

from django import template
from django.http import HttpRequest

register = template.Library()


@register.simple_tag(takes_context=True)
def lenta_url(context: dict, **kwargs: object) -> str:
    """Joriy so'rov parametrlarini SAQLAB, faqat berilganini almashtiradi.

    Ishlatilishi:

        <a href="{% lenta_url sort='new' %}">Yangi</a>
        <a href="{% lenta_url generation='' %}">Hammasi</a>

    ⚠️ NEGA QO'LDA `?sort=new` YOZILMAYDI
       Maketdagi `href="?sort=new"` boshqa BARCHA parametrlarni yo'q
       qiladi: foydalanuvchi "Moliya + Gen Z" ni tanlab, keyin "Yangi"
       tabini bosса — filtrlari jimgina tushib ketardi. Bu eng bezovta
       qiladigan turdagi xato: hech narsa buzilmaydi, shunchaki
       foydalanuvchi ishini qaytadan qiladi.

    Bo'sh qiymat (`''` yoki `None`) parametrni O'CHIRADI — "Hammasi"
    tugmasi shu bilan yasaladi, alohida shart kerak emas.
    """
    request: HttpRequest = context["request"]
    params = request.GET.copy()

    for kalit, qiymat in kwargs.items():
        if qiymat in (None, ""):
            params.pop(kalit, None)
        else:
            params[kalit] = str(qiymat)

    # Filtr o'zgarganda sahifalash boshidan boshlansin (D1-T12).
    params.pop("after", None)

    sorov = params.urlencode()
    return f"{request.path}?{sorov}" if sorov else request.path
