"""To'lovlar — admin (D6-T1)."""

from __future__ import annotations

from django.contrib import admin

from .models import Subscription


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    """⚠️ Obuna admin'da QO'LDA yaratilishi MUMKIN — ataylab.

    To'lov provayderi yiqilganda yoki apellyatsiya bo'lganda odamga
    obunani qo'lda berish yo'li bo'lishi kerak; aks holda yagona chora
    bazaga to'g'ridan-to'g'ri kirish bo'lardi (u esa hech qayerda
    yozilmaydi).

    ⚠️ `faolmi` HISOBLANADI va admin'da tahrirlab bo'lmaydi — u
       `status` bilan `expires_at` ning kesishmasi. Agar u maydon
       bo'lganda, admin'dagi bitta belgi haqiqatdan uzilib qolardi.
    """

    list_display = (
        "user",
        "plan",
        "status",
        "expires_at",
        "faol_belgisi",
        "auto_renew",
    )
    list_filter = ("plan", "status", "auto_renew")
    search_fields = ("user__username",)
    autocomplete_fields = ("user",)
    readonly_fields = ("created_at", "updated_at", "faol_belgisi")
    date_hierarchy = "expires_at"

    @admin.display(description="hozir faolmi", boolean=True)
    def faol_belgisi(self, obj: Subscription) -> bool:
        return obj.faolmi
