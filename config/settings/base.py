"""Dard.uz — umumiy sozlamalar.

Bu fayl HECH QACHON to'g'ridan-to'g'ri ishlatilmaydi. Har doim dev / prod / test
dan biri tanlanadi:

    DJANGO_SETTINGS_MODULE=config.settings.dev     (standart)
    DJANGO_SETTINGS_MODULE=config.settings.prod
    DJANGO_SETTINGS_MODULE=config.settings.test

Muhit o'zgaruvchilari `.env` faylidan va `os.environ` dan o'qiladi
(`config/settings/env.py`) — tashqi bog'liqliksiz.
"""

import os
from pathlib import Path
from typing import Any

from .env import (
    database_from_url,
    env,
    env_bool,
    env_int,
    load_dotenv,
)

# repo ildizi: config/settings/base.py -> config/settings -> config -> <ildiz>
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# ⚠️ Bu qator BIRINCHI env() chaqiruvidan OLDIN turishi shart.
#    Fayl bo'lmasa jimgina o'tib ketadi (Docker'da qiymatlarni compose beradi).
#    Boshqa joyni ko'rsatish: DJANGO_ENV_FILE=/path/to/.env
load_dotenv(os.environ.get("DJANGO_ENV_FILE") or BASE_DIR / ".env")


# --------------------------------------------------------------------------
# Asosiy
# --------------------------------------------------------------------------
# dev va test bu qiymatlarni bekor qiladi; prod ularni MAJBURIY qiladi.
SECRET_KEY = env("DJANGO_SECRET_KEY", "insecure-base-key-faqat-import-uchun")
DEBUG = False
ALLOWED_HOSTS: list[str] = []

ROOT_URLCONF = "config.urls"

# Admin manzili muhitdan sozlanadi. Standart "/admin/" — botlar eng ko'p
# urinadigan yo'l; prod'da uni o'zgartirish arzon va foydali himoya qatlami.
ADMIN_URL = env("DJANGO_ADMIN_URL", "admin").strip("/")
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ⚠️ BIRINCHI migratsiyada belgilangan (D0-T2). Buni keyinroq o'zgartirish
#    amalda bazani noldan qurishni talab qiladi — TEGMANG.
AUTH_USER_MODEL = "accounts.User"


# --------------------------------------------------------------------------
# Ilovalar
# --------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sitemaps",  # M4: SEO
    "django.contrib.postgres",  # M4: to'liq matnli qidiruv
]

THIRD_PARTY_APPS: list[str] = []

# Tartib muhim: `common` eng quyi qatlam, u boshqalarga BOG'LANMAYDI.
LOCAL_APPS = [
    "apps.common",
    "apps.accounts",
    "apps.complaints",
    "apps.solutions",
    "apps.moderation",
    "apps.gamification",
    "apps.notifications",
    "apps.payments",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS


MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Nonce javob yaratilishidan OLDIN kerak (shablon uni o'qiydi).
    # D2-T9 da CSP sarlavhasi shu qiymatdan foydalanadi.
    "apps.common.middleware.CSPMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


# ⚠️ Annotatsiya SHART: dev.py va test.py bu tuzilmalarni ichma-ich
#    indekslab o'zgartiradi (`TEMPLATES[0]["OPTIONS"]["debug"] = True`).
#    Annotatsiyasiz mypy ichki qiymatni `object` deb biladi va
#    "Unsupported target for indexed assignment" beradi.
TEMPLATES: list[dict[str, Any]] = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]


# --------------------------------------------------------------------------
# Ma'lumotlar bazasi — faqat PostgreSQL
# --------------------------------------------------------------------------
# SQLite ataylab ishlatilmaydi: loyiha keyinchalik PostgreSQL'ga xos
# imkoniyatlarga tayanadi (to'liq matnli qidiruv, pg_trgm, JSONB indekslari).
# Dev'da SQLite ishlatilsa, bu farqlar faqat prod'da ochiladi.
#
# Ikki usul qo'llab-quvvatlanadi:
#   1. DATABASE_URL — boshqariladigan bazalar (DigitalOcean, Neon, Supabase)
#      aynan shu formatda bitta qator beradi. Berilgan bo'lsa — USTUN.
#   2. Alohida POSTGRES_* o'zgaruvchilari — Docker Compose uchun qulay,
#      chunki postgres konteyneri baribir shularni talab qiladi.
#
# ⚠️ Ikkalasini bir vaqtda ishlatmang: parolni ikki joyda saqlash ularning
#    bir-biridan uzoqlashishiga olib keladi.
_DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

if _DATABASE_URL:
    _db = database_from_url(_DATABASE_URL)
else:
    _db = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB", "dard"),
        "USER": env("POSTGRES_USER", "dard"),
        "PASSWORD": env("POSTGRES_PASSWORD", "dard"),
        "HOST": env("POSTGRES_HOST", "127.0.0.1"),
        # ⚠️ Standart 5434, 5432 EMAS. Bu mashinada boshqa Docker stack'lar
        #    5432 ni band qilishi mumkin — to'qnashuvni oldindan chetlab o'tamiz.
        "PORT": env("POSTGRES_PORT", "5434"),
    }

_db["CONN_MAX_AGE"] = env_int("DB_CONN_MAX_AGE", 60)
_db["OPTIONS"] = {"connect_timeout": 5}

DATABASES = {"default": _db}


# --------------------------------------------------------------------------
# Kesh (D0-T3 da Redis konteyneri qo'shiladi)
# --------------------------------------------------------------------------
REDIS_URL = env("REDIS_URL", "redis://127.0.0.1:6381/0")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}


# --------------------------------------------------------------------------
# Xavfsizlik sarlavhalari va CSP (D2-T9)
# --------------------------------------------------------------------------
# ⚠️ YO'NALISHLAR SOZLAMADA, kodda emas: yangi tashqi resurs qo'shilganda
#    (M6 to'lov vidjeti kabi) middleware tegilmaydi.
#
# ⚠️⚠️ TELEGRAM QATORLARINI OLIB TASHLAMANG — LOGIN BUTUNLAY BUZILADI.
#    Vidjet `https://telegram.org/js/telegram-widget.js` skriptini
#    yuklaydi va ichkarida `https://oauth.telegram.org` iframe'ini
#    ochadi. Ikkalasi ham CSP'da ochiq bo'lmasa, "Telegram orqali
#    kirish" tugmasi UMUMAN CHIQMAYDI va konsolda faqat CSP xatosi
#    qoladi — sabab tashqaridan ko'rinmaydi.
#    (templates/accounts/login.html da ham shu izoh bor.)
CSP_YONALISHLARI: dict[str, list[str]] = {
    "default-src": ["'self'"],
    # ⚠️ `'unsafe-inline'` YO'Q va bo'lmasligi ham kerak: barcha inline
    #    skriptlar `nonce` oladi (middleware qo'shadi).
    "script-src": ["'self'", "https://telegram.org"],
    # ⚠️ `'unsafe-inline'` bu yerda ham YO'Q. Shu sababli shablonlarda
    #    inline `style=` atributi bo'lmasligi shart — guard test
    #    tekshiradi (D2-T9 da ikkitasi olib tashlandi).
    "style-src": ["'self'", "https://fonts.googleapis.com"],
    "font-src": ["'self'", "https://fonts.gstatic.com"],
    "img-src": ["'self'", "data:"],
    "connect-src": ["'self'"],
    "frame-src": ["https://oauth.telegram.org"],
    # Bizni boshqa saytga ramka qilib qo'yib bo'lmaydi (clickjacking).
    "frame-ancestors": ["'none'"],
    "base-uri": ["'self'"],
    "form-action": ["'self'"],
    "object-src": ["'none'"],
}

# Kerak bo'lmagan brauzer imkoniyatlari o'chiriladi.
PERMISSIONS_POLICY = (
    "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
    "magnetometer=(), microphone=(), payment=(), usb=()"
)

# ⚠️ Qolgan xavfsizlik sarlavhalari (`X_FRAME_OPTIONS`,
#    `SECURE_REFERRER_POLICY`, cookie bayroqlari) SHU FAYLNING PASTIDA,
#    "Xavfsizlik" bo'limida — ular D0-T1 dan beri turibdi.
#
# ⚠️⚠️ D2-T9 da ular BU YERGA HAM yozilgan edi va bu JIM XATO bo'lardi:
#    Python'da oxirgi yozuv g'olib chiqadi, ya'ni yuqoridagi qiymat
#    vakolatli ko'rinadi-yu, amalda pastdagisi ishlaydi. Aynan shu
#    holatda `SECURE_REFERRER_POLICY` "same-origin" dan
#    "strict-origin-when-cross-origin" ga BO'SHASHIB ketardi.
#    Takrorlarni `test_csp.py::test_sozlamalarda_TAKROR_YOQ` qo'riqlaydi.


# --------------------------------------------------------------------------
# Huquqiy sahifalar va rozilik (D2-T10)
# --------------------------------------------------------------------------
# ⚠️ VERSIYA — SANA. Shartlar yoki maxfiylik siyosati MAZMUNAN
#    o'zgarganda bu qiymat yangilanadi va BARCHA foydalanuvchilar qayta
#    rozilik beradi (`User.rozilik_bormi` versiyani solishtiradi).
#
#    Imlo tuzatish uchun o'zgartirmang: har o'zgarish butun bazani
#    "rozilik bermagan" holatga tushiradi va odamlar yozishdan
#    to'xtaydi.
HUQUQIY_VERSIYA = "2026-08-29"

# ⚠️⚠️ MATNLAR YURIST TOMONIDAN KO'RILDIMI (D2-T10 qabul mezoni).
#    `False` bo'lsa har bir huquqiy sahifada ochiq ogohlantirish
#    turadi. Yuristning xulosasi kelgach `True` qilinadi — matnlarga
#    tegilmaydi, bitta joy o'zgaradi.
#
#    ⚠️ Buni "sahifa chiroyliroq ko'rinsin" deb yoqib qo'ymang: belgi
#       foydalanuvchiga NIMANI o'qiyotganini aytadi.
HUQUQIY_KORILDI = env_bool("HUQUQIY_KORILDI", False)

# ⚠️ Reja auditoriyani 16 yoshdan deb belgilagan. Shaxsiy va ruhiy
#    mavzular bilan ishlaydigan platforma uchun bu huquqiy minimum.
YOSH_CHEGARASI = 16

# ⚠️ Bog'lanish ma'lumotlari. Telefon raqami loyiha egasiniki
#    (2026-08-29 da tasdiqlangan) — u INQIROZ LINIYASI EMAS
#    (`ISHONCH_TELEFONI` ga qarang).
#
# ⚠️ Ochiq saytdagi raqam skraper botlar tomonidan yig'iladi va spam
#    qo'ng'iroq keladi. Telegram varianti qo'yilsa, sahifa uni birinchi
#    ko'rsatadi va raqam ikkinchi darajaga tushadi.
ALOQA_TELEGRAM = env("ALOQA_TELEGRAM", "")
ALOQA_EMAIL = env("ALOQA_EMAIL", "")


# --------------------------------------------------------------------------
# Inqirozli kontent (D2-T6)
# --------------------------------------------------------------------------
# ⚠️⚠️ ISHONCH TELEFONI ATAYLAB BO'SH.
#
#    Task eslatmasi: "noto'g'ri inqiroz raqami raqam yo'qligidan
#    XAVFLIROQ". Javob bermaydigan yoki noto'g'ri raqamga qo'ng'iroq
#    qilgan odam ikkinchi marta urinmaydi.
#
#    Bu yerga FAQAT rasmiy manbadan tasdiqlangan ishonch liniyasi
#    yoziladi. Loyiha egasining shaxsiy raqami bu yerga YOZILMAYDI:
#    inqirozdagi odamga tayyorgarliksiz odam javob berishi xavfli
#    (2026-08-29 da loyiha egasi bilan aniqlashtirilgan).
#
#    To'ldirilganda shakl:
#        ISHONCH_TELEFONI = {
#            "nom": "<tashkilot nomi>",
#            "raqam": "1146",
#            "vaqt": "24/7",
#        }
ISHONCH_TELEFONI: dict[str, str] | None = None

# ⚠️ Bular UMUMMILLIY va o'zgarmas raqamlar — ular har doim
#    ko'rsatiladi, ishonch telefoni bo'lmasa ham. "Hech narsa yo'q"
#    degan sahifadan ko'ra shu ikkisi ancha yaxshi.
SHOSHILINCH_RAQAMLAR = [
    {
        "nom": "Tez tibbiy yordam",
        "raqam": "103",
        "izoh": "Hayotga xavf bo'lsa — darhol qo'ng'iroq qiling.",
    },
    {
        "nom": "Yagona chaqiruv markazi",
        "raqam": "112",
        "izoh": "Barcha shoshilinch xizmatlar.",
    },
]

# Loyiha bilan bog'lanish raqami — INQIROZ LINIYASI EMAS (D2-T10 da
# "Bog'lanish" sahifasida ishlatiladi).
ALOQA_TELEFONI = env("ALOQA_TELEFONI", "+998 99 503 63 62")


# --------------------------------------------------------------------------
# Tezlik cheklovi (D2-T4)
# --------------------------------------------------------------------------
# ⚠️ QABUL MEZONI: "cheklovlar sozlamada, kodda emas". Chegarani
#    o'zgartirish uchun kod tegilmaydi — shu lug'at tahrirlanadi
#    (yoki muhitga xos sozlamada qayta belgilanadi).
#
# Shakl: "<son>/<[koeffitsiyent]><birlik>", birlik = s | m | h | d
#        "30/m" = daqiqasiga 30 marta;  "5/2h" = ikki soatda 5 marta.
#
# ⚠️ IP CHEGARALARI ATAYLAB BO'SH. O'zbekistonda mobil operatorlar
#    CGNAT ishlatadi: bitta tashqi IP ortida minglab abonent bo'lishi
#    mumkin. Tor IP cheklovi butun mahallani birdan bloklardi va buni
#    aniqlash juda qiyin bo'lardi ("menda ishlamayapti, do'stimda
#    ishlayapti"). Asosiy og'irlik FOYDALANUVCHI chegarasida.
#
# ⚠️ Sonlar odam uchun juda bo'sh, skript uchun juda tor bo'lishi
#    kerak. Masalan haqiqiy odam daqiqasiga 30 marta ovoz bermaydi,
#    skript esa soniyasiga yuzlab urinadi.
TEZLIK_CHEKLOVLARI = {
    # Post yozish — eng qimmat amal (moderatsiya, lenta, bildirishnoma).
    "dard_yozish": {"foydalanuvchi": "5/h", "ip": "20/h"},
    "yechim_yozish": {"foydalanuvchi": "20/h", "ip": "60/h"},
    # ⚠️ Ovoz — eng arzon va eng ko'p suiiste'mol qilinadigan nuqta
    #    (task tavsifi): cheklovsiz bitta skript reytingni butunlay
    #    buzadi. Shuning uchun oyna daqiqa, soat emas.
    "ovoz": {"foydalanuvchi": "30/m", "ip": "120/m"},
    "shikoyat": {"foydalanuvchi": "10/h", "ip": "40/h"},
    # Xatcho'p — task ro'yxatida yo'q edi, lekin bu ham yozish amali va
    # xuddi ovoz kabi arzon. Ochiq qoldirish ma'nosiz.
    "saqlash": {"foydalanuvchi": "60/m", "ip": "200/m"},
}

# ⚠️ Mijoz IP'sini aniqlash uchun ISHONCHLI proksilar soni.
#    0 = to'g'ridan-to'g'ri ulanish, `REMOTE_ADDR` ishlatiladi (dev/test).
#    Nginx ortida bu 1 bo'lishi SHART (`config/settings/prod.py`), aks
#    holda butun sayt bitta IP hisobiga tushadi. Batafsil:
#    `apps/common/ratelimit.py::mijoz_ip`.
ISHONCHLI_PROKSILAR_SONI = 0


# --------------------------------------------------------------------------
# Autentifikatsiya
# --------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "/kirish/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"


# --------------------------------------------------------------------------
# Til va vaqt
# --------------------------------------------------------------------------
LANGUAGE_CODE = "uz"
TIME_ZONE = "Asia/Tashkent"
USE_I18N = True
USE_TZ = True

# ⚠️ RUSCHA ATAYLAB O'CHIRILGAN (D1-T7 da jonli sahifada topildi).
#
#    `LocaleMiddleware` tilni brauzerning `Accept-Language` sarlavhasidan
#    tanlaydi — `LANGUAGE_CODE` faqat ZAXIRA. Ya'ni ro'yxatda `ru` tursa,
#    ruscha brauzerli mehmon (O'zbekistonda eng keng tarqalgan holat)
#    ruscha sahifa "oladi". Lekin `locale/` BO'SH va shablon matnlari
#    `{% trans %}` ga o'ralmagan, shuning uchun tarjima faqat Django'ning
#    o'z satrlariga tegadi. Natija — yarim-yarim sahifa:
#
#        "2 минуты oldin"
#
#    Bu ruscha ham, o'zbekcha ham emas. Til ro'yxatiga tilni tarjimadan
#    OLDIN qo'shish shunday ko'rinadi.
#
#    Ruschani qaytarish sharti: (1) shablonlar `{% trans %}` ga o'raladi,
#    (2) `locale/ru/LC_MESSAGES/django.po` to'ldiriladi, (3) til
#    almashtirgich qo'shiladi. Shundan keyin bu qatorni oching.
#    Guard: apps/common/tests/test_settings.py
LANGUAGES = [
    ("uz", "O'zbekcha"),
]
LOCALE_PATHS = [BASE_DIR / "locale"]


# --------------------------------------------------------------------------
# Celery (D0-T3)
# --------------------------------------------------------------------------
# ⚠️ Bu blok TIME_ZONE dan KEYIN turishi shart — u shu qiymatga tayanadi.
#    (Boshiga qo'yilganda NameError bergan; sozlama fayllarida tartib
#     ahamiyatli, chunki bu oddiy modul, deklarativ konfiguratsiya emas.)

# Broker va natijalar uchun ALOHIDA Redis ma'lumotlar bazasi (/1, /2).
# Kesh bilan bitta bazani baham ko'rish xavfli: `cache.clear()` navbatdagi
# vazifalarni ham o'chirib yuboradi.
CELERY_BROKER_URL = env("CELERY_BROKER_URL", REDIS_URL.rsplit("/", 1)[0] + "/1")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", REDIS_URL.rsplit("/", 1)[0] + "/2")

CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_ENABLE_UTC = True

# ⚠️ Vazifa broker'ga YOZILGANDAN keyin emas, BAJARILGANDAN keyin tasdiqlanadi.
# Worker vazifa o'rtasida o'lsa, vazifa yo'qolmaydi va qayta beriladi.
# Buning sharti: vazifalar idempotent bo'lsin (ikki marta bajarilsa ham zarar
# qilmasin) — masalan Telegram'ga xabar yuborishda takroriylikni tekshirish.
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1

CELERY_TASK_TIME_LIMIT = env_int("CELERY_TASK_TIME_LIMIT", 300)
CELERY_TASK_SOFT_TIME_LIMIT = env_int("CELERY_TASK_SOFT_TIME_LIMIT", 240)
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

# --------------------------------------------------------------------------
# Reja bo'yicha ishlaydigan vazifalar (D1-T11)
# --------------------------------------------------------------------------
# ⚠️ Interval `crontab()` EMAS, oddiy sekund: shunda `settings.py` celery'ni
#    IMPORT QILMAYDI. Sozlama moduli og'ir bog'liqliklarsiz qolsin — u
#    `manage.py` ning har chaqiruvida yuklanadi.
#
# ⚠️ 600 sekund (10 daqiqa) — D1-T11 tavsifidagi qiymat. Tez-tez ishlatish
#    lentani jonliroq qiladi, lekin har ishga tushish oxirgi 7 kunlik
#    postlarni aylanadi.
CELERY_BEAT_SCHEDULE = {
    "hot-score-yangilash": {
        "task": "apps.complaints.tasks.hot_scorelarni_yangilash",
        "schedule": 600.0,
        # ⚠️ `expires` — beat vazifani navbatga qo'yadi, lekin worker band
        #    bo'lsa u kutib qoladi. 9 daqiqadan keyin eskirgan vazifa
        #    ma'nosiz: keyingisi baribir kelayotgan bo'ladi va navbatda
        #    bir xil ishning nusxalari to'planib qolmaydi.
        "options": {"expires": 540},
    },
    # ⚠️ Eksport ichida shaxsiy ma'lumot bor (D2-T8). "Bir marta
    #    so'ralgan, keyin unutilgan" fayl bazada yillab turishi —
    #    ma'lumot sizishining eng oddiy yo'li.
    "eskirgan-eksportlarni-ochirish": {
        "task": "apps.accounts.tasks.eskirgan_eksportlarni_ochirish",
        "schedule": 3600.0,
        "options": {"expires": 3000},
    },
}


# --------------------------------------------------------------------------
# Tashqi integratsiyalar
# --------------------------------------------------------------------------
# Kalitlar SHU YERDA e'lon qilinadi (ishlatilishi keyingi fazalarda bo'lsa
# ham), chunki .env.example va sozlama bir-biriga mos turishi kerak.
# Bo'sh qiymat = integratsiya o'chirilgan.

# D1-T1 (Telegram login) va D5-T2 (bot bildirishnomalari).
# ⚠️ Login HMAC imzosi aynan shu tokendan olinadi — u sir, hech qachon
#    shablonga yoki jurnalga tushmasligi kerak.
TELEGRAM_BOT_TOKEN = env("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_BOT_USERNAME = env("TELEGRAM_BOT_USERNAME", "")
TELEGRAM_CHANNEL_ID = env("TELEGRAM_CHANNEL_ID", "")  # D5-T3 avto-post

# D7-T1 — xatolarni kuzatish
SENTRY_DSN = env("SENTRY_DSN", "")
SENTRY_ENVIRONMENT = env("SENTRY_ENVIRONMENT", "development")
SENTRY_TRACES_SAMPLE_RATE = float(env("SENTRY_TRACES_SAMPLE_RATE", "0.1"))

# D6-T2 / D6-T3 — to'lov tizimlari
CLICK_MERCHANT_ID = env("CLICK_MERCHANT_ID", "")
CLICK_SECRET_KEY = env("CLICK_SECRET_KEY", "")
PAYME_MERCHANT_ID = env("PAYME_MERCHANT_ID", "")
PAYME_SECRET_KEY = env("PAYME_SECRET_KEY", "")


# --------------------------------------------------------------------------
# Statik va media fayllar
# --------------------------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"  # collectstatic natijasi
STATICFILES_DIRS = [BASE_DIR / "static"]  # manba (Tailwind chiqishi shu yerda)

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}


# --------------------------------------------------------------------------
# Xavfsizlik (prod.py bularni kuchaytiradi)
# --------------------------------------------------------------------------
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False  # HTMX sarlavhada token yuboradi
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024  # 5 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024


# --------------------------------------------------------------------------
# Loglash (D7-T1 da Sentry qo'shiladi)
# --------------------------------------------------------------------------
LOGGING: dict[str, Any] = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
    "loggers": {
        "django.db.backends": {"level": "INFO"},  # dev.py DEBUG ga o'zgartiradi
    },
}
