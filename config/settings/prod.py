"""Ishlab chiqarish (production) sozlamalari.

Bu yerda STANDART QIYMAT YO'Q. Har bir sir muhitdan keladi va yetishmasa
Django ishga tushmaydi. Bu ataylab: "vaqtincha standart bilan ishlab tursin"
degan yondashuv oxir-oqibat prod'da dev kaliti bilan ishlashga olib keladi.
"""

from .base import *

# ⚠️ Yordamchilar MANBADAN (`.env`), `.base` orqali EMAS — bilvosita
#    eksportni linter "ishlatilmagan import" deb o'chirib yuborishi mumkin.
from .env import env, env_bool, env_int, env_list

DEBUG = False

# ⬇️ Bularsiz server KO'TARILMAYDI
SECRET_KEY = env("DJANGO_SECRET_KEY")
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")

if not ALLOWED_HOSTS:
    from django.core.exceptions import ImproperlyConfigured

    raise ImproperlyConfigured(
        "DJANGO_ALLOWED_HOSTS bo'sh. Masalan: 'dard.uz,www.dard.uz'"
    )

# --------------------------------------------------------------------------
# HTTPS va cookie xavfsizligi
# --------------------------------------------------------------------------
# ⚠️ BITTA KALIT: DJANGO_HTTPS.
#
#    Ilgari `SECURE_SSL_REDIRECT` muhitdan, cookie'lar esa qattiq `True`
#    edi. Bu YARIM ISHLAYDIGAN holatga yo'l ochardi va uni tashxislash
#    juda qiyin:
#      · TLS'siz serverda `SESSION_COOKIE_SECURE=True` bo'lsa, brauzer
#        cookie'ni UMUMAN YUBORMAYDI -> admin paneliga kira olmaysiz,
#        xato xabari esa "login noto'g'ri" bo'lib ko'rinadi;
#      · `SECURE_SSL_REDIRECT=True` bo'lsa, nginx'da TLS bo'lmagani uchun
#        cheksiz qayta yo'naltirish (redirect loop) yuzaga keladi.
#
#    Endi uchalasi BIR manbadan keladi — yarim holat mumkin emas.
#
#    DJANGO_HTTPS=0 faqat VAQTINCHALIK: domen olinmagan, IP orqali
#    ishlayotgan bosqich uchun. Domen va sertifikat tayyor bo'lgach 1 ga
#    qaytariladi (DEPLOY.md, "TLS qo'shish" bo'limi).
HTTPS_ENABLED = env_bool("DJANGO_HTTPS", True)

# Nginx orqasida turadi — HTTPS ekanini shu sarlavhadan biladi.
# ⚠️ Nginx `proxy_set_header X-Forwarded-Proto $scheme;` yubormasa, bu sozlama
#    xavfli bo'ladi (foydalanuvchi sarlavhani o'zi qo'yishi mumkin).
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# ⚠️ Xuddi shu sabab tezlik cheklovi uchun ham (D2-T4): nginx ortida
#    `REMOTE_ADDR` HAR DOIM nginx'ning manzili bo'ladi, ya'ni IP
#    chegarasi butun saytni bitta hisobga qo'shib, hammani birdan
#    bloklab qo'yardi. Nginx `X-Forwarded-For` ro'yxatining OXIRIGA
#    o'ziga ulangan manzilni qo'shadi (`$proxy_add_x_forwarded_for`),
#    shuning uchun bitta proksi = 1.
#
#    ⚠️ Bu qiymat proksilar sonidan KATTA bo'lmasligi kerak: har bir
#       ortiqcha birlik mijoz o'zi yozgan sarlavhaga ishonish degani
#       va cheklovni butunlay chetlab o'tish imkonini beradi.
#       CDN (masalan Cloudflare) qo'shilsa — 2.
ISHONCHLI_PROKSILAR_SONI = 1

SECURE_SSL_REDIRECT = HTTPS_ENABLED
SESSION_COOKIE_SECURE = HTTPS_ENABLED
CSRF_COOKIE_SECURE = HTTPS_ENABLED

_SXEMA = "https" if HTTPS_ENABLED else "http"
CSRF_TRUSTED_ORIGINS = env_list(
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    ",".join(f"{_SXEMA}://{host}" for host in ALLOWED_HOSTS),
)

# HSTS: brauzerga "bu domenga faqat HTTPS orqali kir" deydi.
# ⚠️ Birinchi deploy'da kichik qiymatdan boshlang (masalan 3600). Sertifikat
#    buzilsa, uzun HSTS saytni brauzerlarda uzoq muddat yopib qo'yadi.
# HTTPS o'chiq bo'lsa HSTS ham 0 — aks holda brauzer domenni "faqat HTTPS"
# deb eslab qoladi va TLS yo'q joyda sayt umuman ochilmaydi.
SECURE_HSTS_SECONDS = env_int("DJANGO_HSTS_SECONDS", 3600) if HTTPS_ENABLED else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("DJANGO_HSTS_SUBDOMAINS", True)
SECURE_HSTS_PRELOAD = env_bool("DJANGO_HSTS_PRELOAD", False)

# `check --deploy` HSTS preload yoqilmaganini ogohlantiradi (W021).
# Bu ATAYLAB o'chirilgan: preload ro'yxatiga qo'shilish amalda QAYTARIB
# BO'LMAYDIGAN qadam — chiqarish oylar davom etadi va shu vaqt davomida
# HTTPS'da muammo bo'lsa sayt brauzerlarda umuman ochilmaydi.
#
# Qachon yoqiladi: domen barqaror, sertifikat avtomatik yangilanadi va
# HSTS 1 yil (31536000) bilan bir necha oy muammosiz ishlaganidan KEYIN.
# O'shanda DJANGO_HSTS_PRELOAD=1 qiling — ogohlantirish o'zi yo'qoladi.
if not SECURE_HSTS_PRELOAD:
    SILENCED_SYSTEM_CHECKS = ["security.W021"]


# --------------------------------------------------------------------------
# Statik fayllar — hash bilan (uzoq muddatli kesh xavfsiz bo'lsin)
# --------------------------------------------------------------------------
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.ManifestStaticFilesStorage",
    },
}


# --------------------------------------------------------------------------
# Email
# --------------------------------------------------------------------------
# ⚠️ Django 6.1 dan boshlab EMAIL_BACKEND / EMAIL_HOST / EMAIL_PORT va
#    boshqalar ESKIRGAN (Django 7.0 da olib tashlanadi). Yangi shakl —
#    MAILERS: backend parametrlari `OPTIONS` orqali beriladi.
#    Eski va yangi sozlamalarni BIRGA yozib bo'lmaydi.
#    `DEFAULT_FROM_EMAIL` eskirmagan — u joyida qoladi.
MAILERS = {
    "default": {
        "BACKEND": "django.core.mail.backends.smtp.EmailBackend",
        "OPTIONS": {
            "host": env("EMAIL_HOST", ""),
            "port": env_int("EMAIL_PORT", 587),
            "username": env("EMAIL_HOST_USER", ""),
            "password": env("EMAIL_HOST_PASSWORD", ""),
            "use_tls": env_bool("EMAIL_USE_TLS", True),
            # SMTP javob bermasa Gunicorn worker'i osilib qolmasin
            "timeout": env_int("EMAIL_TIMEOUT", 10),
        },
    },
}

DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "Dard.uz <yordam@dard.uz>")

ADMINS = [("Admin", email) for email in env_list("DJANGO_ADMIN_EMAILS")]
