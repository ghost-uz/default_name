"""Muammolar — admin paneli.

⚠️ ANONIMLIK VA ADMIN — HUJJATLASHTIRILGAN QAROR (D1-T6)
   Anonimlik OMMAVIY va'da, MUTLAQ emas: moderator qoidabuzarlikni
   to'xtatishi uchun kim yozganini bilishi kerak (D2-T11 uch ogohlantirish
   tizimi busiz ishlamaydi).

   Muvozanat quyidagicha qo'yilgan:
     · RO'YXATDA muallif "Anonim" ko'rinadi — moderatsiya navbatini
       varaqlash odamlarni tasodifan oshkor qilmasin;
     · KARTOCHKADA (bitta postni ochganda) haqiqiy muallif ko'rinadi va
       faqat o'qish uchun.

   Bu shart maxfiylik siyosatida ochiq yozilishi kerak (D2-T10):
   "anonim postlarni moderatorlar zarurat bo'lganda muallif bilan
   bog'lay oladi". Aytilmagan istisno — buzilgan va'da.
"""

from __future__ import annotations

from django.contrib import admin

from .models import Category, Complaint, ComplaintVote


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "icon", "order", "is_active", "postlar_soni")
    list_editable = ("order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}

    @admin.display(description="postlar")
    def postlar_soni(self, obj: Category) -> int:
        return obj.complaints.count()


@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
    # ⚠️ `public_author` — ro'yxatda anonimlik saqlanadi (fayl boshidagi izoh).
    list_display = (
        "title",
        "category",
        "public_author",
        "status",
        "moderation_status",
        "score_cached",
        "solutions_count",
        "created_at",
    )
    list_filter = (
        "moderation_status",
        "status",
        "category",
        "generation_tag",
        "is_anonymous",
    )
    search_fields = ("title", "description", "slug")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    # `author` bo'yicha oddiy select 100 ming foydalanuvchida sahifani o'ldiradi
    raw_id_fields = ("author", "accepted_solution")

    # ⚠️ Denormalizatsiya qilingan maydonlar QO'LDA tahrirlanmaydi: ular
    #    ovoz jadvalidan va Celery vazifasidan (D1-T11) hisoblanadi.
    #    Admin orqali o'zgartirilsa keyingi qayta hisoblash ularni
    #    "tuzatib" yuboradi va o'zgarish sababsiz yo'qolgandek ko'rinadi.
    readonly_fields = (
        "slug",
        "upvotes_cached",
        "downvotes_cached",
        "score_cached",
        "views_count",
        "solutions_count",
        "has_expert_answer",
        "hot_score",
        "created_at",
        "updated_at",
        "author",
    )

    fieldsets = (
        (None, {"fields": ("title", "description", "category", "generation_tag")}),
        (
            "Muallif",
            {
                "fields": ("author", "is_anonymous"),
                "description": (
                    "<b>Diqqat:</b> post anonim bo'lsa muallif ommaviy sahifada "
                    "HECH QAYERDA ko'rsatilmaydi. Bu yerda ko'rinishi — faqat "
                    "moderatsiya uchun berilgan istisno (maxfiylik siyosati)."
                ),
            },
        ),
        ("Holat", {"fields": ("status", "accepted_solution")}),
        ("Moderatsiya", {"fields": ("moderation_status", "moderation_note")}),
        (
            "Hisoblanadigan",
            {
                "fields": (
                    "slug",
                    "upvotes_cached",
                    "downvotes_cached",
                    "score_cached",
                    "views_count",
                    "solutions_count",
                    "has_expert_answer",
                    "hot_score",
                ),
                "classes": ("collapse",),
                "description": "Faqat o'qish uchun — hisoblanadigan qiymatlar.",
            },
        ),
        ("Sanalar", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def get_queryset(self, request):
        """⚠️ Admin YUMSHOQ O'CHIRILGANLARNI HAM ko'radi.

        Moderator "o'chirilgan post nima edi?" degan savolga javob
        bera olishi kerak — nizo va huquqiy so'rovda yagona dalil shu
        (D2-T7 audit jurnali).
        """
        return Complaint.all_objects.select_related("author", "category")


@admin.register(ComplaintVote)
class ComplaintVoteAdmin(admin.ModelAdmin):
    """Ovozlar — asosan soxta ovozlarni tekshirish uchun (D2-T5).

    ⚠️ Tahrirlash ATAYLAB yopiq: ovozni qo'lda o'zgartirish keshlangan
       sanoqchini yangilamaydi va ikkisi bir-biridan uzilib qoladi.
    """

    list_display = ("complaint", "user", "value", "created_at")
    list_filter = ("value", "created_at")
    raw_id_fields = ("complaint", "user")
    date_hierarchy = "created_at"

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False
