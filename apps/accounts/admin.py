"""Foydalanuvchilar — admin paneli."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = (
        "username",
        "display_name",
        "telegram_id",
        "karma_cached",
        "is_expert",
        "ban_holati",
        "date_joined",
    )
    list_filter = ("is_expert", "is_banned", "is_active", "is_staff", "date_joined")
    search_fields = ("username", "first_name", "last_name", "email", "telegram_id")
    ordering = ("-date_joined",)

    # ⚠️ Denormalizatsiya qilingan maydonlar QO'LDA tahrirlanmaydi —
    #    ular KarmaEvent (D3-T1) va ExpertProfile (D3-T5) dan hisoblanadi.
    #    Admin orqali o'zgartirilsa, keyingi qayta hisoblash ularni "tuzatib"
    #    yuboradi va o'zgarish sababsiz yo'qolgandek ko'rinadi.
    readonly_fields = ("karma_cached", "is_expert", "date_joined", "last_login")

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Shaxsiy", {"fields": ("first_name", "last_name", "email", "bio")}),
        ("Telegram", {"fields": ("telegram_id",)}),
        (
            "Gamifikatsiya",
            {
                "fields": ("karma_cached", "is_expert"),
                "description": "Faqat o'qish uchun — hisoblanadigan qiymatlar.",
            },
        ),
        (
            "Moderatsiya",
            {
                "fields": ("is_banned", "banned_until", "ban_reason", "is_active"),
                "description": (
                    "<b>is_banned</b>: o'qiy oladi, yoza olmaydi. "
                    "<b>is_active=False</b>: umuman kira olmaydi."
                ),
            },
        ),
        (
            "Ruxsatlar",
            {"fields": ("is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        ("Sanalar", {"fields": ("last_login", "date_joined")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "password1", "password2"),
            },
        ),
    )

    @admin.display(description="blok", boolean=True)
    def ban_holati(self, obj: User) -> bool:
        """Blok HOZIR kuchdami (muddati o'tganini hisobga oladi)."""
        return obj.is_currently_banned
