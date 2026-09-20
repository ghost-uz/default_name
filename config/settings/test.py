"""Test sozlamalari — tezlik uchun optimallashtirilgan.

⚠️ Testlarni ISHGA TUSHIRISHDA alohida shellda ishlating. Agar shu shellda
   avval `DJANGO_SETTINGS_MODULE=config.settings.dev` eksport qilingan bo'lsa,
   pytest DEV sozlamani oladi va email/kesh testlari yolg'ondan yiqiladi.
"""

import tempfile
from pathlib import Path

from .base import *
from .base import LOGGING

DEBUG = False
SECRET_KEY = "test-faqat-testlar-uchun-0123456789abcdefghijklmnop"  # noqa: S105
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]

# Parol hash'lash testdagi eng sekin operatsiya — testda kerak emas
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Har test o'z izolyatsiyasida bo'lsin
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "dard-test",
    }
}

# Yuborilgan xatlarni mail.outbox orqali tekshirish uchun.
# ⚠️ MAILERS — Django 6.1 dagi yangi shakl (EMAIL_BACKEND eskirgan).
MAILERS = {
    "default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"},
}

# Celery vazifalari testda darhol, sinxron bajarilsin (D0-T3 dan keyin kerak)
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Migratsiyalar testni sekinlashtiradi; kerak bo'lsa yoqiladi
LOGGING["root"]["level"] = "WARNING"


# --------------------------------------------------------------------------
# Maxfiy fayllar — VAQTINCHALIK katalogga
# --------------------------------------------------------------------------
# ⚠️⚠️ Busiz testlar repo ichidagi `maxfiy/` ga yozadi va TOZALAMAYDI.
#    Amalda 1118 ta soxta PDF yig'ilgan edi. Ular `.gitignore` da, ya'ni
#    git'da ko'rinmasdi — lekin `.dockerignore` da bo'lmagani uchun prod
#    obraziga tushib ketardi. Ikkala teshik ham yopildi; bu esa
#    manbasini yopadi.
MAXFIY_ROOT = Path(tempfile.gettempdir()) / "dard-test-maxfiy"

# ⚠️ `STORAGES` ni butunlay qayta yozmaymiz — faqat `maxfiy` kalitini.
#    Aks holda `default`/`staticfiles` yo'qoladi (prod.py da aynan shu
#    xato bo'lgan va prod konteyneri ko'tarilmasdi).
STORAGES = {
    **STORAGES,
    "maxfiy": {
        "BACKEND": "apps.common.storage.MaxfiyStorage",
        "OPTIONS": {"location": MAXFIY_ROOT},
    },
}
