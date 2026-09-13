"""Reklama — admin (D6-T6)."""

from __future__ import annotations

from django.contrib import admin

from .models import AdSlot


@admin.register(AdSlot)
class AdSlotAdmin(admin.ModelAdmin):
    """Reklama bloklari staff tomonidan shu yerda yaratiladi.

    ⚠️ SANOQCHILAR FAQAT O'QISH UCHUN: ular o'lchov, tahrir qilinadigan
       maydon emas. Qo'lda «tuzatilgan» ko'rsatish soni reklama
       beruvchi bilan hisob-kitobni asossiz qilib qo'yardi.

    ⚠️ `faolmi` ro'yxatdan turib o'zgartiriladi (`list_editable`):
       muddati tugagan yoki muammoli reklamani darhol o'chirish —
       moderatorga kerak bo'ladigan eng tez amal.
    """

    list_display = (
        "nom",
        "kategoriya",
        "faolmi",
        "boshlanish",
        "tugash",
        "korsatishlar",
        "bosishlar",
        "ctr_belgisi",
    )
    list_editable = ("faolmi",)
    list_filter = ("faolmi", "kategoriya")
    search_fields = ("nom", "sarlavha", "matn", "manzil")
    autocomplete_fields = ("kategoriya",)
    readonly_fields = (
        "korsatishlar",
        "bosishlar",
        "ctr_belgisi",
        "created_at",
        "updated_at",
    )
    date_hierarchy = "created_at"

    @admin.display(description="CTR, %")
    def ctr_belgisi(self, obj: AdSlot) -> str:
        return f"{obj.ctr:.2f}"
