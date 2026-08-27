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


@pytest.fixture(scope="session", autouse=True)
def _sinov_modellari_uchun_jadvallar(django_db_setup, django_db_blocker):
    """⚠️ `apps/common/tests/test_models.py` dagi sinov modellari uchun
    jadvallarni BUTUN SEANS davomida yaratib qo'yadi.

    NEGA BU KERAK (vaqt yegan xato)
       Abstrakt modelni sinash uchun o'sha faylda `SinovOchirish` kabi
       konkret modellar e'lon qilinadi. Django ilova reyestri esa GLOBAL:
       pytest test modulini yig'ish paytida import qilishi bilanoq bu
       modellar BUTUN seansga ro'yxatga olinadi.

       Jadvallar esa avval faqat o'sha test sinfi ichida yaratilardi.
       Natijada boshqa istalgan testda `user.delete()` chaqirilsa,
       Django'ning `Collector` i barcha teskari aloqalarni aylanib chiqib
       `UPDATE common_sinovochirish SET deleted_by_id = NULL` qilmoqchi
       bo'lardi — jadval esa yo'q:

           relation "common_sinovochirish" does not exist

       Eng yomoni — test YOLG'IZ ishlaganda o'tardi, to'liq to'plamda
       yiqilardi. Sabab test faylining o'zida emas, butunlay boshqa
       faylda edi.

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
