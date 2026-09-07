"""To'lovlar — admin (D6-T1)."""

from __future__ import annotations

from django.contrib import admin

from .models import Subscription, Tolov, TolovSorovi


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


@admin.register(Tolov)
class TolovAdmin(admin.ModelAdmin):
    """⚠️⚠️ FAQAT O'QISH — `Subscription` DAN FARQLI.

    `SubscriptionAdmin` da qo'lda yaratishga RUXSAT bor va sabab
    o'sha yerda yozilgan (provayder yiqilsa, apellyatsiya bo'lsa).
    Bu yerda esa teskarisi: `Tolov` — HAQIQIY pul harakati yozuvi.
    Uni qo'lda yaratish "pul kelgan" degan yolg'on dalil yasash
    degani, tahrirlash esa hisobotni haqiqatdan uzib qo'yardi.

    Odamga obunani qo'lda berish yo'li YO'QOLMAYDI — u
    `Subscription` da qoladi, ya'ni qaror QAROR bo'lib yoziladi,
    to'lov bo'lib emas.
    """

    list_display = (
        "id",
        "user",
        "provayder",
        "summa",
        "holat",
        "maqsad",
        "tolangan_at",
    )
    list_filter = ("provayder", "holat", "maqsad")
    search_fields = ("user__username", "provayder_trans_id")
    autocomplete_fields = ("user",)
    date_hierarchy = "created_at"
    readonly_fields = (
        "user",
        "maqsad",
        "provayder",
        "summa",
        "holat",
        "provayder_trans_id",
        "tolangan_at",
        "izoh",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


@admin.register(TolovSorovi)
class TolovSoroviAdmin(admin.ModelAdmin):
    """O'zgarmas jurnalning TO'RTINCHI qatlami (D2-T7 naqshi).

    ⚠️⚠️ ORM HIMOYASI ADMIN'NI QOPLAMAYDI — teskarisi ham to'g'ri.
       `OzgarmasJurnal.save()` tahrirlashni to'xtatadi, lekin admin'da
       forma baribir OCHILADI va odam saqlashga urinib, 500 xatosini
       ko'rardi. Ruxsatni bu yerda ham yopish — foydalanuvchi
       tajribasi, ikkinchi himoya emas.

    ⚠️ `has_view_permission` ochiq qoladi: jurnalning butun ma'nosi —
       nizoda uni O'QIY olish.
    """

    list_display = (
        "created_at",
        "provayder",
        "amal",
        "merchant_trans_id",
        "provayder_trans_id",
        "imzo_togrimi",
        "natija",
    )
    list_filter = ("provayder", "amal", "imzo_togrimi", "natija")
    search_fields = ("merchant_trans_id", "provayder_trans_id", "ip")
    date_hierarchy = "created_at"
    readonly_fields = (
        "created_at",
        "provayder",
        "amal",
        "tolov",
        "merchant_trans_id",
        "provayder_trans_id",
        "ip",
        "imzo_togrimi",
        "natija",
        "xom",
        "javob",
    )

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
