"""Muammo modeli (D1-T3)."""

from __future__ import annotations

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.models import ProtectedError

from apps.complaints.factories import CategoryFactory, ComplaintFactory
from apps.complaints.models import Complaint, ComplaintStatus

pytestmark = pytest.mark.django_db


# ===========================================================================
# Slug (SEO)
# ===========================================================================
def test_slug_avtomatik_yaratiladi():
    """Qabul mezoni: slug avtomatik yaratiladi va unique."""
    muammo = ComplaintFactory(title="Ipoteka olish juda qiyin")
    assert muammo.slug.startswith("ipoteka-olish-juda-qiyin-")


def test_bir_xil_sarlavhali_ikki_post_YARATILADI():
    """⚠️ Faqat sarlavhadan slug yasalsa, ikkinchi post yozib bo'lmasdi.

    Bu hayotda tez-tez uchraydi: "Ish topa olmayapman" degan sarlavha
    kuniga bir necha marta yoziladi.
    """
    a = ComplaintFactory(title="Ish topa olmayapman")
    b = ComplaintFactory(title="Ish topa olmayapman")
    assert a.slug != b.slug


def test_kirill_sarlavhada_ham_slug_BOSH_QOLMAYDI():
    """⚠️ `slugify` lotin bo'lmagan belgilarni tashlab yuboradi.

    To'liq kirillcha sarlavhada asos bo'sh qolardi va slug faqat
    `-a3f9c1d2` ko'rinishida bo'lardi (yoki bo'sh — 404 bilan tugaydi).
    Zaxira so'z shu holatni yopadi. To'liq yechim — D4-T2.
    """
    muammo = ComplaintFactory(title="Проблема с ипотекой")
    assert muammo.slug.startswith("dard-")
    assert len(muammo.slug) > len("dard-")


def test_slug_qayta_saqlashda_OZGARMAYDI():
    """URL barqaror bo'lishi kerak — sarlavha tahrirlansa ham.

    Aks holda ulashilgan havolalar va Google indeksidagi manzillar
    o'lik bo'lib qoladi.
    """
    muammo = ComplaintFactory(title="Birinchi sarlavha")
    eski = muammo.slug

    muammo.title = "Butunlay boshqa sarlavha"
    muammo.save()

    muammo.refresh_from_db()
    assert muammo.slug == eski


def test_yumshoq_ochirilgan_post_slugni_BOSHATADI():
    """⚠️ Bu aynan `apps/common/models.py` da ogohlantirilgan tuzoq.

    `unique=True` ishlatilganda o'chirilgan post slug'ni band qilib
    turardi va sabab tashqaridan ko'rinmasdi. Qisman indeks faqat tirik
    qatorlarni qamraydi.
    """
    kategoriya = CategoryFactory()
    birinchi = ComplaintFactory(category=kategoriya)
    band = birinchi.slug
    birinchi.delete()  # yumshoq

    ikkinchi = ComplaintFactory(category=kategoriya)
    ikkinchi.slug = band
    ikkinchi.save(update_fields=["slug"])  # xato bermasligi kerak

    assert Complaint.all_objects.filter(slug=band).count() == 2


def test_ikki_TIRIK_post_bir_xil_slug_OLA_OLMAYDI():
    """Qisman indeks tirik qatorlar orasida hamon noyoblikni saqlaydi."""
    birinchi = ComplaintFactory()
    ikkinchi = ComplaintFactory()

    ikkinchi.slug = birinchi.slug
    with pytest.raises(IntegrityError), transaction.atomic():
        ikkinchi.save(update_fields=["slug"])


def test_get_absolute_url_slug_ishlatadi():
    """Qabul mezoni: URL `/dard/<slug>/`."""
    muammo = ComplaintFactory()
    assert muammo.get_absolute_url() == f"/dard/{muammo.slug}/"


# ===========================================================================
# Indekslar
# ===========================================================================
def test_kategoriya_va_hot_score_indeksi_BAZADA_bor():
    """Qabul mezoni: `hot_score` va `(category, hot_score)` bo'yicha indeks.

    ⚠️ Model `Meta` da yozilgan indeks migratsiya qo'llanmasa bazada
       bo'lmaydi. Shuning uchun tekshiruv modelga emas, BAZAGA qaraydi.
    """
    with connection.cursor() as cursor:
        cheklovlar = connection.introspection.get_constraints(
            cursor, Complaint._meta.db_table
        )

    # ⚠️ Ustun nomi `category_id` — bazada FK maydoni shunday ataladi.
    indekslangan = [c["columns"] for c in cheklovlar.values() if c["index"]]
    assert ["category_id", "hot_score"] in indekslangan
    assert ["hot_score"] in indekslangan


# ===========================================================================
# Holat
# ===========================================================================
def test_is_solved_statusdan_hisoblanadi():
    """⚠️ `is_solved` maydon emas — ikkita haqiqat manbai bo'lmasin."""
    muammo = ComplaintFactory()
    assert muammo.is_solved is False

    muammo.status = ComplaintStatus.SOLVED
    assert muammo.is_solved is True
    assert muammo.is_closed is True


def test_yopilgan_muammo_yechilgan_EMAS():
    """ "Yopilgan" — muallif kutishni to'xtatdi, yechim topilgani emas.

    Ikkalasini bitta bayroq bilan ko'rsatish metrikalarni buzardi
    (D7-T8: "yechilish darajasi").
    """
    muammo = ComplaintFactory(status=ComplaintStatus.CLOSED)
    assert muammo.is_closed is True
    assert muammo.is_solved is False


# ===========================================================================
# Bog'lanishlar
# ===========================================================================
def test_kontenti_bor_kategoriyani_OCHIRIB_BOLMAYDI():
    """`on_delete=PROTECT` — kategoriya o'chsa postlar yetim qolardi."""
    kategoriya = CategoryFactory()
    ComplaintFactory(category=kategoriya)

    with pytest.raises(ProtectedError):
        kategoriya.delete()


def test_muallif_ochirilsa_post_QOLADI():
    """⚠️ `SET_NULL`, `CASCADE` emas.

    Bitta ketgan odam o'nlab foydali muhokamani o'zi bilan olib
    ketmasligi kerak (D2-T8).
    """
    muammo = ComplaintFactory()
    muammo.author.delete()

    muammo.refresh_from_db()
    assert muammo.author is None
    assert Complaint.objects.filter(pk=muammo.pk).exists()


def test_sanoqchilar_noldan_boshlanadi():
    """Yangi post uchun barcha keshlangan sanoqchilar 0."""
    muammo = ComplaintFactory()
    assert muammo.upvotes_cached == 0
    assert muammo.downvotes_cached == 0
    assert muammo.score_cached == 0
    assert muammo.solutions_count == 0
    assert muammo.views_count == 0
    assert muammo.hot_score == 0.0
