"""Gamifikatsiya — modellar.

`KarmaEvent` (D1-T10, D3-T1) va nishonlar (`Badge`, `UserBadge` — D3-T2).
Leaderboard — D3-T3.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.common.models import TimeStampedModel


class KarmaReason(models.TextChoices):
    """Karma nima uchun berildi.

    ⚠️ Kalitlar BAZAGA yoziladi va tarixda mangu qoladi — ularni
       o'zgartirish eski yozuvlarni "noma'lum sabab" qilib qo'yadi.
       Yangi turdagi hodisa kerak bo'lsa YANGI kalit qo'shiladi.
    """

    SOLUTION_ACCEPTED = "solution_accepted", "Yechim qabul qilindi"
    # ⚠️ Bu "o'chirish" emas, TESKARI YOZUV. Pastdagi izohga qarang.
    SOLUTION_UNACCEPTED = "solution_unaccepted", "Yechim qabuli bekor qilindi"

    # --- Ovoz karmasi (D3-T1) ------------------------------------------
    SOLUTION_UPVOTED = "solution_upvoted", "Yechimga ovoz berildi"
    SOLUTION_UPVOTE_OLINDI = "solution_upvote_olindi", "Yechimdagi ovoz olindi"

    # --- Kompensatsiya: kontent ko'rinmay qolganda (D3-T1) --------------
    # ⚠️ Bu ikkisining BALLI HISOBLANADI, `KARMA_QIYMATLARI` da YO'Q —
    #    pastdagi izohga qarang.
    KONTENT_OLIB_TASHLANDI = (
        "kontent_olib_tashlandi",
        "Kontent olib tashlandi — karma qaytarildi",
    )
    KONTENT_TIKLANDI = "kontent_tiklandi", "Kontent tiklandi — karma qaytarib berildi"


# ⚠️ QIYMATLAR MAHSULOT QARORI, rejada berilmagan.
#
#    +15 (qabul) — StackOverflow'dagi "qabul qilingan javob" bilan bir xil
#    daraja. Qabul qilish platformaning YAKUNIY qiymati (reja 8-bo'lim),
#    ya'ni u ovozdan sezilarli darajada qimmatroq bo'lishi kerak.
#
#    +2 (ovoz) — qabuldan yetti barobar arzon: ovoz "foydali ko'rindi",
#    qabul esa "menga HAQIQATAN yordam berdi" degani.
#
# ⚠️⚠️ DARD (MUAMMO) KARMA BERMAYDI — foydalanuvchi qarori.
#    Platformaning qiymati YORDAM BERISHDA. Dard yozish bepul bo'lsa,
#    og'ir ahvoldagi odam "ball yig'ish" haqida o'ylamaydi — shunchaki
#    so'raydi. Qarama-qarshi qaror (dardga ham ball) dard yozib ball
#    yig'ish yo'lini ochardi va og'ir mavzuni rag'batlantirardi.
#
# ⚠️⚠️ MINUS OVOZ KARMA AYIRMAYDI — foydalanuvchi qarori.
#    `↓` lentadagi tartibga ta'sir qiladi (`score_cached`), lekin karmaga
#    tegmaydi. Bu og'ir mavzular platformasi: minus karma odamni, ayniqsa
#    birinchi marta yozganini, butunlay jimitib qo'yardi. Sifatsiz javob
#    ko'rinmay qoladi — bu yetarli jazo; qoidabuzarlik esa moderatsiya
#    ishi (D2-T11), karma emas.
KARMA_QIYMATLARI: dict[str, int] = {
    KarmaReason.SOLUTION_ACCEPTED: 15,
    KarmaReason.SOLUTION_UNACCEPTED: -15,
    KarmaReason.SOLUTION_UPVOTED: 2,
    KarmaReason.SOLUTION_UPVOTE_OLINDI: -2,
}

# ⚠️ KOMPENSATSIYA SABABLARI — balli HISOBLANADI, konstanta EMAS.
#
#    Yechim olib tashlanganda qaytariladigan miqdor uning TARIXIGA bog'liq
#    (nechta ovoz oldi, qabul qilinganmi) — ya'ni oldindan ma'lum emas.
#    Shuning uchun bu ikkisi `KARMA_QIYMATLARI` da YO'Q va `karma_yoz()`
#    ularni RAD ETADI: aks holda "ball chaqiruvchidan olinmaydi" qoidasidan
#    qilingan ongli istisno jimgina umumiy teshikka aylanardi.
KOMPENSATSIYA_SABABLARI: tuple[str, ...] = (
    KarmaReason.KONTENT_OLIB_TASHLANDI,
    KarmaReason.KONTENT_TIKLANDI,
)


class KarmaEvent(TimeStampedModel):
    """Karma hodisalari jurnali — `User.karma_cached` ning HAQIQIY MANBAI.

    ⚠️ NEGA JURNAL, BUTUN SON EMAS (reja 6.1-bo'lim)
       `karma_points` oddiy son bo'lsa:
         · post o'chganda karma qaytmaydi;
         · qoida o'zgarsa qayta hisoblab bo'lmaydi;
         · "nega menda 1340?" degan savolga javob yo'q.
       Jurnal uchalasini ham yopadi va istalgan vaqtda qayta hisoblanadi.

    ⚠️ YOZUVLAR O'CHIRILMAYDI — TESKARISI YOZILADI
       Qabul bekor qilinganda `SOLUTION_ACCEPTED` yozuvi o'chirilmaydi,
       o'rniga `-15` li `SOLUTION_UNACCEPTED` qo'shiladi. Buxgalteriyadagi
       kabi: `+15`, `-15`, `+15` = sof `+15`.

       Nega o'chirilmaydi: (1) "nega karmam kamaydi?" savoliga javob
       qoladi; (2) noyoblik cheklovi qo'yilganda ikkinchi marta qabul
       qilish BLOKLANARDI; (3) audit (D2-T7) uchun tarix kerak.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="foydalanuvchi",
        on_delete=models.CASCADE,
        related_name="karma_events",
    )
    reason = models.CharField("sabab", max_length=32, choices=KarmaReason.choices)
    points = models.SmallIntegerField(
        "ball",
        help_text="Manfiy bo'lishi mumkin — teskari (kompensatsion) yozuv.",
    )
    # ⚠️ SET_NULL: yechim haqiqatan o'chirilsa (D2-T8) hodisa QOLADI.
    #    Jurnal o'z ma'nosini yo'qotmasligi kerak — ball allaqachon
    #    berilgan va uni "yo'q edi" qilib bo'lmaydi.
    solution = models.ForeignKey(
        "solutions.Solution",
        verbose_name="yechim",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="karma_events",
    )

    class Meta:
        verbose_name = "karma hodisasi"
        verbose_name_plural = "karma hodisalari"
        ordering = ("-created_at",)
        indexes = [
            # Profil sahifasidagi "karma tarixi" (D3-T4).
            models.Index(fields=["user", "-created_at"], name="karma_user_vaqt_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}: {self.points:+d} ({self.reason})"


# ===========================================================================
# Nishonlar (D3-T2)
# ===========================================================================
class NishonIkonka(models.TextChoices):
    """Ikonka KALITI — SVG kodi emas.

    ⚠️ `CategoryIcon` (apps/complaints/models.py) bilan BIR XIL qaror va
       bir xil sabab: bazada `<svg>` matnini saqlab, shablonda `|safe`
       bilan chiqarish har sahifada ishlaydigan XSS teshigi bo'lardi.
       Admin panelga kirgan kishi `<svg onload=...>` yozardi.

    ⚠️ Yangi ikonka qo'shsangiz `components/_nishon_ikonka.html` ga ham
       qo'shing — guard test ikkalasini solishtiradi.
    """

    CHECK = "check", "Belgi — birinchi qadam"
    BOLT = "bolt", "Chaqmoq — karma"
    CHAT = "chat", "Suhbat — yechimlar"
    SHIELD = "shield", "Qalqon — ishonch"
    STAR = "star", "Yulduz — sifat"
    FLAME = "flame", "Alanga — faollik"


class NishonMetrikasi(models.TextChoices):
    """⚠️⚠️ QABUL MEZONI: "nishon shartlari MA'LUMOTLARDA, kodda emas".

    Bu ro'yxat — shart EMAS, balki O'LCHANADIGAN KATTALIKLAR LUG'ATI.
    Qaysi nishonlar mavjud, ular nima deyiladi, qanday ikonka va QANDAY
    CHEGARA bilan ochiladi — hammasi `Badge` qatorlarida, ya'ni
    ma'lumotda. Yangi nishon qo'shish uchun kod TEGILMAYDI.

    ⚠️⚠️ NEGA IFODA SATRI EMAS (`"qabul >= 10"`).
       "Shart ma'lumotda" degani ba'zan "bazada ifoda saqlaymiz va uni
       hisoblaymiz" deb tushuniladi. Bu yerda ATAYLAB shunday
       QILINMAGAN: bajariladigan mantiqni bazaga solish — admin
       panelga kirgan odam yozgan matn serverda ishga tushishi degani.
       Loyiha bu qarorni allaqachon `CategoryIcon` da qabul qilgan
       (u yerda SVG, bu yerda ifoda — bir xil teshikning ikki shakli).

       Yopiq lug'at + son chegarasi butun ehtiyojni qoplaydi va
       `eval` ham, mini-parser ham talab qilmaydi.

    ⚠️ Yangi metrika qo'shsangiz `services.NISHON_METRIKALARI` ga ham
       qo'shing — guard test ikkalasini solishtiradi.
    """

    KARMA = "karma", "Karma"
    YECHIMLAR = "yechimlar", "Yozilgan yechimlar"
    QABUL_QILINGAN = "qabul_qilingan", "Qabul qilingan yechimlar"
    DARDLAR = "dardlar", "Yozilgan dardlar"
    OLINGAN_OVOZ = "olingan_ovoz", "Yechimlarga olingan ovoz"


class Badge(TimeStampedModel):
    """Nishon TA'RIFI — shartlari bilan birga (D3-T2).

    ⚠️⚠️ ANONIM ISH HAM HISOBLANADI (foydalanuvchi qarori).
       Metrikalar foydalanuvchining BARCHA kontentini sanaydi, anonim
       yozilganini ham. Aks holda anonim javob berish jazolanardi —
       D3-T1 dagi karma qarori bilan aynan bir xil sabab: eng og'ir
       mavzudagi javoblar ko'pincha anonim yoziladi va ular eng
       qimmatlisi.

       ⚠️ QOLGAN TESHIK, ONGLI QABUL QILINGAN: olingan nishon ommaviy
          va uning sharti ma'lum, ommaviy sanoq esa anonimni
          hisoblamaydi (D3-T4). Ya'ni kuzatuvchi "kamida N ta anonim
          ish bor" degan xulosaga kela oladi. Aniq son chiqmaydi —
          progress va qulflangan nishonlar FAQAT EGASIGA ko'rinadi
          (`selectors.nishonlar`).
    """

    slug = models.SlugField(
        "kalit",
        max_length=50,
        unique=True,
        help_text="Barqaror kalit — fixture va testlar shunga tayanadi.",
    )
    nom = models.CharField("nom", max_length=60)
    tavsif = models.CharField(
        "ochilish sharti",
        max_length=160,
        help_text=(
            "QULFLANGAN holatda ko'rsatiladi: «10 ta yechimingiz qabul "
            "qilinsa ochiladi». Bu bezak emas — u xulqni yo'naltiradi."
        ),
    )
    ikonka = models.CharField(
        "ikonka",
        max_length=16,
        choices=NishonIkonka.choices,
        default=NishonIkonka.CHECK,
    )
    metrika = models.CharField(
        "o'lchov", max_length=20, choices=NishonMetrikasi.choices
    )
    chegara = models.PositiveIntegerField(
        "chegara", help_text="Shu qiymatga yetganda nishon beriladi."
    )
    tartib = models.PositiveSmallIntegerField("tartib", default=100)
    is_active = models.BooleanField("faol", default=True, db_index=True)

    class Meta:
        verbose_name = "nishon"
        verbose_name_plural = "nishonlar"
        ordering = ("tartib", "chegara", "pk")
        constraints = [
            # ⚠️ Nol chegarali nishon HAMMAGA darhol berilardi va
            #    "yutuq" so'zi ma'nosini yo'qotardi.
            models.CheckConstraint(
                condition=models.Q(chegara__gt=0),
                name="nishon_chegara_musbat",
                violation_error_message="Chegara noldan katta bo'lishi kerak.",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.nom} ({self.metrika} >= {self.chegara})"


class UserBadge(models.Model):
    """Berilgan nishon — QAYTIB OLINMAYDI.

    ⚠️⚠️ NISHON BIR MARTA BERILADI VA QOLADI. Karma tushib ketsa
       (masalan kontent olib tashlanib kompensatsiya yozilsa, D3-T1)
       nishon O'CHIRILMAYDI: "sizda bor edi, endi yo'q" degan xabar
       odamni jazolagandek bo'lardi va u nimani noto'g'ri qilganini
       tushunmasdi. Yutuq — TARIX, joriy holat emas.

    ⚠️ Shu sababli `berilgan_at` bor va `UserBadge` `TimeStampedModel`
       dan meros olmaydi: `updated_at` ma'nosiz bo'lardi — bu yozuv
       yaratilgandan keyin O'ZGARMAYDI.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="foydalanuvchi",
        on_delete=models.CASCADE,
        related_name="nishonlari",
    )
    badge = models.ForeignKey(
        Badge,
        verbose_name="nishon",
        on_delete=models.CASCADE,
        related_name="egalari",
    )
    berilgan_at = models.DateTimeField("berilgan vaqt", auto_now_add=True)

    class Meta:
        verbose_name = "foydalanuvchi nishoni"
        verbose_name_plural = "foydalanuvchi nishonlari"
        ordering = ("-berilgan_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["user", "badge"],
                name="userbadge_uniq",
                violation_error_message="Bu nishon allaqachon berilgan.",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "-berilgan_at"], name="nishon_user_vaqt_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}: {self.badge_id}"
