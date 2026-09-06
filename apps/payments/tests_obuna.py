"""Obuna va PRO holati (D6-T1)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.accounts.factories import ExpertProfileFactory
from apps.accounts.models import TasdiqHolati
from apps.payments.models import ObunaHolati, ObunaRejasi, Subscription
from apps.payments.services import (
    avto_yangilashni_ozgartirish,
    muddati_otganlarni_belgilash,
    obunani_uzaytirish,
)
from apps.payments.tasks import obunalarni_tekshirish

pytestmark = pytest.mark.django_db


def _obuna(user, *, kun: int, holat: str = ObunaHolati.FAOL) -> Subscription:
    """Muddati aniq berilgan obuna (manfiy kun = o'tib ketgan)."""
    return Subscription.objects.create(
        user=user,
        plan=ObunaRejasi.PRO,
        status=holat,
        expires_at=timezone.now() + timedelta(days=kun),
    )


# ===========================================================================
# 1. ⚠️⚠️ Qabul mezoni: `user.has_pro` yagona haqiqat manbai
# ===========================================================================
def test_OBUNASIZ_odamda_has_pro_YOQ(user):
    """⚠️ Qator hech qachon to'lamagan odamda umuman yaratilmaydi."""
    assert Subscription.objects.filter(user=user).exists() is False
    assert user.has_pro is False


def test_FAOL_obunada_has_pro_BOR(user):
    _obuna(user, kun=10)

    assert user.has_pro is True


def test_MUDDATI_OTGAN_obunada_has_pro_YOQ(user):
    """⚠️⚠️ ENG MUHIM TEST: Celery vazifasi ISHLATILMAYDI.

    Task `nega` bo'limi: «muddati tugagan obuna qayerdadir ishlab
    qolaveradi». Agar `has_pro` faqat `status` ga qarasa, muddat
    tugagan payt bilan vazifaning keyingi ishga tushishi orasida
    obuna BEPUL uzayardi — bu yerda bir kunga.
    """
    obuna = _obuna(user, kun=-1)

    # Holat HAMON "faol" — vazifa hali ishlamagan.
    assert obuna.status == ObunaHolati.FAOL
    assert user.has_pro is False


def test_TUGAGAN_holatda_has_pro_YOQ(user):
    _obuna(user, kun=10, holat=ObunaHolati.TUGAGAN)

    assert user.has_pro is False


def test_has_pro_QOSHIMCHA_sorov_qilmaydi(user):
    """⚠️ `select_related("obuna")` bilan bitta so'rovda keladi."""
    _obuna(user, kun=10)
    User = type(user)

    yuklangan = User.objects.select_related("obuna").get(pk=user.pk)
    with CaptureQueriesContext(connection) as sorovlar:
        assert yuklangan.has_pro is True

    assert len(sorovlar) == 0


# ===========================================================================
# 2. ⚠️⚠️ PRO nishoni = malaka VA to'lov
# ===========================================================================
def test_TASDIQLANMAGAN_ekspert_TOLAGANDA_HAM_nishon_OLMAYDI():
    """⚠️⚠️ D3-T5 mezoni kuchda: pul bilan ishonch sotib olinmaydi."""
    ekspert = ExpertProfileFactory(verification_status=TasdiqHolati.KUTILMOQDA)
    _obuna(ekspert.user, kun=30)

    assert ekspert.user.has_pro is True
    assert ekspert.pro_faolmi is False


def test_TASDIQLANGAN_ekspert_TOLOVSIZ_nishon_OLMAYDI():
    ekspert = ExpertProfileFactory()

    assert ekspert.tasdiqlanganmi is True
    assert ekspert.user.has_pro is False
    assert ekspert.pro_faolmi is False


def test_MALAKA_VA_TOLOV_birga_bolganda_nishon_BOR():
    ekspert = ExpertProfileFactory()
    _obuna(ekspert.user, kun=30)

    assert ekspert.pro_faolmi is True


def test_pro_faolmi_MUDDAT_otganda_ochadi():
    ekspert = ExpertProfileFactory()
    obuna = _obuna(ekspert.user, kun=1)
    assert ekspert.pro_faolmi is True

    obuna.expires_at = timezone.now() - timedelta(seconds=1)
    obuna.save(update_fields=["expires_at"])
    ekspert.user.refresh_from_db()

    assert ekspert.pro_faolmi is False


# ===========================================================================
# 3. ⚠️ Uzaytirish qoidasi
# ===========================================================================
def test_YANGI_obuna_yaratiladi(user, settings):
    settings.OBUNA_MUDDATI_KUN = 30

    obuna = obunani_uzaytirish(user=user)

    assert obuna.status == ObunaHolati.FAOL
    assert 29 <= (obuna.expires_at - timezone.now()).days <= 30
    assert user.has_pro is True


def test_UZAYTIRISH_QOLGAN_MUDDAT_USTIGA_qoshiladi(user):
    """⚠️⚠️ Erta to'lagan mijoz kunlarini YO'QOTMAYDI.

    `now + 30` shakli qolgan 10 kunni o'chirib tashlardi va bu
    xato faqat mijoz sanaganda ko'rinardi.
    """
    _obuna(user, kun=10)

    obuna = obunani_uzaytirish(user=user, kunlar=30)

    assert 39 <= (obuna.expires_at - timezone.now()).days <= 40


def test_MUDDATI_OTGAN_obuna_HOZIRDAN_boshlanadi(user):
    """⚠️ Teskarisida uzoq tanaffusdan keyin qaytgan odam O'TMISHGA
    to'lagan bo'lardi."""
    _obuna(user, kun=-100)

    obuna = obunani_uzaytirish(user=user, kunlar=30)

    assert 29 <= (obuna.expires_at - timezone.now()).days <= 30
    assert user.has_pro is True


def test_MUDDATI_OTGAN_obuna_YANGI_DAVR_boshlaydi(user):
    eski = _obuna(user, kun=-100)
    eski_boshlanish = eski.started_at

    obuna = obunani_uzaytirish(user=user, kunlar=30)

    assert obuna.started_at > eski_boshlanish


def test_FAOL_obunani_uzaytirish_BOSHLANISHNI_ozgartirmaydi(user):
    eski = _obuna(user, kun=10)
    eski_boshlanish = eski.started_at

    obuna = obunani_uzaytirish(user=user, kunlar=30)

    assert obuna.started_at == eski_boshlanish


def test_TUGAGAN_obuna_uzaytirilganda_QAYTA_FAOLLASHADI(user):
    _obuna(user, kun=-5, holat=ObunaHolati.TUGAGAN)

    obuna = obunani_uzaytirish(user=user, kunlar=30)

    assert obuna.status == ObunaHolati.FAOL
    assert user.has_pro is True


def test_IKKI_MARTA_uzaytirish_IKKI_MARTA_qoshadi(user):
    """⚠️ D6-T2/T3 da idempotentlik TRANZAKSIYA darajasida bo'ladi;
    bu funksiya ataylab idempotent EMAS (u haqiqiy to'lovni bildiradi)."""
    obunani_uzaytirish(user=user, kunlar=30)
    obuna = obunani_uzaytirish(user=user, kunlar=30)

    assert 59 <= (obuna.expires_at - timezone.now()).days <= 60


# ===========================================================================
# 4. ⚠️⚠️ Bekor qilish darhol to'xtatmaydi
# ===========================================================================
def test_BEKOR_QILISH_obunani_DARHOL_TOXTATMAYDI(user):
    """⚠️⚠️ Odam to'lagan muddati uchun xizmatni oladi.

    Darhol to'xtatish «bekor qilish» tugmasini JAZOGA aylantirardi:
    oyning boshida bekor qilgan odam 29 kunini yo'qotardi.
    """
    _obuna(user, kun=25)

    obuna = avto_yangilashni_ozgartirish(user=user, yoqilsin=False)

    assert obuna.auto_renew is False
    assert obuna.status == ObunaHolati.FAOL
    assert user.has_pro is True


def test_AVTO_YANGILASHNI_qayta_yoqish(user):
    _obuna(user, kun=25)
    avto_yangilashni_ozgartirish(user=user, yoqilsin=False)

    obuna = avto_yangilashni_ozgartirish(user=user, yoqilsin=True)

    assert obuna.auto_renew is True


def test_OBUNASIZ_bekor_qilish_YIQILMAYDI(user):
    assert avto_yangilashni_ozgartirish(user=user, yoqilsin=False) is None


# ===========================================================================
# 5. ⚠️ Celery vazifasi — TOZALASH, himoya emas
# ===========================================================================
def test_VAZIFA_muddati_otganlarni_belgilaydi(user):
    obuna = _obuna(user, kun=-1)

    assert obunalarni_tekshirish() == "1 ta"

    obuna.refresh_from_db()
    assert obuna.status == ObunaHolati.TUGAGAN


def test_VAZIFA_FAOL_obunaga_TEGMAYDI(user):
    obuna = _obuna(user, kun=5)

    obunalarni_tekshirish()

    obuna.refresh_from_db()
    assert obuna.status == ObunaHolati.FAOL


def test_VAZIFA_IDEMPOTENT(user):
    _obuna(user, kun=-1)

    assert muddati_otganlarni_belgilash() == 1
    assert muddati_otganlarni_belgilash() == 0


def test_VAZIFA_ISHLAMASA_HAM_PRO_ochadi(user):
    """⚠️⚠️ Vazifa — TOZALASH, HAQIQAT MANBAI EMAS.

    Worker o'chib qolsa ham muddati tugagan obuna ishlab qolmasin.
    """
    _obuna(user, kun=-30)

    # Vazifa UMUMAN chaqirilmadi.
    assert user.has_pro is False


def test_VAZIFA_SOROV_SONI_obunalar_soniga_BOGLIQ_EMAS(user_factory):
    """⚠️ `update()` — har qator uchun `save()` qilinmaydi."""
    for _ in range(3):
        _obuna(user_factory(), kun=-1)
    with CaptureQueriesContext(connection) as uchta:
        muddati_otganlarni_belgilash()

    for _ in range(7):
        _obuna(user_factory(), kun=-1)
    with CaptureQueriesContext(connection) as ettita:
        muddati_otganlarni_belgilash()

    assert len(ettita) == len(uchta)


# ===========================================================================
# 6. Profil sahifasi
# ===========================================================================
def test_PROFILDA_PRO_nishoni_korinadi(client):
    ekspert = ExpertProfileFactory()
    _obuna(ekspert.user, kun=30)

    sahifa = client.get(
        reverse("profile", args=[ekspert.user.username])
    ).content.decode()

    assert ">PRO<" in sahifa


def test_PROFILDA_TOLOVSIZ_ekspertda_PRO_YOQ(client):
    ekspert = ExpertProfileFactory()

    sahifa = client.get(
        reverse("profile", args=[ekspert.user.username])
    ).content.decode()

    assert "Ekspert" in sahifa
    assert ">PRO<" not in sahifa


def test_PROFIL_obuna_uchun_QOSHIMCHA_sorov_qilmaydi(client):
    """⚠️ `pro_faolmi` endi `user.has_pro` ga qaraydi — ko'rinish
    `ekspert_profili__user__obuna` ni JOIN qilishi shart."""
    ekspert = ExpertProfileFactory()
    _obuna(ekspert.user, kun=30)
    manzil = reverse("profile", args=[ekspert.user.username])

    with CaptureQueriesContext(connection) as bilan:
        client.get(manzil)

    boshqa = ExpertProfileFactory()
    with CaptureQueriesContext(connection) as siz:
        client.get(reverse("profile", args=[boshqa.user.username]))

    assert len(bilan) == len(siz)
