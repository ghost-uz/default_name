"""To'lovlar — ko'rinishlar (D6-T2).

IKKI XIL KO'RINISH, IKKI XIL QOIDA

    Odam uchun   : `/pro/`, `/pro/sotib-olish/`, `/tolov/<pk>/natija/`
                   — sessiya, CSRF, tezlik cheklovi, HTML.
    Click uchun  : `/tolov/click/prepare/`, `/tolov/click/complete/`
                   — imzo, CSRF YO'Q, tezlik cheklovi YO'Q, JSON.

⚠️⚠️ WEBHOOK'DA `csrf_exempt` — MAJBURIY VA XAVFSIZ.
   CSRF himoyasi BRAUZER hujumidan (foydalanuvchi sessiyasidan
   foydalanish) saqlaydi. Click serverida sessiya ham, cookie ham
   yo'q — u umuman brauzer emas. Tokenni talab qilish integratsiyani
   ishlamaydigan qilardi, xavfsizlik esa OSHMASDI.

   Bu endpoint'ning autentifikatsiyasi — IMZO. Va u kuchliroq: CSRF
   token sessiyaga bog'langan, imzo esa har so'rovning MAZMUNIGA
   (summa, buyurtma raqami) bog'langan.

⚠️⚠️ WEBHOOK HAR DOIM HTTP 200 QAYTARADI (xato bo'lsa ham).
   Click javob TANASIDAGI `error` ga qaraydi. 4xx/5xx esa uning uchun
   "javob yo'q" degani — u so'rovni qayta yuboradi va bir necha
   urinishdan keyin tranzaksiyani BEKOR qiladi. Ya'ni bizning "rad
   etdim" xabarimiz noto'g'ri yetkazilsa, muvaffaqiyatli to'lov ham
   yo'qolardi.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.common.ratelimit import mijoz_ip, tezlik_cheklovi

from . import click
from .models import Provayder, Tolov, TolovHolati, TolovMaqsadi
from .services import (
    Sabab,
    TolovXatosi,
    sorovni_jurnalga,
    tolov_yaratish,
    tolovni_bekor_qilish,
    tolovni_tayyorlash,
    tolovni_yakunlash,
)

log = logging.getLogger(__name__)


# ⚠️⚠️ SEMANTIK SABABNI CLICK KODIGA AYLANTIRISH — ADAPTERNING ISHI.
#    Xizmat qatlami provayder kodlarini bilmaydi (`services.Sabab`
#    izohiga qarang). D6-T3 da Payme o'z jadvalini yozadi va shu
#    ikkalasi bir-biriga xalaqit bermaydi.
#
# ⚠️ `TAYYORLANMAGAN` -> `-6` («Transaction does not exist»): Click
#    uchun "prepare qilinmagan buyurtma" aynan shu — u bilmaydigan
#    tranzaksiya.
SABAB_KODI = {
    Sabab.TOPILMADI: click.BUYURTMA_TOPILMADI,
    Sabab.SUMMA: click.SUMMA_XATO,
    Sabab.ALLAQACHON: click.ALLAQACHON_TOLANGAN,
    Sabab.TAYYORLANMAGAN: click.TRANZAKSIYA_TOPILMADI,
    Sabab.BEKOR: click.BEKOR_QILINGAN,
}


def obuna_narxi() -> Decimal:
    """PRO narxi — SOZLAMADAN, formadan emas."""
    return Decimal(settings.OBUNA_NARXI)


def sotib_ololadimi(user) -> bool:
    """⚠️⚠️ PRO NI FAQAT TASDIQLANGAN EKSPERT SOTIB OLA OLADI.

    NEGA — D6-T2 DA TOPILGAN NUQSON:
       Bugungi kodda PRO ayni bitta narsa beradi: `pro_faolmi`
       (`apps/accounts/models.py`) — «Tasdiqlangan PRO» nishoni. U esa
       IKKI shartning kesishmasi: tasdiqlangan malaka VA amaldagi
       to'lov (D3-T5 qoidasi — pulga ishonch sotilmaydi).

       Ya'ni tasdiqlanmagan odam to'lasa, MUTLAQO hech narsa olmaydi:
       nishon chiqmaydi, boshqa imkoniyat esa hali yo'q
       (`ExpertProfile.contact_visible` yig'iladi, lekin hech qayerda
       ISHLATILMAYDI; `suhbat.kontakt_sorash` PRO ni tekshirmaydi).

       Maketdagi (`accounts/expert_list.html`) to'rtta va'dadan
       («Bog'lanish tugmasi», «ro'yxat boshida», «Telegram
       bildirishnomasi», «14 kun bepul») hech biri kodda YO'Q.

    ⚠️ Bu CHEKLOV emas, HIMOYA: hech narsa bermaydigan pulni olish —
       nuqson. Cheklov PRO imkoniyatlari kengaygach olib tashlanadi
       (bitta funksiya, bitta joy).

    ⚠️ `has_pro` bu yerda TEKSHIRILMAYDI — uzaytirish har doim ochiq
       (`obunani_uzaytirish` qolgan muddat ustiga qo'shadi).
    """
    profil = getattr(user, "ekspert_profili", None)
    return profil is not None and profil.tasdiqlanganmi


# ===========================================================================
# 1. Odam uchun sahifalar
# ===========================================================================
def pro(request: HttpRequest) -> HttpResponse:
    """PRO haqida va sotib olish sahifasi.

    ⚠️ MEHMONGA HAM OCHIQ. Bu sotuv sahifasi: nimani sotib
       olayotganini ko'rmasdan turib kirishga majburlash eng katta
       chiqib ketish nuqtasi bo'lardi. Tugma esa kirishni so'raydi.
    """
    kirgan = request.user.is_authenticated
    return render(
        request,
        "payments/pro.html",
        {
            "active_nav": "profile",
            "narx": obuna_narxi(),
            "kun": settings.OBUNA_MUDDATI_KUN,
            "yoqilganmi": settings.CLICK_YOQILGANMI,
            "obuna": getattr(request.user, "obuna", None) if kirgan else None,
            "ekspertmi": sotib_ololadimi(request.user) if kirgan else False,
        },
    )


@login_required
@require_POST
@tezlik_cheklovi("tolov_boshlash")
def sotib_olish(request: HttpRequest) -> HttpResponse:
    """Buyurtma yaratadi va odamni Click sahifasiga yuboradi.

    ⚠️ `require_POST` — bu YOZISH amali (baza qatori yaratiladi).
       GET bilan ochilsa, sahifani oldindan yuklaydigan brauzer
       kengaytmasi ham buyurtma yasab tashlardi.

    ⚠️ Summa `request.POST` dan OLINMAYDI. Sabab `obuna_narxi()` da.
    """
    # ⚠️ Ikkala tekshiruv ham SHABLONDA takrorlangan (tugma
    #    ko'rsatilmaydi). Bu ikki nusxa emas: shablon KO'RINISHNI,
    #    bu yerdagi shart AMALNI boshqaradi. Manzilni qo'lda ochish
    #    mumkin va o'shanda faqat shu yerdagi tekshiruv qoladi.
    if not settings.CLICK_YOQILGANMI:
        messages.error(request, "To'lov tizimi hozircha ulanmagan.")
        return redirect("pro")

    if not sotib_ololadimi(request.user):
        messages.error(
            request,
            "PRO hozircha tasdiqlangan ekspertlar uchun. "
            "Avval ekspert arizasini yuboring.",
        )
        return redirect("pro")

    tolov = tolov_yaratish(
        user=request.user,
        provayder=Provayder.CLICK,
        summa=obuna_narxi(),
        maqsad=TolovMaqsadi.OBUNA,
    )
    manzil = click.tolov_manzili(
        asos=settings.CLICK_TOLOV_MANZILI,
        service_id=settings.CLICK_SERVICE_ID,
        merchant_id=settings.CLICK_MERCHANT_ID,
        tolov_id=tolov.pk,
        summa=tolov.summa,
        qaytish_manzili=request.build_absolute_uri(
            reverse("tolov_natijasi", args=[tolov.pk])
        ),
    )
    return redirect(manzil)


@login_required
def natija(request: HttpRequest, pk: int) -> HttpResponse:
    """Click'dan qaytgandan keyingi sahifa.

    ⚠️⚠️ BU SAHIFA HOLATNI O'ZGARTIRMAYDI. Odam bu yerga to'lov
       tugagach qaytadi, lekin obunani `return_url` emas, WEBHOOK
       beradi. Sabab: qaytish manzilini brauzerda qo'lda ochish
       mumkin — unga ishonish "to'lamasdan PRO olish" degani bo'lardi.

    ⚠️ Webhook `return_url` dan KECHIKISHI mumkin. Shuning uchun hali
       to'lanmagan buyurtma "kutilmoqda" deb ko'rsatiladi, "xato" deb
       emas: odamga muvaffaqiyatli to'lovni muvaffaqiyatsiz deb
       ko'rsatish yordam bo'limiga qo'ng'iroqni kafolatlaydi.
    """
    tolov = get_object_or_404(Tolov, pk=pk)
    if tolov.user_id != request.user.pk:
        # 404, 403 emas: begona buyurtmaning MAVJUDLIGI ham
        # oshkor qilinmaydi (D6-T5 dagi bilan bir xil qaror).
        raise Http404

    return render(
        request,
        "payments/natija.html",
        {
            "active_nav": "profile",
            "tolov": tolov,
            "kutilmoqda": tolov.holat in {TolovHolati.YANGI, TolovHolati.TAYYOR},
        },
    )


# ===========================================================================
# 2. Click webhook'lari
# ===========================================================================
def _javob(
    *,
    kod: int,
    post,
    amal_nomi: str,
    tolov=None,
    prepare_id: int | None = None,
    confirm_id: int | None = None,
    izoh: str = "",
    imzo_togrimi: bool = False,
    ip: str = "",
) -> JsonResponse:
    """Javobni yasaydi VA jurnalga yozadi — YAGONA chiqish nuqtasi.

    ⚠️⚠️ NEGA YAGONA NUQTA
       Qabul mezoni: «barcha so'rovlar jurnalga yoziladi». Jurnalga
       yozishni har `return` oldiga qo'lda qo'yish — unutish uchun
       tayyor tuzoq, va unutilgan tarmoq aynan xato yo'lida bo'lardi
       (ular kamroq sinaladi). Bu yerda esa jurnalsiz javob
       qaytarishning IMKONI yo'q.
    """
    javob = click.javob(
        kod=kod,
        click_trans_id=(post.get("click_trans_id") or ""),
        merchant_trans_id=(post.get("merchant_trans_id") or ""),
        prepare_id=prepare_id,
        confirm_id=confirm_id,
        izoh=izoh,
    )
    sorovni_jurnalga(
        provayder=Provayder.CLICK,
        amal=amal_nomi,
        xom=post.dict(),
        natija=kod,
        javob=javob,
        tolov=tolov,
        merchant_trans_id=(post.get("merchant_trans_id") or ""),
        provayder_trans_id=(post.get("click_trans_id") or ""),
        ip=ip,
        imzo_togrimi=imzo_togrimi,
    )
    return JsonResponse(javob)


def _click_webhook(request: HttpRequest, *, amal: int, amal_nomi: str) -> JsonResponse:
    """Prepare va Complete uchun umumiy tana.

    ⚠️ Ikkala amalning imzo tekshiruvi, jurnali va xato tarjimasi bir
       xil — farq faqat OXIRGI qadamda. Ularni ikkita mustaqil
       funksiya qilib yozish imzo mantiqini ikki marta berardi va
       bir kuni faqat bittasi tuzatilardi.
    """
    post = request.POST
    ip = mijoz_ip(request)

    # --- 1. Imzo va shakl -------------------------------------------------
    try:
        sorov = click.sorovni_oqish(
            post,
            amal=amal,
            service_id=settings.CLICK_SERVICE_ID,
            maxfiy_kalit=settings.CLICK_SECRET_KEY,
        )
    except click.ClickXatosi as xato:
        log.warning("click/%s rad etildi: %s (ip=%s)", amal_nomi, xato, ip)
        return _javob(
            kod=xato.kod, post=post, amal_nomi=amal_nomi, izoh=xato.izoh, ip=ip
        )

    # ⚠️ IMZO O'TGANDAN KEYINGI HAMMA JAVOB SHU YOPILMA ORQALI.
    #    Boshida bu `**umumiy` lug'ati edi va u DRY bergan, lekin
    #    mypy'ni ko'r qilgan: heterogen `dict[str, object]` ni ochish
    #    HAR BIR argument tipini yo'qotadi (15 ta xato). Yopilma
    #    ikkalasini ham beradi — takrorlanish ham yo'q, tip ham tirik.
    def chiqish(
        kod: int,
        *,
        tolov: Tolov | None = None,
        prepare_id: int | None = None,
        confirm_id: int | None = None,
    ) -> JsonResponse:
        return _javob(
            kod=kod,
            post=post,
            amal_nomi=amal_nomi,
            tolov=tolov,
            prepare_id=prepare_id,
            confirm_id=confirm_id,
            imzo_togrimi=True,
            ip=ip,
        )

    # --- 2. Provayder to'lov amalga oshmaganini bildirdi -------------------
    # ⚠️ `error` MANFIY bo'lsa Click bizdan tasdiq emas, XABAR olib
    #    kelgan: karta rad etdi, foydalanuvchi bekor qildi va h.k.
    #    Buyurtmani yopamiz va O'SHA kodni qaytaramiz.
    if sorov.error < 0:
        bekor = tolovni_bekor_qilish(
            tolov_id=sorov.tolov_id,
            provayder=Provayder.CLICK,
            izoh=sorov.error_note or f"Click xatosi {sorov.error}",
        )
        return chiqish(click.BEKOR_QILINGAN, tolov=bekor)

    # --- 3. Amal ----------------------------------------------------------
    try:
        if amal == click.AMAL_PREPARE:
            tolov = tolovni_tayyorlash(
                tolov_id=sorov.tolov_id,
                provayder=Provayder.CLICK,
                summa=sorov.amount,
                provayder_trans_id=sorov.click_trans_id,
            )
            return chiqish(click.MUVAFFAQIYAT, tolov=tolov, prepare_id=tolov.pk)

        # ⚠️ `merchant_prepare_id` — Prepare'da BIZ bergan son, ya'ni
        #    `Tolov.pk`. Mos kelmasa Click boshqa (yoki mavjud
        #    bo'lmagan) tayyorgarlikka ishora qilyapti.
        if sorov.merchant_prepare_id != sorov.merchant_trans_id:
            return chiqish(click.TRANZAKSIYA_TOPILMADI)

        tolov, yangimi = tolovni_yakunlash(
            tolov_id=sorov.tolov_id,
            provayder=Provayder.CLICK,
            summa=sorov.amount,
            provayder_trans_id=sorov.click_trans_id,
        )
        if not yangimi:
            log.info("click/complete: takroriy so'rov (tolov=%s)", tolov.pk)
        return chiqish(click.MUVAFFAQIYAT, tolov=tolov, confirm_id=tolov.pk)

    except TolovXatosi as xato:
        log.warning("click/%s: %s (tolov=%s)", amal_nomi, xato.sabab, sorov.tolov_id)
        return chiqish(SABAB_KODI[xato.sabab])


@csrf_exempt
@require_POST
def click_prepare(request: HttpRequest) -> JsonResponse:
    """Click: "shunday buyurtma bormi?" (action=0)."""
    return _click_webhook(request, amal=click.AMAL_PREPARE, amal_nomi="prepare")


@csrf_exempt
@require_POST
def click_complete(request: HttpRequest) -> JsonResponse:
    """Click: "pul yechildi" (action=1). Xizmat SHU YERDA beriladi."""
    return _click_webhook(request, amal=click.AMAL_COMPLETE, amal_nomi="complete")
