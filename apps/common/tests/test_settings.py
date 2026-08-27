"""Sozlama modullari import bo'lishini tekshiradi.

⚠️ NEGA BU KERAK
   Testlar `config.settings.test` bilan ishlaydi, ya'ni `dev.py` va
   `prod.py` HECH QACHON bajarilmaydi. Ularda oddiy `NameError` bo'lsa ham
   hech kim bilmaydi — xato faqat deploy paytida chiqadi.

   Bu aynan D0-T3 da yuz bergan: `CELERY_TIMEZONE = TIME_ZONE` qatori
   `TIME_ZONE` e'lonidan OLDIN yozilgan edi va uni faqat konteyner
   restart siklida qolganda payqadik.

   `Settings(...)` moduli global sozlamaga TEGMAYDI — u alohida obyekt
   yaratadi, ya'ni testlar bir-biriga xalaqit bermaydi.
"""

import os
import sys
from unittest import mock

import pytest
from django.conf import Settings
from django.core.exceptions import ImproperlyConfigured


def sozlama(modul: str) -> Settings:
    """Sozlama modulini QAYTADAN bajarib yuklaydi.

    ⚠️ `Settings(...)` ichida `importlib.import_module()` bor, u esa
    `sys.modules` keshiga tayanadi. Ya'ni modul bir marta muvaffaqiyatli
    import qilingandan keyin uning tanasi QAYTA BAJARILMAYDI va
    muhit o'zgaruvchilariga oid tekshiruvlar ishlamaydi — test
    "DID NOT RAISE" bilan yiqiladi va sababi ko'rinmaydi.

    Keshni tozalash global sozlamaga ta'sir qilmaydi: Django allaqachon
    yuklangan qiymatlarni o'zida saqlaydi.
    """
    for nom in [n for n in sys.modules if n.startswith("config.settings")]:
        del sys.modules[nom]
    return Settings(modul)


# ⚠️ DJANGO_ENV_FILE mavjud bo'lmagan yo'lga qaratiladi.
#    Aks holda base.py ishlab turgan `.env` faylini o'qiydi va test
#    dasturchining lokal sozlamasiga bog'liq bo'lib qoladi — ya'ni bir
#    mashinada o'tib, boshqasida yiqiladi.
ENV_FAYLSIZ = {"DJANGO_ENV_FILE": "/mavjud-emas/.env"}

PROD_MUHIT = ENV_FAYLSIZ | {
    "DJANGO_SECRET_KEY": "test-uchun-yetarlicha-uzun-va-xilma-xil-kalit-0123456789abcdef",
    "DJANGO_ALLOWED_HOSTS": "dard.uz,www.dard.uz",
}


def test_dev_sozlamasi_import_boladi():
    s = sozlama("config.settings.dev")
    assert s.DEBUG is True
    assert "127.0.0.1" in s.ALLOWED_HOSTS


def test_dev_hech_qanday_muhit_ozgaruvchisisiz_ishlaydi():
    """`git clone` dan keyin darhol ishga tushishi kerak."""
    with mock.patch.dict(os.environ, ENV_FAYLSIZ, clear=True):
        s = sozlama("config.settings.dev")
        assert s.SECRET_KEY  # standart qiymat bor
        assert s.DATABASES["default"]["NAME"]


def test_prod_sozlamasi_import_boladi():
    with mock.patch.dict(os.environ, PROD_MUHIT, clear=True):
        s = sozlama("config.settings.prod")
        assert s.DEBUG is False
        assert s.ALLOWED_HOSTS == ["dard.uz", "www.dard.uz"]
        assert s.SESSION_COOKIE_SECURE is True
        assert s.CSRF_COOKIE_SECURE is True


def test_prod_SECRET_KEY_siz_YIQILADI():
    """Yarim sozlangan server eng yomon holat — darhol to'xtasin."""
    muhit = ENV_FAYLSIZ | {"DJANGO_ALLOWED_HOSTS": "dard.uz"}
    with mock.patch.dict(os.environ, muhit, clear=True):
        with pytest.raises(ImproperlyConfigured, match="DJANGO_SECRET_KEY"):
            sozlama("config.settings.prod")


def test_prod_BOSH_SECRET_KEY_bilan_ham_YIQILADI():
    """⚠️ Eng ehtimolli xato stsenariysi.

    `.env.example` da kalitlar BO'SH turadi (`DJANGO_SECRET_KEY=`).
    Kimdir uni nusxa olib to'ldirmasa, o'zgaruvchi "bor" bo'ladi-yu,
    qiymati bo'sh chiqadi. Faqat `None` tekshirilsa server bo'sh sir
    bilan ko'tarilardi.
    """
    muhit = ENV_FAYLSIZ | {"DJANGO_SECRET_KEY": "", "DJANGO_ALLOWED_HOSTS": "dard.uz"}
    with mock.patch.dict(os.environ, muhit, clear=True):
        with pytest.raises(ImproperlyConfigured, match="DJANGO_SECRET_KEY"):
            sozlama("config.settings.prod")


def test_prod_ALLOWED_HOSTS_siz_YIQILADI():
    muhit = ENV_FAYLSIZ | {"DJANGO_SECRET_KEY": PROD_MUHIT["DJANGO_SECRET_KEY"]}
    with mock.patch.dict(os.environ, muhit, clear=True):
        with pytest.raises(ImproperlyConfigured, match="ALLOWED_HOSTS"):
            sozlama("config.settings.prod")


def test_HTTPS_ochiq_bolsa_cookie_va_redirect_BIRGA_ochadi():
    """⚠️ Yarim holat mumkin bo'lmasligi kerak.

    TLS'siz serverda `SESSION_COOKIE_SECURE=True` qolsa, brauzer
    cookie'ni umuman yubormaydi va admin paneliga kirib bo'lmaydi —
    xato esa "login noto'g'ri" bo'lib ko'rinadi. `SECURE_SSL_REDIRECT`
    esa cheksiz qayta yo'naltirish beradi.
    """
    muhit = PROD_MUHIT | {"DJANGO_HTTPS": "0"}
    with mock.patch.dict(os.environ, muhit, clear=True):
        s = sozlama("config.settings.prod")
        assert s.SECURE_SSL_REDIRECT is False
        assert s.SESSION_COOKIE_SECURE is False
        assert s.CSRF_COOKIE_SECURE is False
        # HSTS ham 0 — aks holda brauzer domenni "faqat HTTPS" deb eslaydi
        assert s.SECURE_HSTS_SECONDS == 0
        # CSRF manbalari ham http:// bo'lishi kerak
        assert all(o.startswith("http://") for o in s.CSRF_TRUSTED_ORIGINS)


def test_HTTPS_standart_boyicha_YOQILGAN():
    """Xavfsiz holat — standart. O'chirish ATAYLAB qilinadi."""
    with mock.patch.dict(os.environ, PROD_MUHIT, clear=True):
        s = sozlama("config.settings.prod")
        assert s.SECURE_SSL_REDIRECT is True
        assert s.SESSION_COOKIE_SECURE is True
        assert s.CSRF_COOKIE_SECURE is True
        assert all(o.startswith("https://") for o in s.CSRF_TRUSTED_ORIGINS)


def test_prod_da_statik_fayllar_hash_bilan():
    """ManifestStaticFilesStorage fayl nomiga hash qo'shadi — nginx uzoq
    muddatli kesh berishi xavfsiz bo'lsin (docker/nginx.conf)."""
    with mock.patch.dict(os.environ, PROD_MUHIT, clear=True):
        s = sozlama("config.settings.prod")
        assert "Manifest" in s.STORAGES["staticfiles"]["BACKEND"]


def test_celery_vaqt_mintaqasi_togri():
    """⚠️ D0-T3 regressiyasi: CELERY_TIMEZONE TIME_ZONE dan KEYIN
    e'lon qilinishi kerak, aks holda NameError."""
    for modul in ("config.settings.dev", "config.settings.test"):
        s = sozlama(modul)
        assert s.CELERY_TIMEZONE == s.TIME_ZONE == "Asia/Tashkent"


def test_celery_redis_bazalari_ALOHIDA():
    """Kesh va navbat bitta bazada bo'lsa cache.clear() vazifalarni
    o'chirib yuboradi."""
    s = sozlama("config.settings.dev")
    bazalar = {
        s.REDIS_URL.rsplit("/", 1)[1],
        s.CELERY_BROKER_URL.rsplit("/", 1)[1],
        s.CELERY_RESULT_BACKEND.rsplit("/", 1)[1],
    }
    assert len(bazalar) == 3, f"Redis bazalari takrorlanmoqda: {bazalar}"


def test_eskirgan_EMAIL_sozlamalari_ishlatilmaydi():
    """⚠️ Django 6.1 da EMAIL_BACKEND va boshqalar eskirgan (7.0 da olib
    tashlanadi). Ularni MAILERS bilan BIRGA yozib ham bo'lmaydi —
    Django ImproperlyConfigured beradi."""
    eskirgan = {
        "EMAIL_BACKEND",
        "EMAIL_HOST",
        "EMAIL_PORT",
        "EMAIL_HOST_USER",
        "EMAIL_HOST_PASSWORD",
        "EMAIL_USE_TLS",
        "EMAIL_USE_SSL",
        "EMAIL_TIMEOUT",
    }
    for modul, muhit in (
        ("config.settings.dev", {}),
        ("config.settings.test", {}),
        ("config.settings.prod", PROD_MUHIT),
    ):
        with mock.patch.dict(os.environ, muhit, clear=True):
            s = sozlama(modul)
            topilgan = {nom for nom in eskirgan if nom in s._explicit_settings}
            assert not topilgan, f"{modul} da eskirgan sozlama: {topilgan}"
            assert "default" in s.MAILERS
