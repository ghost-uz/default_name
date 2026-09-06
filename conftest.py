"""pytest uchun umumiy fixture'lar va himoya tekshiruvlari.

Bu fayl repo ildizida — shuning uchun barcha testlarga taalluqli.
"""

from __future__ import annotations

import pytest
from django.conf import settings
from django.test import Client

from apps.accounts.factories import (
    BannedUserFactory,
    ExpertFactory,
    StaffFactory,
    TelegramUserFactory,
    UserFactory,
)


# ===========================================================================
# Himoya: to'g'ri sozlama bilan ishlayapmizmi?
# ===========================================================================
def pytest_configure(config) -> None:
    """⚠️ pytest-django uchun `DJANGO_SETTINGS_MODULE` MUHIT O'ZGARUVCHISI
    pyproject.toml dagi sozlamadan USTUN turadi.

    Ya'ni shu shellda avval

        $env:DJANGO_SETTINGS_MODULE = "config.settings.dev"

    qilingan bo'lsa, pytest DEV sozlamani oladi va buni HECH KIM AYTMAYDI.
    Oqibati jim va chalg'ituvchi:
      · email testlari yiqiladi (dev'da konsol backend, locmem emas);
      · kesh testlari yiqiladi (dev'da locmem, lekin boshqa nom bilan);
      · parol hash'lash sekin ishlaydi va testlar cho'ziladi.

    Shuning uchun bu yerda darhol va ochiq to'xtatamiz.
    """
    kutilgan = "config.settings.test"
    haqiqiy = settings.SETTINGS_MODULE

    if haqiqiy != kutilgan:
        raise pytest.UsageError(
            f"\n\nNoto'g'ri sozlama moduli: {haqiqiy!r}\n"
            f"Kutilgan: {kutilgan!r}\n\n"
            "Sabab: DJANGO_SETTINGS_MODULE muhit o'zgaruvchisi pyproject.toml\n"
            "dagi sozlamadan ustun turadi. Uni tozalang yoki testni toza\n"
            "shellda ishga tushiring:\n\n"
            "  PowerShell:  $env:DJANGO_SETTINGS_MODULE = $null; pytest\n"
            "  bash:        env -u DJANGO_SETTINGS_MODULE pytest\n"
        )


@pytest.fixture(scope="session")
def django_db_setup(django_db_setup, django_db_blocker):
    """Test bazasi qurilgandan KEYIN sinov modellari jadvallarini qo'shadi.

    NEGA BU KERAK (vaqt yegan xato)
       Abstrakt modelni sinash uchun `apps/common/tests/test_models.py` da
       `SinovOchirish` kabi konkret modellar e'lon qilinadi. Django ilova
       reyestri esa GLOBAL: pytest test modulini YIG'ISH paytida import
       qilishi bilanoq bu modellar BUTUN seansga ro'yxatga olinadi.

       Jadvallar avval faqat o'sha test sinfi ichida yaratilardi. Natijada
       boshqa istalgan testda `user.delete()` chaqirilsa, Django'ning
       `Collector` i barcha teskari aloqalarni aylanib chiqib
       `UPDATE common_sinovochirish SET deleted_by_id = NULL` qilmoqchi
       bo'lardi — jadval esa yo'q:

           relation "common_sinovochirish" does not exist

       Eng yomoni — test YOLG'IZ ishlaganda o'tardi, to'liq to'plamda
       yiqilardi. Sabab test faylining o'zida emas, boshqa faylda edi.

    ⚠️ NEGA `autouse` SEANS FIXTURE'I EMAS, `django_db_setup` USTIGA
       Birinchi urinish `autouse=True` seans fixture'i edi va u DEV
       BAZASINI IFLOSLANTIRDI: faqat `SimpleTestCase` tanlangan seansda
       (masalan bitta test fayli) test bazasi umuman qurilmaydi, fixture
       esa baribir ishga tushib, jadvallarni HAQIQIY `dard` bazasida
       yaratdi. Buni faqat bazani qo'lda ko'zdan kechirish oshkor qildi.

       `django_db_setup` ustiga qurilganda esa u FAQAT baza haqiqatan
       kerak bo'lgan seansda ishlaydi — bu pytest-django hujjatlaridagi
       standart kengaytirish nuqtasi.

    Jadvallar o'chirilmaydi: test bazasi seans oxirida baribir tashlanadi.
    """
    from django.db import connection

    from apps.common.tests.test_models import SINOV_MODELLAR

    with django_db_blocker.unblock(), connection.schema_editor() as editor:
        for model in SINOV_MODELLAR:
            editor.create_model(model)


@pytest.fixture(autouse=True)
def _tashqi_tarmoqni_taqiqlash(monkeypatch, request):
    """Testlar tashqi tarmoqqa CHIQMASIN.

    ⚠️ Telegram (D1-T1, D5-T2) va to'lov tizimlari (D6-T2/T3) tashqi HTTP
    chaqiradi. Test ularni mock qilishni unutsa:
      · CI sekinlashadi va tarmoqqa bog'liq bo'lib qoladi;
      · haqiqiy Telegram botiga test xabari ketishi mumkin;
      · sandbox to'lovi yaratilishi mumkin.

    Bu fixture chiqishga urinishni DARHOL ko'rsatadi.
    Kerak bo'lsa: @pytest.mark.usefixtures ni bekor qilib, socket'ni
    ochiq qoldiradigan test yozing yoki mock ishlating.
    """
    import socket

    haqiqiy_ulanish = socket.socket.connect

    def taqiqlangan(self, address, *args, **kwargs):
        host = address[0] if isinstance(address, tuple) else str(address)
        # Lokal ulanishlarga ruxsat: PostgreSQL, Redis, test serveri
        if host in ("127.0.0.1", "::1", "localhost", "db", "redis"):
            return haqiqiy_ulanish(self, address, *args, **kwargs)
        raise RuntimeError(
            f"Test tashqi tarmoqqa chiqmoqchi: {host}. "
            "Tashqi chaqiruvni mock qiling (responses / monkeypatch)."
        )

    monkeypatch.setattr(socket.socket, "connect", taqiqlangan)


@pytest.fixture(autouse=True)
def _media_izolyatsiyasi(settings, tmp_path):
    """Har test O'Z `MEDIA_ROOT` ida ishlasin (D4-T4).

    ⚠️⚠️ BUSIZ TESTLAR HAQIQIY `media/` KATALOGIGA YOZARDI.

       D4-T4 dan keyin muammo yaratadigan HAR bir test OG rasmini ham
       yasaydi (`CELERY_TASK_ALWAYS_EAGER=True`). Ular loyihaning
       haqiqiy `media/og/` katalogiga tushib, u yerda yuzlab yetim
       fayl to'planardi — va buni faqat qo'lda ko'zdan kechirish
       oshkor qilardi (D0-T7 dagi sinov modellari bilan bir xil
       turdagi xato).

    ⚠️ `tmp_path` — HAR TEST uchun yangi katalog va pytest uni o'zi
       tozalaydi. Bundan tashqari bu izolyatsiya beradi: bir test
       yasagan fayl ikkinchisiga ko'rinmaydi.

    ⚠️ `settings` fixture'i `setting_changed` signalini yuboradi va
       Django saqlash (storage) obyektini QAYTA QURADI — aks holda
       `default_storage` eski `location` ni keshda ushlab qolardi.
    """
    settings.MEDIA_ROOT = tmp_path / "media"


@pytest.fixture(autouse=True)
def _jim_soatlarni_ochirish(settings):
    """⚠️⚠️ TESTLAR DEVOR SOATIGA BOG'LIQ BO'LMASIN (D5-T4).

    Jim soatlar oynasi (standart 22:00-08:00, MAHALLIY vaqtda) haqiqiy
    vaqtga qaraydi. Usiz `telegram_yuborish` ni chaqiradigan HAR QANDAY
    test kechqurun boshqacha ishlardi: 2026-09-06 da soat 22:00 dan
    o'tganda 14 ta ALOQASIZ test yiqildi va to'plam 87s dan 331s ga
    cho'zildi.

    Bu xatoning eng yomon turi: kod o'zgarmagan, test o'zgarmagan,
    faqat SOAT o'zgargan. Kunduzi qayta ishga tushirsangiz "o'zi
    tuzalib ketgan"dek ko'rinadi.

    Oyna nol kenglikda (`boshi == oxiri`) — `jim_vaqtmi()` uni
    "hech qachon" deb o'qiydi. Oynani sinaydigan testlar uni ochiq
    beradi (`settings.JIM_SOATLAR_*`) yoki `jim_vaqtmi` ni mock qiladi.
    """
    from datetime import time

    settings.JIM_SOATLAR_BOSHI = time(0, 0)
    settings.JIM_SOATLAR_OXIRI = time(0, 0)


@pytest.fixture(autouse=True)
def _keshni_tozalash():
    """Har test toza keshdan boshlasin (D2-T4).

    ⚠️⚠️ BUSIZ TEZLIK CHEKLOVI TESTLAR ORASIDA OQIB KETADI.

       Kesh (test muhitida LocMem) baza kabi qaytarilmaydi: u jarayon
       xotirasida yashaydi va testdan testga o'tadi. Cheklov kaliti esa
       foydalanuvchi `pk` va IP (`127.0.0.1`) dan quriladi — ikkalasi
       ham testlar orasida TAKRORLANADI.

       Natijasi eng yomon turdagi xato bo'lardi: testlar ALOHIDA
       o'tadi, birga ishlatilganda esa tasodifiy 429 bilan yiqiladi —
       va yiqiladigan test aybdor testdan butunlay boshqa faylda
       bo'lishi mumkin.
    """
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


# ===========================================================================
# Foydalanuvchi fixture'lari
# ===========================================================================
@pytest.fixture
def user(db):
    """Oddiy foydalanuvchi (Telegram orqali kirgan)."""
    return TelegramUserFactory()


@pytest.fixture
def other_user(db):
    """Ikkinchi foydalanuvchi — ruxsatlarni tekshirish uchun.

    "Boshqa odamning postini tahrirlay olmaydi" turkumidagi testlar
    aynan shuni talab qiladi.
    """
    return TelegramUserFactory()


@pytest.fixture
def expert(db):
    return ExpertFactory()


@pytest.fixture
def staff(db):
    return StaffFactory()


@pytest.fixture
def banned_user(db):
    """Bloklangan: o'qiy oladi, yoza olmaydi (D0-T2)."""
    return BannedUserFactory()


@pytest.fixture
def anonymous_client() -> Client:
    """Kirmagan foydalanuvchi."""
    return Client()


@pytest.fixture
def auth_client(user) -> Client:
    """Kirgan foydalanuvchi.

    `force_login` ishlatiladi — parol tekshirilmaydi, chunki haqiqiy
    foydalanuvchilarda parol yo'q (Telegram login).
    """
    c = Client()
    c.force_login(user)
    return c


@pytest.fixture
def staff_client(staff) -> Client:
    c = Client()
    c.force_login(staff)
    return c


@pytest.fixture
def user_factory():
    """Fabrikaning o'zi — testda bir nechta foydalanuvchi kerak bo'lsa."""
    return UserFactory
