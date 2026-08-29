"""Shikoyat yuborish (D2-T1) va moderatsiya navbati (D2-T2)."""

from __future__ import annotations

import functools
from collections.abc import Callable

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.accounts.models import User
from apps.common.inqiroz import inqiroz_konteksti
from apps.common.ratelimit import tezlik_cheklovi
from apps.complaints.models import Complaint
from apps.solutions.models import Solution

from .forms import ReportForm
from .models import (
    AuditAction,
    AuditLog,
    ModerationAction,
    ModerationActionType,
    ReportReason,
)
from .selectors import navbat as navbat_holatlari
from .services import (
    AllaqachonShikoyatQilingan,
    BekorQilibBolmaydi,
    cheklovni_yechish,
    foydalanuvchini_cheklash,
    qaror_qabul_qilish,
    qarorni_bekor_qilish,
    shikoyat_yuborish,
)


def _xavfsiz_next(request: HttpRequest, zaxira: str) -> str:
    """Begona manzilga yo'naltirmaymiz (ochiq yo'naltirish)."""
    xom = request.GET.get("next") or request.POST.get("next") or ""
    if xom and url_has_allowed_host_and_scheme(
        xom, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return xom
    return zaxira


def _shikoyat_sahifasi(
    request: HttpRequest, *, maqsad, tur: str, sarlavha: str
) -> HttpResponse:
    """Shikoyat formasi — muammo va yechim uchun umumiy.

    ⚠️ MAKETDA MODAL EDI, BU YERDA ALOHIDA SAHIFA — ataylab.

       Modal bitta obyekt uchun yaxshi, lekin batafsil sahifada 15 ta
       yechim bo'lishi mumkin: har biriga modal chizish 15 marta
       takrorlangan markup va 15 ta yashirin dialog degani.

       Alohida sahifa yana ikki narsani beradi: JavaScript'siz ishlaydi
       va qoidalar matnini to'liq ko'rsatishga joy bor — shikoyat
       yuborishdan oldin odam nima qoidabuzarlik ekanini o'qiy oladi.

       Keyinchalik uni HTMX bilan dialogga yuklash mumkin (`hx-get`),
       lekin manzil va forma o'zgarmaydi.
    """
    keyingi = _xavfsiz_next(request, maqsad.get_absolute_url())

    if request.method == "POST":
        form = ReportForm(request.POST)
        if form.is_valid():
            kwargs = {tur: maqsad}
            try:
                # Eskalatsiya bayrog'i ATAYLAB olinmaydi — pastdagi
                # izohga qarang: u foydalanuvchiga ko'rsatilmaydi.
                shikoyat_yuborish(
                    reporter=request.user,
                    reason=form.cleaned_data["reason"],
                    comment=form.cleaned_data["comment"],
                    **kwargs,
                )
            except AllaqachonShikoyatQilingan as exc:
                form.add_error(None, exc.messages[0])
            except PermissionDenied as exc:
                return HttpResponseForbidden(str(exc))
            else:
                # ⚠️ Foydalanuvchiga eskalatsiya HAQIDA AYTILMAYDI.
                #    "Yana 2 ta shikoyat kerak" degan xabar odamlarni
                #    kelishib shikoyat qilishga undardi — ya'ni tizimni
                #    o'yinga aylantirardi.
                messages.success(
                    request,
                    "Shikoyatingiz yuborildi. Moderatorlar ko'rib chiqadi.",
                )
                return redirect(keyingi)
    else:
        form = ReportForm()

    return render(
        request,
        "moderation/shikoyat.html",
        {
            "form": form,
            "maqsad": maqsad,
            "sarlavha": sarlavha,
            "next": keyingi,
            # `XAVF` sababi alohida ko'rsatiladi (D2-T6 ga tayyorgarlik).
            "xavf_sababi": ReportReason.XAVF,
        },
    )


@login_required
@tezlik_cheklovi("shikoyat")
def dard_shikoyat(request: HttpRequest, pk: int) -> HttpResponse:
    """Muammoga shikoyat.

    ⚠️ `visible()` — yashirilgan postga shikoyat qilishning ma'nosi yo'q:
       u allaqachon navbatda yoki olib tashlangan.
    """
    muammo = get_object_or_404(Complaint.objects.visible(), pk=pk)
    return _shikoyat_sahifasi(
        request, maqsad=muammo, tur="complaint", sarlavha=muammo.title
    )


@login_required
@tezlik_cheklovi("shikoyat")
def yechim_shikoyat(request: HttpRequest, pk: int) -> HttpResponse:
    """Yechimga shikoyat."""
    yechim = get_object_or_404(Solution.objects.visible(), pk=pk)
    return _shikoyat_sahifasi(
        request,
        maqsad=yechim,
        tur="solution",
        sarlavha=yechim.content[:80],
    )


# ===========================================================================
# Moderatsiya navbati (D2-T2)
# ===========================================================================
def moderator_kerak(fn: Callable) -> Callable:
    """Staff bo'lmaganga `Http404` — 403 EMAS.

    ⚠️ ATAYLAB 404. `403 Forbidden` "bu manzil bor, lekin sizga ruxsat
       yo'q" degani — ya'ni moderatsiya interfeysining manzilini
       tasdiqlab beradi. Bu qidirib topish uchun boshlang'ich nuqta.
       404 esa hech narsa aytmaydi.

       `staff_member_required` ham to'g'ri kelmaydi: u admin login
       sahifasiga yo'naltiradi va shu bilan manzil borligini oshkor
       qiladi.
    """

    @functools.wraps(fn)
    def orash(request: HttpRequest, *args, **kwargs):
        if not (request.user.is_authenticated and request.user.is_staff):
            raise Http404()
        return fn(request, *args, **kwargs)

    return orash


# Bekor qilish tugmasi ko'rsatiladigan so'nggi qarorlar soni.
SONGGI_QARORLAR = 8


@moderator_kerak
def navbat(request: HttpRequest) -> HttpResponse:
    """Moderatsiya navbati — bitta ekran, bitta qaror.

    ⚠️ Nima uchun admin emas (task tavsifidan): admin shikoyatlarni
       birma-bir ko'rsatadi va kontentni ko'rish uchun har safar boshqa
       sahifaga o'tish kerak. Bu yerda kontent, shikoyat sabablari va
       tugmalar BITTA kartada.
    """
    holatlar = navbat_holatlari()
    return render(
        request,
        "moderation/navbat.html",
        {
            "holatlar": holatlar,
            "kechikkanlar": sum(1 for h in holatlar if h.kechikkanmi),
            "shoshilinchlar": sum(1 for h in holatlar if h.shoshilinchmi),
            "songgi_qarorlar": (
                ModerationAction.objects.select_related(
                    "moderator", "complaint", "solution"
                )
                .filter(bekor_qiladi__isnull=True)
                .prefetch_related("bekor_qilishlar")[:SONGGI_QARORLAR]
            ),
            "choralar": [
                (t.value, t.label)
                for t in ModerationActionType
                if t != ModerationActionType.BEKOR_QILISH
            ],
            # ⚠️ Tugmadagi "7 kunga cheklash" yozuvi SOZLAMADAN keladi
            #    (D2-T11). Shablonga qo'lda yozilsa, sozlama
            #    o'zgarganda interfeys yolg'on gapirib qolardi va buni
            #    hech kim payqamasdi.
            "cheklov_kun": settings.CHEKLOV_MUDDATI_KUN,
        },
    )


def _maqsadni_olish(*, turi: str, pk: int):
    """Chora ko'riladigan obyekt.

    ⚠️ `all_objects` — moderatorga YASHIRILGAN va O'CHIRILGAN kontent ham
       kerak: u aynan shular ustidan qaror qabul qiladi.
    """
    if turi == "muammo":
        # korinish-istisno: moderatsiya navbati — yashirilgan kontentni
        # KO'RSATISHI kerak. Himoyasi `visible()` emas, `@moderator_kerak`
        # (staff bo'lmaganga Http404).
        return get_object_or_404(Complaint.all_objects, pk=pk)
    # korinish-istisno: yuqoridagi bilan bir xil sabab.
    return get_object_or_404(Solution.all_objects, pk=pk)


def _qaror(request: HttpRequest, *, turi: str, pk: int) -> HttpResponse:
    maqsad = _maqsadni_olish(turi=turi, pk=pk)
    chora = request.POST.get("action", "")
    izoh = request.POST.get("izoh", "")

    try:
        yozuv = qaror_qabul_qilish(
            moderator=request.user, target=maqsad, action=chora, izoh=izoh
        )
    except ValueError as exc:
        return HttpResponseForbidden(str(exc))

    if request.headers.get("HX-Request"):
        # HTMX: kartaning o'rniga "bajarildi" tasmasi (bekor qilish bilan).
        return render(request, "moderation/_bajarildi.html", {"chora": yozuv})

    messages.success(request, f"{yozuv.get_action_display()} — {yozuv.target_nomi}.")
    return redirect("moderatsiya_navbat")


@moderator_kerak
@require_POST
def qaror_muammo(request: HttpRequest, pk: int) -> HttpResponse:
    return _qaror(request, turi="muammo", pk=pk)


@moderator_kerak
@require_POST
def qaror_yechim(request: HttpRequest, pk: int) -> HttpResponse:
    return _qaror(request, turi="yechim", pk=pk)


@moderator_kerak
@require_POST
def qarorni_bekor(request: HttpRequest, pk: int) -> HttpResponse:
    """Qarorni orqaga qaytaradi (yozuv o'chirilmaydi — kompensatsiya)."""
    chora = get_object_or_404(ModerationAction, pk=pk)
    try:
        qarorni_bekor_qilish(moderator=request.user, chora=chora)
    except BekorQilibBolmaydi as exc:
        messages.error(request, exc.messages[0])
    else:
        messages.info(request, f"Qaror bekor qilindi — {chora.target_nomi}.")
    return redirect("moderatsiya_navbat")


# ⚠️ Bir sahifadagi yozuvlar soni. Jurnal tez o'sadi, ya'ni cheklovsiz
#    ro'yxat bir kuni sahifani o'ldiradi.
JURNAL_SAHIFA = 50


@moderator_kerak
def jurnal(request: HttpRequest) -> HttpResponse:
    """Audit jurnali — staff uchun (D2-T7).

    ⚠️ Django admin ham bor, lekin bu sahifa ATAYLAB alohida: nizo yoki
       huquqiy so'rov paytida jurnalni O'QISH kerak bo'ladi, admin esa
       tahrirlash uchun mo'ljallangan interfeys va u yerda "nima
       bo'lgan?" savoliga javob qidirish noqulay.

    ⚠️ Sahifalash RAQAMLI (`Paginator`), lentadagidek kursor emas:
       jurnalda "3-sahifaga o'tish" real ehtiyoj, lentada esa yo'q.
    """
    yozuvlar = AuditLog.objects.select_related("actor")

    tanlangan = request.GET.get("harakat", "")
    if tanlangan in AuditAction.values:
        yozuvlar = yozuvlar.filter(action=tanlangan)

    sahifalovchi = Paginator(yozuvlar, JURNAL_SAHIFA)
    sahifa = sahifalovchi.get_page(request.GET.get("sahifa"))

    return render(
        request,
        "moderation/jurnal.html",
        {
            "sahifa": sahifa,
            "harakatlar": AuditAction.choices,
            "tanlangan": tanlangan,
            "jami": sahifalovchi.count,
        },
    )


@moderator_kerak
def qollanma(request: HttpRequest) -> HttpResponse:
    """Inqirozli kontent bilan ishlash qo'llanmasi (D2-T6 qabul mezoni).

    ⚠️ Qo'llanma KOD ICHIDA va navbatdan bir bosish narida — ataylab.
       Alohida hujjatda turgan qo'llanma tungi soat 2 da topilmaydi,
       task tavsifi esa aynan shu holatdan ogohlantiradi: "tayyor
       siyosat bo'lmasa qaror tungi soat 2 da shoshib qabul qilinadi".
    """
    return render(request, "moderation/qollanma.html", inqiroz_konteksti())


# ===========================================================================
# Foydalanuvchini cheklash — navbatdan (D2-T11)
# ===========================================================================
# ⚠️ NEGA NAVBATDA, ADMINDA EMAS.
#    Django admin `is_banned` maydonini tahrirlash imkonini beradi,
#    lekin u AUDIT JURNALIGA HECH NARSA YOZMAYDI (D2-T7): kim, qachon,
#    nega chekladi — iz qolmasdi. Bu yerdagi yo'l `services` orqali
#    o'tadi, ya'ni har cheklov jurnalda ko'rinadi.
#
# ⚠️ Cheklov qarori KONTENT qarori bilan BITTA ekranda, lekin ALOHIDA
#    formada: HTML ichma-ich forma qo'llab-quvvatlamaydi, va bu ajratish
#    to'g'ri ham — "postni yashirish" va "odamni cheklash" bir bosishda
#    tasodifan birga ketmasligi kerak.
def _cheklov_maqsadi(pk: int) -> User:
    """Cheklanadigan foydalanuvchi.

    ⚠️ O'chirilgan hisob CHEKLANMAYDI: uning kontenti allaqachon
       anonimlashtirilgan (D2-T8) va cheklash hech narsani
       o'zgartirmaydi — faqat jurnalni ma'nosiz yozuv bilan to'ldirardi.
    """
    return get_object_or_404(User, pk=pk, ochirilgan_at__isnull=True)


@moderator_kerak
@require_POST
def foydalanuvchini_cheklash_view(request: HttpRequest, pk: int) -> HttpResponse:
    """Moderator foydalanuvchini QO'LDA cheklaydi.

    ⚠️ QO'LDA CHEKLOV AVTOMATIKANI KUTMAYDI. Uch ogohlantirish —
       o'rtacha holat uchun; og'ir holat (masalan, uyushtirilgan
       hujum yoki tahdid) uchun moderator birinchi chorada ham
       to'xtata olishi kerak. Aks holda task tavsifidagi muammo
       teskari tomondan qaytardi: yagona qurol AVTOMATIKA bo'lsa,
       moderator uchta qoidabuzarlik "yig'ilishini" kutib o'tirardi.

    ⚠️ MODERATOR O'ZINI CHEKLAY OLMAYDI — bu xato bosish, qasd emas;
       lekin oqibati bir xil: moderator o'z hisobini yopib qo'yardi.
    """
    kim = _cheklov_maqsadi(pk)
    sabab = request.POST.get("sabab", "").strip()
    doimiy = request.POST.get("doimiy") == "1"

    if kim.pk == request.user.pk:
        messages.error(request, "O'zingizni cheklay olmaysiz.")
        return redirect(_xavfsiz_next(request, "moderatsiya_navbat"))

    foydalanuvchini_cheklash(
        moderator=request.user,
        user=kim,
        sabab=sabab or "Moderator qarori (sabab ko'rsatilmagan).",
        doimiy=doimiy,
    )
    messages.success(
        request,
        f"@{kim.username} "
        + ("doimiy bloklandi." if doimiy else "vaqtinchalik cheklandi."),
    )
    return redirect(_xavfsiz_next(request, "moderatsiya_navbat"))


@moderator_kerak
@require_POST
def cheklovni_yechish_view(request: HttpRequest, pk: int) -> HttpResponse:
    """Cheklovni orqaga qaytaradi.

    ⚠️ QAYTARISH YO'LI SHU YERDA BO'LISHI SHART. Cheklash bir bosish,
       yechish esa faqat adminda bo'lsa — moderator xatosini
       tuzatmaydi, chunki tuzatish yo'li ko'rinmaydi. Bu qoida
       foydalanuvchi bloklari uchun ham amal qiladi (`/hisob/`).
    """
    kim = get_object_or_404(User, pk=pk)
    cheklovni_yechish(
        moderator=request.user,
        user=kim,
        sabab=request.POST.get("sabab", "").strip(),
    )
    messages.info(request, f"@{kim.username} cheklovi yechildi.")
    return redirect(_xavfsiz_next(request, "moderatsiya_navbat"))
