"""Gamifikatsiya — xizmat funksiyalari (D1-T10, D3-T1, D3-T2, D3-T3)."""

from __future__ import annotations

import logging
from datetime import date, datetime

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import models, transaction
from django.utils import timezone

from .models import (
    KARMA_QIYMATLARI,
    KOMPENSATSIYA_SABABLARI,
    Badge,
    KarmaEvent,
    KarmaReason,
    NishonMetrikasi,
    UserBadge,
)

log = logging.getLogger(__name__)


@transaction.atomic
def karma_yoz(*, user, reason: str, solution=None) -> KarmaEvent | None:
    """Karma hodisasini jurnalga yozadi va keshni yangilaydi.

    `user` `None` bo'lsa (o'chirilgan hisob) hech nima qilinmaydi —
    chaqiruvchida har safar `if` yozilmasin.

    ⚠️ Ball qiymati CHAQIRUVCHIDAN OLINMAYDI, `KARMA_QIYMATLARI` dan.
       Aks holda qoida ikki joyda bo'lardi va bir kuni faqat bittasi
       o'zgartirilardi (masalan +15 dan +10 ga). Jurnalning butun
       ma'nosi — qoida bitta joyda bo'lishi.

    ⚠️ `karma_cached` `F()` bilan yangilanadi: ikki hodisa bir vaqtda
       yozilsa oddiy `user.karma_cached += x` biri ikkinchisini
       yo'qotardi (o'qish-o'zgartirish-yozish poygasi).
    """
    if user is None:
        return None

    # ⚠️ KOMPENSATSIYA SABABLARI BU YO'LDAN O'TMAYDI (D3-T1).
    #    Ularning balli TARIXGA bog'liq va `KARMA_QIYMATLARI` da yo'q.
    #    Guard bo'lmasa `KeyError` chiqardi — u ham to'xtatadi, lekin
    #    "nega?" degan savolga javob bermasdi. Bundan ham yomoni:
    #    kimdir bir kuni "tuzatish" uchun ularni lug'atga qo'shib
    #    qo'yardi va kompensatsiya jimgina noto'g'ri ball yozardi.
    if reason in KOMPENSATSIYA_SABABLARI:
        raise ValueError(
            f"{reason!r} — kompensatsiya sababi, balli hisoblanadi. "
            "`kontent_karmasini_qaytarish()` / `kontent_karmasini_tiklash()` "
            "ishlating."
        )

    ball = KARMA_QIYMATLARI[reason]
    hodisa = KarmaEvent.objects.create(
        user=user, reason=reason, points=ball, solution=solution
    )

    type(user).objects.filter(pk=user.pk).update(
        karma_cached=models.F("karma_cached") + ball
    )
    # Chaqiruvchida eskirgan qiymat qolmasin (masalan darhol render qilinsa).
    user.refresh_from_db(fields=["karma_cached"])
    return hodisa


def karmani_qayta_hisoblash(*, user) -> int:
    """`karma_cached` ni jurnaldan QAYTA TIKLAYDI.

    ⚠️ Bu funksiya kesh haqiqatga mos ekanini isbotlaydigan yagona yo'l
       va D7-T3 (tiklash mashqi) uchun kerak. Usiz "jurnal haqiqiy manba"
       degan da'vo tekshirilmaydigan bo'lib qolardi.
    """
    jami = KarmaEvent.objects.filter(user=user).aggregate(
        s=models.Sum("points", default=0)
    )["s"]
    type(user).objects.filter(pk=user.pk).update(karma_cached=jami)
    user.refresh_from_db(fields=["karma_cached"])
    return jami


def yechim_qabul_karmasi(*, solution) -> KarmaEvent | None:
    """Yechim qabul qilinganda muallifga karma.

    ⚠️ ANONIM YECHIMDA HAM YOZILADI: anonimlik faqat KO'RSATISHGA
       taalluqli (D1-T6), ballar esa haqiqiy hisobga tegishli. Aks holda
       anonim javob berish jazolanardi va odamlar eng qimmatli
       (og'ir mavzudagi) javoblarni yozmay qo'yardi.
    """
    return karma_yoz(
        user=solution.author,
        reason=KarmaReason.SOLUTION_ACCEPTED,
        solution=solution,
    )


def yechim_qabuli_bekor_karmasi(*, solution) -> KarmaEvent | None:
    """Qabul bekor qilinganda TESKARI yozuv (o'chirish emas)."""
    return karma_yoz(
        user=solution.author,
        reason=KarmaReason.SOLUTION_UNACCEPTED,
        solution=solution,
    )


# ===========================================================================
# Ovoz karmasi (D3-T1)
# ===========================================================================
def ovoz_karmasi(*, solution, natija, qiymat: int, ovoz_beruvchi) -> KarmaEvent | None:
    """Ovoz berilgandan KEYIN yechim muallifiga karma yozadi.

    ⚠️ NEGA BU YERDA, `cast_vote()` ICHIDA EMAS.
       `apps/common/voting.py` boshqa ilovalarni import qilmaydi (u eng
       quyi qatlam). Bundan tashqari karma FAQAT yechimga tegishli —
       dardga ovoz karma bermaydi — ya'ni mantiq umumiy funksiyada
       turishi ham noto'g'ri bo'lardi: u yerda "bu Complaint emasmi?"
       degan tekshiruv paydo bo'lardi.

    ⚠️⚠️ O'ZIGA BERILGAN OVOZ KARMA BERMAYDI.
       Ovoz berishning o'zi to'silmagan (bu D1-T5 qarori va unga
       tegilmaydi), lekin karma berilsa bu OCHIQ FERMA bo'lardi:
       yechim yoz → o'zingga ovoz ber → +2, cheksiz takrorlanadi.

    ⚠️ MINUS OVOZ NOL: `↓` faqat `score_cached` ga ta'sir qiladi
       (`KARMA_QIYMATLARI` izohiga qarang). Shuning uchun quyida faqat
       PLUS ovoz holati o'zgarganda yozuv qo'shiladi.
    """
    from apps.common.models import VoteValue

    muallif = solution.author
    if muallif is None or ovoz_beruvchi is None:
        return None
    if muallif.pk == getattr(ovoz_beruvchi, "pk", None):
        return None

    # Plus ovoz holati QANDAY o'zgardi: `cast_vote()` dagi `delta_up`
    # bilan bir xil mantiq, lekin natijadan qayta tiklangan.
    endi_plus = natija.value == VoteValue.UP
    if natija.created:
        oldin_plus = False
    elif natija.removed:
        # Qaytarib olingan ovoz — bosilgan tugma bilan bir xil qiymatda
        # bo'lgan (aks holda u ALMASHTIRISH bo'lardi).
        oldin_plus = qiymat == VoteValue.UP
    else:  # switched
        oldin_plus = not endi_plus

    if endi_plus and not oldin_plus:
        sabab = KarmaReason.SOLUTION_UPVOTED
    elif oldin_plus and not endi_plus:
        sabab = KarmaReason.SOLUTION_UPVOTE_OLINDI
    else:
        # Minus ovoz berildi yoki olindi — karmaga tegmaydi.
        return None

    return karma_yoz(user=muallif, reason=sabab, solution=solution)


# ===========================================================================
# Kompensatsiya: kontent ko'rinmay qolganda (D3-T1)
# ===========================================================================
def _yechim_hisobi(*, solution) -> tuple[int, int]:
    """`(jami_ball, kompensatsiya_jami)` — shu yechim bo'yicha jurnaldan.

    `kompensatsiya_jami` manfiy bo'lsa, karma HOZIR qaytarib olingan.
    """
    qs = KarmaEvent.objects.filter(solution=solution)
    jami = qs.aggregate(s=models.Sum("points", default=0))["s"]
    kompensatsiya = qs.filter(reason__in=KOMPENSATSIYA_SABABLARI).aggregate(
        s=models.Sum("points", default=0)
    )["s"]
    return jami, kompensatsiya


def _kompensatsiya_yozish(*, solution, reason: str, ball: int) -> KarmaEvent | None:
    """Hisoblangan balli yozuv — `KARMA_QIYMATLARI` dan o'tmaydi.

    ⚠️ Bu `karma_yoz()` ning YAGONA istisnosi va shuning uchun ALOHIDA,
       ichki funksiya: umumiy yo'l "ball chaqiruvchidan olinmaydi"
       qoidasini saqlab qoladi.
    """
    if ball == 0 or solution.author_id is None:
        return None

    hodisa = KarmaEvent.objects.create(
        user_id=solution.author_id, reason=reason, points=ball, solution=solution
    )
    # ⚠️ `F()` bilan — `karma_yoz()` dagi bir xil sabab: ikki hodisa bir
    #    vaqtda yozilsa oddiy `+=` biri ikkinchisini yo'qotardi.
    get_user_model()._default_manager.filter(pk=solution.author_id).update(
        karma_cached=models.F("karma_cached") + ball
    )
    log.info("Karma kompensatsiyasi: yechim #%s %+d (%s)", solution.pk, ball, reason)
    return hodisa


@transaction.atomic
def kontent_karmasini_qaytarish(*, solution) -> KarmaEvent | None:
    """Yechim ko'rinmay qolganda BERILGAN karmani qaytarib oladi.

    ⚠️ QABUL MEZONI (D3-T1): "kontent o'chirilsa teskari hodisa yoziladi".
       Yozuvlar O'CHIRILMAYDI — kompensatsiya qo'shiladi. Sabab
       `KarmaEvent` docstring'ida: "nega karmam kamaydi?" savoliga javob
       qolishi kerak.

    ⚠️⚠️ IDEMPOTENT — va bu BAYROQ bilan emas, HISOB bilan.
       Maqsad: shu yechim bo'yicha sof karma NOL bo'lsin. Shuning uchun
       yoziladigan ball = `0 - jami`. Ikkinchi marta chaqirilsa `jami`
       allaqachon nol va hech nima yozilmaydi.

       `is_karma_reversed` degan bayroq qo'yish oson ko'rinadi, lekin u
       jurnaldan uzilib qolardi: birov qo'lda yozuv qo'shsa yoki
       migratsiya ishlatsa, bayroq yolg'on gapirardi. Hisob esa har
       doim jurnalning O'ZIDAN keladi.
    """
    jami, _ = _yechim_hisobi(solution=solution)
    return _kompensatsiya_yozish(
        solution=solution,
        reason=KarmaReason.KONTENT_OLIB_TASHLANDI,
        ball=-jami,
    )


@transaction.atomic
def kontent_karmasini_tiklash(*, solution) -> KarmaEvent | None:
    """Moderator qarorini bekor qilganda karmani qaytarib beradi.

    ⚠️ Bu ham IDEMPOTENT: maqsad — kompensatsiya yozuvlarining sof
       yig'indisi NOL bo'lsin, ya'ni yechim o'z tabiiy karmasiga
       qaytsin. Yoziladigan ball = `-kompensatsiya_jami`.

    ⚠️ Chora bekor qilinganda karma QAYTARILISHI SHART: aks holda
       moderatorning xatosi foydalanuvchining ballida abadiy qolardi.
       Bu D2-T11 dagi "bekor qilingan chora qoidabuzarlik sanalmaydi"
       qoidasining karmadagi ko'rinishi.
    """
    _, kompensatsiya = _yechim_hisobi(solution=solution)
    return _kompensatsiya_yozish(
        solution=solution,
        reason=KarmaReason.KONTENT_TIKLANDI,
        ball=-kompensatsiya,
    )


# ===========================================================================
# Nishonlar (D3-T2)
# ===========================================================================
def _metrikalar(*, user) -> dict[str, int]:
    """Foydalanuvchining barcha o'lchovlari — IKKI so'rovda.

    ⚠️⚠️ ANONIM ISH HAM SANALADI (foydalanuvchi qarori). Filtrda
       `is_anonymous` YO'Q: anonim javob berish jazolanmasligi kerak —
       D3-T1 dagi karma qarori bilan aynan bir xil sabab.

    ⚠️ `visible()` esa BOR: moderator olib tashlagan yechim nishonga
       hisoblanmaydi. D3-T1 da uning karmasi ham qaytariladi, ya'ni
       ikkala tizim bir xil narsani "yo'q" deb biladi.

    ⚠️ Metrikalar HAR SAFAR QAYTA HISOBLANADI, keshlanmaydi. Kesh
       bo'lsa u haqiqatdan uzilardi (aynan `karma_cached` da bo'lgani
       kabi) va nishon "bor edi, endi yo'q" holatiga tushardi. Ikki
       so'rov bu narxni to'lashga arziydi — funksiya kamdan-kam
       chaqiriladi.
    """
    from apps.complaints.models import Complaint
    from apps.solutions.models import Solution

    yechimlar = (
        Solution.objects.visible()
        .filter(author=user)
        .aggregate(
            soni=models.Count("pk"),
            qabul=models.Count("pk", filter=models.Q(is_accepted=True)),
            ovoz=models.Sum("upvotes_cached", default=0),
        )
    )
    dardlar = Complaint.objects.visible().filter(author=user).count()

    return {
        NishonMetrikasi.KARMA: max(user.karma_cached, 0),
        NishonMetrikasi.YECHIMLAR: yechimlar["soni"],
        NishonMetrikasi.QABUL_QILINGAN: yechimlar["qabul"],
        NishonMetrikasi.DARDLAR: dardlar,
        NishonMetrikasi.OLINGAN_OVOZ: yechimlar["ovoz"],
    }


# ⚠️ Guard test buni `NishonMetrikasi` bilan solishtiradi: yangi metrika
#    qo'shilib, hisoblash unutilsa, nishon HECH QACHON berilmasdi va bu
#    hech qanday xato bermasdi.
NISHON_METRIKALARI: frozenset[str] = frozenset(NishonMetrikasi.values)


@transaction.atomic
def nishonlarni_tekshirish(*, user) -> list[UserBadge]:
    """Foydalanuvchi yangi nishon olganmi — tekshiradi va beradi.

    ⚠️ SIGNAL EMAS, OCHIQ CHAQIRUV — D1-T10 dagi bir xil qaror:
       signal `bulk_create`, `loaddata` va ommaviy import'da ishlamaydi.

    ⚠️ NISHON QAYTIB OLINMAYDI: bu funksiya faqat QO'SHADI. Karma
       tushib ketsa ham (kompensatsiya, D3-T1) nishon qoladi — sabab
       `UserBadge` docstring'ida.

    ⚠️ `ignore_conflicts` — poyga holati: ikki so'rov bir vaqtda
       tekshirsa, ikkinchisi noyoblik cheklovига urilardi. Xato o'rniga
       jimgina o'tkazib yuborish TO'G'RI: natija baribir bir xil.
    """
    if user is None or getattr(user, "pk", None) is None:
        return []

    faol = list(Badge.objects.filter(is_active=True))
    if not faol:
        return []

    bor = set(UserBadge.objects.filter(user=user).values_list("badge_id", flat=True))
    kutilayotgan = [b for b in faol if b.pk not in bor]
    if not kutilayotgan:
        return []

    olchovlar = _metrikalar(user=user)
    yangilar = [
        UserBadge(user=user, badge=b)
        for b in kutilayotgan
        if olchovlar.get(b.metrika, 0) >= b.chegara
    ]
    if yangilar:
        UserBadge.objects.bulk_create(yangilar, ignore_conflicts=True)
        log.info(
            "Nishon berildi: user=%s -> %s",
            user.pk,
            [b.badge.slug for b in yangilar],
        )
    return yangilar


def nishon_holati(*, profil, ozimi: bool) -> list[dict]:
    """Profil uchun nishonlar ro'yxati (D3-T2 + D3-T4).

    ⚠️⚠️ QULFLANGAN NISHON VA PROGRESS FAQAT EGASIGA (foydalanuvchi
       qarori). Ommaviy profilda faqat OLINGAN nishonlar, RAQAMSIZ.

       Sabab — D3-T4 dagi sanoq-teshigining qaytishi: ommaviy sanoq
       anonim ishni hisoblamaydi, nishon esa hisoblaydi. Progress
       ommaviy bo'lsa, ayirma anonim ishlarning ANIQ sonini berardi.
       Olingan nishonning o'zi esa faqat "kamida N ta" degan noaniq
       xulosaga imkon beradi — bu ongli qabul qilingan qoldiq.

    ⚠️ Mehmon uchun ham ishlaydi (`ozimi=False`).
    """
    olingan = {
        ub.badge_id: ub.berilgan_at
        for ub in UserBadge.objects.filter(user=profil).select_related("badge")
    }

    if not ozimi:
        return [
            {
                "badge": b,
                "olingan": True,
                "berilgan_at": olingan[b.pk],
                "progress": None,
            }
            for b in Badge.objects.filter(is_active=True, pk__in=olingan)
        ]

    olchovlar = _metrikalar(user=profil)
    natija = []
    for b in Badge.objects.filter(is_active=True):
        bormi = b.pk in olingan
        natija.append(
            {
                "badge": b,
                "olingan": bormi,
                "berilgan_at": olingan.get(b.pk),
                # ⚠️ Progress chegaradan OSHMAYDI: "12/10" chalkash
                #    ko'rinardi va progress chizig'i buzilardi.
                "progress": None
                if bormi
                else min(olchovlar.get(b.metrika, 0), b.chegara),
            }
        )
    return natija


# ===========================================================================
# Oylik reyting (D3-T3)
# ===========================================================================
REYTING_SONI = 5

# ⚠️ TTL beat oralig'idan (1 soat) UZUNROQ — ataylab. Bitta o'tkazib
#    yuborilgan ishga tushish (worker qayta joylashdi, navbat band edi)
#    reytingni BO'SHATMASLIGI kerak: eskiroq reyting bo'sh paneldan
#    yaxshiroq.
REYTING_TTL = 2 * 60 * 60


def reyting_kaliti(oy: date | None = None) -> str:
    """Kesh kaliti — OY bilan birga.

    ⚠️ Oy kalitda bo'lishi SHART. Aks holda oy almashganda eski
       reyting TTL tugagunicha ko'rinib turardi va "oyning
       maslahatchilari" o'tgan oyniki bo'lardi — hech qanday xato
       bermasdan.
    """
    oy = oy or timezone.localdate()
    return f"reyting:{oy:%Y-%m}"


def _oy_oraligi(oy: date) -> tuple[datetime, datetime]:
    """Oyning boshi va oxiri — MAHALLIY vaqt bo'yicha.

    ⚠️ `localdate`/`localtime`, UTC EMAS. Baza UTC'da saqlaydi, lekin
       "oy" — foydalanuvchi tushunchasi: Toshkentda 1-sentabr soat
       02:00 da yozilgan hodisa UTC'da hali avgust bo'ladi va
       sentabr reytingiga TUSHMASDI (D3-T4 dagi bir xil tuzoq).
    """
    boshi = timezone.make_aware(
        datetime(oy.year, oy.month, 1), timezone.get_current_timezone()
    )
    keyingi = date(oy.year + (oy.month // 12), (oy.month % 12) + 1, 1)
    oxiri = timezone.make_aware(
        datetime(keyingi.year, keyingi.month, 1), timezone.get_current_timezone()
    )
    return boshi, oxiri


def oylik_reytingni_hisoblash(*, oy: date | None = None, soni: int = REYTING_SONI):
    """Reytingni JURNALDAN hisoblaydi — IKKI so'rovda.

    ⚠️ `karma_cached` EMAS, `KarmaEvent` yig'indisi: kesh UMUMIY karmani
       saqlaydi, reyting esa SHU OYNIKINI so'raydi. D3-T1 ledgeri
       aynan shuning uchun bor ("ledger oylik reytingni ham arzon
       qiladi" — task tavsifidan).

    ⚠️⚠️ O'CHIRILGAN va HOZIR CHEKLANGAN hisoblar CHIQARILADI.
       · O'chirilgan (D2-T8) — hisob anonimlashtirilgan, uni
         ko'rsatish ma'nosiz.
       · Cheklangan (D2-T11) — REYTING TAVSIYA, tarix emas. Nishon
         (D3-T2) va ekspert tasdig'i (D3-T5) cheklovda ham QOLADI,
         chunki ular odamning YOZUVI. Reyting esa platformaning
         "mana bu odamga qarang" degan gapi — cheklangan odamni
         ko'rsatish platformaning o'z qaroriga zid bo'lardi.

    ⚠️ Faqat MUSBAT yig'indi: nol yoki manfiy natija bilan "oyning
       maslahatchisi" ro'yxatiga tushish ma'nosiz.
    """
    from apps.accounts.models import User

    oy = oy or timezone.localdate()
    boshi, oxiri = _oy_oraligi(oy)

    juftlar = list(
        KarmaEvent.objects.filter(created_at__gte=boshi, created_at__lt=oxiri)
        .values("user_id")
        .annotate(jami=models.Sum("points"))
        .filter(jami__gt=0)
        .order_by("-jami", "user_id")[: soni * 3]
    )
    if not juftlar:
        return []

    # ⚠️ `soni * 3` yuqorida: chiqarib tashlanadiganlar (o'chirilgan,
    #    cheklangan) o'rnini to'ldirish uchun zaxira. Ikkinchi so'rov
    #    yuborib "yana kerak" deyishdan arzonroq.
    foydalanuvchilar = {
        u.pk: u
        for u in User.objects.filter(
            pk__in=[j["user_id"] for j in juftlar], ochirilgan_at__isnull=True
        )
    }

    natija = []
    for j in juftlar:
        user = foydalanuvchilar.get(j["user_id"])
        if user is None or user.is_currently_banned:
            continue
        natija.append(
            {
                "username": user.username,
                "nom": user.display_name,
                "initial": user.initial,
                "karma": j["jami"],
            }
        )
        if len(natija) >= soni:
            break
    return natija


def oylik_reyting(oy: date | None = None) -> list[dict]:
    """⭐⭐ QABUL MEZONI: "reyting so'rovi KESHDAN keladi".

    Bu funksiya BAZAGA UMUMAN BORMAYDI. U lentaning yon panelida, ya'ni
    HAR SAHIFADA chaqiriladi — hisoblash u yerda bo'lsa, har ko'rish
    ikkita agregat so'rov qilardi.

    ⚠️ Kesh BO'SH bo'lsa BO'SH RO'YXAT qaytadi, hisoblab yubormaydi.
       "Yo'q bo'lsa hisoblab, keshga solamiz" jozibali ko'rinadi, lekin
       Redis qayta ishga tushgan paytda BARCHA so'rovlar bir vaqtda
       hisoblashga kirishardi (thundering herd) — ya'ni kesh eng kerak
       bo'lgan payt eng katta yukni berardi. Bo'sh yon panel esa bir
       soatga (beat oralig'i) zararsiz.

    ⚠️ DEPLOY'DA: `nishonlarni_yangilash` kabi, birinchi reyting beat
       ishga tushgunicha bo'sh bo'ladi. Kerak bo'lsa vazifani qo'lda
       bir marta chaqiring.
    """
    return cache.get(reyting_kaliti(oy)) or []


def oylik_reytingni_yangilash(*, oy: date | None = None) -> list[dict]:
    """Hisoblab, keshga soladi. Celery vazifasi shuni chaqiradi."""
    natija = oylik_reytingni_hisoblash(oy=oy)
    cache.set(reyting_kaliti(oy), natija, REYTING_TTL)
    log.info("Oylik reyting yangilandi: %s ta", len(natija))
    return natija
