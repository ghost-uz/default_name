"""Yechimlar — URL manzillari (D1-T8)."""

from django.urls import path

from . import views

urlpatterns = [
    path("ovoz/yechim/<int:pk>/", views.yechim_ovoz, name="yechim_ovoz"),
]
