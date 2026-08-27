"""Muammolar — ko'rinishlar (D1-T7, D1-T8)."""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.common.vote_views import (
    htmx_sorovimi,
    ovoz_qiymatini_oqish,
    ovoz_ruxsati,
    ovozdan_keyingi_manzil,
)
from apps.common.voting import cast_vote, user_votes_for

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
