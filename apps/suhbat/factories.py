"""Suhbat fabrikalari (test ma'lumoti)."""

from __future__ import annotations

import factory

from .models import KontaktSorovi, SorovHolati, Suhbat, Xabar


class KontaktSoroviFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = KontaktSorovi

    solution = factory.SubFactory("apps.solutions.factories.SolutionFactory")
    soragan = factory.LazyAttribute(lambda o: o.solution.complaint.author)


class SuhbatFactory(factory.django.DjangoModelFactory):
    """⚠️ So'rov QABUL QILINGAN holatda yaratiladi — suhbat faqat
    shunda mavjud bo'ladi (`services.sorovga_javob`)."""

    class Meta:
        model = Suhbat

    sorov = factory.SubFactory(KontaktSoroviFactory, holat=SorovHolati.QABUL_QILINDI)


class XabarFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Xabar

    suhbat = factory.SubFactory(SuhbatFactory)
    author = factory.LazyAttribute(lambda o: o.suhbat.sorov.soragan)
    content = factory.Sequence(lambda n: f"Test xabari {n}")
