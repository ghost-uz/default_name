"""Yechim fabrikalari (test ma'lumoti)."""

from __future__ import annotations

import factory

from apps.accounts.factories import ExpertFactory, TelegramUserFactory
from apps.complaints.factories import ComplaintFactory

from .models import Solution, SolutionVote


class SolutionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Solution

    complaint = factory.SubFactory(ComplaintFactory)
    author = factory.SubFactory(TelegramUserFactory)
    content = factory.Sequence(
        lambda n: f"{n}-yechim: men ham shu holatdan o'tganman, menga bu yordam berdi."
    )

    # ⚠️ `is_accepted` fabrikada BERILMAYDI. Uni qo'lda `True` qilish
    #    `accepted_at` bilan birga bo'lishi shart (CheckConstraint) va
    #    muammoning `status`/`accepted_solution` maydonlari yangilanmay
    #    qoladi — ya'ni testda haqiqatda bo'lmaydigan holat quriladi.
    #    Qabul qilingan yechim kerak bo'lsa:
    #        accept_solution(solution=s, by_user=s.complaint.author)


class ExpertSolutionFactory(SolutionFactory):
    """Ekspert yozgan yechim — maketdagi "Ekspert javob berdi" nishoni uchun."""

    author = factory.SubFactory(ExpertFactory)


class SolutionVoteFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SolutionVote

    user = factory.SubFactory(TelegramUserFactory)
    solution = factory.SubFactory(SolutionFactory)
    value = 1
