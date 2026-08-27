"""Ovoz berish (D1-T5).

Bu fayl `apps.common.voting` ni `ComplaintVote` orqali sinaydi — mantiq
umumiy, shuning uchun `SolutionVote` uchun faqat "u ham ulangan" degan
qisqa test bor (apps/solutions/tests/test_solution.py).
"""

from __future__ import annotations

import pytest
from django.db import IntegrityError, transaction

from apps.common.models import VoteValue
from apps.common.voting import cast_vote, user_votes_for
from apps.complaints.factories import ComplaintFactory, ComplaintVoteFactory
from apps.complaints.models import Complaint, ComplaintVote

pytestmark = pytest.mark.django_db


def _ovoz(muammo, user, value):
    return cast_vote(
        target=muammo,
        vote_model=ComplaintVote,
        target_field="complaint",
        user=user,
        value=value,
    )


# ===========================================================================
# Baza darajasidagi kafolat
# ===========================================================================
def test_bir_foydalanuvchi_ikki_marta_ovoz_bera_OLMAYDI(user):
    """Qabul mezoni: DB darajasida unique cheklov (user + target).

    ⚠️ Bu tekshiruv KODDA emas, BAZADA bo'lishi shart: ikki bir vaqtli
       so'rov `exists()` da ikkalasi ham "yo'q" deb ko'radi.
    """
    muammo = ComplaintFactory()
    ComplaintVoteFactory(user=user, complaint=muammo, value=VoteValue.UP)

    with pytest.raises(IntegrityError), transaction.atomic():
        ComplaintVote.objects.create(user=user, complaint=muammo, value=VoteValue.UP)


def test_ikki_xil_foydalanuvchi_bir_postga_ovoz_BERA_OLADI(user, other_user):
    muammo = ComplaintFactory()
    _ovoz(muammo, user, VoteValue.UP)
    _ovoz(muammo, other_user, VoteValue.UP)

    assert ComplaintVote.objects.filter(complaint=muammo).count() == 2


# ===========================================================================
# Uch xil holat
# ===========================================================================
def test_yangi_ovoz_sanoqchini_oshiradi(user):
    muammo = ComplaintFactory()
    natija = _ovoz(muammo, user, VoteValue.UP)

    assert natija.created is True
    assert natija.value == VoteValue.UP
    assert (natija.upvotes, natija.downvotes, natija.score) == (1, 0, 1)


def test_bir_xil_tugma_ikkinchi_marta_ovozni_BEKOR_qiladi(user):
    """ "Qaytarib olish" imkoni — rejadagi `upvotes` butun sonida yo'q edi."""
    muammo = ComplaintFactory()
    _ovoz(muammo, user, VoteValue.UP)
    natija = _ovoz(muammo, user, VoteValue.UP)

    assert natija.removed is True
    assert natija.value is None
    assert (natija.upvotes, natija.score) == (0, 0)
    assert ComplaintVote.objects.filter(complaint=muammo).count() == 0


def test_qarama_qarshi_ovozga_almashish_IKKI_BIRLIK_farq_beradi(user):
    """⚠️ D1-T5 ning eng oson unutiladigan qabul mezoni.

    `+1` dan `-1` ga o'tish — bitta ovozning YO'NALISHI o'zgarishi,
    ya'ni ball 2 birlikka tushadi. Sodda amalga oshirishda (eskisini
    o'chirib, yangisini qo'shish) oraliqda ball noto'g'ri bo'lib qoladi
    va parallel so'rov o'sha oraliqni ko'rishi mumkin.
    """
    muammo = ComplaintFactory()
    oldingi = _ovoz(muammo, user, VoteValue.UP).score

    natija = _ovoz(muammo, user, VoteValue.DOWN)

    assert natija.switched is True
    assert natija.score == oldingi - 2
    assert (natija.upvotes, natija.downvotes) == (0, 1)
    # Ovoz qatori YANGISI emas — o'shanisi yangilangan
    assert ComplaintVote.objects.filter(complaint=muammo).count() == 1


def test_notogri_qiymat_rad_etiladi(user):
    """`0` yoki `+5` kabi qiymatlar sanoqchini jimgina buzardi."""
    muammo = ComplaintFactory()
    with pytest.raises(ValueError, match="faqat"):
        _ovoz(muammo, user, 5)


# ===========================================================================
# Sanoqchi haqiqatga mos
# ===========================================================================
def test_sanoqchi_ovoz_jadvalidan_QAYTA_HISOBLANADI(user_factory):
    """⚠️ Sanoqchi — KESH. Uni har doim ovoz jadvalidan tiklash mumkin
    bo'lishi kerak (D7-T3 tiklash mashqi shuni talab qiladi).
    """
    muammo = ComplaintFactory()
    for i in range(7):
        _ovoz(muammo, user_factory(), VoteValue.UP if i % 3 else VoteValue.DOWN)

    muammo.refresh_from_db()
    haqiqiy_up = ComplaintVote.objects.filter(
        complaint=muammo, value=VoteValue.UP
    ).count()
    haqiqiy_down = ComplaintVote.objects.filter(
        complaint=muammo, value=VoteValue.DOWN
    ).count()

    assert muammo.upvotes_cached == haqiqiy_up
    assert muammo.downvotes_cached == haqiqiy_down
    assert muammo.score_cached == haqiqiy_up - haqiqiy_down


def test_score_cached_ga_YOZIB_BOLMAYDI(user):
    """⚠️ `score_cached` — GENERATED ustun, uni baza hisoblaydi.

    Bu cheklov emas, kafolat: sanoqchilar bilan ball hech qachon
    farq qila olmaydi.
    """
    muammo = ComplaintFactory()
    _ovoz(muammo, user, VoteValue.UP)

    muammo.score_cached = 999
    muammo.save()

    muammo.refresh_from_db()
    assert muammo.score_cached == 1


def test_ochirilgan_postda_ham_sanoqchi_YANGILANADI(user):
    """⚠️ Xizmat `_base_manager` ishlatadi, `objects` emas.

    `objects` yumshoq o'chirilganlarni filtrlaydi — u holda `update()`
    hech nimani o'zgartirmasdi va XATO HAM BERMASDI: sanoqchi jimgina
    haqiqatdan uzilardi.
    """
    muammo = ComplaintFactory()
    muammo.delete()  # yumshoq

    natija = _ovoz(muammo, user, VoteValue.UP)
    assert natija.score == 1


# ===========================================================================
# Lentadagi "men ovoz berganmanmi?" (D1-T14 — N+1)
# ===========================================================================
def test_user_votes_for_BITTA_sorovda_ishlaydi(user, django_assert_num_queries):
    """⚠️ Har karta uchun alohida so'rash 20 ta kartada 20 ta so'rov."""
    muammolar = [ComplaintFactory() for _ in range(5)]
    _ovoz(muammolar[0], user, VoteValue.UP)
    _ovoz(muammolar[3], user, VoteValue.DOWN)

    with django_assert_num_queries(1):
        xarita = user_votes_for(
            vote_model=ComplaintVote,
            target_field="complaint",
            user=user,
            targets=muammolar,
        )

    assert xarita == {muammolar[0].pk: 1, muammolar[3].pk: -1}


def test_kirmagan_foydalanuvchi_uchun_SOROV_KETMAYDI(django_assert_num_queries):
    """Mehmon lentani ko'p ochadi — u yerda ortiqcha so'rov qilmaymiz."""
    from django.contrib.auth.models import AnonymousUser

    muammolar = [ComplaintFactory()]
    with django_assert_num_queries(0):
        xarita = user_votes_for(
            vote_model=ComplaintVote,
            target_field="complaint",
            user=AnonymousUser(),
            targets=muammolar,
        )
    assert xarita == {}


def test_foydalanuvchi_ochirilsa_ovozlari_ham_KETADI(user):
    """`CASCADE` — ovoz shaxsga bog'liq, kontent emas."""
    muammo = ComplaintFactory()
    _ovoz(muammo, user, VoteValue.UP)

    user.delete()

    assert ComplaintVote.objects.filter(complaint=muammo).count() == 0
    # ⚠️ Sanoqchi AVTOMATIK tuzalmaydi — u D2-T8 da qayta hisoblanadi.
    #    Test shu haqiqatni qotiradi, "to'g'ri" deb ko'rsatmaydi.
    assert Complaint.objects.get(pk=muammo.pk).upvotes_cached == 1
