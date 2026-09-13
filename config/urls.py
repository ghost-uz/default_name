"""Dard.uz — ildiz URL konfiguratsiyasi.

URL manzillari o'zbekcha: /dard/<slug>/, /kirish/, /ekspertlar/ ...
Sabab: SEO (5-bo'lim) va foydalanuvchi uchun tushunarli havolalar.
Ilova URL'lari o'z fazasida shu yerga ulanadi.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path

from apps.common.views import health, robots
from apps.complaints.sitemaps import SITEMAPLAR

urlpatterns = [
    # Konteyner healthcheck'i (D0-T3). Autentifikatsiyasiz — Docker'ning
    # o'zi chaqiradi. D7-T2 da /health/deep/ qo'shiladi.
    path("health/", health, name="health"),
    # SEO (D4-T5).
    # ⚠️ Ikkalasi ham ILDIZDA bo'lishi SHART: qidiruv tizimlari ularni
    #    aynan `/sitemap.xml` va `/robots.txt` da izlaydi, boshqa yo'lda
    #    turgan fayl umuman topilmaydi.
    path("sitemap.xml", sitemap, {"sitemaps": SITEMAPLAR}, name="sitemap"),
    path("robots.txt", robots, name="robots"),
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
    path("", include("apps.notifications.urls")),
    path("", include("apps.suhbat.urls")),
    path("", include("apps.payments.urls")),
    path("", include("apps.reklama.urls")),
    # Huquqiy sahifalar (D2-T10)
    path("", include("apps.common.huquqiy")),
]

# ⚠️ VAQTINCHALIK (D0-T6): hali haqiqiy ko'rinishi yozilmagan sahifalarning
#    maketi. Qolgani: category_list, expert_list, landing.
#
#    ⚠️ Fayl BIRDAN emas, BIRMA-BIR bo'shatiladi: har safar haqiqiy
#       ko'rinish yozilganda tegishli yo'l maketdan olib tashlanadi
#       (`feed`, `complaint_create`, `complaint_detail` shunday ko'chgan).
#       Ya'ni "M1 oxirida o'chiriladi" degan dastlabki reja amalda
#       bajarilmadi va bajarilishi ham shart emas — bu uchta sahifa
#       o'z taskini kutadi.
urlpatterns += [path("", include("apps.common.maket"))]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
