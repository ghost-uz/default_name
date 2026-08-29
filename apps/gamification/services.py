"""Gamifikatsiya — xizmat funksiyalari (D1-T10, D3-T1)."""

from __future__ import annotations

import logging

from django.contrib.auth import get_user_model
from django.db import models, transaction

from .models import (
    KARMA_QIYMATLARI,
    KOMPENSATSIYA_SABABLARI,
    KarmaEvent,
    KarmaReason,
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
