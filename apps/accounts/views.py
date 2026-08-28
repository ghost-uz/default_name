"""Kirish va chiqish (D1-T1)."""

from __future__ import annotations

import logging
import secrets

from django.conf import settings
from django.contrib.auth import login, logout
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .services import telegram_foydalanuvchisini_olish_yoki_yaratish
from .telegram import TelegramAuthXatosi, tekshirish

log = logging.getLogger(__name__)

# Sessiyadagi bir martalik kalit (pastdagi izohga qarang).
STATE_KALITI = "telegram_login_state"


def _xavfsiz_next(request: HttpRequest, xom: str) -> str:
    """Kirishdan keyin qayerga. Begona manzil RAD ETILADI.

    ⚠️ Tekshiruvsiz `next` ochiq yo'naltirish (open redirect) bo'lardi:
       hujumchi `?next=https://soxta-dard.uz/` bilan havola tarqatib,
       kirgan odamni o'z saytiga olib chiqib, u yerda "sessiyangiz
       tugadi, qayta kiring" degan soxta oyna ko'rsatardi.
    """
    if xom and url_has_allowed_host_and_scheme(
        xom, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return xom
    return settings.LOGIN_REDIRECT_URL


def login_page(request: HttpRequest) -> HttpResponse:
    """Kirish sahifasi — Telegram Login Widget shu yerda chiziladi."""
    if request.user.is_authenticated:
        return redirect(_xavfsiz_next(request, request.GET.get("next", "")))

    # ⚠️ BIR MARTALIK `state` — "login CSRF" ga qarshi.
    #
    #    Telegram Login Widget kirish so'rovini GET bilan qaytaradi.
    #    Imzo Telegram foydalanuvchisiga bog'langan, LEKIN brauzerga
    #    emas. Ya'ni hujumchi o'z hisobining yaroqli imzosini qo'lga
    #    kiritib (u o'ziniki — bemalol), havolani qurbon odamga
    #    yuborishi mumkin. Qurbon havolani bosadi va SEZMASDAN
    #    HUJUMCHINING hisobiga kiradi.
    #
    #    Dard.uz uchun bu jiddiy: odam o'zining eng shaxsiy muammosini
    #    yozadi va u hujumchining hisobiga tushadi — ya'ni hujumchi uni
    #    o'qiy oladi.
    #
    #    `state` sessiyaga yoziladi va callback'da solishtiriladi. Uni
    #    faqat shu brauzer biladi, shuning uchun begona havola o'tmaydi.
    #    Telegram imzosiga kirmaydi (u faqat o'z maydonlarini imzolaydi)
    #    — ammo bu yerda kerak bo'lgan narsa "brauzerga bog'lash", imzo
    #    emas.
    state = secrets.token_urlsafe(24)
    request.session[STATE_KALITI] = state

    callback = request.build_absolute_uri(reverse("telegram_callback"))
    keyingi = request.GET.get("next", "")

    return render(
        request,
        "accounts/login.html",
        {
            "bot_username": settings.TELEGRAM_BOT_USERNAME,
            # ⚠️ Widget SOZLANMAGAN bo'lsa shablon buni ochiq aytadi.
            #    Ishlamaydigan tugma ko'rsatish "sayt buzuq" degan
            #    taassurot qoldiradi.
            "telegram_sozlangan": bool(
                settings.TELEGRAM_BOT_USERNAME and settings.TELEGRAM_BOT_TOKEN
            ),
            "auth_url": f"{callback}?state={state}&next={keyingi}",
            "next": keyingi,
        },
    )


def telegram_callback(request: HttpRequest) -> HttpResponse:
    """Telegram qaytargan ma'lumotni tekshiradi va sessiyani ochadi.

    ⚠️ Xato holatida 403 va UMUMIY xabar (D1-T1 qabul mezoni).
       "imzo noto'g'ri" bilan "sana eskirgan" ni ajratib ko'rsatish
       hujumchiga qaysi qadamda to'xtaganini aytadi. Aniq sabab faqat
       jurnalga tushadi.
    """
    kutilgan_state = request.session.pop(STATE_KALITI, None)
    kelgan_state = request.GET.get("state", "")

    # ⚠️ `compare_digest` shart emas: `state` sirli kalit emas, u faqat
    #    seansni brauzerga bog'laydi va bir marta ishlatiladi.
    if not kutilgan_state or kelgan_state != kutilgan_state:
        log.warning("Telegram login: state mos kelmadi")
        return HttpResponseForbidden(
            "Kirish so'rovi yaroqsiz. Qaytadan urinib ko'ring."
        )

    try:
        malumot = tekshirish(request.GET.dict(), bot_token=settings.TELEGRAM_BOT_TOKEN)
    except TelegramAuthXatosi as exc:
        # ⚠️ Sabab JURNALDA, foydalanuvchiga EMAS.
        log.warning("Telegram login rad etildi: %s", exc)
        return HttpResponseForbidden(
            "Kirish so'rovi yaroqsiz. Qaytadan urinib ko'ring."
        )

    user, yangi = telegram_foydalanuvchisini_olish_yoki_yaratish(
        {
            "id": malumot.id,
            "first_name": malumot.first_name,
            "last_name": malumot.last_name,
            "username": malumot.username,
        }
    )

    if not user.is_active:
        # `is_banned` dan FARQLI: bloklangan odam o'qiy oladi, o'chirilgan
        # hisob esa umuman kira olmaydi (D0-T2).
        return HttpResponseForbidden("Bu hisob o'chirilgan.")

    # ⚠️ `backend` OCHIQ beriladi: `authenticate()` chaqirilmagani uchun
    #    Django qaysi backend ishlatilganini bilmaydi va `login()`
    #    `ValueError` beradi.
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    log.info("Telegram login: user=%s yangi=%s", user.pk, yangi)

    return redirect(_xavfsiz_next(request, request.GET.get("next", "")))


@require_POST
def logout_view(request: HttpRequest) -> HttpResponse:
    """Chiqish — FAQAT POST.

    ⚠️ GET bilan chiqish `<img src="/chiqish/">` qo'yilgan istalgan
       sahifa ziyoratchini tizimdan chiqarib yuborishiga imkon berardi.
       Django 5 dan beri standart `LogoutView` ham faqat POST qabul qiladi.
    """
    logout(request)
    return redirect(settings.LOGOUT_REDIRECT_URL)
