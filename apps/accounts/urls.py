"""Foydalanuvchilar — URL manzillari (D1-T1).

⚠️ URL nomlari maketdagi bilan bir xil (`login`) — shablonlarga tegilmaydi.
"""

from django.urls import path

from . import views

urlpatterns = [
    path("kirish/", views.login_page, name="login"),
    path("kirish/telegram/", views.telegram_callback, name="telegram_callback"),
    path("chiqish/", views.logout_view, name="logout"),
]
