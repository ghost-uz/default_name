"""Reklama — URL manzillari (D6-T6).

⚠️ Manzil qisqa va BARQAROR: u reklama beruvchining hisobotida va
   bosilgan havolalarda qoladi.
"""

from django.urls import path

from . import views

urlpatterns = [
    path("reklama/<int:pk>/", views.reklama_bosildi, name="reklama_bosildi"),
]
