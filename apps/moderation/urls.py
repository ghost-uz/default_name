"""Moderatsiya — URL manzillari (D2-T1)."""

from django.urls import path

from . import views

urlpatterns = [
    path("shikoyat/dard/<int:pk>/", views.dard_shikoyat, name="dard_shikoyat"),
    path("shikoyat/yechim/<int:pk>/", views.yechim_shikoyat, name="yechim_shikoyat"),
]
