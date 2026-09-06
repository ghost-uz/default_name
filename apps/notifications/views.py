"""Bildirishnomalar markazi (D5-T1)."""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from .services import bildirishnomalar_royxati, hammasini_oqilgan_deb_belgilash


@login_required
def bildirishnomalar(request: HttpRequest) -> HttpResponse:
    """Ro'yxat + "hammasi o'qildi" (qabul mezoni).

    ⚠️⚠️ RO'YXAT AVVAL OLINADI, KEYIN O'QILGAN DEB BELGILANADI.
       Teskari tartibda foydalanuvchi qaysi bildirishnomalar YANGI
       ekanini ko'ra olmasdi: sahifa ochilgan zahoti hammasi "eski"
       bo'lib qolardi va ro'yxat mutlaqo bir xil ko'rinardi.

       Endi esa sahifada yangilari ajratib ko'rsatiladi, KEYINGI
       tashrifda esa ular oddiy qatorga aylanadi.

    ⚠️ Sahifalash OFFSET: bildirishnomalar dolzarbligini tez yo'qotadi
       va hech kim 5-sahifaga o'tmaydi (qidiruv sahifasi bilan bir xil
       mulohaza, D4-T3).
    """
    sahifalovchi = Paginator(
        bildirishnomalar_royxati(user=request.user),
        settings.BILDIRISHNOMA_SAHIFA_HAJMI,
    )
    sahifa = sahifalovchi.get_page(request.GET.get("sahifa"))

    # ⚠️ `list(...)` ATAYLAB: quyidagi `update()` dan OLDIN bajarilsin,
    #    aks holda `okilgan_at` allaqachon to'ldirilgan holda o'qilardi
    #    (QuerySet dangasa).
    bildirishnomalar_royxati_sahifasi = list(sahifa.object_list)

    hammasini_oqilgan_deb_belgilash(user=request.user)

    return render(
        request,
        "notifications/royxat.html",
        {
            "active_nav": "profile",
            "bildirishnomalar": bildirishnomalar_royxati_sahifasi,
            "sahifa": sahifa,
        },
    )
