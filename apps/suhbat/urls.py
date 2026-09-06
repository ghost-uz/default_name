"""Suhbatlar — URL manzillari (D6-T5)."""

from django.urls import path

from . import views

urlpatterns = [
    path("suhbatlar/", views.suhbatlar, name="suhbatlar"),
    path("suhbatlar/<int:pk>/", views.suhbat, name="suhbat"),
    path("suhbatlar/<int:pk>/yopish/", views.yopish, name="suhbatni_yopish"),
    # ⚠️ So'rov manzili SUHBATDAN alohida: so'rov qabul qilinmaguncha
    #    suhbat mavjud emas va uning `pk` i ham yo'q.
    path("suhbatlar/sorov/<int:pk>/", views.kontakt_sorovi, name="kontakt_sorovi"),
    # ⚠️ `pk` — YECHIMNIKI: so'rov aynan qabul qilingan yechimdan
    #    boshlanadi (D6-T5 tavsifi).
    path(
        "suhbatlar/sorov/yuborish/<int:pk>/",
        views.sorov_yuborish,
        name="kontakt_sorov_yuborish",
    ),
]
