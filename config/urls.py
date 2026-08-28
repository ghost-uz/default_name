"""Dard.uz — ildiz URL konfiguratsiyasi.

URL manzillari o'zbekcha: /dard/<slug>/, /kirish/, /ekspertlar/ ...
Sabab: SEO (5-bo'lim) va foydalanuvchi uchun tushunarli havolalar.
Ilova URL'lari o'z fazasida shu yerga ulanadi.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from apps.common.views import health

urlpatterns = [
    # Konteyner healthcheck'i (D0-T3). Autentifikatsiyasiz — Docker'ning
    # o'zi chaqiradi. D7-T2 da /health/deep/ qo'shiladi.
    path("health/", health, name="health"),
    # Admin manzili muhitdan — standart /admin/ eng ko'p skanerlanadigan yo'l
    path(f"{settings.ADMIN_URL}/", admin.site.urls),
]

# ⚠️ HAQIQIY KO'RINISHLAR AVVAL, maket KEYIN.
#    Ikkalasida bir xil nom bo'lsa `reverse()` OXIRGISINI oladi — ya'ni
#    maket haqiqiy manzilni jimgina bosib qo'yardi. Shuning uchun maketdan
#    tayyor bo'lgan sahifalar BIRMA-BIR o'chirib boriladi (hozircha: feed).
urlpatterns += [
    path("", include("apps.accounts.urls")),
    path("", include("apps.complaints.urls")),
    path("", include("apps.solutions.urls")),
    path("", include("apps.moderation.urls")),
]

# ⚠️ VAQTINCHALIK (D0-T6): hali yozilmagan sahifalarning maketi.
#    M1 oxirida butunlay o'chiriladi.
#    Qolgani: category_list, expert_list, profile, landing.
urlpatterns += [path("", include("apps.common.maket"))]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
