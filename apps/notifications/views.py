"""Bildirishnomalar markazi (D5-T1)."""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render

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


@login_required
def sozlamalar(request: HttpRequest) -> HttpResponse:
    """Bildirishnoma sozlamalari (D5-T4).

    ⚠️ Sozlama YETKAZISHNI boshqaradi, yozuvni emas: o'chirilgan turda
       ham bildirishnoma markazda ko'rinadi (sabab `sozlama.py` da).
    """
    from django.contrib import messages

    from .forms import SozlamaForm

    sozlama = getattr(request.user, "bildirishnoma_sozlamasi", None)

    if request.method == "POST":
        form = SozlamaForm(request.POST, sozlama=sozlama)
        if form.is_valid():
            form.saqlash(user=request.user)
            messages.success(request, "Sozlamalar saqlandi.")
            return redirect("bildirishnoma_sozlamalari")
    else:
        form = SozlamaForm(sozlama=sozlama)

    return render(
        request,
        "notifications/sozlamalar.html",
        {"active_nav": "profile", "form": form},
    )
