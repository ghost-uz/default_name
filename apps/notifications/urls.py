"""Bildirishnomalar — URL manzillari (D5-T1)."""

from django.urls import path

from . import views

urlpatterns = [
    # Manzil o'zbekcha (config/urls.py qoidasi).
    path("bildirishnomalar/", views.bildirishnomalar, name="bildirishnomalar"),
]
