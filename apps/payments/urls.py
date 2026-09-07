"""To'lovlar — URL manzillari (D6-T2).

⚠️⚠️ WEBHOOK MANZILLARI O'ZGARMAYDI. Ular Click merchant kabinetiga
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
    path("pro/sotib-olish/", views.sotib_olish, name="pro_sotib_olish"),
    path("tolov/<int:pk>/natija/", views.natija, name="tolov_natijasi"),
    # Click uchun (merchant kabinetida shu manzillar ko'rsatiladi)
    path("tolov/click/prepare/", views.click_prepare, name="click_prepare"),
    path("tolov/click/complete/", views.click_complete, name="click_complete"),
]
