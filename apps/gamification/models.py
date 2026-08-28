"""Gamifikatsiya — modellar.

Hozircha faqat `KarmaEvent` (D1-T10 qabul mezoni uni talab qiladi).
Badge / UserBadge / Leaderboard — D3-T2, D3-T3.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.common.models import TimeStampedModel


class KarmaReason(models.TextChoices):
    """Karma nima uchun berildi.

    ⚠️ Kalitlar BAZAGA yoziladi va tarixda mangu qoladi — ularni
       o'zgartirish eski yozuvlarni "noma'lum sabab" qilib qo'yadi.
       Yangi turdagi hodisa kerak bo'lsa YANGI kalit qo'shiladi.
    """

    SOLUTION_ACCEPTED = "solution_accepted", "Yechim qabul qilindi"
    # ⚠️ Bu "o'chirish" emas, TESKARI YOZUV. Pastdagi izohga qarang.
    SOLUTION_UNACCEPTED = "solution_unaccepted", "Yechim qabuli bekor qilindi"


# ⚠️ QIYMATLAR MAHSULOT QARORI, rejada berilmagan.
#    +15 — StackOverflow'dagi "qabul qilingan javob" bilan bir xil daraja.
#    Sabab: qabul qilish platformaning YAKUNIY qiymati (reja 8-bo'lim), ya'ni
#    u ovoz berishdan sezilarli darajada qimmatroq bo'lishi kerak. Ovoz
#    karmasi keyinroq qo'shiladi (D3-T1) va u kichikroq bo'ladi.
KARMA_QIYMATLARI: dict[str, int] = {
    KarmaReason.SOLUTION_ACCEPTED: 15,
    KarmaReason.SOLUTION_UNACCEPTED: -15,
}


class KarmaEvent(TimeStampedModel):
    """Karma hodisalari jurnali — `User.karma_cached` ning HAQIQIY MANBAI.

    ⚠️ NEGA JURNAL, BUTUN SON EMAS (reja 6.1-bo'lim)
       `karma_points` oddiy son bo'lsa:
         · post o'chganda karma qaytmaydi;
         · qoida o'zgarsa qayta hisoblab bo'lmaydi;
         · "nega menda 1340?" degan savolga javob yo'q.
       Jurnal uchalasini ham yopadi va istalgan vaqtda qayta hisoblanadi.

    ⚠️ YOZUVLAR O'CHIRILMAYDI — TESKARISI YOZILADI
       Qabul bekor qilinganda `SOLUTION_ACCEPTED` yozuvi o'chirilmaydi,
       o'rniga `-15` li `SOLUTION_UNACCEPTED` qo'shiladi. Buxgalteriyadagi
       kabi: `+15`, `-15`, `+15` = sof `+15`.

       Nega o'chirilmaydi: (1) "nega karmam kamaydi?" savoliga javob
       qoladi; (2) noyoblik cheklovi qo'yilganda ikkinchi marta qabul
       qilish BLOKLANARDI; (3) audit (D2-T7) uchun tarix kerak.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="foydalanuvchi",
        on_delete=models.CASCADE,
        related_name="karma_events",
    )
    reason = models.CharField("sabab", max_length=32, choices=KarmaReason.choices)
    points = models.SmallIntegerField(
        "ball",
        help_text="Manfiy bo'lishi mumkin — teskari (kompensatsion) yozuv.",
    )
    # ⚠️ SET_NULL: yechim haqiqatan o'chirilsa (D2-T8) hodisa QOLADI.
    #    Jurnal o'z ma'nosini yo'qotmasligi kerak — ball allaqachon
    #    berilgan va uni "yo'q edi" qilib bo'lmaydi.
    solution = models.ForeignKey(
        "solutions.Solution",
        verbose_name="yechim",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="karma_events",
    )

    class Meta:
        verbose_name = "karma hodisasi"
        verbose_name_plural = "karma hodisalari"
        ordering = ("-created_at",)
        indexes = [
            # Profil sahifasidagi "karma tarixi" (D3-T4).
            models.Index(fields=["user", "-created_at"], name="karma_user_vaqt_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}: {self.points:+d} ({self.reason})"
