"""Yechim modeli va qabul qilish oqimi (D1-T4)."""

from __future__ import annotations

import pytest
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.common.models import VoteValue
from apps.common.voting import cast_vote
from apps.complaints.factories import ComplaintFactory
from apps.complaints.models import ComplaintStatus
from apps.solutions.factories import SolutionFactory
from apps.solutions.models import Solution, SolutionVote
from apps.solutions.services import accept_solution, unaccept_solution

pytestmark = pytest.mark.django_db


# ===========================================================================
# "Bitta muammoda bitta qabul qilingan yechim" — baza kafolati
# ===========================================================================
def test_ikkita_qabul_qilingan_yechim_BOLA_OLMAYDI():
    """Qabul mezoni: `UniqueConstraint(complaint, condition=is_accepted)`."""
    muammo = ComplaintFactory()
    birinchi = SolutionFactory(complaint=muammo)
    ikkinchi = SolutionFactory(complaint=muammo)

    accept_solution(solution=birinchi, by_user=muammo.author)

    ikkinchi.is_accepted = True
    ikkinchi.accepted_at = timezone.now()
    with pytest.raises(IntegrityError), transaction.atomic():
        ikkinchi.save(update_fields=["is_accepted", "accepted_at"])


def test_yangi_yechim_qabul_qilinsa_eskisi_AVTOMATIK_bekor_boladi():
    """Qabul mezoni: "yangi yechim qabul qilinsa eskisi avtomatik bekor bo'ladi".

    ⚠️ Xizmat ichida TARTIB muhim: avval eskisi bekor qilinadi, keyin
       yangisi belgilanadi. Teskari tartibda noyoblik indeksi darhol
       buzilardi.
    """
    muammo = ComplaintFactory()
    eski = SolutionFactory(complaint=muammo)
    yangi = SolutionFactory(complaint=muammo)

    accept_solution(solution=eski, by_user=muammo.author)
    accept_solution(solution=yangi, by_user=muammo.author)

    eski.refresh_from_db()
    yangi.refresh_from_db()
    assert eski.is_accepted is False
    assert eski.accepted_at is None
    assert yangi.is_accepted is True


def test_ochirilgan_qabul_qilingan_yechim_ORNINI_BOSHATADI():
    """⚠️ `deleted_at__isnull=True` sharti bo'lmasa yuz beradigan tuzoq.

    Moderator qabul qilingan yechimni o'chiradi -> qator bazada qoladi
    va "qabul qilingan" o'rnini band qilib turadi -> muallif boshqasini
    qabul qilmoqchi bo'lganda sababi ko'rinmaydigan xato chiqadi,
    ekranda esa hech qanday qabul qilingan yechim yo'q.
    """
    muammo = ComplaintFactory()
    birinchi = SolutionFactory(complaint=muammo)
    ikkinchi = SolutionFactory(complaint=muammo)

    accept_solution(solution=birinchi, by_user=muammo.author)
    birinchi.delete()  # yumshoq — is_accepted HAMON True

    accept_solution(solution=ikkinchi, by_user=muammo.author)  # xato bermasin

    ikkinchi.refresh_from_db()
    assert ikkinchi.is_accepted is True


def test_qabul_sanasi_bayroq_bilan_BIRGA_boladi():
    """`CheckConstraint` — "qachon yechildi?" metrikasini saqlaydi (D7-T8)."""
    yechim = SolutionFactory()
    yechim.is_accepted = True  # accepted_at berilmagan
    with pytest.raises(IntegrityError), transaction.atomic():
        yechim.save(update_fields=["is_accepted"])


# ===========================================================================
# Qabul qilish oqimi
# ===========================================================================
def test_qabul_qilish_muammo_holatini_yangilaydi():
    muammo = ComplaintFactory()
    yechim = SolutionFactory(complaint=muammo)

    accept_solution(solution=yechim, by_user=muammo.author)

    muammo.refresh_from_db()
    assert muammo.status == ComplaintStatus.SOLVED
    assert muammo.is_solved is True
    assert muammo.accepted_solution_id == yechim.pk


def test_begona_odam_qabul_QILA_OLMAYDI(other_user):
    """⚠️ Ruxsat tekshiruvi XIZMATDA — bu funksiya keyinchalik bot va
    admin buyruqlaridan ham chaqiriladi (D5-T2).
    """
    muammo = ComplaintFactory()
    yechim = SolutionFactory(complaint=muammo)

    with pytest.raises(PermissionDenied):
        accept_solution(solution=yechim, by_user=other_user)

    yechim.refresh_from_db()
    assert yechim.is_accepted is False


def test_qabulni_bekor_qilish_muammoni_OCHIQ_qiladi():
    """Qaytarib bo'lmaydigan tugma foydalanuvchini bosmaslikka undaydi."""
    muammo = ComplaintFactory()
    yechim = SolutionFactory(complaint=muammo)
    accept_solution(solution=yechim, by_user=muammo.author)

    unaccept_solution(solution=yechim, by_user=muammo.author)

    muammo.refresh_from_db()
    yechim.refresh_from_db()
    assert muammo.status == ComplaintStatus.OPEN
    assert muammo.accepted_solution_id is None
    assert yechim.is_accepted is False
    assert yechim.accepted_at is None


# ===========================================================================
# Model xulqi
# ===========================================================================
def test_muallif_ochirilsa_yechim_QOLADI():
    yechim = SolutionFactory()
    yechim.author.delete()

    yechim.refresh_from_db()
    assert yechim.author is None
    assert Solution.objects.filter(pk=yechim.pk).exists()


def test_ekspert_javobi_belgisi(expert):
    oddiy = SolutionFactory()
    ekspertniki = SolutionFactory(author=expert)

    assert oddiy.is_by_expert is False
    assert ekspertniki.is_by_expert is True


def test_ovoz_berish_yechimga_ham_ISHLAYDI(user):
    """`SolutionVote` bir xil umumiy mantiqqa ulangan (Q1)."""
    yechim = SolutionFactory()
    natija = cast_vote(
        target=yechim,
        vote_model=SolutionVote,
        target_field="solution",
        user=user,
        value=VoteValue.UP,
    )
    assert natija.score == 1
    yechim.refresh_from_db()
    assert yechim.score_cached == 1
