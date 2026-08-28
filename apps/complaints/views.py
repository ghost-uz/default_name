"""Muammolar — ko'rinishlar (D1-T7, D1-T8)."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import models
from django.http import (
    Http404,
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.common.vote_views import (
    htmx_sorovimi,
    ovoz_qiymatini_oqish,
    ovoz_ruxsati,
    ovozdan_keyingi_manzil,
)
from apps.common.voting import cast_vote, user_votes_for
from apps.solutions.forms import SolutionForm
from apps.solutions.models import Solution, SolutionVote

from .forms import ComplaintForm
from .models import Complaint, ComplaintVote, Generation
from .selectors import (
    SAHIFA_HAJMI,
    SARALASH_SARLAVHASI,
    SARALASH_TABI,
    filtrni_oqish,
    lenta_queryset,
    yon_panel_kategoriyalari,
)


# ===========================================================================
# Lenta (D1-T7)
# ===========================================================================
def feed(request: HttpRequest) -> HttpResponse:
    """Bosh sahifa: Qaynoq / Yangi / Eng yaxshi / Yechilgan.

    Butun holat URL'da: `?sort=hot&category=moliya&generation=genz`.
    """
    filtr = filtrni_oqish(request.GET)

    # ⚠️ `list(...)` ATAYLAB: quyida `user_votes_for` shu ro'yxatni oladi.
    #    QuerySet bo'lsa u ikki marta bajarilardi (biri ovozlar uchun,
    #    biri shablon uchun) — bu jim ikkilanish, xato bermaydi.
    muammolar = list(lenta_queryset(filtr)[:SAHIFA_HAJMI])

    # ⚠️ Ovozlar BITTA so'rovda olinadi va obyektlarga YOPISHTIRILADI.
    #    Shablonga lug'at berib `user_votes[complaint.pk]` deb yozib
    #    bo'lmaydi — Django shablon tili lug'atni o'zgaruvchi kalit bilan
    #    indekslamaydi. Maxsus filtr yozish mumkin edi, lekin atribut
    #    ancha oddiy va karta shabloni HTMX qayta renderida ham AYNAN
    #    shu nomni o'qiydi.
    ovozlar = user_votes_for(
        vote_model=ComplaintVote,
        target_field="complaint",
        user=request.user,
        targets=muammolar,
    )
    for muammo in muammolar:
        muammo.user_vote = ovozlar.get(muammo.pk)

    return render(
        request,
        "complaints/feed.html",
        {
            "active_nav": "feed",
            "show_search": True,
            "complaints": muammolar,
            "filtr": filtr,
            "sarlavha": SARALASH_SARLAVHASI[filtr.sort],
            "tablar": SARALASH_TABI.items(),
            "kategoriyalar": yon_panel_kategoriyalari(),
            "avlodlar": Generation.choices,
        },
    )


# ===========================================================================
# Ovoz berish (D1-T8)
# ===========================================================================
@require_POST
def dard_ovoz(request: HttpRequest, pk: int) -> HttpResponse:
    """Muammoga ovoz berish / bekor qilish / almashtirish.

    ⚠️ NEGA JAVOB BUTUN KARTANI QAYTARADI, "faqat ovoz bloki"ni EMAS
       Kartada ovoz bloki IKKI marta turadi: desktopda chap ustun,
       mobilda pastki qator (maket qarori — CSS bilan almashadi, ikkalasi
       ham DOM'da). Faqat bittasini almashtirsak, ikkinchisi ESKI sanoq
       bilan qolardi va foydalanuvchi telefonni burganda "ovozim
       yo'qoldi" degan holatni ko'rardi.

       Karta esa baribir butun sahifa emas — D1-T8 mezonining maqsadi
       (lentani qayta render qilmaslik) bajarilyapti. Maket ham shunga
       ulangan: `hx-target="closest [data-vote-group]"`.

    CSRF: `{% csrf_token %}` forma ichida + HTMX `hx-headers` orqali
    (base.html). Django'ning standart middleware'i tekshiradi.
    """
    if (javob := ovoz_ruxsati(request)) is not None:
        return javob

    try:
        qiymat = ovoz_qiymatini_oqish(request)
    except ValueError as exc:
        return HttpResponseBadRequest(str(exc))

    # ⚠️ `visible()` — yashirilgan yoki o'chirilgan postga ovoz berib
    #    bo'lmaydi. Usiz moderator yashirgan post lentadan yo'qolardi,
    #    lekin havolasi bor odam unga ovoz berishda davom etardi.
    muammo = get_object_or_404(Complaint.objects.visible(), pk=pk)

    natija = cast_vote(
        target=muammo,
        vote_model=ComplaintVote,
        target_field="complaint",
        user=request.user,
        value=qiymat,
    )

    if not htmx_sorovimi(request):
        # JavaScript'siz brauzer: forma POST -> qayta yo'naltirish.
        # (POST/Redirect/GET — "orqaga" tugmasi qayta yuborishni so'ramasin.)
        return redirect(ovozdan_keyingi_manzil(request, muammo.get_absolute_url()))

    # Karta shabloni ovoz holatini obyektdan o'qiydi (lenta bilan bir xil yo'l).
    muammo.user_vote = natija.value
    return render(request, "components/_complaint_card.html", {"complaint": muammo})


# ===========================================================================
# Batafsil sahifa (D1-T10 uchun asos)
# ===========================================================================
def complaint_detail(
    request: HttpRequest, slug: str, solution_form: SolutionForm | None = None
) -> HttpResponse:
    """Muammo + unga berilgan yechimlar.

    `solution_form` — yechim formasi XATO bilan qaytganda beriladi
    (apps/solutions/views.py). Shunda foydalanuvchi yozgan matn
    yo'qolmaydi. `TemplateResponse` bilan o'ynash o'rniga oddiy
    parametr: kamroq sehr, ko'proq ko'rinadigan aloqa.

    ⚠️ MUALLIF O'Z YASHIRILGAN POSTINI KO'RA OLADI
       `visible()` bu yerda ATAYLAB qo'llanmaydi. `ModeratedModel`
       docstring'ida yozilganidek: posti yashirilgan foydalanuvchi buni
       BILISHI kerak, aks holda post "yo'qolgan" bo'lib ko'rinadi va
       ishonch yo'qoladi. Boshqalarga esa 404.
    """
    muammo = get_object_or_404(
        Complaint.objects.select_related("author", "category", "accepted_solution"),
        slug=slug,
    )

    ozinikimi = request.user.is_authenticated and muammo.author_id == request.user.pk
    if not muammo.is_publicly_visible and not (ozinikimi or request.user.is_staff):
        raise Http404("Bunday muammo yo'q.")

    # ⚠️ Muallifning o'z ko'rishlari sanalmaydi: aks holda post yozgan odam
    #    uni bir necha marta ochib, sanoqni o'zi shishirib qo'yardi va
    #    "ko'rildi" ko'rsatkichi ma'nosini yo'qotardi.
    if not ozinikimi:
        Complaint.all_objects.filter(pk=muammo.pk).update(
            views_count=models.F("views_count") + 1
        )
        muammo.views_count += 1  # shu render uchun

    yechimlar = list(
        Solution.objects.visible()
        .filter(complaint=muammo)
        .select_related("author")
        # ⚠️ Qabul qilingan yechim DOIM birinchi (maket ham shunday).
        #    `-is_accepted` bo'yicha saralash aynan shuni beradi.
        .order_by("-is_accepted", "-score_cached", "created_at")
    )

    muammo.user_vote = user_votes_for(
        vote_model=ComplaintVote,
        target_field="complaint",
        user=request.user,
        targets=[muammo],
    ).get(muammo.pk)

    yechim_ovozlari = user_votes_for(
        vote_model=SolutionVote,
        target_field="solution",
        user=request.user,
        targets=yechimlar,
    )
    for yechim in yechimlar:
        yechim.user_vote = yechim_ovozlari.get(yechim.pk)

    return render(
        request,
        "complaints/detail.html",
        {
            "active_nav": "feed",
            "complaint": muammo,
            "solutions": yechimlar,
            "solution_form": solution_form or SolutionForm(),
            "muallifmi": ozinikimi,
            "tahrirlay_oladi": muammo.tahrirlay_oladimi(request.user),
        },
    )


# ===========================================================================
# Yaratish va tahrirlash (D1-T9)
# ===========================================================================
@login_required
def complaint_create(request: HttpRequest) -> HttpResponse:
    """Yangi dard yozish."""
    # `getattr` — `@login_required` autentifikatsiyani kafolatlaydi, lekin
    # tip tekshiruvchi buni bilmaydi (`AnonymousUser` da `can_write` yo'q).
    # Zaxira `False`: noma'lum holatda yozishga RUXSAT BERMAYMIZ.
    if not getattr(request.user, "can_write", False):
        return HttpResponseForbidden("Hisobingiz cheklangan.")

    if request.method == "POST":
        form = ComplaintForm(request.POST)
        if form.is_valid():
            muammo = form.save(commit=False)
            muammo.author = request.user
            muammo.save()
            messages.success(request, "Dardingiz e'lon qilindi.")
            return redirect(muammo.get_absolute_url())
    else:
        form = ComplaintForm()

    return render(
        request,
        "complaints/create.html",
        {"form": form, "tahrirlash": False},
    )


@login_required
def complaint_edit(request: HttpRequest, slug: str) -> HttpResponse:
    """Yozilgan dardni tahrirlash — cheklangan oyna ichida (D1-T9).

    ⚠️ Ruxsat `Complaint.tahrirlay_oladimi()` da: muallif + 30 daqiqa +
       yechim kelmagan. Uchinchi shart eng muhimi — batafsil izoh
       o'sha metodda.
    """
    muammo = get_object_or_404(Complaint.objects.all(), slug=slug)

    if not muammo.tahrirlay_oladimi(request.user):
        # 403, 404 EMAS: post bor va foydalanuvchi uni ko'ra oladi —
        # faqat tahrirlash oynasi yopilgan. 404 chalg'ituvchi bo'lardi.
        return HttpResponseForbidden(
            "Tahrirlash oynasi yopilgan: 30 daqiqa o'tgan yoki yechim kelgan."
        )

    if request.method == "POST":
        form = ComplaintForm(request.POST, instance=muammo, tahrirlash=True)
        if form.is_valid():
            form.save()
            messages.success(request, "O'zgarishlar saqlandi.")
            return redirect(muammo.get_absolute_url())
    else:
        form = ComplaintForm(instance=muammo, tahrirlash=True)

    return render(
        request,
        "complaints/create.html",
        {"form": form, "tahrirlash": True, "complaint": muammo},
    )
