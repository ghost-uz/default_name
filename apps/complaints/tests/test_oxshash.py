"""O'xshash muammolar — trigram/FTS + kesh (D4-T7)."""

from __future__ import annotations

from unittest import mock

import pytest
from django.core.cache import cache
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.common.matn import mavzuli_sozlar
from apps.common.models import ModerationStatus
from apps.complaints.factories import ComplaintFactory
from apps.complaints.selectors import oxshash_muammolar
from apps.complaints.tasks import (
    oxshash_ish_kaliti,
    oxshash_kesh_kaliti,
    oxshash_muammolarni_hisoblash,
)

pytestmark = pytest.mark.django_db


# ===========================================================================
# 1. Mavzuli so'zlar
# ===========================================================================
def test_TOXTASH_sozlar_tashlanadi():
    """⚠️ O'lchangan farq (`apps/common/matn.py`): to'xtash so'zlarsiz
    to'g'ri natija birinchi o'ringa chiqdi va shovqingacha bo'lgan
    masofa 20 barobar oshdi."""
    sozlar = mavzuli_sozlar("Ipoteka to'lovini kechiktirsam nima bo'ladi?")

    assert "ipoteka" in sozlar
    assert "nima" not in sozlar
    assert "boladi" not in sozlar


def test_QISQA_sozlar_tashlanadi():
    """Uch harfli o'zbekcha so'zlarning ko'pi qo'shimcha yoki
    bog'lovchi va ular mavzuni belgilamaydi."""
    assert "uy" not in mavzuli_sozlar("Uy va ish haqida savol")


def test_tinish_belgisi_sozga_YOPISHMAYDI():
    """⚠️ `qidiruv_sozlari()` bilan bir xil tokenizatsiya: "qiladi,"
    emas, "qiladi"."""
    assert "qoshnilar" in mavzuli_sozlar("Qo'shnilar shovqin qiladi, tinim yo'q")


def test_mavzuli_sozlar_bosh_matnda_yiqilmaydi():
    assert mavzuli_sozlar("") == []
    assert mavzuli_sozlar("nima bo'ladi") == []


# ===========================================================================
# 2. Vazifa
# ===========================================================================
def test_vazifa_oxshashlarni_topadi_va_KESHLAYDI():
    manba = ComplaintFactory(title="Ipoteka to'lovini kechiktirsam nima bo'ladi")
    mos = ComplaintFactory(title="Ipoteka olmoqchiman lekin bank rad etdi")
    ComplaintFactory(title="Velosiped sotib olmoqchiman qaysi model yaxshi")

    soni = oxshash_muammolarni_hisoblash(manba.pk)

    assert soni == 1
    assert cache.get(oxshash_kesh_kaliti(manba.pk)) == [mos.pk]


def test_OZINI_royxatga_QOSHMAYDI():
    manba = ComplaintFactory(title="Ipoteka olish qiyinmi")
    ComplaintFactory(title="Ipoteka olish haqida savol")

    oxshash_muammolarni_hisoblash(manba.pk)

    assert manba.pk not in cache.get(oxshash_kesh_kaliti(manba.pk))


def test_YASHIRILGAN_post_natijaga_TUSHMAYDI():
    manba = ComplaintFactory(title="Ipoteka olish qiyinmi")
    ComplaintFactory(
        title="Ipoteka haqida yashirin savol",
        moderation_status=ModerationStatus.HIDDEN,
    )

    assert oxshash_muammolarni_hisoblash(manba.pk) == 0


def test_MAVZULI_SOZI_YOQ_sarlavha_bosh_royxat_KESHLAYDI():
    """⚠️ Bo'sh ro'yxat ham keshlanadi: aks holda "Nima qilay?" kabi
    sarlavha har ochilishida yangi vazifa yaratardi."""
    manba = ComplaintFactory(title="Nima qilay?")

    assert oxshash_muammolarni_hisoblash(manba.pk) == 0
    assert cache.get(oxshash_kesh_kaliti(manba.pk)) == []


def test_YOQ_muammo_bilan_yiqilmaydi():
    assert oxshash_muammolarni_hisoblash(999999) == 0


def test_chegaradan_past_oxshashlik_TASHLANADI(settings):
    manba = ComplaintFactory(title="Ipoteka olish qiyinmi")
    ComplaintFactory(title="Ipoteka haqida savol")

    settings.OXSHASH_CHEGARASI = 0.99
    cache.clear()

    assert oxshash_muammolarni_hisoblash(manba.pk) == 0


def test_soni_CHEGARALANGAN(settings):
    manba = ComplaintFactory(title="Ipoteka olish qiyinmi")
    for i in range(6):
        ComplaintFactory(title=f"Ipoteka masalasi {i} haqida savol")

    settings.OXSHASH_SONI = 3
    cache.clear()

    assert oxshash_muammolarni_hisoblash(manba.pk) == 3


# ===========================================================================
# 3. Selektor — kesh va ko'rinish
# ===========================================================================
def test_SOVUQ_keshda_BOSH_royxat_qaytadi():
    """⚠️⚠️ D4-T7 qabul mezoni: "hisoblash fon vazifasida, so'rov
    paytida emas". Kesh bo'sh bo'lsa selektor HECH NARSA hisoblamaydi —
    vazifani navbatga qo'yadi va bo'sh ro'yxat qaytaradi."""
    manba = ComplaintFactory(title="Ipoteka olish qiyinmi")
    ComplaintFactory(title="Ipoteka haqida savol")

    with mock.patch(
        "apps.complaints.tasks.oxshash_muammolarni_hisoblash.delay"
    ) as vazifa:
        natija = oxshash_muammolar(manba)

    assert natija == []
    vazifa.assert_called_once_with(manba.pk)


def test_ILIQ_keshda_royxat_qaytadi():
    manba = ComplaintFactory(title="Ipoteka to'lovini kechiktirsam nima bo'ladi")
    mos = ComplaintFactory(title="Ipoteka olmoqchiman lekin bank rad etdi")

    oxshash_muammolarni_hisoblash(manba.pk)

    assert [m.pk for m in oxshash_muammolar(manba)] == [mos.pk]


def test_VAZIFA_BIR_MARTA_navbatga_tushadi():
    """⚠️ Sovuq keshdagi mashhur postga bir vaqtda kelgan 100 ta so'rov
    100 ta bir xil vazifani navbatga qo'yardi (thundering herd).
    `cache.add()` faqat birinchisini o'tkazadi."""
    manba = ComplaintFactory(title="Ipoteka olish qiyinmi")

    with mock.patch(
        "apps.complaints.tasks.oxshash_muammolarni_hisoblash.delay"
    ) as vazifa:
        for _ in range(5):
            oxshash_muammolar(manba)

    assert vazifa.call_count == 1
    assert cache.get(oxshash_ish_kaliti(manba.pk)) is not None


def test_KESHLANGANDAN_KEYIN_yashirilgan_post_KORSATILMAYDI():
    """⚠️⚠️ Keshda `pk` lar turadi va ular HAR so'rovda `visible()` dan
    qayta o'tadi.

    Sarlavhani keshda saqlash bitta so'rovni tejardi, lekin post
    keshlangandan KEYIN yashirilsa, yon panel unga havola berishda
    davom etardi — ko'rinish invarianti (D2-T3) kesh muddati (24 soat)
    davomida buzilardi.
    """
    manba = ComplaintFactory(title="Ipoteka to'lovini kechiktirsam nima bo'ladi")
    mos = ComplaintFactory(title="Ipoteka olmoqchiman lekin bank rad etdi")

    oxshash_muammolarni_hisoblash(manba.pk)
    assert oxshash_muammolar(manba)  # kesh iliq

    mos.moderation_status = ModerationStatus.HIDDEN
    mos.save(update_fields=["moderation_status"])

    assert oxshash_muammolar(manba) == []


def test_KESHLANGANDAN_KEYIN_ochirilgan_post_ham_KORSATILMAYDI():
    manba = ComplaintFactory(title="Ipoteka to'lovini kechiktirsam nima bo'ladi")
    mos = ComplaintFactory(title="Ipoteka olmoqchiman lekin bank rad etdi")

    oxshash_muammolarni_hisoblash(manba.pk)
    mos.delete()

    assert oxshash_muammolar(manba) == []


def test_TARTIB_keshdan_keladi():
    """⚠️ `pk__in` tartibni saqlamaydi — eng o'xshashi uchinchi o'ringa
    tushib qolardi."""
    manba = ComplaintFactory(title="Ipoteka olish qiyinmi")
    a = ComplaintFactory(title="Birinchi post")
    b = ComplaintFactory(title="Ikkinchi post")

    cache.set(oxshash_kesh_kaliti(manba.pk), [b.pk, a.pk], 60)

    assert [m.pk for m in oxshash_muammolar(manba)] == [b.pk, a.pk]


def test_ILIQ_kesh_BITTA_qoshimcha_sorov():
    """⚠️ Yon panel uchun bitta indeksli `pk__in` so'rovi — hisoblash
    emas, faqat ko'rinish tekshiruvi bilan olish."""
    manba = ComplaintFactory(title="Ipoteka olish qiyinmi")
    mos = ComplaintFactory(title="Ipoteka haqida savol")
    cache.set(oxshash_kesh_kaliti(manba.pk), [mos.pk], 60)

    with CaptureQueriesContext(connection) as sorovlar:
        oxshash_muammolar(manba)

    assert len(sorovlar) == 1


# ===========================================================================
# 4. Sahifada ko'rinishi
# ===========================================================================
def test_sahifada_blok_KORINADI(anonymous_client):
    manba = ComplaintFactory(title="Ipoteka to'lovini kechiktirsam nima bo'ladi")
    mos = ComplaintFactory(title="Ipoteka olmoqchiman lekin bank rad etdi")
    oxshash_muammolarni_hisoblash(manba.pk)

    sahifa = anonymous_client.get(manba.get_absolute_url()).content.decode()

    assert "O'xshash dardlar" in sahifa
    assert mos.title in sahifa


def test_BOSH_royxatda_blok_UMUMAN_chizilmaydi(anonymous_client):
    """⚠️ Bo'sh ro'yxatli quti chalkash bo'lardi (D3-T3 dagi reyting
    bloki bilan bir xil qaror)."""
    manba = ComplaintFactory(title="Ipoteka olish qiyinmi")
    cache.set(oxshash_kesh_kaliti(manba.pk), [], 60)

    sahifa = anonymous_client.get(manba.get_absolute_url()).content.decode()

    assert "xshash dardlar" not in sahifa
