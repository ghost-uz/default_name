"""Gamifikatsiya — xizmat funksiyalari (D1-T10 uchun minimal qism)."""

from __future__ import annotations

from django.db import models, transaction

from .models import KARMA_QIYMATLARI, KarmaEvent, KarmaReason


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
