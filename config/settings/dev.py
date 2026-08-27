"""Lokal ishlab chiqish sozlamalari.

Maqsad: `git clone` dan keyin HECH QANDAY muhit o'zgaruvchisisiz ishga tushsin.
Shuning uchun bu yerdagi barcha qiymatlar standart bilan keladi.
"""

from .base import *
from .base import LOGGING, TEMPLATES

# ⚠️ Yordamchilar MANBADAN import qilinadi (`.env`), `.base` orqali EMAS.
#    Sabab: `.base` ularni faqat qayta eksport qilardi va linter'ning
#    "ishlatilmagan import" avtomatik tuzatishi ularni o'chirib yubordi —
#    natijada dev va prod sozlamalari ImportError bilan yiqildi.
#    Bilvosita eksport mo'rt; to'g'ridan-to'g'ri import buzilmaydi.
from .env import env_bool

DEBUG = True

# Ataylab qattiq yozilgan: bu kalit FAQAT dev uchun.
# prod.py uni muhitdan MAJBURIY talab qiladi.
SECRET_KEY = "django-insecure-dev-faqat-mahalliy-ishlab-chiqish-uchun-0123456789"  # noqa: S105

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0", "[::1]"]

INTERNAL_IPS = ["127.0.0.1"]

# Email konsolga chiqadi — hech qayerga yuborilmaydi.
# ⚠️ EMAIL_BACKEND EMAS: Django 6.1 dan boshlab u eskirgan (Django 7.0 da
#    olib tashlanadi). Yangi shakl — MAILERS lug'ati.
#    Ikkalasini BIRGA e'lon qilib bo'lmaydi: Django ImproperlyConfigured beradi.
MAILERS = {
    "default": {"BACKEND": "django.core.mail.backends.console.EmailBackend"},
}

# Redis ko'tarilmagan bo'lsa ham dev ishlashi kerak
if env_bool("USE_REDIS_IN_DEV", False) is False:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "dard-dev",
        }
    }

# SQL so'rovlarini ko'rish uchun: SHOW_SQL=1 python manage.py runserver
if env_bool("SHOW_SQL", False):
    LOGGING["loggers"]["django.db.backends"]["level"] = "DEBUG"

# Shablon o'zgarishi darhol ko'rinsin.
# ⚠️ Dev'da keshlangan template loader ISHLATILMAYDI — u --noreload bilan
#    birga shablon tahririni "yo'qoladi" qilib qo'yadi va vaqt yeydi.
TEMPLATES[0]["OPTIONS"]["debug"] = True
