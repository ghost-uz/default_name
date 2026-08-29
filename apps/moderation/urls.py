"""Moderatsiya — URL manzillari (D2-T1, D2-T2)."""

from django.urls import path

from . import views

urlpatterns = [
    path("shikoyat/dard/<int:pk>/", views.dard_shikoyat, name="dard_shikoyat"),
    path("shikoyat/yechim/<int:pk>/", views.yechim_shikoyat, name="yechim_shikoyat"),
    # ⚠️ Moderatsiya navbati — staff bo'lmaganga 404 (views.moderator_kerak).
    #    Manzil chiroyli bo'lishi shart emas, lekin taxmin qilinadigan
    #    bo'lgani ma'qul: moderator uni yodda saqlaydi.
    path("moderatsiya/", views.navbat, name="moderatsiya_navbat"),
    path("moderatsiya/jurnal/", views.jurnal, name="moderatsiya_jurnal"),
    path(
        "moderatsiya/qollanma/",
        views.qollanma,
        name="moderatsiya_qollanma",
    ),
    path(
        "moderatsiya/qaror/dard/<int:pk>/",
        views.qaror_muammo,
        name="moderatsiya_qaror_muammo",
    ),
    path(
        "moderatsiya/qaror/yechim/<int:pk>/",
        views.qaror_yechim,
        name="moderatsiya_qaror_yechim",
    ),
    path(
        "moderatsiya/bekor/<int:pk>/",
        views.qarorni_bekor,
        name="moderatsiya_bekor",
    ),
    # ⚠️ Foydalanuvchini cheklash (D2-T11) — `pk` FOYDALANUVCHINIKI,
    #    kontentniki emas. Chora kontent ustidan, cheklov esa ODAM
    #    ustidan: manzil ham shu farqni ko'rsatib turishi kerak.
    path(
        "moderatsiya/cheklash/<int:pk>/",
        views.foydalanuvchini_cheklash_view,
        name="moderatsiya_cheklash",
    ),
    path(
        "moderatsiya/cheklov-yechish/<int:pk>/",
        views.cheklovni_yechish_view,
        name="moderatsiya_cheklov_yechish",
    ),
]
