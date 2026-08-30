"""Oylik reyting (D3-T3)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from django.core.cache import cache
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.gamification.models import KarmaEvent, KarmaReason
from apps.gamification.services import (
    karma_yoz,
    oylik_reyting,
    oylik_reytingni_hisoblash,
    oylik_reytingni_yangilash,
    reyting_kaliti,
)

pytestmark = pytest.mark.django_db


def ball(user, *, marta: int = 1, sabab=KarmaReason.SOLUTION_ACCEPTED):
    """`marta` ta karma hodisasi yozadi (+15 har biri)."""
    for _ in range(marta):
        karma_yoz(user=user, reason=sabab)


# ===========================================================================
# ⭐⭐ QABUL MEZONI: reyting so'rovi KESHDAN keladi
# ===========================================================================
def test_QABUL_MEZONI_reyting_soravi_BAZAGA_BORMAYDI(user):
    """⭐⭐ Qabul mezoni: "reyting so'rovi keshdan keladi".

    Reyting lentaning yon panelida, ya'ni HAR SAHIFADA chaqiriladi —
    hisoblash u yerda bo'lsa, har ko'rish ikkita agregat so'rov qilardi.
    """
    ball(user)
    oylik_reytingni_yangilash()

    with CaptureQueriesContext(connection) as sorovlar:
        natija = oylik_reyting()

    assert len(natija) == 1
    assert len(sorovlar) == 0, (
        f"Reyting bazaga bordi: {[s['sql'][:80] for s in sorovlar]}"
    )


def test_LENTA_reyting_uchun_QOSHIMCHA_sorov_qilmaydi(user):
    """⚠️ Bu D1-T14 dagi so'rov byudjetining davomi: yon paneldagi blok
    lentaning so'rov sonini oshirmasligi kerak."""
    c = Client()
    c.force_login(user)
    c.get("/")  # sessiyani ilitamiz

    with CaptureQueriesContext(connection) as reytingsiz:
        c.get("/")

    ball(user)
    oylik_reytingni_yangilash()

    with CaptureQueriesContext(connection) as reyting_bilan:
        javob = c.get("/")

    assert len(reytingsiz) == len(reyting_bilan)
    assert "Oyning maslahatchilari" in javob.content.decode()


def test_KESH_BOSH_bolsa_HISOBLAB_YUBORMAYDI(user):
    """⚠️⚠️ "Yo'q bo'lsa hisoblab, keshga solamiz" jozibali ko'rinadi,
    lekin Redis qayta ishga tushgan paytda BARCHA so'rovlar bir vaqtda
    hisoblashga kirishardi (thundering herd) — kesh eng kerak bo'lgan
    payt eng katta yukni berardi."""
    ball(user)
    cache.clear()

    with CaptureQueriesContext(connection) as sorovlar:
        natija = oylik_reyting()

    assert natija == []
    assert len(sorovlar) == 0


def test_KESH_BOSH_bolsa_BLOK_umuman_chizilmaydi(user):
    """⚠️ Bo'sh ro'yxatli quti chalkash bo'lardi."""
    c = Client()
    c.force_login(user)
    cache.clear()

    matn = c.get("/").content.decode()

    assert "Oyning maslahatchilari" not in matn


# ===========================================================================
# Hisoblash
# ===========================================================================
def test_JORIY_OY_yigindisi_hisoblanadi(user, other_user):
    ball(user, marta=3)  # 45
    ball(other_user, marta=1)  # 15

    natija = oylik_reytingni_hisoblash()

    assert [q["username"] for q in natija] == [user.username, other_user.username]
    assert [q["karma"] for q in natija] == [45, 15]


def test_OTGAN_OY_hodisalari_HISOBLANMAYDI(user):
    """⚠️ Reyting `karma_cached` dan emas, `KarmaEvent` dan yig'iladi —
    aynan shuning uchun: kesh UMUMIY karmani saqlaydi, reyting esa
    SHU OYNIKINI so'raydi (D3-T1 ledgeri buni arzon qiladi)."""
    hodisa = karma_yoz(user=user, reason=KarmaReason.SOLUTION_ACCEPTED)
    KarmaEvent.objects.filter(pk=hodisa.pk).update(
        created_at=timezone.now() - timedelta(days=60)
    )

    assert oylik_reytingni_hisoblash() == []


def test_MANFIY_yoki_NOL_yigindi_royxatga_TUSHMAYDI(user):
    """Nol bilan "oyning maslahatchisi" bo'lish ma'nosiz."""
    ball(user, sabab=KarmaReason.SOLUTION_ACCEPTED)
    ball(user, sabab=KarmaReason.SOLUTION_UNACCEPTED)

    assert oylik_reytingni_hisoblash() == []


def test_OCHIRILGAN_hisob_royxatga_TUSHMAYDI(user, other_user):
    ball(user, marta=3)
    ball(other_user)
    user.ochirilgan_at = timezone.now()
    user.save(update_fields=["ochirilgan_at"])

    natija = oylik_reytingni_hisoblash()

    assert [q["username"] for q in natija] == [other_user.username]


def test_CHEKLANGAN_hisob_royxatga_TUSHMAYDI(staff, user, other_user):
    """⚠️⚠️ REYTING — TAVSIYA, TARIX EMAS.

    Nishon (D3-T2) va ekspert tasdig'i (D3-T5) cheklovda ham QOLADI,
    chunki ular odamning YOZUVI. Reyting esa platformaning "mana bu
    odamga qarang" degan gapi — cheklangan odamni ko'rsatish
    platformaning o'z qaroriga zid bo'lardi.
    """
    from apps.moderation.services import foydalanuvchini_cheklash

    ball(user, marta=3)
    ball(other_user)
    foydalanuvchini_cheklash(moderator=staff, user=user, sabab="Spam")

    natija = oylik_reytingni_hisoblash()

    assert [q["username"] for q in natija] == [other_user.username]
    # ...lekin karmasi va tarixi TEGILMAGAN:
    user.refresh_from_db()
    assert user.karma_cached == 45


def test_MUDDATI_OTGAN_cheklov_royxatni_TOSMAYDI(staff, user):
    """⚠️ `is_currently_banned` — muddat tekshiruvi bilan. Bayroqqa
    qarasak, muddati tugagan odam abadiy reytingdan tashqarida qolardi."""
    from apps.moderation.services import foydalanuvchini_cheklash

    ball(user, marta=3)
    foydalanuvchini_cheklash(moderator=staff, user=user, sabab="Spam")
    user.refresh_from_db()
    user.banned_until = timezone.now() - timedelta(minutes=1)
    user.save(update_fields=["banned_until"])

    assert [q["username"] for q in oylik_reytingni_hisoblash()] == [user.username]


def test_CHIQARILGANLAR_ornini_ZAXIRA_toldiradi(staff, user_factory):
    """⚠️ `soni * 3` zaxira: chiqarib tashlanganlar o'rniga ikkinchi
    so'rov yubormaymiz."""
    from apps.gamification.services import REYTING_SONI
    from apps.moderation.services import foydalanuvchini_cheklash

    # Eng yuqori REYTING_SONI ta odam cheklanadi.
    for i in range(REYTING_SONI):
        cheklangan = user_factory()
        ball(cheklangan, marta=10 + i)
        foydalanuvchini_cheklash(moderator=staff, user=cheklangan, sabab="Spam")

    kutilganlar = []
    for i in range(REYTING_SONI):
        toza = user_factory()
        ball(toza, marta=i + 1)
        kutilganlar.append(toza.username)

    natija = oylik_reytingni_hisoblash()

    assert len(natija) == REYTING_SONI
    assert {q["username"] for q in natija} == set(kutilganlar)


def test_ANONIM_ish_karmasi_ham_HISOBLANADI(user):
    """⚠️ Reyting karma yig'indisi, karma esa anonim yechimni ham
    sanaydi (D3-T1). Bu YANGI teshik OCHMAYDI: umumiy karma profilda
    allaqachon ommaviy."""
    from apps.solutions.factories import SolutionFactory

    yechim = SolutionFactory(author=user, is_anonymous=True)
    karma_yoz(user=user, reason=KarmaReason.SOLUTION_ACCEPTED, solution=yechim)

    assert len(oylik_reytingni_hisoblash()) == 1


# ===========================================================================
# Kesh kaliti
# ===========================================================================
def test_KESH_KALITI_OY_bilan(user):
    """⚠️⚠️ Oy kalitda bo'lmasa, oy almashganda eski reyting TTL
    tugagunicha ko'rinib turardi — "oyning maslahatchilari" o'tgan
    oyniki bo'lardi va hech qanday xato bermasdi."""
    avgust = date(2026, 8, 15)
    sentabr = date(2026, 9, 15)

    assert reyting_kaliti(avgust) != reyting_kaliti(sentabr)
    assert "2026-08" in reyting_kaliti(avgust)


def test_BOSHQA_OY_keshi_joriy_oyga_SIZMAYDI(user):
    ball(user)
    oylik_reytingni_yangilash()
    keyingi_oy = timezone.localdate().replace(day=1) + timedelta(days=32)

    assert oylik_reyting() != []
    assert oylik_reyting(keyingi_oy) == []


# ===========================================================================
# Celery vazifasi
# ===========================================================================
def test_VAZIFA_keshni_toldiradi(user):
    from apps.gamification.tasks import reytingni_yangilash

    ball(user, marta=2)
    cache.clear()
    assert oylik_reyting() == []

    assert reytingni_yangilash() == 1

    natija = oylik_reyting()
    assert [q["username"] for q in natija] == [user.username]
    assert natija[0]["karma"] == 30


def test_VAZIFA_qayta_ishga_tushsa_natija_BIR_XIL(user):
    """Idempotent: bir xil ma'lumotda bir xil natija."""
    from apps.gamification.tasks import reytingni_yangilash

    ball(user)
    reytingni_yangilash()
    birinchi = oylik_reyting()
    reytingni_yangilash()

    assert oylik_reyting() == birinchi


def test_reyting_LENTADA_korinadi(user, user_factory):
    from apps.gamification.tasks import reytingni_yangilash

    kuchli = user_factory(username="kuchlimaslahatchi", first_name="")
    ball(kuchli, marta=4)
    reytingni_yangilash()

    c = Client()
    c.force_login(user)
    matn = c.get("/").content.decode()

    assert "Oyning maslahatchilari" in matn
    assert "kuchlimaslahatchi" in matn
    assert reverse("profile", args=["kuchlimaslahatchi"]) in matn
