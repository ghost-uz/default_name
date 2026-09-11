"""To'lovlar — ko'rinishlar (D6-T2, D6-T3).

IKKI XIL KO'RINISH, IKKI XIL QOIDA

    Odam uchun   : `/pro/`, `/pro/sotib-olish/<provayder>/`,
                   `/tolov/<pk>/natija/`
                   — sessiya, CSRF, tezlik cheklovi, HTML.
    Provayder    : `/tolov/click/prepare/`, `/tolov/click/complete/`,
                   `/tolov/payme/`
                   — imzo yoki Basic auth, CSRF YO'Q, tezlik cheklovi
                   YO'Q, JSON.

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

import json
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
from apps.complaints.models import Complaint

from . import click, payme
from .models import BoostOrder, Provayder, Tolov, TolovHolati, TolovMaqsadi
from .selectors import boost_joylari_soni
from .services import (
    Sabab,
    TolovXatosi,
    boost_buyurtmasi_yaratish,
    kotarib_bolmaslik_sababi,
    sorovni_jurnalga,
    tolov_yaratish,
    tolov_yaroqliligini_tekshirish,
    tolovni_bekor_qilish,
    tolovni_qaytarish,
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
    # ⚠️ D6-T4: buyurtma bor, lekin xizmatni endi berib bo'lmaydi
    #    (ko'tarilayotgan post shu orada yashirildi yoki yechildi). Prepare
    #    bosqichidagi xato — Click to'lovni PUL YECHMASDAN yopadi.
    Sabab.YAROQSIZ: click.BEKOR_QILINGAN,
}


def obuna_narxi() -> Decimal:
    """PRO narxi — SOZLAMADAN, formadan emas."""
    return Decimal(settings.OBUNA_NARXI)


def boost_narxi() -> Decimal:
    """Ko'tarish narxi — SOZLAMADAN, formadan emas (`obuna_narxi` bilan bir xil)."""
    return Decimal(settings.BOOST_NARXI)


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
            # ⚠️ HAR PROVAYDER ALOHIDA. Bittasi sozlangan bo'lsa
            #    faqat o'sha tugma chiqadi — "Payme" tugmasini
            #    kalitsiz ko'rsatish odamni Payme'ning xato
            #    sahifasiga olib borardi.
            "click_yoqilganmi": settings.CLICK_YOQILGANMI,
            "payme_yoqilganmi": settings.PAYME_YOQILGANMI,
            "yoqilganmi": settings.CLICK_YOQILGANMI or settings.PAYME_YOQILGANMI,
            "obuna": getattr(request.user, "obuna", None) if kirgan else None,
            "ekspertmi": sotib_ololadimi(request.user) if kirgan else False,
        },
    )


def _provayder_yoqilganmi(provayder: str) -> bool:
    """Manzildan kelgan nom TANIQLI va SOZLANGAN provayderni bildiradimi.

    ⚠️ Annotatsiya SHART va sabab `services._MAQSAD_BAJARUVCHILARI`
       dagi bilan bir xil: `Provayder` kalitlaridan mypy kalit tipini
       enum deb chiqaradi, `provayder` esa manzildan kelgan oddiy
       `str`. Ikkinchi marta uchragan bir xil tuzoq.
    """
    yoqilgan: dict[str, bool] = {
        Provayder.CLICK: settings.CLICK_YOQILGANMI,
        Provayder.PAYME: settings.PAYME_YOQILGANMI,
    }
    return yoqilgan.get(provayder, False)


def _tolov_manzili(tolov: Tolov, *, qaytish_manzili: str) -> str:
    """Buyurtmani provayderning to'lov sahifasi manziliga aylantiradi.

    ⚠️ Ikki provayderning manzil formati BUTUNLAY boshqa: Click —
       oddiy query-string, Payme — `;` bilan ajratilgan va base64
       qilingan satr. Shuning uchun har biri O'Z modulida quriladi
       va bu yerda faqat tanlov bor.
    """
    if tolov.provayder == Provayder.PAYME:
        return payme.tolov_manzili(
            asos=settings.PAYME_CHECKOUT_MANZILI,
            merchant_id=settings.PAYME_MERCHANT_ID,
            tolov_id=tolov.pk,
            summa=tolov.summa,
            qaytish_manzili=qaytish_manzili,
        )
    return click.tolov_manzili(
        asos=settings.CLICK_TOLOV_MANZILI,
        service_id=settings.CLICK_SERVICE_ID,
        merchant_id=settings.CLICK_MERCHANT_ID,
        tolov_id=tolov.pk,
        summa=tolov.summa,
        qaytish_manzili=qaytish_manzili,
    )


@login_required
@require_POST
@tezlik_cheklovi("tolov_boshlash")
def sotib_olish(request: HttpRequest, provayder: str) -> HttpResponse:
    """Buyurtma yaratadi va odamni provayder sahifasiga yuboradi.

    ⚠️ `require_POST` — bu YOZISH amali (baza qatori yaratiladi).
       GET bilan ochilsa, sahifani oldindan yuklaydigan brauzer
       kengaytmasi ham buyurtma yasab tashlardi.

    ⚠️ Summa `request.POST` dan OLINMAYDI. Sabab `obuna_narxi()` da.

    ⚠️⚠️ PROVAYDER MANZILDAN, lekin u RO'YXAT bilan tekshiriladi
       (`_provayder_yoqilganmi`). Tekshirmasdan `Provayder(provayder)`
       yozish `ValueError` bilan 500 berardi — ya'ni manzilni qo'lda
       terib server xatosini chiqarish mumkin bo'lardi.
    """
    # ⚠️ Tekshiruvlar SHABLONDA ham bor (tugma ko'rsatilmaydi). Bu
    #    ikki nusxa emas: shablon KO'RINISHNI, bu yerdagi shart
    #    AMALNI boshqaradi. Manzilni qo'lda ochish mumkin va
    #    o'shanda faqat shu yerdagi tekshiruv qoladi.
    if not _provayder_yoqilganmi(provayder):
        messages.error(request, "Bu to'lov tizimi hozircha ulanmagan.")
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
        provayder=provayder,
        summa=obuna_narxi(),
        maqsad=TolovMaqsadi.OBUNA,
    )
    return redirect(
        _tolov_manzili(
            tolov,
            qaytish_manzili=request.build_absolute_uri(
                reverse("tolov_natijasi", args=[tolov.pk])
            ),
        )
    )


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
    # ⚠️ `boost__complaint` — boost to'lovida matn postga havola beradi;
    #    `select_related` siz bu ikkita qo'shimcha so'rov bo'lardi (D6-T4).
    tolov = get_object_or_404(Tolov.objects.select_related("boost__complaint"), pk=pk)
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
            # ⚠️ Teskari OneToOne yo'q bo'lsa `RelatedObjectDoesNotExist`
            #    otiladi — u `AttributeError` dan meros oladi, ya'ni
            #    `getattr(..., None)` to'g'ri ishlaydi.
            "boost": getattr(tolov, "boost", None),
            "kutilmoqda": tolov.holat in {TolovHolati.YANGI, TolovHolati.TAYYOR},
        },
    )


# ---------------------------------------------------------------------------
# Postni ko'tarish (D6-T4)
# ---------------------------------------------------------------------------
def _oz_postini_olish(request: HttpRequest, pk: int) -> Complaint:
    """Faqat MUALLIFNING ko'rinadigan posti; qolgan hamma holatda 404.

    ⚠️ 404, 403 EMAS — begona buyurtma sahifasi (`natija`) bilan bir xil
       qaror: begona postga ko'tarish sahifasi borligi ham oshkor
       qilinmaydi.
    """
    return get_object_or_404(
        Complaint.objects.visible().select_related("category"),
        pk=pk,
        author=request.user,
    )


@login_required
def kotarish(request: HttpRequest, pk: int) -> HttpResponse:
    """Postni ko'tarish: qoidalar, joriy holat va to'lov tugmalari (D6-T4).

    ⚠️⚠️ SOTUV CHEKLANMAGAN (foydalanuvchi qarori, 2026-09-11), shuning
       uchun hozir nechta post ko'tarilgani OCHIQ yoziladi: joylar
       navbat bilan bo'linishini odam pul to'lashdan OLDIN bilsin.

    ⚠️ `faol_soni` ko'rinish filtrisiz sanaladi — yashirilgan postning
       boosti ham kiradi. Ya'ni raqam raqobatni OSHIRIB ko'rsatadi,
       kamaytirib emas: xato ehtiyotkor tomonda.
    """
    muammo = _oz_postini_olish(request, pk)
    joriy = (
        BoostOrder.objects.tugamagan()
        .filter(complaint=muammo)
        .order_by("-ends_at")
        .first()
    )
    return render(
        request,
        "payments/kotarish.html",
        {
            "active_nav": "feed",
            "muammo": muammo,
            "narx": boost_narxi(),
            "kun": settings.BOOST_MUDDATI_KUN,
            "sabab": kotarib_bolmaslik_sababi(user=request.user, muammo=muammo),
            "tugashi": joriy.ends_at if joriy else None,
            "faol_soni": BoostOrder.objects.faol().count(),
            "joylar_soni": boost_joylari_soni(),
            "birinchi_joy": settings.BOOST_BIRINCHI_JOY,
            "oraliq": settings.BOOST_ORALIQ,
            "click_yoqilganmi": settings.CLICK_YOQILGANMI,
            "payme_yoqilganmi": settings.PAYME_YOQILGANMI,
            "yoqilganmi": settings.CLICK_YOQILGANMI or settings.PAYME_YOQILGANMI,
        },
    )


@login_required
@require_POST
@tezlik_cheklovi("tolov_boshlash")
def kotarish_sotib_olish(request: HttpRequest, pk: int, provayder: str) -> HttpResponse:
    """Ko'tarish buyurtmasini yaratadi va odamni provayder sahifasiga yuboradi.

    ⚠️ `sotib_olish` (PRO) dagi himoyalarning hammasi: POST majburiy,
       provayder ro'yxat bilan tekshiriladi (qo'lda terilgan nom 500
       bermaydi), summa SOZLAMADAN.

    ⚠️ Yaroqlilik bu yerda VA to'lovni tayyorlash bosqichida
       tekshiriladi. Bu ikki nusxa emas: bu yerdagisi odamga TUSHUNARLI
       xabar beradi, webhook'dagisi esa buyurtma bilan to'lov orasidagi
       o'zgarishni ushlaydi (`services._MAQSAD_TEKSHIRUVCHILARI`).
    """
    muammo = _oz_postini_olish(request, pk)

    if not _provayder_yoqilganmi(provayder):
        messages.error(request, "Bu to'lov tizimi hozircha ulanmagan.")
        return redirect("kotarish", pk=muammo.pk)

    sabab = kotarib_bolmaslik_sababi(user=request.user, muammo=muammo)
    if sabab is not None:
        messages.error(request, sabab)
        return redirect("kotarish", pk=muammo.pk)

    tolov = boost_buyurtmasi_yaratish(
        user=request.user, muammo=muammo, provayder=provayder, summa=boost_narxi()
    )
    return redirect(
        _tolov_manzili(
            tolov,
            qaytish_manzili=request.build_absolute_uri(
                reverse("tolov_natijasi", args=[tolov.pk])
            ),
        )
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


# ===========================================================================
# 3. Payme webhook'i (D6-T3) — BITTA JSON-RPC endpoint
# ===========================================================================
# ⚠️⚠️ SEMANTIK SABABNI PAYME KODIGA AYLANTIRISH — IKKINCHI JADVAL.
#    `services.Sabab` provayderdan mustaqil (D6-T2 qarori) va aynan
#    shuning uchun bu yerda Click'nikidan BUTUNLAY boshqa kodlarga
#    tushadi. Xizmat qatlamiga tegilmadi.
#
# ⚠️ `TOPILMADI` -> `-31050`: Payme uchun bu `account` maydonining
#    xatosi va javobda `data` MAJBURIY — u foydalanuvchiga qaysi
#    maydon xato ekanini ko'rsatadi.
PAYME_SABAB_KODI = {
    Sabab.TOPILMADI: payme.BUYURTMA_TOPILMADI,
    Sabab.SUMMA: payme.SUMMA_XATO,
    Sabab.ALLAQACHON: payme.AMAL_BAJARILMAYDI,
    Sabab.TAYYORLANMAGAN: payme.AMAL_BAJARILMAYDI,
    Sabab.BEKOR: payme.AMAL_BAJARILMAYDI,
    Sabab.BAND: payme.AMAL_BAJARILMAYDI,
    # ⚠️ D6-T4: xizmatni endi berib bo'lmaydi — bu `account` (buyurtma)
    #    xatosi, shuning uchun `-31050..-31099` oralig'idan va javobda
    #    `data` bilan. `-31008` EMAS: u `CheckPerformTransaction` uchun
    #    hujjatda sanab o'tilmagan (D6-T3 dagi qaror).
    Sabab.YAROQSIZ: payme.BUYURTMA_YAKUNLANGAN,
}


def _payme_holat(tolov: Tolov) -> int:
    """Bizning `holat` -> Payme `state`.

    ⚠️⚠️ AYNAN SHU YERDA IKKI TIZIM UCHRASHADI. Bizda «bekor» BITTA,
       Payme'da IKKITA: `-1` (pul yechilmagan) va `-2` (yechilgan va
       qaytarilgan). Farq `tolangan_at` da yozilgan — shuning uchun
       alohida maydon kerak emas (`Tolov.qaytarilganmi`).
    """
    if tolov.holat == TolovHolati.TOLANDI:
        return payme.HOLAT_BAJARILDI
    if tolov.holat == TolovHolati.BEKOR:
        return payme.HOLAT_QAYTARILDI if tolov.qaytarilganmi else payme.HOLAT_BEKOR
    return payme.HOLAT_YARATILDI


def _payme_tranzaksiya(params: dict) -> Tolov:
    """`params.id` (Payme tranzaksiyasi) -> bizning `Tolov`.

    ⚠️ Noyoblik cheklovi (`provayder` + `provayder_trans_id`) bitta
       qatordan ko'p bo'lishini baza darajasida imkonsiz qiladi.
    """
    trans_id = str(params.get("id") or "")
    tolov = (
        Tolov.objects.select_related("user")
        .filter(provayder=Provayder.PAYME, provayder_trans_id=trans_id)
        .first()
    )
    if tolov is None or not trans_id:
        raise payme.PaymeXatosi(payme.TRANZAKSIYA_TOPILMADI)
    return tolov


def _payme_muddatni_tekshirish(tolov: Tolov) -> None:
    """12 soatlik oyna o'tgan bo'lsa tranzaksiyani bekor qiladi.

    ⚠️⚠️ PAYME QOIDASI: yaratilganidan 12 soat o'tib bajarilmagan
       tranzaksiya bekor qilinadi (`state = -1`, `reason = 4`) va
       so'rovga `-31008` qaytariladi.

       Buni Payme O'ZI qilmaydi — MERCHANT bajarishi kerak. Qilmasak,
       yarim yil oldin ochilgan to'lov sahifasi bugun ham
       muvaffaqiyatli yakunlanardi.
    """
    if tolov.holat != TolovHolati.TAYYOR:
        return
    if not payme.muddati_otganmi(yaratilgan=tolov.tayyorlangan_at):
        return
    tolovni_bekor_qilish(
        tolov_id=tolov.pk,
        provayder=Provayder.PAYME,
        izoh="Taymaut: 12 soat ichida yakunlanmadi",
        bekor_kodi=payme.SABAB_TAYMAUT,
    )
    raise payme.PaymeXatosi(payme.AMAL_BAJARILMAYDI)


def _payme_check_perform(params: dict) -> dict:
    """`CheckPerformTransaction` — "shunday buyurtma bormi?".

    ⚠️ Bu bosqichda hech narsa YOZILMAYDI. Payme uni foydalanuvchi
       summani kiritayotganda ham chaqiradi, ya'ni har chaqiruvda
       qator o'zgarsa baza bekorga yozilardi.
    """
    tolov_id = payme.buyurtma_raqami(params.get("account"))
    summa = payme.somga(params.get("amount") or 0)

    tolov = Tolov.objects.filter(pk=tolov_id, provayder=Provayder.PAYME).first()
    if tolov is None:
        raise payme.PaymeXatosi(payme.BUYURTMA_TOPILMADI, data=payme.ACCOUNT_MAYDONI)
    if tolov.summa != summa:
        raise payme.PaymeXatosi(payme.SUMMA_XATO)
    if tolov.yakunlanganmi:
        raise payme.PaymeXatosi(payme.BUYURTMA_YAKUNLANGAN, data=payme.ACCOUNT_MAYDONI)
    # ⚠️ D6-T4: maqsadga xos shart (`TolovXatosi` -> `PAYME_SABAB_KODI`).
    #    Odam aynan shu paytda Payme sahifasida summani ko'rib turibdi —
    #    xizmatni endi berib bo'lmasa, bu pul yechilishidan OLDIN aytiladi.
    tolov_yaroqliligini_tekshirish(tolov)
    return {"allow": True}


def _payme_create(params: dict) -> dict:
    """`CreateTransaction` — tranzaksiyani ro'yxatga oladi.

    ⚠️⚠️ `almashtirishga_ruxsat=False`: Payme'da bir buyurtmada bir
       vaqtda BITTA tranzaksiya bo'ladi. Click'da esa teskarisi
       to'g'ri (odam qaytadan urinadi) — farq shu yerda, xizmat
       qatlamida emas.

    ⚠️ TAKRORIY chaqiruvda AYNAN o'sha `create_time` qaytadi:
       `tayyorlangan_at` bazadan o'qiladi, hisoblanmaydi.
    """
    trans_id = str(params.get("id") or "")
    tolov_id = payme.buyurtma_raqami(params.get("account"))
    summa = payme.somga(params.get("amount") or 0)

    mavjud = Tolov.objects.filter(
        provayder=Provayder.PAYME, provayder_trans_id=trans_id
    ).first()
    if mavjud is not None:
        # Takror: avval muddat, keyin holat tekshiriladi.
        _payme_muddatni_tekshirish(mavjud)
        if mavjud.holat != TolovHolati.TAYYOR:
            raise payme.PaymeXatosi(payme.AMAL_BAJARILMAYDI)
        return {
            "create_time": payme.vaqtga_ms(mavjud.tayyorlangan_at),
            "transaction": str(mavjud.pk),
            "state": payme.HOLAT_YARATILDI,
        }

    tolov = tolovni_tayyorlash(
        tolov_id=tolov_id,
        provayder=Provayder.PAYME,
        summa=summa,
        provayder_trans_id=trans_id,
        almashtirishga_ruxsat=False,
    )
    return {
        "create_time": payme.vaqtga_ms(tolov.tayyorlangan_at),
        "transaction": str(tolov.pk),
        "state": payme.HOLAT_YARATILDI,
    }


def _payme_perform(params: dict) -> dict:
    """`PerformTransaction` — pul yechildi, XIZMAT SHU YERDA beriladi."""
    tolov = _payme_tranzaksiya(params)

    if tolov.holat == TolovHolati.TOLANDI:
        # ⚠️ Takror: o'sha javob, obuna QAYTA uzaytirilmaydi.
        return {
            "transaction": str(tolov.pk),
            "perform_time": payme.vaqtga_ms(tolov.tolangan_at),
            "state": payme.HOLAT_BAJARILDI,
        }

    _payme_muddatni_tekshirish(tolov)

    # ⚠️ Summa `tolov.summa` dan olinadi — `PerformTransaction` da
    #    summa UMUMAN kelmaydi (Payme uni yubormaydi). Tekshiruv
    #    allaqachon `CheckPerform` va `Create` bosqichlarida o'tgan.
    tolov, _ = tolovni_yakunlash(
        tolov_id=tolov.pk,
        provayder=Provayder.PAYME,
        summa=tolov.summa,
        provayder_trans_id=tolov.provayder_trans_id,
    )
    return {
        "transaction": str(tolov.pk),
        "perform_time": payme.vaqtga_ms(tolov.tolangan_at),
        "state": payme.HOLAT_BAJARILDI,
    }


def _payme_cancel(params: dict) -> dict:
    """`CancelTransaction` — bekor qilish yoki PUL QAYTARISH.

    ⚠️⚠️ `-31007` («buyurtma bajarilgan, bekor qilib bo'lmaydi»)
       QAYTARILMAYDI — ataylab. U yetkazib berilgan JISMONIY tovar
       uchun mo'ljallangan. Bizda esa xizmat qaytariladigan: obuna
       kunlari qaytarib olinadi (`services.tolovni_qaytarish`).
       Mijozga pulini qaytarib bera olmaslik bu yerda mahsulot
       nuqsoni bo'lardi, protokol talabi emas.
    """
    tolov = _payme_tranzaksiya(params)
    tolov = tolovni_qaytarish(
        tolov_id=tolov.pk,
        provayder=Provayder.PAYME,
        provayder_trans_id=tolov.provayder_trans_id,
        bekor_kodi=payme.bekor_sababi(params.get("reason")),
    )
    return {
        "transaction": str(tolov.pk),
        "cancel_time": payme.vaqtga_ms(tolov.bekor_at),
        "state": _payme_holat(tolov),
    }


def _payme_check(params: dict) -> dict:
    """`CheckTransaction` — Payme bizdan holatni SO'RAYDI."""
    tolov = _payme_tranzaksiya(params)
    return {
        "create_time": payme.vaqtga_ms(tolov.tayyorlangan_at),
        "perform_time": payme.vaqtga_ms(tolov.tolangan_at),
        "cancel_time": payme.vaqtga_ms(tolov.bekor_at),
        "transaction": str(tolov.pk),
        "state": _payme_holat(tolov),
        "reason": tolov.bekor_kodi,
    }


def _payme_statement(params: dict) -> dict:
    """`GetStatement` — davr ichidagi tranzaksiyalar (solishtirish uchun).

    ⚠️ `time` maydoniga `create_time` qo'yiladi. Payme'ning O'Z
       `time` i (u tranzaksiyani qachon yaratgani) saqlanmaydi:
       solishtirish `id` va `amount` bo'yicha boradi, ikkita deyarli
       bir xil vaqtni saqlash esa yana bitta sinxron tutiladigan
       maydon degani bo'lardi.
    """
    boshi = payme.ms_dan_vaqtga(int(params.get("from") or 0))
    oxiri = payme.ms_dan_vaqtga(int(params.get("to") or 0))

    qatorlar = Tolov.objects.filter(
        provayder=Provayder.PAYME,
        tayyorlangan_at__gte=boshi,
        tayyorlangan_at__lte=oxiri,
    ).order_by("tayyorlangan_at")

    return {
        "transactions": [
            {
                "id": t.provayder_trans_id,
                "time": payme.vaqtga_ms(t.tayyorlangan_at),
                "amount": payme.tiyinga(t.summa),
                "account": {payme.ACCOUNT_MAYDONI: str(t.pk)},
                "create_time": payme.vaqtga_ms(t.tayyorlangan_at),
                "perform_time": payme.vaqtga_ms(t.tolangan_at),
                "cancel_time": payme.vaqtga_ms(t.bekor_at),
                "transaction": str(t.pk),
                "state": _payme_holat(t),
                "reason": t.bekor_kodi,
            }
            for t in qatorlar
        ]
    }


PAYME_METODLARI = {
    payme.CHECK_PERFORM: _payme_check_perform,
    payme.CREATE: _payme_create,
    payme.PERFORM: _payme_perform,
    payme.CANCEL: _payme_cancel,
    payme.CHECK: _payme_check,
    payme.STATEMENT: _payme_statement,
}


def _payme_javob(
    tana: dict, *, metod: str, xom: dict, avtorizatsiya: bool, ip: str
) -> JsonResponse:
    """Javobni qaytaradi VA jurnalga yozadi — YAGONA chiqish nuqtasi.

    Click'dagi `_javob()` bilan bir xil sabab: jurnalga yozishni har
    `return` oldiga qo'lda qo'yish unutish uchun tayyor tuzoq, va
    unutilgan tarmoq aynan XATO yo'lida bo'lardi.
    """
    params = xom.get("params")
    params = params if isinstance(params, dict) else {}
    account = params.get("account")
    account = account if isinstance(account, dict) else {}

    sorovni_jurnalga(
        provayder=Provayder.PAYME,
        amal=metod or "?",
        xom=xom,
        natija=tana.get("error", {}).get("code", payme.MUVAFFAQIYAT_KODI),
        javob=tana,
        merchant_trans_id=str(account.get(payme.ACCOUNT_MAYDONI, "")),
        provayder_trans_id=str(params.get("id") or ""),
        ip=ip,
        imzo_togrimi=avtorizatsiya,
    )
    return JsonResponse(tana)


@csrf_exempt
def payme_webhook(request: HttpRequest) -> JsonResponse:
    """Payme Merchant API — barcha metodlar shu yerda (D6-T3).

    ⚠️⚠️ `require_POST` ISHLATILMAYDI. U `405` qaytaradi, Payme esa
       aynan shu holat uchun O'Z kodini belgilagan: `-32300`
       («metod POST emas»). `405` uning uchun «javob yo'q» degani
       bo'lardi.

    ⚠️ TARTIB: POST -> JSON -> avtorizatsiya -> metod.
       Avtorizatsiya JSON'dan KEYIN — Click'dagi «imzo eng birinchi»
       qoidasidan ONGLI chekinish: JSON-RPC javobi so'rovning `id`
       sini qaytarishi kerak va uni bilish uchun tanani o'qish shart.
       Xavf yo'q: tanani Django allaqachon o'qigan va JSON tahlili
       hech qanday domen amalini bajarmaydi.
    """
    ip = mijoz_ip(request)
    holat = {"metod": "", "xom": {}, "avtorizatsiya": False}

    # ⚠️⚠️ YOPILMA, `**lug'at` EMAS. D6-T2 da aynan shu joyda
    #    heterogen `dict[str, object]` ni ochish mypy'ni ko'r qilgan
    #    (har argument tipi yo'qoladi) va u xato TAKRORLANDI —
    #    tuzatilgan naqsh yozib qo'yilgani yetmas ekan.
    def chiqish(tana: dict) -> JsonResponse:
        return _payme_javob(
            tana,
            metod=str(holat["metod"]),
            xom=holat["xom"] if isinstance(holat["xom"], dict) else {},
            avtorizatsiya=bool(holat["avtorizatsiya"]),
            ip=ip,
        )

    if request.method != "POST":
        return chiqish(payme.xato_javobi(payme.USUL_POST_EMAS))

    try:
        xom = json.loads(request.body.decode())
    except (ValueError, UnicodeDecodeError):
        return chiqish(payme.xato_javobi(payme.JSON_XATO))

    if not isinstance(xom, dict):
        return chiqish(payme.xato_javobi(payme.SOROV_NOTOGRI))

    sorov_id = xom.get("id")
    metod = str(xom.get("method") or "")
    params = xom.get("params")
    params = params if isinstance(params, dict) else {}
    holat["metod"] = metod
    holat["xom"] = xom

    if not payme.avtorizatsiya_togrimi(
        request.headers.get("Authorization", ""), kalit=settings.PAYME_SECRET_KEY
    ):
        log.warning("payme: avtorizatsiya rad etildi (metod=%s, ip=%s)", metod, ip)
        return chiqish(payme.xato_javobi(payme.HUQUQ_YETARLI_EMAS, sorov_id=sorov_id))

    holat["avtorizatsiya"] = True

    ishlovchi = PAYME_METODLARI.get(metod)
    if ishlovchi is None:
        return chiqish(payme.xato_javobi(payme.METOD_TOPILMADI, sorov_id=sorov_id))

    try:
        natija = ishlovchi(params)
    except payme.PaymeXatosi as xato:
        log.warning("payme/%s: %s", metod, xato)
        return chiqish(payme.xato_javobi(xato.kod, sorov_id=sorov_id, data=xato.data))
    except TolovXatosi as xato:
        kod = PAYME_SABAB_KODI[xato.sabab]
        data = payme.ACCOUNT_MAYDONI if kod in payme.ACCOUNT_XATOLARI else None
        log.warning("payme/%s: %s -> %s", metod, xato.sabab, kod)
        return chiqish(payme.xato_javobi(kod, sorov_id=sorov_id, data=data))

    return chiqish(payme.javob(natija, sorov_id=sorov_id))
