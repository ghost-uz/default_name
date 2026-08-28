"""Shikoyat yuborish (D2-T1).

Moderatsiya navbati (staff interfeysi) — D2-T2.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from apps.complaints.models import Complaint
from apps.solutions.models import Solution

from .forms import ReportForm
from .models import ReportReason
from .services import AllaqachonShikoyatQilingan, shikoyat_yuborish


def _xavfsiz_next(request: HttpRequest, zaxira: str) -> str:
    """Begona manzilga yo'naltirmaymiz (ochiq yo'naltirish)."""
    xom = request.GET.get("next") or request.POST.get("next") or ""
    if xom and url_has_allowed_host_and_scheme(
        xom, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return xom
    return zaxira


def _shikoyat_sahifasi(
    request: HttpRequest, *, maqsad, tur: str, sarlavha: str
) -> HttpResponse:
    """Shikoyat formasi — muammo va yechim uchun umumiy.

    ⚠️ MAKETDA MODAL EDI, BU YERDA ALOHIDA SAHIFA — ataylab.

       Modal bitta obyekt uchun yaxshi, lekin batafsil sahifada 15 ta
       yechim bo'lishi mumkin: har biriga modal chizish 15 marta
       takrorlangan markup va 15 ta yashirin dialog degani.

       Alohida sahifa yana ikki narsani beradi: JavaScript'siz ishlaydi
       va qoidalar matnini to'liq ko'rsatishga joy bor — shikoyat
       yuborishdan oldin odam nima qoidabuzarlik ekanini o'qiy oladi.

       Keyinchalik uni HTMX bilan dialogga yuklash mumkin (`hx-get`),
       lekin manzil va forma o'zgarmaydi.
    """
    keyingi = _xavfsiz_next(request, maqsad.get_absolute_url())

    if request.method == "POST":
        form = ReportForm(request.POST)
        if form.is_valid():
            kwargs = {tur: maqsad}
            try:
                # Eskalatsiya bayrog'i ATAYLAB olinmaydi — pastdagi
                # izohga qarang: u foydalanuvchiga ko'rsatilmaydi.
                shikoyat_yuborish(
                    reporter=request.user,
                    reason=form.cleaned_data["reason"],
                    comment=form.cleaned_data["comment"],
                    **kwargs,
                )
            except AllaqachonShikoyatQilingan as exc:
                form.add_error(None, exc.messages[0])
            except PermissionDenied as exc:
                return HttpResponseForbidden(str(exc))
            else:
                # ⚠️ Foydalanuvchiga eskalatsiya HAQIDA AYTILMAYDI.
                #    "Yana 2 ta shikoyat kerak" degan xabar odamlarni
                #    kelishib shikoyat qilishga undardi — ya'ni tizimni
                #    o'yinga aylantirardi.
                messages.success(
                    request,
                    "Shikoyatingiz yuborildi. Moderatorlar ko'rib chiqadi.",
                )
                return redirect(keyingi)
    else:
        form = ReportForm()

    return render(
        request,
        "moderation/shikoyat.html",
        {
            "form": form,
            "maqsad": maqsad,
            "sarlavha": sarlavha,
            "next": keyingi,
            # `XAVF` sababi alohida ko'rsatiladi (D2-T6 ga tayyorgarlik).
            "xavf_sababi": ReportReason.XAVF,
        },
    )


@login_required
def dard_shikoyat(request: HttpRequest, pk: int) -> HttpResponse:
    """Muammoga shikoyat.

    ⚠️ `visible()` — yashirilgan postga shikoyat qilishning ma'nosi yo'q:
       u allaqachon navbatda yoki olib tashlangan.
    """
    muammo = get_object_or_404(Complaint.objects.visible(), pk=pk)
    return _shikoyat_sahifasi(
        request, maqsad=muammo, tur="complaint", sarlavha=muammo.title
    )


@login_required
def yechim_shikoyat(request: HttpRequest, pk: int) -> HttpResponse:
    """Yechimga shikoyat."""
    yechim = get_object_or_404(Solution.objects.visible(), pk=pk)
    return _shikoyat_sahifasi(
        request,
        maqsad=yechim,
        tur="solution",
        sarlavha=yechim.content[:80],
    )
