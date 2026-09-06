"""Umumiy — infratuzilma ko'rinishlari."""

from django.http import HttpRequest, HttpResponse
from django.urls import reverse


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


# ===========================================================================
# robots.txt (D4-T5)
# ===========================================================================
# ⚠️⚠️ ADMIN MANZILI BU RO'YXATDA YO'Q VA BO'LMASLIGI HAM KERAK.
#
#    `robots.txt` — OMMAVIY fayl. Unga `Disallow: /maxfiy-admin/` deb
#    yozish admin panelning manzilini butun dunyoga E'LON QILISH degani.
#    Loyihada `DJANGO_ADMIN_URL` aynan shuning uchun sozlanadigan qilingan
#    (`config/settings/base.py`): standart `/admin/` eng ko'p skanerlanadigan
#    yo'l va uni o'zgartirish arzon himoya qatlami. Uni robots.txt ga yozish
#    o'sha himoyani bir qatorda yo'q qilardi.
#
#    Admin baribir indekslanmaydi: u login talab qiladi va bot uni ocholmaydi.
#
# ⚠️ RO'YXAT "YASHIRISH" EMAS, "SKANERLASHNI TEJASH" uchun. `Disallow`
#    kirishni to'smaydi va maxfiylik bermaydi — u faqat halol botlarga
#    "bu yerda indekslashga arziydigan narsa yo'q" deydi. Haqiqiy himoya
#    har doim kodda (avtorizatsiya, `visible()`), robots.txt da emas.
TAQIQLANGAN_YOLLAR = (
    # Cheksiz kombinatsiya beradi va sahifaning o'zi `noindex` (D4-T3).
    "/qidiruv/",
    # Autentifikatsiya va shaxsiy sahifalar — indekslashga arzimaydi.
    "/kirish/",
    "/chiqish/",
    "/rozilik/",
    "/hisob/",
    "/saqlanganlar/",
    # Staff interfeysi (D2-T2).
    "/moderatsiya/",
    "/shikoyat/",
    # Faqat POST qabul qiladigan amallar — bot ularni bekorga urinadi.
    "/ovoz/",
    "/saqlash/",
)


def robots(request: HttpRequest) -> HttpResponse:
    """`/robots.txt` — skanerlash qoidalari va sitemap havolasi.

    ⚠️ STATIK FAYL EMAS, KO'RINISH: sitemap manzili MUTLAQ bo'lishi
       kerak va u domenga bog'liq (`dard.uz`, staging, lokal). Statik
       faylda domen qotib qolardi va staging'da prod sitemap'iga
       ko'rsatardi.
    """
    qatorlar = ["User-agent: *"]
    qatorlar += [f"Disallow: {yol}" for yol in TAQIQLANGAN_YOLLAR]
    qatorlar += [
        "",
        f"Sitemap: {request.build_absolute_uri(reverse('sitemap'))}",
        "",
    ]
    return HttpResponse("\n".join(qatorlar), content_type="text/plain")
