"""Muammolar — URL manzillari (D1-T7, D1-T8).

⚠️ URL NOMLARI `apps/common/maket.py` dagi bilan AYNAN BIR XIL.
   Maket shu nomlarni ishlatib yozilgan (`{% url 'feed' %}`), shuning
   uchun ko'rinishlar haqiqiylashganda shablonlarga tegish shart emas —
   faqat maketdan tegishli qator o'chiriladi.
"""

from django.urls import path

from . import views

urlpatterns = [
    path("", views.feed, name="feed"),
    # ⚠️ Yo'nalish URL'da emas, POST tanasida (`qiymat=+1|-1`).
    #    Sabab: apps/common/vote_views.py -> ovoz_qiymatini_oqish().
    path("ovoz/dard/<int:pk>/", views.dard_ovoz, name="dard_ovoz"),
]
