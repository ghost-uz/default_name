"""Suhbatlar — admin (D6-T5)."""

from __future__ import annotations

from django.contrib import admin

from .models import KontaktSorovi, Suhbat, Xabar


@admin.register(KontaktSorovi)
class KontaktSoroviAdmin(admin.ModelAdmin):
    list_display = ("pk", "holat", "soragan", "created_at", "javob_at")
    list_filter = ("holat",)
    autocomplete_fields = ("soragan",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(Suhbat)
class SuhbatAdmin(admin.ModelAdmin):
    """⚠️⚠️ XABARLAR ADMIN'DA `inline` QILINMAGAN — ATAYLAB.

    Shaxsiy yozishmani "shunchaki ochib ko'rish" oson bo'lmasligi
    kerak. Moderator xabarni SHIKOYAT orqali ko'radi (D2-T2 navbati),
    ya'ni kirish uchun sabab bor va u audit jurnalida qoladi.
    """

    list_display = ("pk", "yopilgan_at", "yopgan", "created_at")
    list_filter = ("yopilgan_at",)
    readonly_fields = ("sorov", "created_at", "updated_at")


@admin.register(Xabar)
class XabarAdmin(admin.ModelAdmin):
    """⚠️ Faqat MODERATSIYA holati tahrirlanadi — matn EMAS.

    Xabar matnini admin'da o'zgartirish yozishmani soxtalashtirish
    imkonini berardi va shikoyat uchun dalilni yo'q qilardi.
    """

    list_display = ("pk", "suhbat", "moderation_status", "created_at")
    list_filter = ("moderation_status", "inqiroz_aniqlandi")
    readonly_fields = ("suhbat", "author", "content", "created_at", "updated_at")
