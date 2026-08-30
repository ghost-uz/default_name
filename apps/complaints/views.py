"""Muammolar — ko'rinishlar (D1-T7, D1-T8)."""

from __future__ import annotations

from typing import cast

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import models
from django.http import (
    Http404,
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.models import User
from apps.accounts.services import bloklangan_idlar
from apps.common.inqiroz import inqiroz_konteksti
from apps.common.ratelimit import tezlik_cheklovi
from apps.common.vote_views import (
    htmx_sorovimi,
    ovoz_qiymatini_oqish,
    ovoz_ruxsati,
    ovozdan_keyingi_manzil,
)
from apps.common.voting import cast_vote, user_votes_for
from apps.gamification.services import oylik_reyting
from apps.moderation.services import avtomatik_belgilash, inqirozni_belgilash
from apps.solutions.forms import SolutionForm
from apps.solutions.models import Solution, SolutionVote

from .forms import ComplaintForm
from .models import Complaint, ComplaintVote, Generation, SavedComplaint
from .selectors import (
    SAHIFA_HAJMI,
    SARALASH_SARLAVHASI,
    SARALASH_TABI,
    filtrni_oqish,
    kursorni_oqish,
    lenta_sahifasi,
    saqlangan_idlari,
    saqlanganlar_queryset,
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
    # ⚠️ Bloklanganlar ro'yxati BIR MARTA olinadi va lentaga
    #    parametr sifatida beriladi (D2-T11).
    bloklanganlar = bloklangan_idlar(user=request.user)

    # ⚠️ Reyting KESHDAN keladi va bazaga bormaydi (D3-T3 qabul
    #    mezoni). Kesh bo'sh bo'lsa bo'sh ro'yxat — hisoblab
    #    yubormaydi (thundering herd sababi `services` da).
    reyting = oylik_reyting()

    muammolar, keyingi_kursor = lenta_sahifasi(
        filtr,
        after_pk=kursorni_oqish(request.GET),
        bloklanganlar=bloklanganlar,
    )

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
    saqlanganlar_toplami = saqlangan_idlari(user=request.user, targets=muammolar)
    for muammo in muammolar:
        muammo.user_vote = ovozlar.get(muammo.pk)
        muammo.saqlangan = muammo.pk in saqlanganlar_toplami

    kontekst = {
        "active_nav": "feed",
        "show_search": True,
        "complaints": muammolar,
        "keyingi_kursor": keyingi_kursor,
        "filtr": filtr,
        "sarlavha": SARALASH_SARLAVHASI[filtr.sort],
        "tablar": SARALASH_TABI.items(),
        "kategoriyalar": yon_panel_kategoriyalari(),
        "avlodlar": Generation.choices,
        "reyting": reyting,
    }

    # ⚠️ HTMX "Yana yuklash" faqat KARTALARNI so'raydi.
    #    Butun sahifani qaytarish yon panel va sarlavhani qaytadan
    #    qurish degani — bekorga trafik, va HTMX uni baribir tashlab
    #    yuborardi. Bu shart JavaScript'siz yo'lni buzmaydi: oddiy
    #    havola bilan kelgan so'rov to'liq sahifani oladi.
    if htmx_sorovimi(request):
        return render(request, "complaints/_feed_sahifa.html", kontekst)

    return render(request, "complaints/feed.html", kontekst)


# ===========================================================================
# Ovoz berish (D1-T8)
# ===========================================================================
@require_POST
@tezlik_cheklovi("ovoz")
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


# ===========================================================================
# Batafsil sahifa (D1-T10 uchun asos)
# ===========================================================================
def complaint_detail(
    request: HttpRequest, slug: str, solution_form: SolutionForm | None = None
) -> HttpResponse:
    """Muammo + unga berilgan yechimlar.

    `solution_form` — yechim formasi XATO bilan qaytganda beriladi
    (apps/solutions/views.py). Shunda foydalanuvchi yozgan matn
    yo'qolmaydi. `TemplateResponse` bilan o'ynash o'rniga oddiy
    parametr: kamroq sehr, ko'proq ko'rinadigan aloqa.

    ⚠️ MUALLIF O'Z YASHIRILGAN POSTINI KO'RA OLADI
       `visible()` bu yerda ATAYLAB qo'llanmaydi. `ModeratedModel`
       docstring'ida yozilganidek: posti yashirilgan foydalanuvchi buni
       BILISHI kerak, aks holda post "yo'qolgan" bo'lib ko'rinadi va
       ishonch yo'qoladi. Boshqalarga esa 404.
    """
    # korinish-istisno: ATAYLAB `visible()` YO'Q — muallif va moderator
    # o'z/yashirilgan postni ko'rishi kerak. Ko'rinish tekshiruvi
    # DARHOL quyida, `Http404` bilan (yuqoridagi docstring'ga qarang).
    muammo = get_object_or_404(
        Complaint.objects.select_related("author", "category", "accepted_solution"),
        slug=slug,
    )

    ozinikimi = request.user.is_authenticated and muammo.author_id == request.user.pk
    if not muammo.is_publicly_visible and not (ozinikimi or request.user.is_staff):
        raise Http404("Bunday muammo yo'q.")

    # ⚠️ Muallifning o'z ko'rishlari sanalmaydi: aks holda post yozgan odam
    #    uni bir necha marta ochib, sanoqni o'zi shishirib qo'yardi va
    #    "ko'rildi" ko'rsatkichi ma'nosini yo'qotardi.
    if not ozinikimi:
        # korinish-istisno: sanoqchini yangilash, kontent ko'rsatish emas.
        Complaint.all_objects.filter(pk=muammo.pk).update(
            views_count=models.F("views_count") + 1
        )
        muammo.views_count += 1  # shu render uchun

    # korinish-istisno: muammo YUQORIDA allaqachon avtorizatsiya qilindi
    # (muallif/staff o'z yashirilgan postini ko'radi). `visible()` bu yerda
    # ota-postning ochiqligini ham talab qiladi — ya'ni muallif o'z
    # yashirilgan postini ochganda yechimlar BUTUNLAY yo'qolardi.
    yechimlar = list(
        Solution.objects.ozi_korinadigan()
        .filter(complaint=muammo)
        .select_related("author")
        # ⚠️ Qabul qilingan yechim DOIM birinchi (maket ham shunday).
        #    `-is_accepted` bo'yicha saralash aynan shuni beradi.
        .order_by("-is_accepted", "-score_cached", "created_at")
    )

    # ⚠️ BLOKLANGAN MUALLIF JAVOBI YIG'ILGAN HOLDA CHIQADI (D2-T11) —
    #    ro'yxatdan OLIB TASHLANMAYDI. Olib tashlansa "3 yechim" deb
    #    yozilgan joyda 2 tasi ko'rinardi va javoblar zanjiri uzilardi
    #    ("yuqoridagi javobga qo'shilaman" — kimga?).
    #
    # ⚠️⚠️ ANONIM JAVOB HECH QACHON YIG'ILMAYDI, garchi muallifi
    #    bloklangan bo'lsa ham. "Bloklangan foydalanuvchi javobi"
    #    yozuvi anonim postda o'quvchiga muallif KIM ekanini aytib
    #    qo'yardi (u bloklaganlari ro'yxatini biladi) — ya'ni blok
    #    anonimlikni ochadigan asbobga aylanardi. Lentada bunday
    #    xavf yo'q: u yerda post shunchaki YO'Q bo'ladi va yo'qlik
    #    signal bermaydi.
    bloklanganlar = set(bloklangan_idlar(user=request.user))
    for yechim in yechimlar:
        yechim.bloklangan = (
            yechim.public_author is not None and yechim.author_id in bloklanganlar
        )
    # ⚠️ Muammoning O'ZI yig'ilmaydi: odam bu sahifaga ataylab kelgan,
    #    ya'ni aynan shu postni ko'rmoqchi. Bayroq faqat tugmani
    #    almashtirish uchun — "Bloklash" o'rniga "Blokdan chiqarish",
    #    aks holda allaqachon bloklangan odamni yana bloklashni
    #    taklif qilardik.
    muammo.bloklangan = (
        muammo.public_author is not None and muammo.author_id in bloklanganlar
    )

    muammo.user_vote = user_votes_for(
        vote_model=ComplaintVote,
        target_field="complaint",
        user=request.user,
        targets=[muammo],
    ).get(muammo.pk)
    muammo.saqlangan = muammo.pk in saqlangan_idlari(
        user=request.user, targets=[muammo]
    )

    yechim_ovozlari = user_votes_for(
        vote_model=SolutionVote,
        target_field="solution",
        user=request.user,
        targets=yechimlar,
    )
    for yechim in yechimlar:
        yechim.user_vote = yechim_ovozlari.get(yechim.pk)

    # ⚠️ Yordam bloki MUALLIFGA HAM, O'QUVCHIGA HAM ko'rinadi (D2-T6):
    #    do'stining postini ochgan odamga ham raqam kerak bo'lishi
    #    mumkin. Yechimlardan birida belgi bo'lsa ham blok chiqadi.
    inqiroz = muammo.inqiroz_aniqlandi or any(y.inqiroz_aniqlandi for y in yechimlar)

    return render(
        request,
        "complaints/detail.html",
        {
            "active_nav": "feed",
            "complaint": muammo,
            "solutions": yechimlar,
            "solution_form": solution_form or SolutionForm(),
            "muallifmi": ozinikimi,
            "tahrirlay_oladi": muammo.tahrirlay_oladimi(request.user),
            "inqiroz": inqiroz,
            **inqiroz_konteksti(),
        },
    )


# ===========================================================================
# Yaratish va tahrirlash (D1-T9)
# ===========================================================================
@login_required
@tezlik_cheklovi("dard_yozish")
def complaint_create(request: HttpRequest) -> HttpResponse:
    """Yangi dard yozish."""
    # `getattr` — `@login_required` autentifikatsiyani kafolatlaydi, lekin
    # tip tekshiruvchi buni bilmaydi (`AnonymousUser` da `can_write` yo'q).
    # Zaxira `False`: noma'lum holatda yozishga RUXSAT BERMAYMIZ.
    if not getattr(request.user, "can_write", False):
        return HttpResponseForbidden("Hisobingiz cheklangan.")

    if request.method == "POST":
        form = ComplaintForm(request.POST, foydalanuvchi=request.user)
        if form.is_valid():
            muammo = form.save(commit=False)
            muammo.author = request.user
            muammo.save()
            # ⚠️ INQIROZ birinchi tekshiriladi: u navbatning eng
            #    tepasiga chiqadi va spam signalidan muhimroq.
            inqirozni_belgilash(
                target=muammo, matnlar=[muammo.title, muammo.description]
            )
            # ⚠️ Shubhali bo'lsa NAVBATGA tushadi, YASHIRILMAYDI
            #    (D2-T5 mahsulot qarori — apps/common/spam.py).
            avtomatik_belgilash(target=muammo, baho=form.spam_bahosi)
            messages.success(request, "Dardingiz e'lon qilindi.")
            return redirect(muammo.get_absolute_url())
    else:
        form = ComplaintForm(foydalanuvchi=request.user)

    return render(
        request,
        "complaints/create.html",
        {"form": form, "tahrirlash": False},
    )


@login_required
def complaint_edit(request: HttpRequest, slug: str) -> HttpResponse:
    """Yozilgan dardni tahrirlash — cheklangan oyna ichida (D1-T9).

    ⚠️ Ruxsat `Complaint.tahrirlay_oladimi()` da: muallif + 30 daqiqa +
       yechim kelmagan. Uchinchi shart eng muhimi — batafsil izoh
       o'sha metodda.
    """
    # korinish-istisno: tahrirlash sahifasi. Ruxsat `tahrirlay_oladimi()`
    # da (FAQAT muallif) — ya'ni begona odam bu yerga umuman kirmaydi.
    # Yashirilgan postni muallif tahrirlashi mumkin: u baribir
    # yashirinligicha qoladi va moderator qayta ko'rib chiqadi.
    muammo = get_object_or_404(Complaint.objects.all(), slug=slug)

    if not muammo.tahrirlay_oladimi(request.user):
        # 403, 404 EMAS: post bor va foydalanuvchi uni ko'ra oladi —
        # faqat tahrirlash oynasi yopilgan. 404 chalg'ituvchi bo'lardi.
        return HttpResponseForbidden(
            "Tahrirlash oynasi yopilgan: 30 daqiqa o'tgan yoki yechim kelgan."
        )

    if request.method == "POST":
        form = ComplaintForm(
            request.POST,
            instance=muammo,
            tahrirlash=True,
            foydalanuvchi=request.user,
        )
        if form.is_valid():
            form.save()
            inqirozni_belgilash(
                target=muammo, matnlar=[muammo.title, muammo.description]
            )
            avtomatik_belgilash(target=muammo, baho=form.spam_bahosi)
            messages.success(request, "O'zgarishlar saqlandi.")
            return redirect(muammo.get_absolute_url())
    else:
        form = ComplaintForm(instance=muammo, tahrirlash=True)

    return render(
        request,
        "complaints/create.html",
        {"form": form, "tahrirlash": True, "complaint": muammo},
    )


# ===========================================================================
# Saqlanganlar (D1-T13)
# ===========================================================================
@require_POST
@tezlik_cheklovi("saqlash")
def dard_saqlash(request: HttpRequest, pk: int) -> HttpResponse:
    """Saqlash / saqlanganlardan olib tashlash — bitta tugma, ikki holat.

    ⚠️ Ovoz berish bilan BIR XIL naqsh: `<form>` + ustiga HTMX, mehmonga
       401 (ko'rinish darajasida app.js login taklifini ko'rsatadi).
    """
    if (javob := ovoz_ruxsati(request)) is not None:
        return javob

    muammo = get_object_or_404(Complaint.objects.visible(), pk=pk)

    # `ovoz_ruxsati()` autentifikatsiyani kafolatlaydi, lekin tip
    # tekshiruvchi buni bilmaydi (`AnonymousUser` qolib ketadi).
    user = cast(User, request.user)

    # ⚠️ `delete()` qaytargan sonni ishlatamiz: "bor edimi?" ni alohida
    #    `exists()` bilan so'rash ikkita so'rov va poyga holati degani.
    ochirildi, _ = SavedComplaint.objects.filter(user=user, complaint=muammo).delete()
    if not ochirildi:
        # ⚠️ `get_or_create`: takroriy so'rov (ikki marta bosish, HTMX
        #    qayta urinishi) `IntegrityError` bermasin.
        SavedComplaint.objects.get_or_create(user=user, complaint=muammo)

    muammo.saqlangan = not ochirildi

    if not htmx_sorovimi(request):
        return redirect(ovozdan_keyingi_manzil(request, muammo.get_absolute_url()))

    return render(
        request,
        "components/_save_button.html",
        {"complaint": muammo, "korsatilsin": request.POST.get("korsatilsin") == "1"},
    )


@login_required
def saqlanganlar(request: HttpRequest) -> HttpResponse:
    """Foydalanuvchi saqlagan muammolar ro'yxati.

    ⚠️ ALOHIDA SAHIFA, profil tabi EMAS — hozircha.
       Maketda "Saqlanganlar" profil sahifasining tabi, lekin profil
       hali maket (D3-T4). Ishlaydigan alohida sahifa ishlamaydigan
       tabdan foydaliroq; D3-T4 uni profilga ko'chirishi mumkin —
       o'shanda faqat shablon o'zgaradi, `selectors` qoladi.
    """
    muammolar = list(saqlanganlar_queryset(user=request.user)[:SAHIFA_HAJMI])

    ovozlar = user_votes_for(
        vote_model=ComplaintVote,
        target_field="complaint",
        user=request.user,
        targets=muammolar,
    )
    for muammo in muammolar:
        muammo.user_vote = ovozlar.get(muammo.pk)
        muammo.saqlangan = True  # ta'rifi bo'yicha hammasi saqlangan

    return render(
        request,
        "complaints/saqlanganlar.html",
        {"active_nav": "profile", "complaints": muammolar},
    )
