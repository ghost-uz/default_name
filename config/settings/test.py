"""Test sozlamalari — tezlik uchun optimallashtirilgan.

⚠️ Testlarni ISHGA TUSHIRISHDA alohida shellda ishlating. Agar shu shellda
   avval `DJANGO_SETTINGS_MODULE=config.settings.dev` eksport qilingan bo'lsa,
   pytest DEV sozlamani oladi va email/kesh testlari yolg'ondan yiqiladi.
"""

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
