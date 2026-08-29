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
    # Ekspert tasdiqlash oqimi (D3-T5)
    path("ekspert/ariza/", views.ekspert_ariza, name="ekspert_ariza"),
    # ⚠️ Staff yo'llari `moderatsiya/` prefiksida — moderator ularni
    #    bitta joyda kutadi, garchi kod `accounts` ilovasida bo'lsa ham.
    path(
        "moderatsiya/ekspertlar/",
        views.ekspert_navbati,
        name="ekspert_navbati",
    ),
    # ⚠️⚠️ MAXFIY HUJJAT — bu manzil yagona kirish yo'li va u staff'ga
    #    cheklangan. Fayl `MAXFIY_ROOT` da, ya'ni veb-server uni
    #    to'g'ridan-to'g'ri uzata olmaydi.
    path(
        "moderatsiya/ekspert/<int:pk>/hujjat/",
        views.ekspert_hujjati,
        name="ekspert_hujjati",
    ),
    path(
        "moderatsiya/ekspert/<int:pk>/qaror/",
        views.ekspert_qarori,
        name="ekspert_qarori",
    ),
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
