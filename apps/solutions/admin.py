"""Yechimlar — admin paneli.

Anonimlik bo'yicha qoida `apps/complaints/admin.py` boshidagi izoh bilan
bir xil: ro'yxatda "Anonim", kartochkada moderator uchun haqiqiy muallif.
"""

from __future__ import annotations

from django.contrib import admin

from .models import Solution, SolutionVote


@admin.register(Solution)
class SolutionAdmin(admin.ModelAdmin):
    list_display = (
        "__str__",
        "complaint",
        "public_author",
        "is_accepted",
        "moderation_status",
        "score_cached",
        "created_at",
    )
    list_filter = ("is_accepted", "moderation_status", "is_anonymous", "created_at")
    search_fields = ("content",)
    date_hierarchy = "created_at"
    raw_id_fields = ("complaint", "author")

    # ⚠️ `is_accepted` bu yerdan O'ZGARTIRILMAYDI.
    #    Qabul qilish uchta jadvalga tegadi (yechim, eski yechim, muammo
    #    holati) va `accept_solution()` xizmatidan o'tishi shart. Admin
    #    orqali bayroqni yoqish muammoni "yechilgan" qilmaydi va
    #    `accepted_solution` havolasi bo'sh qoladi — natijada ma'lumot
    #    ikkiga bo'linadi.
    readonly_fields = (
        "author",
        "is_accepted",
        "accepted_at",
        "upvotes_cached",
        "downvotes_cached",
        "score_cached",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (None, {"fields": ("complaint", "content")}),
        (
            "Muallif",
            {
                "fields": ("author", "is_anonymous"),
                "description": (
                    "Anonim yechimda muallif ommaviy sahifada ko'rsatilmaydi, "
                    "lekin karma unga yoziladi."
                ),
            },
        ),
        (
            "Qabul qilish",
            {
                "fields": ("is_accepted", "accepted_at"),
                "description": (
                    "Faqat o'qish uchun — qabul qilish <code>accept_solution()</code> "
                    "xizmatidan o'tadi (u muammo holatini ham yangilaydi)."
                ),
            },
        ),
        ("Moderatsiya", {"fields": ("moderation_status", "moderation_note")}),
        (
            "Hisoblanadigan",
            {
                "fields": ("upvotes_cached", "downvotes_cached", "score_cached"),
                "classes": ("collapse",),
            },
        ),
        ("Sanalar", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def get_queryset(self, request):
        """O'chirilganlar ham ko'rinadi — moderatsiya dalili (D2-T7)."""
        return Solution.all_objects.select_related("author", "complaint")


@admin.register(SolutionVote)
class SolutionVoteAdmin(admin.ModelAdmin):
    list_display = ("solution", "user", "value", "created_at")
    list_filter = ("value", "created_at")
    raw_id_fields = ("solution", "user")
    date_hierarchy = "created_at"

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False
