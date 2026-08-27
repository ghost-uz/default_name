"""Yechimlar — ko'rinishlar (D1-T8).

Yechim yozish va qabul qilish oqimi — D1-T10.
"""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.common.vote_views import (
    htmx_sorovimi,
    ovoz_qiymatini_oqish,
    ovoz_ruxsati,
    ovozdan_keyingi_manzil,
)
from apps.common.voting import cast_vote

from .models import Solution, SolutionVote


@require_POST
def yechim_ovoz(request: HttpRequest, pk: int) -> HttpResponse:
    """Yechimga ovoz berish.

    ⚠️ Muammoning ovozidan FARQI: bu yerda javob FAQAT ovoz blokini
       qaytaradi. Sabab — yechimda karta komponenti yo'q (muammo
       sahifasidagi ro'yxat elementi), ya'ni almashtiriladigan eng kichik
       mustaqil bo'lak aynan shu blok. `layout` POST'da qaytariladi, aks
       holda mobil variant desktop varianti bilan almashib qolardi.
    """
    if (javob := ovoz_ruxsati(request)) is not None:
        return javob

    try:
        qiymat = ovoz_qiymatini_oqish(request)
    except ValueError as exc:
        return HttpResponseBadRequest(str(exc))

    yechim = get_object_or_404(Solution.objects.visible(), pk=pk)

    natija = cast_vote(
        target=yechim,
        vote_model=SolutionVote,
        target_field="solution",
        user=request.user,
        value=qiymat,
    )

    if not htmx_sorovimi(request):
        return redirect(ovozdan_keyingi_manzil(request, yechim.get_absolute_url()))

    return render(
        request,
        "components/_vote.html",
        {
            "obj": yechim,
            "user_vote": natija.value,
            "vote_url": reverse("yechim_ovoz", args=[yechim.pk]),
            # Qaysi variant so'ralgan bo'lsa, o'shanisi qaytadi.
            "layout": "row" if request.POST.get("layout") == "row" else "column",
        },
    )
