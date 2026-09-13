"""Reklama ko'rinishlari (D6-T6)."""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_GET

from .models import AdSlot
from .services import bosishni_qayd_etish


@require_GET
def reklama_bosildi(request: HttpRequest, pk: int) -> HttpResponse:
    """Reklama havolasi: bosishni sanaydi va tashqi manzilga yo'naltiradi.

    ⚠️⚠️ MANZIL BAZADAN OLINADI, so'rovdan EMAS. Ochiq yo'naltirish
       (open redirect) — reklama havolalarining klassik teshigi: `?url=`
       parametrini qabul qilgan sayt hujumchiga o'z domeniga ishonchli
       havola yasash imkonini beradi.

    ⚠️ FAQAT FAOL reklama yo'naltiradi. Muddati tugagan yoki o'chirilgan
       blokka bosilsa 404: aks holda saytda eskirgan shartnomaning
       havolasi yashab qolardi (masalan qidiruv keshidan kelgan bosish).

    ⚠️ `target="_blank"` va `rel="sponsored nofollow noopener"` shablonda
       (`components/_reklama.html`) — SEO uchun ham, xavfsizlik uchun ham.
    """
    reklama = get_object_or_404(AdSlot.objects.faol(), pk=pk)
    bosishni_qayd_etish(reklama.pk)
    return redirect(reklama.manzil)
