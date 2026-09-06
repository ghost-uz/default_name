"""Kontakt so'rovi va suhbat — ko'rinishlar (D6-T5)."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.common.ratelimit import tezlik_cheklovi
from apps.solutions.models import Solution

from .models import KontaktSorovi, SorovHolati, Suhbat
from .selectors import suhbatlar_royxati
from .services import (
    kontakt_sorash,
    okilgan_deb_belgilash,
    sorovga_javob,
    suhbatni_yopish,
    xabar_yozish,
)


def _sorovni_olish(pk: int, user) -> KontaktSorovi:
    """⚠️⚠️ BEGONAGA 404, 403 EMAS.

    `403` «bu so'rov bor, lekin sizga ruxsat yo'q» degani — ya'ni
    kimning kim bilan yozishayotganini tasdiqlab beradi. Shaxsiy
    kanalda bu ma'lumotning o'zi oshkor qilinmasligi kerak
    (D2-T2 dagi moderatsiya navbati bilan bir xil mulohaza).
    """
    sorov = get_object_or_404(
        KontaktSorovi.objects.select_related(
            "solution__complaint__author", "solution__author", "soragan"
        ),
        pk=pk,
    )
    ishtirokchilar = {
        sorov.solution.complaint.author_id,
        sorov.solution.author_id,
    }
    if user.pk not in ishtirokchilar:
        raise Http404
    return sorov


def _suhbatni_olish(pk: int, user) -> Suhbat:
    suhbat = get_object_or_404(
        Suhbat.objects.select_related(
            "sorov__solution__complaint__author",
            "sorov__solution__author",
            "sorov__solution__complaint__category",
        ),
        pk=pk,
    )
    if not suhbat.ishtirokchimi(user):
        raise Http404  # sabab `_sorovni_olish` da
    return suhbat


@login_required
def suhbatlar(request: HttpRequest) -> HttpResponse:
    """Mening suhbatlarim va javob kutayotgan so'rovlar."""
    royxat, sorovlar = suhbatlar_royxati(user=request.user)
    return render(
        request,
        "suhbat/royxat.html",
        {
            "active_nav": "profile",
            "suhbatlar": royxat,
            "sorovlar": sorovlar,
        },
    )


@login_required
@tezlik_cheklovi("suhbat_xabar")
def suhbat(request: HttpRequest, pk: int) -> HttpResponse:
    """Bitta suhbat — o'qish va yozish.

    ⚠️ Tezlik cheklovi FAQAT YOZISH so'rovlarini sanaydi (D2-T4),
       ya'ni suhbatni qayta-qayta ochish cheklovga tushmaydi.
    """
    obj = _suhbatni_olish(pk, request.user)

    if request.method == "POST":
        try:
            xabar_yozish(
                suhbat=obj, author=request.user, matn=request.POST.get("matn", "")
            )
        except (ValidationError, PermissionDenied) as xato:
            messages.error(request, str(getattr(xato, "messages", [xato])[0]))
        return redirect("suhbat", pk=obj.pk)

    # ⚠️ Ro'yxat o'qilgan deb belgilashdan OLDIN olinadi (D5-T1 dagi
    #    bir xil sabab: foydalanuvchi nima yangi ekanini ko'rsin).
    # ⚠️ `visible()` — moderator YASHIRGAN xabar ISHTIROKCHIGA HAM
    #    ko'rinmaydi. Shaxsiy suhbatda bu ayniqsa muhim: chora
    #    ko'rilgan xabar o'sha yerda turaversa, moderatsiyaning
    #    ma'nosi qolmasdi (D2-T3 invariantining suhbatdagi shakli).
    xabarlar = list(
        obj.xabarlar.visible().select_related("author").order_by("created_at", "id")
    )
    # ⚠️ Hamma xabar AYNAN SHU suhbatga tegishli — `xabar.suhbat` ni
    #    oldindan to'ldirish har xabardagi qo'shimcha so'rovni yo'q
    #    qiladi (`Xabar.korinadigan_nom` unga tayanadi).
    for xabar in xabarlar:
        xabar.suhbat = obj
        # ⚠️ Yorliq SHU YERDA hisoblanadi: Django shabloni argumentli
        #    metod chaqira olmaydi, `xabar.nom(request.user)` esa
        #    kuzatuvchini biladi.
        xabar.korsatiladigan_nom = xabar.nom(request.user)
    okilgan_deb_belgilash(suhbat=obj, user=request.user)

    return render(
        request,
        "suhbat/suhbat.html",
        {
            "active_nav": "profile",
            "suhbat": obj,
            "xabarlar": xabarlar,
        },
    )


@login_required
def kontakt_sorovi(request: HttpRequest, pk: int) -> HttpResponse:
    """So'rovni ko'rish va javob berish (qabul / rad)."""
    sorov = _sorovni_olish(pk, request.user)

    if request.method == "POST":
        try:
            sorovga_javob(
                sorov=sorov,
                user=request.user,
                qabul=request.POST.get("javob") == "qabul",
            )
        except (ValidationError, PermissionDenied) as xato:
            messages.error(request, str(getattr(xato, "messages", [xato])[0]))
            return redirect("kontakt_sorovi", pk=sorov.pk)

        sorov.refresh_from_db()
        if sorov.holat == SorovHolati.QABUL_QILINDI:
            messages.success(request, "Suhbat ochildi.")
            return redirect("suhbat", pk=sorov.suhbat.pk)
        messages.success(request, "So'rov rad etildi.")
        return redirect("suhbatlar")

    return render(
        request,
        "suhbat/sorov.html",
        {
            "active_nav": "profile",
            "sorov": sorov,
            "javob_berish_mumkinmi": (
                sorov.holat == SorovHolati.KUTILMOQDA
                and sorov.qarshi_tomon_id == request.user.pk
            ),
        },
    )


@login_required
@require_POST
@tezlik_cheklovi("kontakt_sorovi")
def sorov_yuborish(request: HttpRequest, pk: int) -> HttpResponse:
    """Qabul qilingan yechim uchun suhbat so'raydi."""
    yechim = get_object_or_404(
        Solution.objects.visible().select_related("complaint", "author"), pk=pk
    )
    try:
        sorov = kontakt_sorash(solution=yechim, soragan=request.user)
    except (ValidationError, PermissionDenied) as xato:
        messages.error(request, str(getattr(xato, "messages", [xato])[0]))
        return redirect(yechim.complaint.get_absolute_url())

    messages.success(request, "So'rov yuborildi — javobni kutamiz.")
    return redirect("kontakt_sorovi", pk=sorov.pk)


@login_required
@require_POST
def yopish(request: HttpRequest, pk: int) -> HttpResponse:
    obj = _suhbatni_olish(pk, request.user)
    suhbatni_yopish(suhbat=obj, user=request.user)
    messages.success(request, "Suhbat yopildi.")
    return redirect("suhbat", pk=obj.pk)
