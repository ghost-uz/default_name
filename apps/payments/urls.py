"""To'lovlar — URL manzillari (D6-T2).

⚠️⚠️ WEBHOOK MANZILLARI O'ZGARMAYDI. Ular Click/Payme kabinetiga
   QO'LDA kiritiladi va u yerdagi qiymatni biz ko'rmaymiz. Manzilni
   o'zgartirish to'lovlarni JIMGINA to'xtatardi: sayt ishlaydi,
   tugma ishlaydi, faqat obuna berilmaydi.

   Shuning uchun ular `ADMIN_URL` kabi muhitdan OLINMAYDI ham —
   maxfiylikdan foyda yo'q (himoya imzo), zarar esa aniq: prod va
   sandbox manzillari farq qilib qolardi.
"""

from django.urls import path

from . import views

urlpatterns = [
    # Odam uchun
    path("pro/", views.pro, name="pro"),
    # ⚠️ Provayder MANZILDA, forma maydonida emas: havolani
    #    ulashish va jurnalda ko'rish oson bo'lsin. Qiymat baribir
    #    ko'rinishda ro'yxat bilan tekshiriladi.
    path(
        "pro/sotib-olish/<slug:provayder>/",
        views.sotib_olish,
        name="pro_sotib_olish",
    ),
    path("tolov/<int:pk>/natija/", views.natija, name="tolov_natijasi"),
    # D6-T4 — postni ko'tarish. ⚠️ Faqat MUALLIF uchun; begonaga 404.
    path("kotarish/<int:pk>/", views.kotarish, name="kotarish"),
    path(
        "kotarish/<int:pk>/sotib-olish/<slug:provayder>/",
        views.kotarish_sotib_olish,
        name="kotarish_sotib_olish",
    ),
    # Click uchun (merchant kabinetida shu manzillar ko'rsatiladi)
    path("tolov/click/prepare/", views.click_prepare, name="click_prepare"),
    path("tolov/click/complete/", views.click_complete, name="click_complete"),
    # Payme uchun (kabinetda «Endpoint URL» sifatida ko'rsatiladi).
    # ⚠️ BITTA manzil — Payme'ning oltita metodi ham shu yerga
    #    JSON-RPC bo'lib keladi.
    path("tolov/payme/", views.payme_webhook, name="payme_webhook"),
]
