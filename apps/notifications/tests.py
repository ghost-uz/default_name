"""Bildirishnomalar markazi (D5-T1)."""

from __future__ import annotations

import pytest
from django.core.cache import cache
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.complaints.factories import ComplaintFactory
from apps.notifications.models import BildirishnomaTuri, Notification
from apps.notifications.services import (
    bildirishnoma_yaratish,
    hammasini_oqilgan_deb_belgilash,
    kesh_kaliti,
    oqilmagan_soni,
)
from apps.solutions.services import accept_solution, yechim_yozish

pytestmark = pytest.mark.django_db

MANZIL = "/bildirishnomalar/"


# ===========================================================================
# 1. Yechim oqimiga ulanish (D1-T10)
# ===========================================================================
def test_yechim_yozilganda_MUALLIFGA_bildirishnoma(user, other_user):
    muammo = ComplaintFactory(author=user)

    yechim_yozish(complaint=muammo, author=other_user, content="Mana yechim matni.")

    b = Notification.objects.get(recipient=user)
    assert b.turi == BildirishnomaTuri.YANGI_YECHIM
    assert b.actor == other_user
    assert b.complaint == muammo


def test_OZ_muammosiga_javob_yozgan_odam_XABAR_OLMAYDI(user):
    """⚠️ Eng ko'p uchraydigan bezovtalik: o'z savoliga o'zi javob
    yozgan odam "sizga yechim keldi" degan xabar olardi."""
    muammo = ComplaintFactory(author=user)

    yechim_yozish(complaint=muammo, author=user, content="O'zim javob beraman.")

    assert not Notification.objects.filter(recipient=user).exists()


def test_yechim_QABUL_qilinganda_MUALLIFIGA_bildirishnoma(user, other_user):
    muammo = ComplaintFactory(author=user)
    yechim = yechim_yozish(
        complaint=muammo, author=other_user, content="Mana yechim matni."
    )
    Notification.objects.all().delete()

    accept_solution(solution=yechim, by_user=user)

    b = Notification.objects.get(recipient=other_user)
    assert b.turi == BildirishnomaTuri.YECHIM_QABUL
    assert b.actor == user


def test_OCHIRILGAN_HISOB_egasiga_bildirishnoma_yozilmaydi(other_user):
    """⚠️ Hisobini o'chirgan foydalanuvchining posti qoladi, lekin
    `author` `None` bo'ladi (D2-T8)."""
    muammo = ComplaintFactory(author=None)

    yechim_yozish(complaint=muammo, author=other_user, content="Mana yechim matni.")

    assert Notification.objects.count() == 0


# ===========================================================================
# 2. ⚠️⚠️ Anonimlik — D1-T6 invariantining TO'RTINCHI joyi
# ===========================================================================
def test_ANONIM_yechimda_AKTYOR_YOZILMAYDI(user, other_user):
    """⚠️⚠️ "Yozib qo'yib, shablonda yashirish" bu loyihada uch marta
    muammo bo'lgan. Bu yerda qoida qattiqroq: yozuvning O'ZI bazada
    qolmaydi — aks holda uni admin, eksport (D2-T8) yoki kelajakdagi
    API oshkor qilardi."""
    muammo = ComplaintFactory(author=user)

    yechim_yozish(
        complaint=muammo,
        author=other_user,
        content="Anonim javob matni.",
        is_anonymous=True,
    )

    b = Notification.objects.get(recipient=user)
    assert b.actor is None
    assert b.matn == "Kimdir muammoingizga yechim yozdi"


def test_ANONIM_muammoda_qabul_aktyori_ham_YOZILMAYDI(user, other_user):
    muammo = ComplaintFactory(author=user, is_anonymous=True)
    yechim = yechim_yozish(
        complaint=muammo, author=other_user, content="Mana yechim matni."
    )
    Notification.objects.all().delete()

    accept_solution(solution=yechim, by_user=user)

    b = Notification.objects.get(recipient=other_user)
    assert b.actor is None


def test_ANONIM_muallif_nomi_SAHIFADA_ham_chiqmaydi(user, other_user):
    muammo = ComplaintFactory(author=user)
    yechim_yozish(
        complaint=muammo,
        author=other_user,
        content="Anonim javob matni.",
        is_anonymous=True,
    )

    c = Client()
    c.force_login(user)
    sahifa = c.get(MANZIL).content.decode()

    assert other_user.username not in sahifa
    assert "Kimdir" in sahifa


# ===========================================================================
# 3. O'qilmaganlar sanog'i — kesh (qabul mezoni)
# ===========================================================================
def test_sanoq_KESHLANADI(user):
    """⚠️ Sarlavha HAR sahifada chiziladi — keshsiz bu har ko'rishda
    bitta qo'shimcha `COUNT` degani bo'lardi."""
    ComplaintFactory(author=user)
    bildirishnoma_yaratish(recipient=user, turi=BildirishnomaTuri.YANGI_YECHIM)

    assert oqilmagan_soni(user) == 1

    with CaptureQueriesContext(connection) as sorovlar:
        assert oqilmagan_soni(user) == 1

    assert len(sorovlar) == 0, "ikkinchi chaqiruv keshdan kelishi kerak"


def test_YANGI_bildirishnoma_KESHNI_tozalaydi(user):
    bildirishnoma_yaratish(recipient=user, turi=BildirishnomaTuri.YANGI_YECHIM)
    assert oqilmagan_soni(user) == 1

    bildirishnoma_yaratish(recipient=user, turi=BildirishnomaTuri.YANGI_YECHIM)

    assert oqilmagan_soni(user) == 2


def test_MEHMON_uchun_sorov_YOQ(anonymous_client):
    """⚠️ Kirmagan foydalanuvchida bildirishnoma bo'lishi mumkin emas —
    baza so'rovi ham bo'lmasligi kerak."""
    from django.contrib.auth.models import AnonymousUser

    with CaptureQueriesContext(connection) as sorovlar:
        assert oqilmagan_soni(AnonymousUser()) == 0

    assert len(sorovlar) == 0


def test_HAMMASI_oqilgan_deb_belgilanadi(user):
    for _ in range(3):
        bildirishnoma_yaratish(recipient=user, turi=BildirishnomaTuri.YANGI_YECHIM)

    soni = hammasini_oqilgan_deb_belgilash(user=user)

    assert soni == 3
    assert oqilmagan_soni(user) == 0
    assert cache.get(kesh_kaliti(user.pk)) == 0


def test_BOSHQA_foydalanuvchining_sanogi_ozgarmaydi(user, other_user):
    bildirishnoma_yaratish(recipient=user, turi=BildirishnomaTuri.YANGI_YECHIM)
    bildirishnoma_yaratish(recipient=other_user, turi=BildirishnomaTuri.YANGI_YECHIM)

    hammasini_oqilgan_deb_belgilash(user=user)

    assert oqilmagan_soni(user) == 0
    assert oqilmagan_soni(other_user) == 1


# ===========================================================================
# 4. Markaz sahifasi
# ===========================================================================
def test_sahifa_KIRISH_talab_qiladi(anonymous_client):
    javob = anonymous_client.get(MANZIL)

    assert javob.status_code == 302
    assert "/kirish/" in javob["Location"]


def test_sahifa_royxatni_korsatadi(user, other_user):
    muammo = ComplaintFactory(author=user, title="Ipoteka olish qiyinmi")
    yechim_yozish(complaint=muammo, author=other_user, content="Mana yechim matni.")

    c = Client()
    c.force_login(user)
    sahifa = c.get(MANZIL).content.decode()

    assert "muammoingizga yechim yozdi" in sahifa
    assert "Ipoteka olish qiyinmi" in sahifa


def test_KORILGANDAN_KEYIN_tozalanadi(user, other_user):
    """⚠️ Qabul mezoni: "ko'rilgandan keyin tozalanadi"."""
    muammo = ComplaintFactory(author=user)
    yechim_yozish(complaint=muammo, author=other_user, content="Mana yechim matni.")
    assert oqilmagan_soni(user) == 1

    c = Client()
    c.force_login(user)
    c.get(MANZIL)

    assert oqilmagan_soni(user) == 0


def test_SHU_SAHIFADA_yangilar_AJRATIB_korsatiladi(user, other_user):
    """⚠️⚠️ Ro'yxat o'qilgan deb belgilashdan OLDIN olinadi.

    Teskari tartibda foydalanuvchi qaysi bildirishnomalar YANGI ekanini
    ko'ra olmasdi: sahifa ochilgan zahoti hammasi "eski" bo'lib qolardi
    va ro'yxat mutlaqo bir xil ko'rinardi.
    """
    muammo = ComplaintFactory(author=user)
    yechim_yozish(complaint=muammo, author=other_user, content="Mana yechim matni.")

    c = Client()
    c.force_login(user)

    birinchi = c.get(MANZIL).content.decode()
    ikkinchi = c.get(MANZIL).content.decode()

    assert "bg-primary/5" in birinchi, "yangi bildirishnoma ajratilmagan"
    assert "bg-primary/5" not in ikkinchi, "ikkinchi ochishda ham yangi ko'rinyapti"


def test_bosh_holat(user):
    c = Client()
    c.force_login(user)

    assert "Hozircha bildirishnoma yo'q" in c.get(MANZIL).content.decode()


def test_sahifa_NOINDEX(user):
    """Shaxsiy ro'yxat qidiruv tizimida turmasligi kerak."""
    c = Client()
    c.force_login(user)
    sahifa = c.get(MANZIL).content.decode()

    assert 'content="noindex, nofollow"' in sahifa
    assert 'rel="canonical"' not in sahifa


# ===========================================================================
# 5. Sarlavhadagi belgi
# ===========================================================================
def test_belgi_sonni_korsatadi(user):
    for _ in range(3):
        bildirishnoma_yaratish(recipient=user, turi=BildirishnomaTuri.YANGI_YECHIM)

    c = Client()
    c.force_login(user)
    sahifa = c.get("/").content.decode()

    assert "3 ta yangi" in sahifa


def test_NOL_bolsa_belgi_UMUMAN_chizilmaydi(user):
    """⚠️ "0" yozilgan belgi foydalanuvchiga "yangi narsa bor" degan
    yolg'on signal berardi."""
    c = Client()
    c.force_login(user)
    sahifa = c.get("/").content.decode()

    assert "ta yangi" not in sahifa
    assert "Bildirishnomalar" in sahifa  # havolaning o'zi turadi


def test_KATTA_son_qisqartiriladi(user, settings):
    settings.BILDIRISHNOMA_BELGI_CHEGARASI = 2
    cache.clear()
    for _ in range(5):
        bildirishnoma_yaratish(recipient=user, turi=BildirishnomaTuri.YANGI_YECHIM)

    c = Client()
    c.force_login(user)

    assert "2+" in c.get("/").content.decode()


def test_MEHMONGA_belgi_korinmaydi(anonymous_client):
    sahifa = anonymous_client.get("/").content.decode()

    assert reverse("bildirishnomalar") not in sahifa


# ===========================================================================
# 6. Model
# ===========================================================================
def test_manzil_yechim_LANGARIGA_olib_boradi(user, other_user):
    muammo = ComplaintFactory(author=user)
    yechim = yechim_yozish(
        complaint=muammo, author=other_user, content="Mana yechim matni."
    )

    b = Notification.objects.get(recipient=user)

    assert b.manzil == f"{muammo.get_absolute_url()}#yechim-{yechim.pk}"


def test_KONTENT_ochirilsa_bildirishnoma_ham_ketadi(user, other_user):
    """⚠️ `ContentType` o'rniga aniq FK'lar aynan shuning uchun
    (ochiq qaror Q1): baza darajasida butunlik va yetim yozuv yo'q."""
    muammo = ComplaintFactory(author=user)
    yechim_yozish(complaint=muammo, author=other_user, content="Mana yechim matni.")
    assert Notification.objects.count() == 1

    muammo.hard_delete()

    assert Notification.objects.count() == 0
