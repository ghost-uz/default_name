"""Yechimlar — ko'rinishlar (D1-T8).

Yechim yozish va qabul qilish oqimi — D1-T10.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.common.ratelimit import tezlik_cheklovi
from apps.common.vote_views import (
    htmx_sorovimi,
    ovoz_qiymatini_oqish,
    ovoz_ruxsati,
    ovozdan_keyingi_manzil,
)
from apps.common.voting import cast_vote
from apps.complaints.models import Complaint
from apps.moderation.services import avtomatik_belgilash

from .forms import SolutionForm
from .models import Solution, SolutionVote
from .services import accept_solution, unaccept_solution, yechim_yozish


@require_POST
@tezlik_cheklovi("ovoz")
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


# ===========================================================================
# Yechim yozish va qabul qilish (D1-T10)
# ===========================================================================
@login_required
@require_POST
@tezlik_cheklovi("yechim_yozish")
def solution_create(request: HttpRequest, slug: str) -> HttpResponse:
    """Muammoga yechim qo'shish.

    ⚠️ POST/Redirect/GET: muvaffaqiyatda qayta yo'naltiriladi, aks holda
       "orqaga" tugmasi brauzerdan formani QAYTA YUBORISHNI so'raydi va
       foydalanuvchi bilmasdan ikkinchi yechim yozib yuboradi.

    ⚠️ Xato bo'lganda sahifa QAYTA RENDER qilinadi (yo'naltirish emas):
       yozilgan matn yo'qolmasligi kerak. Uzun javobni qaytadan yozish —
       odamni ketkazadigan turdagi tajriba.
    """
    muammo = get_object_or_404(Complaint.objects.visible(), slug=slug)

    # ⚠️ `is_closed` EMAS: yechilgan muammoga ham javob yozish mumkin
    #    (muallif qabul qilishni yaxshiroq yechimga o'tkaza oladi).
    #    Batafsil: `Complaint.yangi_yechim_qabul_qiladimi`.
    if not muammo.yangi_yechim_qabul_qiladimi:
        return HttpResponseForbidden(
            "Bu muammo yopilgan — yangi yechim qabul qilinmaydi."
        )

    form = SolutionForm(request.POST, foydalanuvchi=request.user)
    if form.is_valid():
        yechim = yechim_yozish(
            complaint=muammo,
            author=request.user,
            content=form.cleaned_data["content"],
            is_anonymous=form.cleaned_data["is_anonymous"],
        )
        # ⚠️ Shubhali bo'lsa navbatga tushadi, yashirilmaydi (D2-T5).
        avtomatik_belgilash(target=yechim, baho=form.spam_bahosi)
        messages.success(request, "Yechimingiz qo'shildi.")
        return redirect(yechim.get_absolute_url())

    # ⚠️ Xatoda batafsil sahifa QAYTA RENDER qilinadi va forma xatolari
    #    bilan birga uzatiladi. Import funksiya ICHIDA: modul darajasida
    #    `complaints.views` <-> `solutions.views` aylanma import bo'lardi.
    from apps.complaints.views import complaint_detail

    return complaint_detail(request, slug=slug, solution_form=form)


@login_required
@require_POST
def solution_accept(request: HttpRequest, pk: int) -> HttpResponse:
    """Muammo muallifi yechimni qabul qiladi (D1-T10).

    ⚠️ Butun sahifa qayta yuklanadi (HTMX EMAS) — ATAYLAB.
       Qabul qilish sahifaning bir nechta joyini o'zgartiradi: muammoning
       "Yechilgan" nishoni, yechimlar TARTIBI (qabul qilingani birinchiga
       chiqadi), eski qabul qilinganning belgisi va muallifning karmasi.
       Bularni bo'lak-bo'lak almashtirish HTMX'da bir nechta
       `hx-swap-oob` talab qilardi va bittasi unutilsa sahifa
       ZIDDIYATLI holatda qolardi ("Yechilgan" yozuvi bor, lekin qaysi
       yechim qabul qilingani ko'rinmaydi).
    """
    yechim = get_object_or_404(Solution.objects.visible(), pk=pk)
    try:
        accept_solution(solution=yechim, by_user=request.user)
    except PermissionDenied as exc:
        return HttpResponseForbidden(str(exc))
    except ValidationError as exc:
        return HttpResponseBadRequest("; ".join(exc.messages))

    messages.success(request, "Yechim qabul qilindi.")
    return redirect(yechim.get_absolute_url())


@login_required
@require_POST
def solution_unaccept(request: HttpRequest, pk: int) -> HttpResponse:
    """Qabul qilishni bekor qilish.

    Qaytarib bo'lmaydigan tugma foydalanuvchini umuman bosmaslikka
    undaydi — shuning uchun bu yo'l ochiq qoldirilgan.
    """
    yechim = get_object_or_404(Solution.objects.visible(), pk=pk)
    try:
        unaccept_solution(solution=yechim, by_user=request.user)
    except PermissionDenied as exc:
        return HttpResponseForbidden(str(exc))

    messages.info(request, "Qabul qilish bekor qilindi.")
    return redirect(yechim.get_absolute_url())
