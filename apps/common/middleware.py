"""Umumiy middleware."""

from __future__ import annotations

import secrets
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse


class CSPNonceMiddleware:
    """Har bir so'rov uchun bir martalik `nonce` yaratadi.

    Shablonlarda:  <script nonce="{{ request.csp_nonce }}">

    ⚠️ NEGA HOZIR, CSP sarlavhasi esa keyin (D2-T9)?
       Nonce shablonlarda bo'lishi kerak. Agar u keyin qo'shilsa, CSP
       yoqilgan kunda BARCHA shablonlarni qayta ko'rib chiqish kerak
       bo'ladi va bittasi unutilsa — sayt jim ravishda buziladi
       (masalan mavzu skripti ishlamay qoladi va sahifa "chaqnaydi").
       Nonce'ni oldin qo'yish arzon, keyin qo'yish qimmat.

    ⚠️ Har so'rovga YANGI qiymat. Takrorlanuvchi nonce CSP'ni butunlay
       ma'nosiz qiladi — hujumchi uni bir marta bilsa yetarli bo'ladi.

    D2-T9 da shu qiymat `Content-Security-Policy` sarlavhasiga qo'shiladi:
        script-src 'self' 'nonce-{{ nonce }}'
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        # token_urlsafe(16) -> 128 bit tasodifiylik, CSP tavsiyasidan yuqori.
        # ⚠️ `type: ignore` — `HttpRequest` da bunday maydon yo'q; middleware
        #    uni dinamik qo'shadi. Bu Django'da odatiy naqsh, lekin statik
        #    tahlil uni bilmaydi.
        request.csp_nonce = secrets.token_urlsafe(16)  # type: ignore[attr-defined]
        return self.get_response(request)
