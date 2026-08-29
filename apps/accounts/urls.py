"""Foydalanuvchilar — URL manzillari (D1-T1).

⚠️ URL nomlari maketdagi bilan bir xil (`login`) — shablonlarga tegilmaydi.
"""

from django.urls import path

from . import views

urlpatterns = [
    path("kirish/", views.login_page, name="login"),
    path("kirish/telegram/", views.telegram_callback, name="telegram_callback"),
    path("chiqish/", views.logout_view, name="logout"),
    # Shartlarga rozilik (D2-T10)
    path("rozilik/", views.rozilik, name="rozilik"),
    # ⚠️ Profil ENG OXIRIDA turishi kerak (`@<username>/` juda keng
    #    naqsh) — lekin bu faylda u boshqa yo'llardan keyin keladi va
    #    hammasi `/@` prefiksi bilan farqlanadi, ya'ni to'qnashuv yo'q.
    #    Profil sahifasi (D3-T4)
    path("@<str:username>/", views.profile, name="profile"),
    # Foydalanuvchilar o'zaro bloklashi (D2-T11)
    path(
        "bloklash/@<str:username>/",
        views.foydalanuvchini_bloklash,
        name="foydalanuvchini_bloklash",
    ),
    path(
        "blokni-yechish/@<str:username>/",
        views.blokni_bekor_qilish,
        name="blokni_bekor_qilish",
    ),
    # Hisob sozlamalari (D2-T8)
    path("hisob/", views.hisob, name="hisob"),
    path("hisob/eksport/", views.hisob_eksport, name="hisob_eksport"),
    path(
        "hisob/eksport/<int:pk>/",
        views.hisob_eksport_yuklash,
        name="hisob_eksport_yuklash",
    ),
    path("hisob/ochirish/", views.hisob_ochirish, name="hisob_ochirish"),
]
