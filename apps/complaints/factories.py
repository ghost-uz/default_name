"""Muammo fabrikalari (test ma'lumoti).

Uslub `apps/accounts/factories.py` bilan bir xil: testda faqat SINALAYOTGAN
maydon ko'rinib tursin.
"""

from __future__ import annotations

import factory

from apps.accounts.factories import TelegramUserFactory

from .models import Category, CategoryIcon, Complaint, ComplaintVote, Generation


class CategoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Category
        # Bir xil slug bilan ikki marta chaqirilsa mavjudini qaytaradi —
        # ko'p muammo bitta kategoriyada bo'lishi odatiy holat.
        django_get_or_create = ("slug",)

    name = factory.Sequence(lambda n: f"Kategoriya {n}")
    slug = factory.Sequence(lambda n: f"kategoriya-{n}")
    icon = CategoryIcon.DOTS
    order = factory.Sequence(lambda n: n)


class ComplaintFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Complaint

    author = factory.SubFactory(TelegramUserFactory)
    category = factory.SubFactory(CategoryFactory)
    title = factory.Sequence(lambda n: f"Ipoteka olish qiyinmi {n}")
    description = factory.Sequence(
        lambda n: f"Bu {n}-sonli test muammosining batafsil tavsifi. " * 3
    )
    generation_tag = Generation.GENZ

    # ⚠️ `slug` ATAYLAB berilmaydi — uni `save()` avtomatik yasashi kerak
    #    va fabrika shu xulqni ham sinovdan o'tkazishi lozim. Fabrika
    #    slug'ni o'zi bersa, avtomatik yasash hech qachon ishlamay qolsa
    #    ham testlar yashil bo'lib turaverardi.


class AnonimComplaintFactory(ComplaintFactory):
    """Anonim muammo — D1-T6 invariantini tekshirish uchun."""

    is_anonymous = True


class ComplaintVoteFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ComplaintVote

    user = factory.SubFactory(TelegramUserFactory)
    complaint = factory.SubFactory(ComplaintFactory)
    value = 1

    # ⚠️ Bu fabrika sanoqchilarni YANGILAMAYDI — u faqat ovoz qatorini
    #    yaratadi. Sanoqchi bilan birga kerak bo'lsa
    #    `apps.common.voting.cast_vote()` ishlating. Ajratilgani ataylab:
    #    "sanoqchi haqiqatdan uzilib qolsa nima bo'ladi?" turkumidagi
    #    testlar aynan shu holatni qura olishi kerak.
