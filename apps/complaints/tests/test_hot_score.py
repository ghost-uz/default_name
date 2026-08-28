"""Trending (`hot_score`) algoritmi va Celery vazifasi (D1-T11)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from django.utils import timezone

from apps.common.models import ModerationStatus, VoteValue
from apps.common.voting import cast_vote
from apps.complaints.factories import ComplaintFactory
from apps.complaints.models import Complaint, ComplaintVote
from apps.complaints.tasks import (
    HOT_OYNA_KUNLARI,
    hot_score_hisobla,
    hot_scorelarni_yangilash,
)

HOZIR = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)


# ===========================================================================
# Formula (qabul mezoni: "formula testda qoplangan")
# ===========================================================================
def test_YANGIROQ_post_yuqoriroq_turadi():
    """⚠️ TAVSIFDAGI FORMULA TESKARI ISHLARDI.

    Taskda `yosh_sekundlarda / 45000` yozilgan edi. Yosh vaqt o'tishi
    bilan O'SADI, ya'ni ESKI postlar kattaroq ball olardi va «Qaynoq»
    lenta teskariga aylanardi. Bu test aynan shuni qotiradi.
    """
    yangi = hot_score_hisobla(score=0, created_at=HOZIR)
    eski = hot_score_hisobla(score=0, created_at=HOZIR - timedelta(days=1))

    assert yangi > eski


def test_KOPROQ_ovoz_yuqoriroq_turadi():
    kam = hot_score_hisobla(score=1, created_at=HOZIR)
    kop = hot_score_hisobla(score=100, created_at=HOZIR)

    assert kop > kam


def test_ovoz_LOGARIFMIK_shkalada():
    """10 barobar ko'p ovoz = bir pog'ona yuqori (`log10`).

    Ma'nosi: 1000 ovozli post 100 ovozlidan 10 barobar emas, BIR
    POG'ONA yuqori turadi — shunda eski hitlar lentani mangu band
    qilib turmaydi.
    """
    a = hot_score_hisobla(score=10, created_at=HOZIR)
    b = hot_score_hisobla(score=100, created_at=HOZIR)
    c = hot_score_hisobla(score=1000, created_at=HOZIR)

    assert round(b - a, 5) == 1.0
    assert round(c - b, 5) == 1.0


def test_MANFIY_ovoz_pastga_tushiradi():
    """⚠️ Tavsifda `sign` VAQT hadida edi — u holda eski minusli post
    yangi minusli postdan YUQORI turardi. `sign` tartib hadida bo'lgani
    uchun vaqt hamma uchun bir yo'nalishda ishlaydi.
    """
    nol = hot_score_hisobla(score=0, created_at=HOZIR)
    manfiy = hot_score_hisobla(score=-10, created_at=HOZIR)

    assert manfiy < nol

    yangi_manfiy = hot_score_hisobla(score=-10, created_at=HOZIR)
    eski_manfiy = hot_score_hisobla(score=-10, created_at=HOZIR - timedelta(days=1))
    assert yangi_manfiy > eski_manfiy


def test_bir_va_nol_ovoz_bir_xil():
    """`log10(max(|0|,1)) == log10(1) == 0` — nol va bitta ovoz teng.

    Bu Reddit algoritmining ataylab qilingan xususiyati: birinchi ovoz
    postni "ko'tarmaydi", u faqat yangilikka tayanadi.
    """
    assert hot_score_hisobla(score=0, created_at=HOZIR) == hot_score_hisobla(
        score=1, created_at=HOZIR
    )


def test_vaqt_ogirligi_taxminan_12_yarim_soat():
    """45000 sekund ≈ 12.5 soat: shuncha yangiroq post 10 barobar
    ko'proq ovoz olgan postga teng keladi."""
    ovozli = hot_score_hisobla(score=10, created_at=HOZIR - timedelta(seconds=45000))
    yangi = hot_score_hisobla(score=1, created_at=HOZIR)

    assert round(ovozli, 4) == round(yangi, 4)


# ===========================================================================
# Celery vazifasi
# ===========================================================================
@pytest.mark.django_db
def test_vazifa_ballarni_yangilaydi(user):
    muammo = ComplaintFactory()
    assert muammo.hot_score == 0.0

    cast_vote(
        target=muammo,
        vote_model=ComplaintVote,
        target_field="complaint",
        user=user,
        value=VoteValue.UP,
    )
    hot_scorelarni_yangilash()

    muammo.refresh_from_db()
    assert muammo.hot_score != 0.0
    assert muammo.hot_score == hot_score_hisobla(
        score=muammo.score_cached, created_at=muammo.created_at
    )


@pytest.mark.django_db
def test_faqat_OYNA_ichidagilar_yangilanadi():
    """⚠️ 7 kundan eski postning balli allaqachon shu qadar past-ki, uni
    qayta hisoblash lentaga ta'sir qilmaydi. Butun bazani aylanish esa
    har 10 daqiqada takrorlanadi va serverni doimiy yuk ostida qoldiradi.
    """
    yangi = ComplaintFactory()
    eski = ComplaintFactory(
        created_at=timezone.now() - timedelta(days=HOT_OYNA_KUNLARI + 1)
    )

    hot_scorelarni_yangilash()

    yangi.refresh_from_db()
    eski.refresh_from_db()
    assert yangi.hot_score != 0.0
    assert eski.hot_score == 0.0


@pytest.mark.django_db
def test_ochirilgan_post_yangilanmaydi():
    muammo = ComplaintFactory()
    muammo.delete()

    hot_scorelarni_yangilash()

    muammo.refresh_from_db()
    assert muammo.hot_score == 0.0


@pytest.mark.django_db
def test_yashirilgan_post_HAM_yangilanadi():
    """⚠️ `visible()` ATAYLAB ishlatilmaydi: yashirilgan post keyinroq
    tiklanishi mumkin va o'shanda balli tayyor turishi kerak. Aks holda
    u lentaning eng pastida paydo bo'lardi."""
    muammo = ComplaintFactory(moderation_status=ModerationStatus.HIDDEN)

    hot_scorelarni_yangilash()

    muammo.refresh_from_db()
    assert muammo.hot_score != 0.0


@pytest.mark.django_db
def test_vazifa_BULK_UPDATE_ishlatadi(django_assert_max_num_queries):
    """Qabul mezoni: "bulk_update bilan yangilanadi".

    ⚠️ Har qatorni alohida `save()` qilish 60 post uchun 60 ta so'rov
       degani. `bulk_update` bo'laklab yangilaydi, ya'ni so'rov soni
       postlar soniga QARAB O'SMAYDI.

    Bu qabul mezonidagi "5 sekunddan kam" talabining o'lchanadigan
    shakli: vaqt mashinaga bog'liq, so'rov soni esa bog'liq emas.
    """
    ComplaintFactory.create_batch(60)

    # 1 ta o'qish (iterator) + 1 ta bulk_update = 2; zaxira bilan 6
    with django_assert_max_num_queries(6):
        yangilangan = hot_scorelarni_yangilash()

    assert yangilangan == 60


@pytest.mark.django_db
def test_ozgarmagan_ball_qayta_YOZILMAYDI():
    """Ikkinchi marta ishga tushirilganda hech nima o'zgarmasligi kerak."""
    ComplaintFactory.create_batch(3)

    assert hot_scorelarni_yangilash() == 3
    assert hot_scorelarni_yangilash() == 0


@pytest.mark.django_db
def test_lenta_QAYNOQ_saralashi_ball_boyicha(client, user_factory):
    """Vazifa natijasi haqiqiy lentada ko'rinadimi."""
    eski_ommabop = ComplaintFactory(
        created_at=timezone.now() - timedelta(days=3), title="Eski ommabop"
    )
    yangi_ovozsiz = ComplaintFactory(title="Yangi ovozsiz")

    for _ in range(5):
        cast_vote(
            target=eski_ommabop,
            vote_model=ComplaintVote,
            target_field="complaint",
            user=user_factory(),
            value=VoteValue.UP,
        )
    hot_scorelarni_yangilash()

    natija = list(client.get("/", {"sort": "hot"}).context["complaints"])
    # 3 kunlik farqni 5 ta ovoz qoplay olmaydi (log10(5) < 3*86400/45000)
    assert natija[0].pk == yangi_ovozsiz.pk
    assert Complaint.objects.get(pk=eski_ommabop.pk).hot_score < natija[0].hot_score
