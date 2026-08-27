"""Umumiy — infratuzilma ko'rinishlari."""

from django.http import HttpRequest, HttpResponse


def health(request: HttpRequest) -> HttpResponse:
    """Konteyner tirikmi degan savolga javob.

    ATAYLAB minimal: bu tekshiruv Docker healthcheck'i tomonidan har necha
    soniyada chaqiriladi. Unga ma'lumotlar bazasi so'rovi qo'shilsa, DB
    sekinlashganda konteyner "sog'lom emas" deb qayta ishga tushiriladi va
    vaziyat yanada yomonlashadi.

    D7-T2 da bog'liqliklarni tekshiradigan ALOHIDA `/health/deep/` qo'shiladi
    (db, redis, celery beat oxirgi ishlashi) — u tashqi monitoring uchun.
    """
    return HttpResponse("ok", content_type="text/plain")
