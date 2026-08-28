"""Yechimlar — modellar (D1-T4, D1-T5).

Solution, SolutionVote.
Match (kontakt almashinuvi) — M6, D6-T5.
"""

from __future__ import annotations

from typing import Self

from django.conf import settings
from django.db import models

from apps.common.models import (
    ContentModel,
    ContentQuerySet,
    ModerationStatus,
    VotableModel,
    VoteModel,
)


class SolutionQuerySet(ContentQuerySet):  # type: ignore[override]
    """⚠️ `visible()` YECHIMNING O'ZINI EMAS, OTA-POSTNI HAM TEKSHIRADI.

    ⚠️⚠️ BU XATO D2-T1 DA, D2-T3 GUARD'I ORQALI TOPILDI (D1-T5 dan beri
       bor edi). Sabab-oqibati yozib qo'yiladi, chunki xato turi
       takrorlanuvchan:

       `ModeratedQuerySet.visible()` yozuvning O'Z `moderation_status`
       ini tekshiradi. Yechim uchun bu YETARLI EMAS: muammo yashirilsa
       (yoki yumshoq o'chirilsa), undagi yechimlarning o'z holati
       `VISIBLE` bo'lib qolaveradi — ya'ni `Solution.objects.visible()`
       ularni HAMON qaytaradi.

       Nega uzoq vaqt ko'rinmadi: yechimlar faqat muammo sahifasi orqali
       olinardi, muammo esa avtorizatsiyadan o'tardi. D2-T1 birinchi
       marta yechimni TO'G'RIDAN-TO'G'RI `pk` bo'yicha oladigan ommaviy
       manzil qo'shdi (`/shikoyat/yechim/<pk>/`) va invariant darhol
       yiqildi. Ya'ni xato kodda emas, KIRISH YO'LIDA yashiringan edi.

       Tuzatish shu yerda — bitta joyda. Chaqiruv joylariga
       `complaint__moderation_status=...` tarqatish keyingi safar
       yangi ko'rinishda yana unutilardi.
    """

    def visible(self) -> Self:
        """Ommaviy ko'rinadigan yechimlar: o'zi ham, ota-posti ham ochiq."""
        return (
            super()
            .visible()
            .filter(
                complaint__moderation_status=ModerationStatus.VISIBLE,
                complaint__deleted_at__isnull=True,
            )
        )

    def ozi_korinadigan(self) -> Self:
        """Faqat yechimning O'Z holati bo'yicha filtr.

        ⚠️ FAQAT ota-post ALLAQACHON avtorizatsiya qilingan joyda
           ishlatiladi (`complaint_detail`: muallif va moderator o'z
           yashirilgan postini ko'radi — u yerda `visible()` yechimlarni
           butunlay yo'qotib yuborardi va muallif "javoblarim qayoqqa
           ketdi?" degan holatda qolardi).

           Boshqa hamma joyda `visible()`.
        """
        return super().visible()


class SolutionAliveManager(models.Manager.from_queryset(SolutionQuerySet)):  # type: ignore[misc]
    def get_queryset(self) -> SolutionQuerySet:
        return super().get_queryset().filter(deleted_at__isnull=True)


class SolutionAllManager(models.Manager.from_queryset(SolutionQuerySet)):  # type: ignore[misc]
    """O'chirilganlar bilan birga — audit uchun."""


class Solution(ContentModel, VotableModel):
    """Muammoga berilgan yechim.

    Nima uchun alohida ilova (`solutions`), `complaints` ichida emas:
    yechim atrofida o'z oqimi bor — qabul qilish, ekspert belgisi, karma
    berish, M6 dagi kontakt almashinuvi (Match). Ular `complaints` ichida
    o'sib, ilovani ikki mas'uliyatli qilib qo'yardi.
    """

    complaint = models.ForeignKey(
        "complaints.Complaint",
        verbose_name="muammo",
        # ⚠️ CASCADE — lekin bu FAQAT haqiqiy o'chirishda ishlaydi.
        #    Muammo yumshoq o'chirilganda (odatiy holat) yechimlar tirik
        #    qoladi: ular postgina yo'q, ya'ni ularga yo'l ham yo'q.
        #    Haqiqiy o'chirish esa faqat huquqiy so'rovda bo'ladi (D2-T8)
        #    va o'shanda yechimlar ham ketishi to'g'ri.
        on_delete=models.CASCADE,
        related_name="solutions",
    )
    # ⚠️ Complaint bilan bir xil sabab: hisob o'chsa javob qolishi kerak.
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="muallif",
        on_delete=models.SET_NULL,
        null=True,
        related_name="solutions",
    )
    content = models.TextField("yechim matni", max_length=5000)

    # -- Anonimlik ---------------------------------------------------------
    # ⚠️ Rejadagi ro'yxatda bu maydon YO'Q edi — ataylab qo'shildi.
    #    Sabab: platformaning va'dasi "og'ir mavzuni ayta ol" bo'lsa, u
    #    faqat SAVOL berishga emas, JAVOB berishga ham tegishli. "Men ham
    #    shu holatdan o'tganman, menga bu yordam berdi" degan eng qimmatli
    #    javoblar ko'pincha ism bilan yozilmaydi.
    #    Karma baribir HAQIQIY hisobga yoziladi (D3-T1) — anonimlik faqat
    #    ko'rsatishga taalluqli.
    is_anonymous = models.BooleanField(
        "anonim",
        default=False,
        help_text="Yoqilsa muallif ko'rsatilmaydi, lekin karma o'ziga yoziladi.",
    )

    # -- Qabul qilish ------------------------------------------------------
    is_accepted = models.BooleanField(
        "qabul qilingan",
        default=False,
        help_text="Muammo muallifi tanlaydi. Bitta muammoda faqat bitta.",
    )
    accepted_at = models.DateTimeField("qabul qilingan vaqt", null=True, blank=True)

    # ⚠️ `ContentModel` dagi menejerlar qayta belgilanadi — `visible()`
    #    ota-postni ham tekshirishi uchun (yuqoridagi `SolutionQuerySet`).
    objects = SolutionAliveManager()  # type: ignore[misc]
    all_objects = SolutionAllManager()  # type: ignore[misc]

    class Meta:
        verbose_name = "yechim"
        verbose_name_plural = "yechimlar"
        ordering = ("-score_cached", "created_at")
        constraints = [
            # ⚠️ "Bitta muammoda bitta qabul qilingan yechim" — BAZADA.
            #    Kodda tekshirish yetarli emas: muallif ikki oynada ikki
            #    yechimni deyarli bir vaqtda qabul qilsa, ikkala so'rov ham
            #    "hozircha qabul qilingani yo'q" deb ko'radi.
            #
            # ⚠️⚠️ `deleted_at__isnull=True` SHARTI MUHIM (oson unutiladi)
            #    Usiz: moderator qabul qilingan yechimni yashirib/o'chirib
            #    yuborsa, u qator bazada QOLADI va "qabul qilingan" o'rnini
            #    band qilib turadi. Muallif boshqa yechimni qabul qilmoqchi
            #    bo'lganda IntegrityError chiqadi va sababi ko'rinmaydi —
            #    ekranda esa hech qanday qabul qilingan yechim yo'q.
            models.UniqueConstraint(
                fields=["complaint"],
                condition=models.Q(is_accepted=True, deleted_at__isnull=True),
                name="solution_one_accepted_per_complaint",
                violation_error_message=(
                    "Bu muammoda allaqachon qabul qilingan yechim bor."
                ),
            ),
            # Qabul qilingan yechimda sana bo'lsin — "qachon yechildi?"
            # savoliga javob (D7-T8 metrikalari uchun kerak).
            models.CheckConstraint(
                condition=models.Q(is_accepted=False, accepted_at__isnull=True)
                | models.Q(is_accepted=True, accepted_at__isnull=False),
                name="solution_accepted_at_bilan_birga",
            ),
        ]
        indexes = [
            # Muammo sahifasidagi yechimlar ro'yxati: eng yaxshisi tepada.
            models.Index(
                fields=["complaint", "score_cached"], name="solution_compl_score_idx"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.complaint_id} uchun yechim #{self.pk}"

    def get_absolute_url(self) -> str:
        """Muammo sahifasidagi shu yechimga langar (anchor)."""
        return f"{self.complaint.get_absolute_url()}#yechim-{self.pk}"

    # -- Anonimlik invarianti (D1-T6) --------------------------------------
    @property
    def public_author(self):
        """Muallifga yagona ommaviy kirish nuqtasi. Batafsil: Complaint."""
        if self.is_anonymous:
            return None
        return self.author

    @property
    def is_by_expert(self) -> bool:
        """Ekspert javobimi (maketdagi "Ekspert javob berdi" nishoni).

        ⚠️ Anonim javobda ham `True` qaytadi — nishon muallifning ISMINI
           oshkor qilmaydi, faqat javob sifatini bildiradi. Agar bu ham
           ortiqcha deb topilsa, mahsulot qarori sifatida o'zgartiriladi.
        """
        return bool(self.author and self.author.is_expert)


class SolutionVote(VoteModel):
    """Bitta foydalanuvchining bitta yechimga bergan ovozi.

    `ComplaintVote` bilan bir xil tuzilish — sabab `apps.common.models`
    dagi `VoteModel` docstring'ida (ochiq qaror Q1).
    """

    solution = models.ForeignKey(
        Solution,
        verbose_name="yechim",
        on_delete=models.CASCADE,
        related_name="votes",
    )

    class Meta:
        verbose_name = "yechim ovozi"
        verbose_name_plural = "yechim ovozlari"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "solution"],
                name="solutionvote_user_target_uniq",
                violation_error_message="Bu yechimga allaqachon ovoz bergansiz.",
            ),
        ]
