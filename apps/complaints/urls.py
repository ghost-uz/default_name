"""Muammolar — URL manzillari (D1-T7, D1-T8, D1-T9).

⚠️ URL NOMLARI `apps/common/maket.py` dagi bilan AYNAN BIR XIL.
   Maket shu nomlarni ishlatib yozilgan (`{% url 'feed' %}`), shuning
   uchun ko'rinishlar haqiqiylashganda shablonlarga tegish shart emas —
   faqat maketdan tegishli qator o'chiriladi.
"""

from django.urls import path

from . import views

urlpatterns = [
    path("", views.feed, name="feed"),
    path("yozish/", views.complaint_create, name="complaint_create"),
    path("dard/<slug:slug>/", views.complaint_detail, name="complaint_detail"),
    path("dard/<slug:slug>/tahrirlash/", views.complaint_edit, name="complaint_edit"),
    # ⚠️ Yo'nalish URL'da emas, POST tanasida (`qiymat=+1|-1`).
    #    Sabab: apps/common/vote_views.py -> ovoz_qiymatini_oqish().
    path("ovoz/dard/<int:pk>/", views.dard_ovoz, name="dard_ovoz"),
]
