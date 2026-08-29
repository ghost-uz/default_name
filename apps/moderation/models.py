"""Moderatsiya — modellar (D2-T1).

`Report` — moderatsiyaning KIRISH NUQTASI. Shikoyatsiz platforma —
moderatsiyasi ko'r platforma: qoidabuzarlikni faqat moderator tasodifan
ko'rgandagina topiladi.

`ModerationAction` — moderator kontent ustidan ko'rgan chorasi (D2-T2).
`AuditLog` — o'zgarmas audit jurnali, barcha staff harakatlari (D2-T7).
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.common.models import ModerationStatus, TimeStampedModel

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
    # ⚠️ QAYSI CHORA bu shikoyatni yopgan (D2-T2).
    #    Bekor qilish AYNAN o'sha chora yopgan shikoyatlarni qayta
    #    ochishi kerak. Vaqt bo'yicha taxmin qilish ("bir xil soniyada
    #    yopilganlar") mo'rt bo'lardi: ikki moderator bir vaqtda ishlashi
    #    yoki bitta obyektga ikki marta chora ko'rilishi mumkin.
    yopgan_chora = models.ForeignKey(
        "moderation.ModerationAction",
        verbose_name="yopgan chora",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
        related_name="yopilgan_shikoyatlar",
    )
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


# ===========================================================================
# Moderator chorasi (D2-T2)
# ===========================================================================
class ModerationActionType(models.TextChoices):
    """Moderator ko'rgan chora.

    ⚠️ TARTIB — YENGILDAN OG'IRGA. Ro'yxat shu tartibda ko'rsatiladi va
       bu ataylab: interfeys eng oson topiladigan tugmani eng og'ir
       chora qilib qo'ymasligi kerak.
    """

    RAD_ETISH = "rad_etish", "Qoidabuzarlik yo'q"
    OGOHLANTIRISH = "ogohlantirish", "Ogohlantirish (kontent qoladi)"
    YASHIRISH = "yashirish", "Yashirish"
    OLIB_TASHLASH = "olib_tashlash", "Olib tashlash"
    BEKOR_QILISH = "bekor_qilish", "Oldingi qaror bekor qilindi"


# Chora -> kontentning yangi moderatsiya holati.
# `None` = kontentga TEGILMAYDI.
CHORA_HOLATI: dict[str, str | None] = {
    ModerationActionType.RAD_ETISH: None,
    ModerationActionType.OGOHLANTIRISH: None,
    ModerationActionType.YASHIRISH: ModerationStatus.HIDDEN,
    ModerationActionType.OLIB_TASHLASH: ModerationStatus.REMOVED,
}


class ModerationAction(TimeStampedModel):
    """Moderator kontent ustidan ko'rgan chora — QO'SHILADI, o'zgartirilmaydi.

    ⚠️ QARORNI BEKOR QILISH — YOZUVNI O'CHIRISH EMAS.
       Xato bosilgan tugma yozuvni yo'q qilmaydi: uning o'rniga
       `BEKOR_QILISH` turidagi YANGI yozuv qo'shiladi va u `bekor_qiladi`
       orqali asl qarorga bog'lanadi. Sabab `KarmaEvent` dagi bilan bir
       xil: jurnal tahrirlansa u dalil bo'lishdan to'xtaydi.

       Amaliy foydasi ham bor — "moderator qaror qildi, keyin qaytarib
       oldi" ning o'zi ma'lumot: agar bu tez-tez takrorlansa, qoidalar
       tushunarsiz degani.

    ⚠️ `oldingi_holat` NEGA SAQLANADI
       Bekor qilish kontentni QAYSI holatga qaytarishni bilishi kerak.
       "VISIBLE ga qaytar" deb qotirib qo'yish xato bo'lardi: post
       yashirilishidan oldin allaqachon `PENDING` da turgan bo'lishi
       mumkin va bekor qilish uni jimgina ko'rinadigan qilib yuborardi.

    ⚠️ `target_author` DENORMALIZATSIYA
       Kontent bir kuni haqiqatan o'chirilishi mumkin (D2-T8, huquqiy
       so'rov). Chora esa "kimga nisbatan ko'rilgan" ma'lumotini
       yo'qotmasligi kerak — D2-T11 (uch ogohlantirish) aynan shuni
       sanaydi.
    """

    moderator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="moderator",
        on_delete=models.SET_NULL,
        null=True,
        related_name="moderation_actions",
    )
    action = models.CharField(
        "chora", max_length=16, choices=ModerationActionType.choices
    )

    # Maqsad — `Report` bilan bir xil naqsh (ikkita nullable FK + cheklov).
    complaint = models.ForeignKey(
        "complaints.Complaint",
        verbose_name="muammo",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="moderation_actions",
    )
    solution = models.ForeignKey(
        "solutions.Solution",
        verbose_name="yechim",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="moderation_actions",
    )

    target_author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="kontent muallifi",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="olingan_choralar",
        help_text="Denormalizatsiya: kontent o'chsa ham chora kimga tegishli ekani qoladi.",
    )

    note = models.CharField(
        "izoh",
        max_length=300,
        blank=True,
        help_text="Muallifga KO'RSATILADI — sababsiz chora shikoyat keltiradi.",
    )
    oldingi_holat = models.CharField(
        "chora oldidagi holat",
        max_length=16,
        choices=ModerationStatus.choices,
        blank=True,
        editable=False,
        help_text="Bekor qilish kontentni aynan shu holatga qaytaradi.",
    )
    bekor_qiladi = models.ForeignKey(
        "self",
        verbose_name="qaysi qarorni bekor qiladi",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="bekor_qilishlar",
    )

    class Meta:
        verbose_name = "moderator chorasi"
        verbose_name_plural = "moderator choralari"
        ordering = ("-created_at",)
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(complaint__isnull=False, solution__isnull=True)
                    | models.Q(complaint__isnull=True, solution__isnull=False)
                ),
                name="action_aynan_bitta_maqsad",
                violation_error_message="Chora aynan bitta obyektga tegishli bo'lishi kerak.",
            ),
        ]
        indexes = [
            # D2-T11: foydalanuvchining ogohlantirishlarini sanash.
            models.Index(
                fields=["target_author", "action"], name="action_muallif_chora_idx"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_action_display()} -> {self.target_nomi}"

    @property
    def target(self):
        return self.complaint or self.solution

    @property
    def target_nomi(self) -> str:
        if self.complaint_id:
            return f"muammo #{self.complaint_id}"
        return f"yechim #{self.solution_id}"

    @property
    def bekor_qilinganmi(self) -> bool:
        """Bu qarorni keyinchalik bekor qilishganmi."""
        return self.bekor_qilishlar.exists()

    @property
    def qaytarilishi_mumkinmi(self) -> bool:
        """Bekor qilish tugmasi ko'rsatiladimi.

        Bekor qilishning o'zini bekor qilib bo'lmaydi — aks holda
        interfeysda cheksiz "bekor qilishning bekori" zanjiri paydo
        bo'lardi. Xato bo'lsa moderator oddiy yangi qaror qabul qiladi.
        """
        return self.action != ModerationActionType.BEKOR_QILISH


# ===========================================================================
# Audit jurnali (D2-T7)
# ===========================================================================
class JurnalOzgarmas(Exception):
    """Audit jurnalini o'zgartirishga urinish."""


class AuditAction(models.TextChoices):
    """Jurnalga tushadigan harakatlar.

    ⚠️ Ro'yxat O'SADI (D2-T11 bloklash, D2-T8 ma'lumot eksporti...).
       Yangi staff amali qo'shilganda bu yerga ham qo'shiladi —
       `test_audit.py` dagi guard buni majburlaydi.
    """

    KONTENT_CHORA = "kontent_chora", "Kontent ustidan chora"
    CHORA_BEKOR = "chora_bekor", "Chora bekor qilindi"
    SHIKOYAT_YOPILDI = "shikoyat_yopildi", "Shikoyat yopildi"
    AVTOMATIK_BELGI = "avtomatik_belgi", "Avtomatik filtr belgiladi"


class AuditQuerySet(models.QuerySet):
    """⚠️ Ommaviy o'zgartirish va o'chirish YOPIQ.

    Model darajasidagi `save()`/`delete()` ni chetlab o'tish oson:
    `AuditLog.objects.filter(...).update(izoh="")` hech qanday model
    metodini chaqirmaydi. Jurnal uchun bu teshik ochiq qolsa,
    himoyaning ma'nosi yo'q.
    """

    def update(self, **kwargs):
        raise JurnalOzgarmas(
            "Audit jurnali o'zgartirilmaydi (D2-T7). Xato yozuv bo'lsa, "
            "uni TUZATUVCHI yangi yozuv qo'shing."
        )

    def delete(self):
        raise JurnalOzgarmas("Audit jurnali o'chirilmaydi (D2-T7).")

    def _haqiqiy_ochirish(self):
        """FAQAT test va ma'lumot saqlash siyosati uchun (D2-T8).

        Nomi ataylab noqulay: tasodifan chaqirilmasin.
        """
        return super().delete()


class AuditLog(models.Model):
    """Staff harakatlarining O'ZGARMAS jurnali.

    ⚠️ NEGA `ModerationAction` YETARLI EMAS
       `ModerationAction` — DOMEN yozuvi: u navbat, bekor qilish va
       kontent holati bilan ishlaydi va faqat KONTENT ustidagi
       choralarni biladi. Audit jurnali esa boshqa savolga javob
       beradi: "shu hisob nima qildi?". Unga kontentga tegmaydigan
       amallar ham tushadi — shikoyat yopish, kelajakda bloklash
       (D2-T11), ma'lumot eksporti (D2-T8).

       Ikkalasi bir modelga siqilsa, `ModerationAction` ning domen
       maydonlari (`oldingi_holat`, `bekor_qiladi`) yarim hollarda
       bo'sh turardi va model nima ekani tushunarsiz bo'lardi.

    ⚠️ `actor_nomi` DENORMALIZATSIYA — MAJBURIY
       `actor` FK `SET_NULL`: hisob o'chirilsa u `None` bo'ladi. Audit
       jurnali uchun aynan shu ma'lumotni yo'qotish mumkin emas —
       "kim qildi?" savoliga javobsiz jurnal dalil emas. Shuning uchun
       ism YOZUV PAYTIDA nusxalanadi.

    ⚠️ CHEKLOV (bilib qo'yilgan): himoya ORM darajasida. To'g'ridan-
       to'g'ri SQL (yoki `psql`) yozuvni baribir o'zgartira oladi.
       Haqiqiy kafolat — baza darajasidagi trigger yoki `REVOKE
       UPDATE, DELETE`. U deploy bosqichida qo'shiladi.
    """

    created_at = models.DateTimeField("vaqt", auto_now_add=True, db_index=True)

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="kim",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_yozuvlari",
    )
    actor_nomi = models.CharField(
        "kim (nusxa)",
        max_length=150,
        blank=True,
        help_text="Hisob o'chirilsa ham qoladi. Bo'sh = tizim.",
    )

    action = models.CharField("harakat", max_length=32, choices=AuditAction.choices)
    obyekt = models.CharField(
        "obyekt",
        max_length=100,
        help_text="Masalan: «muammo #12», «shikoyat #4».",
    )
    izoh = models.TextField("sabab / izoh", blank=True)
    malumot = models.JSONField("qo'shimcha", default=dict, blank=True)

    objects = AuditQuerySet.as_manager()

    class Meta:
        verbose_name = "audit yozuvi"
        verbose_name_plural = "audit jurnali"
        ordering = ("-created_at", "-pk")
        indexes = [
            models.Index(fields=["action", "-created_at"], name="audit_harakat_idx"),
            models.Index(fields=["actor", "-created_at"], name="audit_kim_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.get_action_display()} — {self.obyekt}"

    def save(self, *args, **kwargs):
        """⚠️ FAQAT QO'SHISH. Mavjud yozuvni saqlash — xato."""
        if not self._state.adding:
            raise JurnalOzgarmas(
                "Audit yozuvi tahrirlanmaydi (D2-T7). Xato bo'lsa, uni "
                "TUZATUVCHI yangi yozuv qo'shing."
            )
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise JurnalOzgarmas("Audit yozuvi o'chirilmaydi (D2-T7).")

    @property
    def kim(self) -> str:
        return self.actor_nomi or "tizim"
