"""Reklama fabrikalari (D6-T6) — faqat testlar uchun."""

from __future__ import annotations

import factory

from .models import AdSlot


class AdSlotFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AdSlot

    nom = factory.Sequence(lambda n: f"Reklama {n}")
    sarlavha = factory.Sequence(lambda n: f"Ipoteka bo'yicha maslahat {n}")
    matn = "Bank tanlashda bepul konsultatsiya."
    manzil = "https://example.uz/ipoteka"
    # ⚠️ Fabrikada `faolmi=True`: modelda standart `False` (saytga
    #    tasodifan chiqib ketmasin), testda esa ko'p hollarda FAOL
    #    reklama kerak. Nofaol holat ochiq beriladi.
    faolmi = True
