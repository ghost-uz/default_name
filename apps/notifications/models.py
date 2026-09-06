"""Bildirishnomalar — modellar (D5-T1).

⚠️ NEGA ICHKI MARKAZ KERAK, TELEGRAM YETARLI EMAS
   Telegram bildirishnomasi (D5-T2) tezroq va ko'proq ochiladi, lekin
   unga TAYANIB BO'LMAYDI: foydalanuvchi botni bloklashi, Telegram'dan
   umuman chiqib ketishi yoki hisobini boshqa raqamga ko'chirishi
   mumkin. O'shanda u yechim kelganini HECH QACHON bilmaydi.

   Ichki markaz — zaxira kanal: u har doim shu yerda va uni bloklab
   bo'lmaydi.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.urls import reverse

from apps.common.models import TimeStampedModel


class BildirishnomaTuri(models.TextChoices):
    """Bildirishnoma turi.

    ⚠️ QIYMATLAR BAZAGA YOZILADI — o'zgartirilsa migratsiya kerak
       (D2-T6 dagi `AuditAction` bilan bir xil tuzoq: Django `choices`
       o'zgarishini kuzatadi).

    ⚠️ Yangi tur qo'shish ARZON: qiymat, yorliq va
       `Notification.matn` dagi bitta qator. Turlar ATAYLAB kam —
       har biri foydalanuvchining e'tiborini talab qiladi va ortiqcha
       bildirishnoma botdan chiqib ketishga olib keladi (D5-T4).
    """

    YANGI_YECHIM = "yangi_yechim", "Muammoingizga yechim yozildi"
    YECHIM_QABUL = "yechim_qabul", "Yechimingiz qabul qilindi"


class Notification(TimeStampedModel):
    """Bitta foydalanuvchiga bitta bildirishnoma.

    ⚠️⚠️ ANONIMLIK: ANONIM MANBADA `actor` UMUMAN YOZILMAYDI.

       "Ismni ko'rsatmaymiz" degan yondashuv (yozib qo'yib, shablonda
       yashirish) bu loyihada allaqachon uch marta muammo bo'lgan
       (D1-T6, OG metalari, JSON-LD). Bu yerda esa yozuvning O'ZI
       bazada qoladi va uni admin, eksport (D2-T8) yoki kelajakdagi
       API oshkor qilishi mumkin.

       Shuning uchun qoida qattiqroq: anonim yechim uchun
       `actor=None`. Bildirishnoma "Kimdir yechim yozdi" deydi va
       bu — TO'G'RI matn.

    ⚠️ `target` UCHUN `ContentType` ISHLATILMADI (ochiq qaror Q1 bilan
       izchil — `ComplaintVote` / `SavedComplaint` da ham shunday).
       Aniq FK'lar baza darajasida butunlikni beradi: kontent
       o'chirilsa bildirishnoma ham ketadi va yetim yozuv qolmaydi.
    """

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="kimga",
        on_delete=models.CASCADE,
        related_name="bildirishnomalar",
    )

    # ⚠️ SET_NULL: bildirishnoma matni aktyorsiz ham ma'noli
    #    ("Yechimingiz qabul qilindi"). CASCADE bo'lsa hisobini
    #    o'chirgan odam boshqalarning tarixini ham olib ketardi.
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="kim",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Anonim manbada BO'SH — sabab model docstring'ida.",
    )

    turi = models.CharField(
        "turi", max_length=20, choices=BildirishnomaTuri.choices, db_index=True
    )

    complaint = models.ForeignKey(
        "complaints.Complaint",
        verbose_name="muammo",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
    )
    solution = models.ForeignKey(
        "solutions.Solution",
        verbose_name="yechim",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
    )

    # ⚠️ `is_read` BOOLEAN EMAS, SANA.
    #    Boolean bilan "qachon o'qilgan?" savoliga javob yo'qoladi va
    #    D5-T4 (jim soatlar) hamda kelajakdagi tahlil uchun u kerak
    #    bo'ladi. `is_read` esa shundan hisoblanadi — `Complaint.status`
    #    va `is_solved` bilan bir xil naqsh.
    okilgan_at = models.DateTimeField("o'qilgan", null=True, blank=True, editable=False)

    class Meta:
        verbose_name = "bildirishnoma"
        verbose_name_plural = "bildirishnomalar"
        ordering = ("-created_at", "-id")
        indexes = [
            # ⚠️ O'qilmaganlar SANOG'I sarlavhada, ya'ni HAR sahifada
            #    so'raladi (kesh bo'sh bo'lganda). Bu indeks o'sha
            #    so'rovni qoplaydi.
            models.Index(
                fields=["recipient", "okilgan_at"], name="bildirishnoma_oqilm_idx"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.recipient_id}: {self.get_turi_display()}"

    @property
    def okilganmi(self) -> bool:
        return self.okilgan_at is not None

    @property
    def matn(self) -> str:
        """Foydalanuvchi ko'radigan matn.

        ⚠️ Aktyor nomi FAQAT `actor` mavjud bo'lganda qo'shiladi.
           Anonim manbada u `None` va matn "Kimdir..." bo'lib qoladi
           (model docstring'idagi anonimlik qoidasi).
        """
        kim = self.actor.display_name if self.actor else "Kimdir"

        if self.turi == BildirishnomaTuri.YANGI_YECHIM:
            return f"{kim} muammoingizga yechim yozdi"
        if self.turi == BildirishnomaTuri.YECHIM_QABUL:
            return "Yechimingiz to'g'ri javob deb belgilandi"
        return self.get_turi_display()

    @property
    def manzil(self) -> str:
        """Bosilganda qayerga olib boradi.

        ⚠️ Yechimga bog'liq bo'lsa LANGAR bilan (`#yechim-<pk>`) —
           foydalanuvchi uzun sahifada javobni qidirib o'tirmasin.
           Langar `templates/components/_solution.html` da.
        """
        # ⚠️ `complaint_id` EMAS, obyektning O'ZI tekshiriladi: `None`
        #    bo'lgan FK uchun Django so'rov QILMAYDI, ya'ni narxi bir xil,
        #    lekin tip tekshiruvchi shartni tushunadi (mypy `union-attr`).
        muammo = self.complaint
        if muammo is None:
            return reverse("bildirishnomalar")

        yol = muammo.get_absolute_url()
        if self.solution_id is not None:
            return f"{yol}#yechim-{self.solution_id}"
        return yol
