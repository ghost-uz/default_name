"""Moderatsiya — modellar (D2-T1).

`Report` — moderatsiyaning KIRISH NUQTASI. Shikoyatsiz platforma —
moderatsiyasi ko'r platforma: qoidabuzarlikni faqat moderator tasodifan
ko'rgandagina topiladi.

Moderatsiya navbati (staff interfeysi) — D2-T2.
O'zgarmas audit jurnali — D2-T7.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.common.models import TimeStampedModel

# ⚠️ MAHSULOT QARORI: nechta shikoyatdan keyin navbatda YUQORIGA ko'tariladi.
#    3 — kichik jamoada bir odamning g'arazi yetarli bo'lmasligi uchun eng
#    kichik ishonarli son. O'sganda 5 ga ko'tarilishi mumkin.
ESKALATSIYA_CHEGARASI = 3


class ReportReason(models.TextChoices):
    """Shikoyat sababi.

    Kalitlar maketdagi variantlardan olingan + ikkitasi qo'shildi.

    ⚠️ `XAVF` ALOHIDA TOIFA va u eng muhimi: D2-T6 (inqirozli kontent)
       aynan shu signalga ulanadi. Uni "Boshqa" ichiga qo'shib yuborish
       — odam hayoti haqidagi xabarni spam bilan bir navbatga qo'yish
       degani.
    """

    SPAM = "spam", "Spam yoki reklama"
    HAQORAT = "haqorat", "Haqorat yoki nafrat"
    SHAXSIY = "shaxsiy", "Shaxsiy ma'lumot oshkor qilingan"
    XAVF = "xavf", "O'ziga yoki boshqaga zarar yetkazish xavfi"
    BOSHQA = "boshqa", "Boshqa sabab"


class ReportStatus(models.TextChoices):
    OCHIQ = "ochiq", "Ko'rib chiqilmagan"
    HAL_QILINDI = "hal_qilindi", "Qabul qilindi (chora ko'rildi)"
    RAD_ETILDI = "rad_etildi", "Rad etildi (qoidabuzarlik yo'q)"


class ReportQuerySet(models.QuerySet):
    def ochiq(self) -> ReportQuerySet:
        return self.filter(status=ReportStatus.OCHIQ)

    def eskalatsiya_qilinganlar(self) -> ReportQuerySet:
        """`ESKALATSIYA_CHEGARASI` dan ko'p ochiq shikoyati bor obyektlar.

        ⚠️ "Navbatga ko'tarish" HISOBLANADI, saqlanmaydi (D2-T1 qabul
           mezoni). Alohida `eskalatsiya` bayrog'i qo'yilsa u shikoyat
           hal qilinganda yangilanishi kerak bo'lardi va bir kuni
           unutilardi — jadval haqiqatdan uzilardi.
        """
        muammolar = (
            Report.objects.ochiq()
            .filter(complaint__isnull=False)
            .values("complaint")
            .annotate(n=models.Count("pk"))
            .filter(n__gte=ESKALATSIYA_CHEGARASI)
            .values_list("complaint", flat=True)
        )
        yechimlar = (
            Report.objects.ochiq()
            .filter(solution__isnull=False)
            .values("solution")
            .annotate(n=models.Count("pk"))
            .filter(n__gte=ESKALATSIYA_CHEGARASI)
            .values_list("solution", flat=True)
        )
        return self.filter(
            models.Q(complaint__in=list(muammolar))
            | models.Q(solution__in=list(yechimlar))
        )


class Report(TimeStampedModel):
    """Foydalanuvchi yuborgan shikoyat.

    ⚠️ NEGA BITTA JADVAL, IKKITA NULLABLE FK (Q1 dan FARQLI)
       Ovoz va xatcho'pda maqsad turi bo'yicha ALOHIDA jadval tanlangan
       (Q1). Bu yerda aksincha, va sababi aniq:

         · Moderatsiya navbati (D2-T2) BITTA ro'yxat bo'lishi kerak —
           moderator "muammolar navbati" va "yechimlar navbati" o'rtasida
           sakrab yurmasin. Ikki jadval har so'rovda `UNION` degani.
         · Shikoyat hajmi ovozdan bir necha TARTIB kichik — indeks
           tezligi bu yerda hal qiluvchi emas.

       `ContentType` (generic FK) esa RAD ETILDI: u bilan baza darajasida
       FK butunligi yo'qoladi va o'chirilgan post uchun yetim shikoyat
       qoladi. Ikkita nullable FK + `CheckConstraint` ikkalasini ham
       beradi: haqiqiy FK va bitta jadval.

    ⚠️ KONTENT AVTOMATIK YASHIRILMAYDI — ATAYLAB.
       N ta shikoyat obyektni navbatda YUQORIGA ko'taradi, lekin uni
       ko'rinmas qilmaydi. Sabab mahsulotga xos: Dard.uz'da odamlar eng
       og'ir shaxsiy holatlarini yozadi. Uchta kelishib olgan odam
       istalgan postni o'chirib tashlay olsa, bu qurolga aylanadi — va
       zarba aynan eng himoyasiz foydalanuvchiga tegadi.

       Shoshilinch olib tashlash MODERATOR qo'lida qoladi (D2-T2), inqiroz
       signali esa alohida yo'l bilan ketadi (D2-T6, `XAVF` sababi).
    """

    # ⚠️ SET_NULL: shikoyatchi hisobini o'chirsa ham shikoyat QOLADI —
    #    u moderator qarorining asosi va D2-T7 auditining bir qismi.
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="shikoyatchi",
        on_delete=models.SET_NULL,
        null=True,
        related_name="reports",
    )

    complaint = models.ForeignKey(
        "complaints.Complaint",
        verbose_name="muammo",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="reports",
    )
    solution = models.ForeignKey(
        "solutions.Solution",
        verbose_name="yechim",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="reports",
    )

    reason = models.CharField("sabab", max_length=16, choices=ReportReason.choices)
    comment = models.TextField(
        "izoh",
        max_length=1000,
        blank=True,
        help_text="Ixtiyoriy — moderatorga kontekst beradi.",
    )

    status = models.CharField(
        "holat",
        max_length=16,
        choices=ReportStatus.choices,
        default=ReportStatus.OCHIQ,
        db_index=True,
    )
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="kim hal qildi",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    resolved_at = models.DateTimeField("hal qilingan vaqt", null=True, blank=True)
    resolution_note = models.CharField(
        "qaror izohi",
        max_length=300,
        blank=True,
        help_text="Nima qilindi va nega. D2-T7 auditiga tushadi.",
    )

    objects = ReportQuerySet.as_manager()

    class Meta:
        verbose_name = "shikoyat"
        verbose_name_plural = "shikoyatlar"
        ordering = ("-created_at",)
        constraints = [
            # ⚠️ AYNAN BITTA maqsad bo'lishi shart. Usiz ikkalasi ham
            #    `NULL` bo'lgan "hech kimga tegishli bo'lmagan" shikoyat
            #    yoki ikkalasi ham to'ldirilgan chalkash yozuv paydo
            #    bo'lardi — va navbat uni qayerga qo'yishni bilmasdi.
            models.CheckConstraint(
                condition=(
                    models.Q(complaint__isnull=False, solution__isnull=True)
                    | models.Q(complaint__isnull=True, solution__isnull=False)
                ),
                name="report_aynan_bitta_maqsad",
                violation_error_message="Shikoyat aynan bitta obyektga tegishli bo'lishi kerak.",
            ),
            # Qabul mezoni: bir foydalanuvchi bitta obyektga BIR MARTA.
            # ⚠️ Qisman indeks: `solution` `NULL` bo'lgan qatorlar ko'p va
            #    PostgreSQL'da `NULL` lar noyoblikda tenglashtirilmaydi —
            #    shart bo'lmasa cheklov umuman ishlamasdi.
            models.UniqueConstraint(
                fields=["reporter", "complaint"],
                condition=models.Q(complaint__isnull=False),
                name="report_bir_muammoga_bir_marta",
                violation_error_message="Siz bu postga allaqachon shikoyat qilgansiz.",
            ),
            models.UniqueConstraint(
                fields=["reporter", "solution"],
                condition=models.Q(solution__isnull=False),
                name="report_bir_yechimga_bir_marta",
                violation_error_message="Siz bu yechimga allaqachon shikoyat qilgansiz.",
            ),
        ]
        indexes = [
            # Moderatsiya navbati: ochiqlari, eskisidan yangisiga (D2-T2).
            models.Index(fields=["status", "created_at"], name="report_navbat_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.get_reason_display()} -> {self.target_nomi}"

    @property
    def target(self):
        """Shikoyat qilingan obyekt (`Complaint` yoki `Solution`)."""
        return self.complaint or self.solution

    @property
    def target_nomi(self) -> str:
        if self.complaint_id:
            return f"muammo #{self.complaint_id}"
        return f"yechim #{self.solution_id}"

    @property
    def shoshilinchmi(self) -> bool:
        """⚠️ `XAVF` — odam hayoti haqidagi signal.

        Navbatda u har doim tepada turishi kerak; D2-T6 bu yerga
        avtomatik javob mexanizmini ulaydi.
        """
        return self.reason == ReportReason.XAVF
