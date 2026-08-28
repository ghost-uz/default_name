"""Moderatsiya — admin paneli (D2-T1, D2-T2).

⚠️ Bu VAQTINCHALIK yechim. To'liq navbat interfeysi — D2-T2:
   "Django admin bu ish uchun juda sekin — moderator har bir holatda
   5 ta sahifa ochishi kerak bo'ladi."

   Shunga qaramay admin hozir ulanadi: shikoyatlar allaqachon kelib
   tushishi mumkin va ularni KO'RADIGAN joy bo'lishi kerak. Ko'rinmagan
   shikoyat — yozilmagan shikoyat bilan barobar.
"""

from __future__ import annotations

from django.contrib import admin
from django.db import models
from django.http import HttpRequest

from .models import ModerationAction, Report, ReportStatus


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "reason",
        "target_nomi",
        "status",
        "shoshilinch",
        "reporter",
    )
    list_filter = ("status", "reason", "created_at")
    search_fields = ("comment", "resolution_note")
    date_hierarchy = "created_at"
    raw_id_fields = ("reporter", "complaint", "solution", "resolved_by")

    # ⚠️ Shikoyat mazmuni O'ZGARTIRILMAYDI: u foydalanuvchi yuborgan dalil.
    #    Moderator faqat QAROR maydonlarini to'ldiradi.
    readonly_fields = (
        "reporter",
        "complaint",
        "solution",
        "reason",
        "comment",
        "created_at",
    )

    fieldsets = (
        (
            "Shikoyat",
            {
                "fields": (
                    "reporter",
                    "complaint",
                    "solution",
                    "reason",
                    "comment",
                    "created_at",
                ),
                "description": "Faqat o'qish uchun — foydalanuvchi yuborgan dalil.",
            },
        ),
        (
            "Qaror",
            {
                "fields": ("status", "resolution_note", "resolved_by", "resolved_at"),
                "description": (
                    "⚠️ Kontent ustidagi chora (yashirish/o'chirish) ALOHIDA: "
                    "muammo yoki yechim kartochkasida qilinadi."
                ),
            },
        ),
    )

    @admin.display(description="shoshilinch", boolean=True)
    def shoshilinch(self, obj: Report) -> bool:
        return obj.shoshilinchmi

    def has_delete_permission(self, request, obj=None) -> bool:
        """⚠️ Shikoyat O'CHIRILMAYDI — u audit zanjirining bir qismi (D2-T7).

        Noto'g'ri shikoyat "rad etildi" deb yopiladi, yo'q qilinmaydi:
        nizo chiqsa "kim, qachon, nima uchun shikoyat qilgan" savoliga
        javob qolishi kerak.
        """
        return False

    def get_queryset(self, request: HttpRequest) -> models.QuerySet[Report]:
        """⚠️ OCHIQ shikoyatlar DOIM tepada.

        Admin standart bo'yicha `-created_at` beradi — ya'ni yopilgan
        shikoyatlar ham aralashib turadi va moderator har safar filtrni
        qo'lda qo'yishi kerak. Bir marta unutilsa, ochiq shikoyat
        ikkinchi sahifaga tushib ko'rinmay qoladi.

        `select_related` — `list_display` dagi `reporter` va
        `target_nomi` har qator uchun alohida so'rov qilmasin.
        """
        return (
            super()
            .get_queryset(request)
            .annotate(
                _ochiqmi=models.Case(
                    models.When(status=ReportStatus.OCHIQ, then=0),
                    default=1,
                    output_field=models.IntegerField(),
                )
            )
            .order_by("_ochiqmi", "-created_at")
            .select_related("reporter", "complaint", "solution", "resolved_by")
        )


@admin.register(ModerationAction)
class ModerationActionAdmin(admin.ModelAdmin):
    """⚠️ TO'LIQ FAQAT O'QISH UCHUN — bu jurnal, jadval emas.

    Qo'shish ham, tahrirlash ham, o'chirish ham yopiq. Chora faqat
    moderatsiya navbati orqali yoziladi (`services.qaror_qabul_qilish`),
    xato bo'lsa esa BEKOR QILINADI — ya'ni yangi yozuv qo'shiladi.

    Adminda tahrirlashga ruxsat berilsa, jurnal dalil bo'lishdan
    to'xtaydi: "kim, nima, qachon" savoliga javob keyinchalik
    o'zgartirilgan bo'lishi mumkin bo'lardi. D2-T7 shu qoidani butun
    audit jurnaliga yoyadi.
    """

    list_display = ("created_at", "action", "target_nomi", "moderator", "bekor_belgi")
    list_filter = ("action", "created_at")
    search_fields = ("note",)
    date_hierarchy = "created_at"

    @admin.display(description="bekor qilingan", boolean=True)
    def bekor_belgi(self, obj: ModerationAction) -> bool:
        return obj.bekor_qilinganmi

    def get_queryset(self, request: HttpRequest) -> models.QuerySet[ModerationAction]:
        return (
            super()
            .get_queryset(request)
            .select_related("moderator", "complaint", "solution")
            .prefetch_related("bekor_qilishlar")
        )

    def has_add_permission(self, request, obj=None) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
