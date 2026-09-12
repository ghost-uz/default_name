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
from datetime import time as _time
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
    "apps.suhbat",
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
# Bloklash va uch ogohlantirish (D2-T11)
# --------------------------------------------------------------------------
# ⚠️ QIYMATLAR SOZLAMADA, kodda emas — D2-T4 dagi tezlik cheklovi bilan
#    bir xil sabab: chegarani o'zgartirish uchun kod tegilmaydi.
#
# ⚠️ NEGA BOSQICHLI. Task tavsifi: "moderator uchun yagona qurol
#    'o'chirish' bo'lsa, u yo hech narsa qilmaydi yo ortiqcha jazolaydi".
#    Bosqichlilik moderatorga o'rtacha javob beradi.
#
# ⚠️ HISOB QANDAY YURITILADI: `ModerationAction` dagi QOIDABUZARLIK
#    choralari sanaladi (ogohlantirish, yashirish, olib tashlash).
#    `RAD_ETISH` sanalmaydi — u "qoidabuzarlik yo'q" degani. Bekor
#    qilingan chora ham sanalmaydi.
CHEKLOV_CHEGARASI = 3  # shu sondan boshlab vaqtinchalik cheklov
DOIMIY_BLOK_CHEGARASI = 5  # shu sondan boshlab doimiy blok
CHEKLOV_MUDDATI_KUN = 7


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
    #
    # ⚠️⚠️ IP CHEGARASI 120 -> 600 (D7-T5 yuk testi; foydalanuvchi qarori,
    #    2026-09-12). O'LCHANGAN SABAB: 1000 odam 5 ta CGNAT IP ortidan bir
    #    daqiqada ovoz berganda 450 ta so'rov (43%) 429 oldi — arifmetikasi
    #    aniq: 5 × 120. O'zbekistonda mobil operatorlar CGNAT ishlatadi,
    #    ya'ni viral postda bitta IP ortida yuzlab HAQIQIY odam bo'ladi va
    #    ular «Juda tez yuboryapsiz» xabarini BIRINCHI bosishdayoq ko'rardi.
    #
    #    600 skriptni baribir to'sadi: har HISOB 30/daqiqa bilan
    #    cheklangan, ya'ni 600 ga yetish uchun kamida 20 ta hisob kerak.
    #    Haqiqiy trafik kelgach D7-T8 metrikalari bilan qayta ko'riladi.
    "ovoz": {"foydalanuvchi": "30/m", "ip": "600/m"},
    "shikoyat": {"foydalanuvchi": "10/h", "ip": "40/h"},
    # Xatcho'p — task ro'yxatida yo'q edi, lekin bu ham yozish amali va
    # xuddi ovoz kabi arzon. Ochiq qoldirish ma'nosiz.
    "saqlash": {"foydalanuvchi": "60/m", "ip": "200/m"},
    # ⚠️ D6-T5: shaxsiy suhbat. So'rov QAT'IY cheklangan — u qarshi
    #    tomonga bildirishnoma yuboradi va bezovtalik uchun eng qulay
    #    vosita bo'lardi. Xabar esa yumshoqroq: suhbat ochilgandan
    #    keyin ikki tomon allaqachon rozilik bergan.
    "kontakt_sorovi": {"foydalanuvchi": "10/h", "ip": "30/h"},
    "suhbat_xabar": {"foydalanuvchi": "60/h", "ip": "200/h"},
    # ⚠️ D6-T2: to'lov BOSHLASH (buyurtma yaratish). Cheklov keng —
    #    to'lov urinishi qonuniy ravishda takrorlanadi (karta rad
    #    etadi, sessiya tugaydi, odam boshqa karta sinaydi). Tor
    #    chegara to'lay olmagan odamni butunlay to'sib qo'yardi.
    #
    #    ⚠️ CLICK WEBHOOK'LARI BU YERDA YO'Q — ataylab. Ular tashqi
    #       server so'rovlari va cheklovga tushishi to'lovni
    #       YO'QOTARDI: Click 429 ni "javob yo'q" deb o'qiydi va bir
    #       necha urinishdan keyin tranzaksiyani bekor qiladi.
    #       Webhook himoyasi — IMZO, tezlik cheklovi emas.
    "tolov_boshlash": {"foydalanuvchi": "20/h", "ip": "60/h"},
}

# ⚠️ Mijoz IP'sini aniqlash uchun ISHONCHLI proksilar soni.
#    0 = to'g'ridan-to'g'ri ulanish, `REMOTE_ADDR` ishlatiladi (dev/test).
#    Nginx ortida bu 1 bo'lishi SHART (`config/settings/prod.py`), aks
#    holda butun sayt bitta IP hisobiga tushadi. Batafsil:
#    `apps/common/ratelimit.py::mijoz_ip`.
ISHONCHLI_PROKSILAR_SONI = 0


# --------------------------------------------------------------------------
# Qidiruv (D4-T1)
# --------------------------------------------------------------------------
# ⚠️ "Qanchalik yaqin — yetarli yaqin?" MAHSULOT savoli, texnik emas.
#    Shuning uchun chegara sozlamada: uni to'g'rilash uchun kod tegilmaydi
#    (D2-T4 dagi tezlik cheklovlari bilan bir xil sabab).
#
# ⚠️ O'LCHANGAN QIYMAT, taxmin emas:
#        word_similarity('ipotaka', 'ipoteka olish qiyinmi') = 0.50
#    0.45 bir harflik xatoni o'tkazadi, ikki butunlay boshqa so'zni esa
#    (masalan 'ipoteka' va 'apteka' = 0.33) o'tkazmaydi.
#
# ⚠️ PASAYTIRMANG. Chegara juda past bo'lsa "hech narsa topilmadi"
#    o'rniga ALOQASIZ takliflar chiqadi — bu yomonroq: foydalanuvchi
#    qidiruv umuman ishlamayapti deb o'ylaydi.
QIDIRUV_OXSHASHLIK_CHEGARASI = 0.45

# Bo'sh natijada nechta taklif ko'rsatiladi. Ko'p bo'lsa taklif emas,
# ikkinchi natijalar ro'yxatiga o'xshab qoladi.
QIDIRUV_TAKLIF_SONI = 5


# --------------------------------------------------------------------------
# O'xshash muammolar (D4-T7)
# --------------------------------------------------------------------------
# ⚠️ Maketda yon panelda AYNAN uchta joy bor. Ko'proq ko'rsatish sahifani
#    uzaytiradi va asosiy kontentdan (yechimlardan) chalg'itadi.
OXSHASH_SONI = 3

# ⚠️ Eng kuchsiz shovqinni kesish uchun. Chegarani KO'TARISH ro'yxatni
#    tez-tez BO'SH qoldiradi (kichik bazada o'xshashlik baribir past),
#    tushirish esa aloqasiz havolalarni chiqaradi.
#
# ⚠️ `ts_rank` qiymatlari SO'ROVLAR ORASIDA taqqoslanmaydi: ular so'z
#    soniga bog'liq. Shuning uchun bu chegara "sifat o'lchovi" emas,
#    faqat pol. Sifatning asosiy manbai — to'xtash so'zlar ro'yxati
#    (`apps/common/matn.py`).
OXSHASH_CHEGARASI = 0.02

# Kesh muddati. Yangi post qo'shilganda eski postlarning ro'yxati
# eskiradi — to'liq qayta hisoblash O(n²) va unga arzimaydi.
OXSHASH_KESH_MUDDATI = 60 * 60 * 24  # 24 soat

# ⚠️ "Hisoblash navbatda" belgisi muddati (D4-T7). Busiz sovuq keshdagi
#    mashhur postga bir vaqtda kelgan 100 ta so'rov 100 ta bir xil
#    vazifani navbatga qo'yardi.
OXSHASH_ISH_MUDDATI = 300


# --------------------------------------------------------------------------
# Bildirishnomalar (D5-T1)
# --------------------------------------------------------------------------
# ⚠️ Kesh muddati — ZAXIRA, asosiy mexanizm emas. Sanoq o'zgarganda kesh
#    OCHIQ tozalanadi (`apps/notifications/services.py`); TTL esa
#    tozalash unutilgan holat uchun xavfsizlik to'ri. Usiz noto'g'ri
#    son mangu qolardi va uni faqat Redis'ni tozalash tuzatardi.
BILDIRISHNOMA_KESH_MUDDATI = 300  # 5 daqiqa

# ⚠️ Belgida ko'rsatiladigan eng katta son. Undan ko'pi "99+" bo'lib
#    chiqadi: sarlavhadagi belgi tor va uch xonali son maketni buzadi.
BILDIRISHNOMA_BELGI_CHEGARASI = 99

BILDIRISHNOMA_SAHIFA_HAJMI = 30

# ⚠️ JIM SOATLAR (D5-T4) — MAHALLIY vaqt bo'yicha (`TIME_ZONE`).
#    Oyna yarim tundan o'tadi (22:00 -> 08:00) va uni tekshirish oddiy
#    `boshlanish <= hozir < tugash` bilan ISHLAMAYDI — sabab
#    `apps/notifications/sozlama.py` da.
#
# ⚠️ Xabar TASHLANMAYDI, KECHIKTIRILADI: foydalanuvchi tunda bezovta
#    qilinmaslikni so'radi, xabardan voz kechishni emas.
JIM_SOATLAR_BOSHI = _time(22, 0)
JIM_SOATLAR_OXIRI = _time(8, 0)


# --------------------------------------------------------------------------
# Obuna (D6-T1)
# --------------------------------------------------------------------------
# ⚠️ Bitta to'lov necha kun beradi. Uzaytirish QOLGAN MUDDAT USTIGA
#    qo'shiladi (`services.obunani_uzaytirish`) — erta to'lagan mijoz
#    kunlarini yo'qotmasin.
OBUNA_MUDDATI_KUN = 30


# --------------------------------------------------------------------------
# Ekspertlarga «javobsiz savollar» dayjesti (D5-T5)
# --------------------------------------------------------------------------
# ⚠️ BESHTA SAVOL. Ko'proq bo'lsa xabar Telegram'da "ko'proq" tugmasi
#    ostiga tushadi va oxirgilari o'qilmaydi; ekspert esa ro'yxatni
#    bajarib bo'lmaydigan ish deb qabul qiladi va umuman boshlamaydi.
DAYJEST_SAVOL_SONI = 5

# ⚠️ IKKI HAFTALIK OYNA, HAFTALIK YUBORISH bilan. Oyna yuborish
#    davridan UZUNROQ: shunda javobsiz savol kamida ikki marta
#    ko'rinadi va bitta o'tkazib yuborilgan hafta uni yo'qotmaydi.
#
#    Cheksiz bo'lmasligi ham shart — bir necha oy javobsiz turgan savol
#    odatda dolzarbligini yo'qotgan va u ro'yxatni to'ldirib, yangi
#    savollarni pastga surardi.
DAYJEST_OYNA_KUNLARI = 14


# --------------------------------------------------------------------------
# Telegram kanaliga avto-post (D5-T3)
# --------------------------------------------------------------------------
# ⚠️ KUNIGA UCHTA. Ko'proq post kanalni "spam" qiladi va obunachi
#    ovozni o'chiradi — o'chirilgan kanal esa o'lik kanal.
#    Kamroq bo'lsa kanal jonsiz ko'rinadi va odam obuna bo'lmaydi.
KANAL_KUNLIK_SONI = 3

# ⚠️ Faqat SO'NGGI kunlardagi postlar. `hot_score` eski postda ham
#    yuqori bo'lishi mumkin (ko'p ovoz yig'gan), kanal esa "bugun nima
#    bo'lyapti" degan lenta.
KANAL_OYNA_KUNLARI = 3

# Telegram uzun xabarni yig'ib qo'yadi va "ko'proq" ostidagi matn
# o'qilmaydi. Maqsad — qiziqtirish, to'liq javob berish emas.
KANAL_PARCHA_UZUNLIGI = 280


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
    # ⚠️ Nishon berish `accept_solution()` da ochiq chaqiriladi, lekin
    #    OVOZ yo'lida chaqirilmaydi (u juda tez-tez bo'ladi va D1-T14 da
    #    qotirilgan so'rov byudjetini yeb qo'yardi). Bu vazifa ovozdan
    #    kelib chiqadigan nishonlarni yopadi — kechikish bor, yo'qotish
    #    yo'q.
    "nishonlarni-yangilash": {
        "task": "apps.gamification.tasks.nishonlarni_yangilash",
        "schedule": 86400.0,
        "options": {"expires": 43200},
    },
    # ⚠️ Reyting lentaning yon panelida — HAR SAHIFADA. So'rov ichida
    #    hisoblansa, har ko'rish ikkita agregat so'rov qilardi (D3-T3).
    #    Kesh TTL (2 soat) bu oraliqdan uzunroq: bitta o'tkazib
    #    yuborilgan ish reytingni bo'shatmaydi.
    # ⚠️ Kuniga BIR MARTA. Ko'proq ishga tushirish kanalni spam qiladi;
    #    kamroq bo'lsa qaynoq postlar dolzarbligini yo'qotadi.
    #
    # ⚠️ `expires` — vazifa kechiksa (worker band) uni bajarish
    #    ma'nosiz: ertaga yangi ro'yxat bilan qaytadan ishlaydi.
    # ⚠️ HAFTADA BIR MARTA. Ko'proq yuborish ekspertni charchatadi va
    #    ro'yxat o'zgarmagan bo'lardi (savollarga javob yozish vaqt
    #    oladi); kamroq bo'lsa savol dolzarbligini yo'qotadi.
    #
    # ⚠️ Aniq SOAT kerak emas: tunda ishga tushsa ham xabarni jim
    #    soatlar (D5-T4) ertalabgacha kechiktiradi.
    #
    # ⚠️ `expires` — bir necha soat kechikish zarar qilmaydi, lekin
    #    bir kundan keyin bajarish ma'nosiz: keyingi hafta baribir
    #    yangi ro'yxat bilan keladi.
    "ekspert-dayjesti": {
        "task": "apps.notifications.tasks.dayjest_yuborish",
        "schedule": 604800.0,
        "options": {"expires": 86400},
    },
    # ⚠️ Bu vazifa PRO ni HIMOYA QILMAYDI — `Subscription.faolmi`
    #    muddatni har chaqiruvda o'zi tekshiradi. Vazifa faqat `status`
    #    ustunini haqiqatga yaqin tutadi (hisobot va so'rovlar uchun).
    #    Kuniga bir marta yetarli.
    "obunalarni-tekshirish": {
        "task": "apps.payments.tasks.obunalarni_tekshirish",
        "schedule": 86400.0,
        "options": {"expires": 43200},
    },
    "kanalga-post": {
        "task": "apps.complaints.tasks.kanalga_post",
        "schedule": 86400.0,
        "options": {"expires": 43200},
    },
    "reytingni-yangilash": {
        "task": "apps.gamification.tasks.reytingni_yangilash",
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

# ⚠️ Bot API so'roviga kutish vaqti (D5-T2). Vazifa Celery ichida
#    ishlaydi, ya'ni foydalanuvchi kutmaydi — lekin cheksiz kutish
#    worker'ni band qilib qo'yardi va navbat to'planardi.
TELEGRAM_TIMEOUT = env_int("TELEGRAM_TIMEOUT", 10)

# ⚠️ SAYT MANZILI — fon vazifalari uchun MAJBURIY.
#    Telegram xabaridagi havola mutlaq bo'lishi kerak, vazifada esa
#    `request` yo'q (`build_absolute_uri` ishlamaydi). Prod'da u
#    `ALLOWED_HOSTS` dan olinadi (`config/settings/prod.py`).
SAYT_MANZILI = env("SAYT_MANZILI", "http://127.0.0.1:8000")

# D7-T1 — xatolarni kuzatish
SENTRY_DSN = env("SENTRY_DSN", "")
SENTRY_ENVIRONMENT = env("SENTRY_ENVIRONMENT", "development")
SENTRY_TRACES_SAMPLE_RATE = float(env("SENTRY_TRACES_SAMPLE_RATE", "0.1"))

# D6-T2 / D6-T3 — to'lov tizimlari
CLICK_MERCHANT_ID = env("CLICK_MERCHANT_ID", "")
CLICK_SERVICE_ID = env("CLICK_SERVICE_ID", "")
CLICK_SECRET_KEY = env("CLICK_SECRET_KEY", "")
PAYME_MERCHANT_ID = env("PAYME_MERCHANT_ID", "")
# ⚠️ Bu Payme Merchant API'ning Basic-auth PAROLI
#    (`Authorization: Basic base64("Paycom:<kalit>")`). Sandbox va
#    prod uchun kalitlar BOSHQA — sandbox'ni prodga olib o'tish
#    hamma so'rovni `-32504` bilan rad ettiradi.
PAYME_SECRET_KEY = env("PAYME_SECRET_KEY", "")
PAYME_CHECKOUT_MANZILI = env("PAYME_CHECKOUT_MANZILI", "https://checkout.paycom.uz")

# ⚠️ Click to'lov sahifasi. Sozlamada — chunki sandbox va prod
#    manzillari boshqa, kod esa ikkalasida BIR XIL bo'lishi kerak.
CLICK_TOLOV_MANZILI = env("CLICK_TOLOV_MANZILI", "https://my.click.uz/services/pay")

# ⚠️⚠️ PRO NARXI SERVERDA. Formadan kelgan summaga ishonish "PRO ni
#    1 so'mga sotib olish"ni so'rovni qo'lda yasash bilan ochardi —
#    to'lov integratsiyalaridagi eng klassik teshik.
#
# ⚠️ `str` — `Decimal` ga o'girish `apps/payments/views.py` da.
#    Sozlamada `Decimal` saqlash `float` bilan adashtirishga olib
#    keladi: kimdir `OBUNA_NARXI * 2` yozsa va qiymat `float` bo'lsa,
#    xato faqat tiyinlarda ko'rinardi.
OBUNA_NARXI = env("OBUNA_NARXI", "19000")

# ⚠️ To'lov provayderi TAYYORMI. Kalitlarsiz "To'lash" tugmasini
#    ko'rsatish odamni Click'ning xato sahifasiga olib borardi va u
#    buni SAYT nosozligi deb qabul qilardi.
#    Ko'rinish shu bayroqqa qaraydi, kalitlarning o'ziga EMAS.
CLICK_YOQILGANMI = bool(CLICK_MERCHANT_ID and CLICK_SERVICE_ID and CLICK_SECRET_KEY)
PAYME_YOQILGANMI = bool(PAYME_MERCHANT_ID and PAYME_SECRET_KEY)

# --------------------------------------------------------------------------
# Boost — postni ko'tarish (D6-T4)
# --------------------------------------------------------------------------
# ⚠️ Narx SERVERDA va `str` — `OBUNA_NARXI` bilan bir xil sabab.
BOOST_NARXI = env("BOOST_NARXI", "5000")

# ⚠️ Bitta to'lov necha kun beradi — SOATDA EMAS, KUNDA: `Tolov.berilgan_kun`
#    pul qaytarilganda (D6-T3) nima berilganini yozib qo'yadi va u obuna
#    bilan BIR XIL birlikda bo'lishi kerak.
BOOST_MUDDATI_KUN = 1

# ⚠️⚠️ LENTADAGI ULUSH — D6-T4 QABUL MEZONI.
#    Ko'tarilgan postlar «Qaynoq»ning BIRINCHI sahifasida ajratilgan
#    joylarda turadi: birinchisi `BOOST_BIRINCHI_JOY`-o'rinda, keyingilari
#    har `BOOST_ORALIQ` kartada. Ya'ni ketma-ket istalgan 5 kartada ko'pi
#    bilan BITTA ko'tarilgan post bo'ladi. Joylar SONI alohida sozlama
#    emas — sahifa hajmidan HISOBLANADI (`payments.selectors`), aks holda
#    u ulush qoidasiga zid kelib qolishi mumkin edi.
#
#    Birinchi joy 3 — foydalanuvchi qarori (2026-09-11): lenta pullik
#    karta bilan BOSHLANMASIN, birinchi ikkita karta doim organik.
BOOST_BIRINCHI_JOY = 3
BOOST_ORALIQ = 5


# --------------------------------------------------------------------------
# Statik va media fayllar
# --------------------------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"  # collectstatic natijasi
STATICFILES_DIRS = [BASE_DIR / "static"]  # manba (Tailwind chiqishi shu yerda)

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# --------------------------------------------------------------------------
# ⚠️⚠️ MAXFIY FAYLLAR — `MEDIA_ROOT` DAN TASHQARIDA (D3-T5)
# --------------------------------------------------------------------------
# `/media/` nginx tomonidan AVTORIZATSIYASIZ va `Cache-Control: public`
# bilan uzatiladi (`docker/nginx.conf`), DEBUG rejimida esa Django uni
# `static()` bilan ochadi. Ya'ni `MEDIA_ROOT` ga tushgan HAR QANDAY fayl —
# havolani bilgan har kimga ochiq.
#
# Ekspert tasdiqlash hujjati (diplom, litsenziya) bunday joyda TURA
# OLMAYDI: fayl nomi sizsa yoki taxmin qilinsa, odamning hujjati ochiq
# internetda bo'lardi.
#
# Shuning uchun alohida ildiz + uni faqat `apps/accounts/views.py::
# ekspert_hujjati` ko'rinishi (staff-only) o'qiydi. Veb-server bu
# katalogni UMUMAN bilmaydi.
#
# ⚠️ DEPLOY'DA: bu katalog konteyner ichida bo'lsa, qayta joylashda
#    yo'qoladi — u `docker-compose` da alohida volume bo'lishi kerak.
#    Lekin hujjatlar qaror bilan birga O'CHIRILADI (D3-T5 qarori), ya'ni
#    u yerda uzoq turadigan narsa yo'q.
MAXFIY_ROOT = BASE_DIR / "maxfiy"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
    # ⚠️⚠️ MAXSUS SINF, oddiy `FileSystemStorage` EMAS — o'lchangan sabab.
    #    `base_url` berilmasa Django uni `MEDIA_URL` ga QAYTARADI
    #    (`_value_or_setting`), ya'ni `.url` ochiq ko'rinishdagi
    #    `/media/ekspert/...` havolasini berardi. `MaxfiyStorage.url()`
    #    esa ochiq rad etadi — batafsil: `apps/common/storage.py`.
    "maxfiy": {
        "BACKEND": "apps.common.storage.MaxfiyStorage",
        "OPTIONS": {"location": MAXFIY_ROOT},
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
