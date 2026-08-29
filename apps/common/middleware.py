"""Umumiy middleware (D0-T6, D2-T9)."""

from __future__ import annotations

import secrets
from collections.abc import Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponse


def csp_sarlavhasi(nonce: str) -> str:
    """`settings.CSP_YONALISHLARI` dan sarlavha satrini quradi.

    ⚠️ Yo'nalishlar SOZLAMADA, kodda emas: yangi tashqi resurs
       qo'shilganda (masalan to'lov tizimi vidjeti — M6) kod tegilmaydi.

    ⚠️ `nonce` FAQAT `script-src` ga qo'shiladi. `style-src` ga nonce
       qo'yish inline `<style>` bloklariga yo'l ochardi va hech qanday
       foyda bermasdi — bizda ular yo'q.
    """
    qismlar = []
    for yonalish, manbalar in settings.CSP_YONALISHLARI.items():
        qiymatlar = list(manbalar)
        if yonalish == "script-src":
            qiymatlar.insert(0, f"'nonce-{nonce}'")
        qismlar.append(f"{yonalish} {' '.join(qiymatlar)}" if qiymatlar else yonalish)
    return "; ".join(qismlar)


class CSPMiddleware:
    """Bir martalik `nonce` + `Content-Security-Policy` sarlavhasi.

    Shablonlarda:  <script nonce="{{ request.csp_nonce }}">

    ⚠️ NONCE VA SARLAVHA BITTA MIDDLEWARE'DA — ataylab.
       Ikkiga bo'linsa ular bir-biridan uzilib ketishi mumkin: sarlavha
       `nonce-abc` deydi, shablon esa boshqa qiymat yozadi va BARCHA
       inline skript jimgina bloklanadi. Bitta joyda ular ajralmaydi.

    ⚠️ Har so'rovga YANGI qiymat. Takrorlanuvchi nonce CSP'ni butunlay
       ma'nosiz qiladi — hujumchi uni bir marta bilsa yetarli bo'ladi.

    ⚠️ CSP HAMMA MUHITDA BIR XIL (dev'da ham). Faqat prodda yoqilsa,
       buzilish faqat prodda ko'rinardi — ya'ni eng qimmat joyda.
       Buning narxi: DEBUG'dagi Django xato sahifasi uslubsiz
       ko'rinadi (uning `<style>` bloki nonce olmaydi). Traceback
       o'qilaveradi.

    ⚠️ `style-src` da `'unsafe-inline'` YO'Q va shu holatda qolishi
       kerak. Buning uchun shablonlarda inline `style=` atributi
       bo'lmasligi shart — buni guard test tekshiradi
       (`test_templates.py::XavfsizlikSarlavhalariTests`).
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        # token_urlsafe(16) -> 128 bit tasodifiylik, CSP tavsiyasidan yuqori.
        # ⚠️ `type: ignore` — `HttpRequest` da bunday maydon yo'q; middleware
        #    uni dinamik qo'shadi. Bu Django'da odatiy naqsh, lekin statik
        #    tahlil uni bilmaydi.
        nonce = secrets.token_urlsafe(16)
        request.csp_nonce = nonce  # type: ignore[attr-defined]

        javob = self.get_response(request)

        # ⚠️ Mavjud sarlavha QAYTA YOZILMAYDI: ko'rinish o'ziga xos
        #    siyosat qo'ygan bo'lsa (masalan tashqi vidjet sahifasi),
        #    uni bosib ketish jim xato bo'lardi.
        if "Content-Security-Policy" not in javob:
            javob["Content-Security-Policy"] = csp_sarlavhasi(nonce)

        if getattr(settings, "PERMISSIONS_POLICY", ""):
            javob["Permissions-Policy"] = settings.PERMISSIONS_POLICY

        return javob
