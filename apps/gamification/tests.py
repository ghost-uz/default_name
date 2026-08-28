"""Karma jurnali (D1-T10 uchun minimal qism, D3-T1 ni tayyorlaydi)."""

from __future__ import annotations

import pytest

from apps.gamification.models import KarmaEvent, KarmaReason
from apps.gamification.services import karma_yoz, karmani_qayta_hisoblash

pytestmark = pytest.mark.django_db


def test_ochirilgan_hisob_uchun_hech_nima_yozilmaydi():
    """⚠️ `user=None` — muallif hisobini o'chirgan (D2-T8).

    Chaqiruvchida har safar `if user is not None` yozilmasin: xizmat
    o'zi jim o'tkazib yuboradi. Aks holda bitta unutilgan tekshiruv
    `AttributeError` bilan butun qabul qilish oqimini yiqitardi.
    """
    assert karma_yoz(user=None, reason=KarmaReason.SOLUTION_ACCEPTED) is None
    assert KarmaEvent.objects.count() == 0


def test_ball_CHAQIRUVCHIDAN_olinmaydi(user):
    """⚠️ Qoida bitta joyda — `KARMA_QIYMATLARI` da.

    Aks holda u ikki joyda bo'lardi va bir kuni faqat bittasi
    o'zgartirilardi (masalan +15 dan +10 ga).
    """
    hodisa = karma_yoz(user=user, reason=KarmaReason.SOLUTION_ACCEPTED)
    assert hodisa is not None
    assert hodisa.points == 15


def test_kesh_jurnal_bilan_mos(user):
    karma_yoz(user=user, reason=KarmaReason.SOLUTION_ACCEPTED)
    karma_yoz(user=user, reason=KarmaReason.SOLUTION_ACCEPTED)
    karma_yoz(user=user, reason=KarmaReason.SOLUTION_UNACCEPTED)

    user.refresh_from_db()
    assert user.karma_cached == 15
    assert karmani_qayta_hisoblash(user=user) == 15


def test_hodisalar_YANGISIDAN_ESKISIGA_tartiblanadi(user):
    """Profil sahifasidagi "karma tarixi" uchun (D3-T4)."""
    birinchi = karma_yoz(user=user, reason=KarmaReason.SOLUTION_ACCEPTED)
    ikkinchi = karma_yoz(user=user, reason=KarmaReason.SOLUTION_UNACCEPTED)

    assert [h.pk for h in KarmaEvent.objects.all()] == [ikkinchi.pk, birinchi.pk]
