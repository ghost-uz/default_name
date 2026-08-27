"""Kategoriya modeli va boshlang'ich ma'lumot (D1-T2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from django.conf import settings
from django.core.management import call_command
from django.db import IntegrityError, transaction

from apps.complaints.factories import CategoryFactory
from apps.complaints.models import Category, CategoryIcon

FIXTURE = Path(settings.BASE_DIR) / "apps/complaints/fixtures/kategoriyalar.json"
IKONKA_SHABLONI = Path(settings.BASE_DIR) / "templates/components/_category_icon.html"


# ===========================================================================
# Boshlang'ich ma'lumot
# ===========================================================================
@pytest.mark.django_db
def test_fixture_loaddata_bilan_yuklanadi():
    """Qabul mezoni: `loaddata` bilan yuklanadi.

    Kategoriyalar kodda qattiq yozilmagani uchun yangi kategoriya qo'shish
    deploy talab qilmaydi — lekin bu faqat fixture haqiqatan yuklansa
    ma'noga ega.
    """
    call_command("loaddata", "kategoriyalar", verbosity=0)
    assert Category.objects.count() == 8


@pytest.mark.django_db
def test_fixture_ikki_marta_yuklansa_dublikat_YARATMAYDI():
    """`pk` fixture'da qotirilgan — takroriy `loaddata` yangilaydi, qo'shmaydi.

    Aks holda serverni qayta sozlashda kategoriyalar ikkilanib ketardi.
    """
    call_command("loaddata", "kategoriyalar", verbosity=0)
    call_command("loaddata", "kategoriyalar", verbosity=0)
    assert Category.objects.count() == 8


def test_fixture_ichidagi_slug_va_ikonkalar_haqiqiy():
    """Fixture bazaga tegmasdan ham tekshiriladi — xato tez ko'rinsin.

    ⚠️ Noto'g'ri `icon` kaliti xato BERMAYDI (`choices` faqat forma
       darajasida tekshiriladi) — u shunchaki bo'sh ikonka bo'lib
       chiqadi va buni hech kim sezmaydi.
    """
    yozuvlar = json.loads(FIXTURE.read_text(encoding="utf-8"))
    ruxsat = set(CategoryIcon.values)

    assert len(yozuvlar) == 8
    sluglar = [y["fields"]["slug"] for y in yozuvlar]
    assert len(set(sluglar)) == 8, "Fixture ichida takroriy slug bor"

    for y in yozuvlar:
        assert y["fields"]["icon"] in ruxsat, f"Noma'lum ikonka: {y['fields']['icon']}"
        assert y["fields"]["slug"].islower(), "Slug kichik harfda bo'lsin"

        # ⚠️ GOTCHA (vaqt yedi): `loaddata` `auto_now` MAYDONLARINI
        #    TO'LDIRMAYDI. Django `SQLInsertCompiler.pre_save_val()` da
        #    ochiq yozgan: xom (raw) yozuvda `pre_save()` o'tkazib
        #    yuboriladi. `created_at` ishlaydi (unda `default=` bor),
        #    `updated_at` esa NULL bo'lib qoladi va fixture
        #    `IntegrityError` bilan yiqiladi — sababi esa fixture'ga
        #    qaraganda umuman ko'rinmaydi.
        assert "updated_at" in y["fields"], (
            "`auto_now` maydoni fixture'da OSHKORA berilishi shart"
        )


def test_har_bir_ikonka_kaliti_shablonda_bor():
    """⚠️ GUARD: `CategoryIcon` ga kalit qo'shilib, shablonga unutilsa,
    kategoriya ikonkasiz (bo'sh kvadrat) chiqadi va sahifa baribir 200
    qaytaradi. Bunday jim buzilishni faqat shu test ushlaydi.
    """
    matn = IKONKA_SHABLONI.read_text(encoding="utf-8")
    yoq = [k for k in CategoryIcon.values if f'"{k}"' not in matn]
    assert yoq == [], f"Shablonda ikonka yo'q: {yoq}"


# ===========================================================================
# Model xulqi
# ===========================================================================
@pytest.mark.django_db
def test_slug_noyob():
    """Qabul mezoni: slug unique va URL'da ishlatiladi."""
    CategoryFactory(slug="moliya")
    with pytest.raises(IntegrityError), transaction.atomic():
        Category.objects.create(name="Boshqa moliya", slug="moliya")


@pytest.mark.django_db
def test_get_absolute_url_lentani_filtrlaydi():
    """Kategoriya havolasi lentaga so'rov parametri bilan olib boradi.

    Holat URL'da bo'lgani uchun foydalanuvchi uni ulasha oladi (D1-T7).
    """
    kategoriya = CategoryFactory(slug="moliya")
    assert kategoriya.get_absolute_url().endswith("?category=moliya")


@pytest.mark.django_db
def test_tartib_alifbo_boyicha_EMAS():
    """⚠️ Standart saralash `order` bo'yicha.

    Alifbo bo'yicha bo'lsa "Boshqa" ro'yxat boshiga chiqib qolardi —
    bu esa aynan eng kam kerakli kategoriya.
    """
    CategoryFactory(name="Boshqa", slug="boshqa", order=100)
    CategoryFactory(name="Karyera", slug="karyera", order=10)

    assert [k.name for k in Category.objects.all()] == ["Karyera", "Boshqa"]


@pytest.mark.django_db
def test_faolsiz_kategoriya_bazadan_ochmaydi():
    """`is_active=False` — tanlov ro'yxatidan olib tashlaydi, o'chirmaydi.

    Mavjud postlar ishlashda davom etishi kerak.
    """
    kategoriya = CategoryFactory(is_active=False)
    assert Category.objects.filter(pk=kategoriya.pk).exists()
    assert not Category.objects.filter(is_active=True, pk=kategoriya.pk).exists()
