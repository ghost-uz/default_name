"""Muammolar — modellar (D1-T2, D1-T3, D1-T5).

Category, Complaint, ComplaintVote.
Tag va SavedItem keyingi tasklarda qo'shiladi (D1-T13).
"""

from __future__ import annotations

import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from apps.common.models import ContentModel, TimeStampedModel, VotableModel, VoteModel

# ⚠️ D1-T9 qabul mezoni: "tahrirlash oynasi cheklangan (masalan 30 daqiqa)".
#    Sozlamaga chiqarilmadi — bu mahsulot qoidasi, muhitga bog'liq emas.
#    O'zgartirilsa `Complaint.tahrirlay_oladimi()` testlari uni ushlaydi.
TAHRIRLASH_OYNASI = timedelta(minutes=30)


# ===========================================================================
# Kategoriya (D1-T2)
# ===========================================================================
class CategoryIcon(models.TextChoices):
    """Ikonka KALITI — SVG kodi emas.

    ⚠️ NEGA BAZADA SVG SAQLANMAYDI
       Ikonkani `<svg>...</svg>` matni sifatida saqlab, shablonda `|safe`
       bilan chiqarish oson yo'l — va aynan shu XSS teshigi: admin panelga
       kirgan (yoki kelajakda kategoriya taklif qila oladigan) kishi
       `<svg onload=...>` yozadi va bu har sahifada bajariladi.

       Kalit esa yopiq ro'yxatdan tanlanadi va `components/_category_icon.html`
       da haqiqiy SVG'ga aylantiriladi. Yangi ikonka qo'shish uchun ikkala
       joyni ham o'zgartirish kerak — bu ATAYLAB shunday.
    """

    BRIEFCASE = "briefcase", "Chamadon — karyera"
    HEART = "heart", "Yurak — munosabatlar"
    MONEY = "money", "Pul — moliya"
    GRADUATION = "graduation", "Qalpoq — ta'lim"
    PULSE = "pulse", "Puls — sog'liq"
    HOME = "home", "Uy — uy-joy"
    SCALE = "scale", "Tarozi — huquq"
    DOTS = "dots", "Nuqtalar — boshqa"


class Category(TimeStampedModel):
    """Muammo kategoriyasi.

    ⚠️ NEGA YUMSHOQ O'CHIRISH EMAS, `is_active`
       Kategoriya — ma'lumotnoma (reference data), foydalanuvchi kontenti
       emas. Uni "o'chirish" degani odatda "yangi post uchun taklif qilma"
       degani, "eski postlarni yo'qot" degani emas. `is_active=False`
       aynan shuni beradi: mavjud postlar ishlashda davom etadi, tanlov
       ro'yxatida esa ko'rinmaydi.

       Shu sababli `Complaint.category` da `on_delete=PROTECT` — kontenti
       bor kategoriyani baza darajasida o'chirib bo'lmaydi.
    """

    name = models.CharField("nomi", max_length=60, unique=True)
    slug = models.SlugField(
        "URL nomi",
        max_length=60,
        unique=True,
        help_text="URL'da ishlatiladi: /?category=moliya",
    )
    icon = models.CharField(
        "ikonka",
        max_length=20,
        choices=CategoryIcon.choices,
        default=CategoryIcon.DOTS,
    )
    description = models.CharField(
        "tavsif",
        max_length=200,
        blank=True,
        help_text="Kategoriyalar sahifasida kartochka ostida ko'rinadi.",
    )
    # ⚠️ Alifbo bo'yicha saralash noto'g'ri tartib beradi: "Boshqa" birinchi
    #    o'ringa chiqib qoladi. Qo'lda tartib kerak.
    order = models.PositiveSmallIntegerField(
        "tartib", default=100, help_text="Kichik raqam — yuqorida."
    )
    is_active = models.BooleanField(
        "faol",
        default=True,
        help_text="O'chirilsa yangi post uchun tanlab bo'lmaydi, eskilari qoladi.",
    )

    class Meta:
        verbose_name = "kategoriya"
        verbose_name_plural = "kategoriyalar"
        ordering = ("order", "name")

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self) -> str:
        """Shu kategoriya bo'yicha filtrlangan lenta.

        ⚠️ Holat URL'da (D1-T7): filtr so'rov parametrida bo'lgani uchun
           foydalanuvchi havolani ulasha oladi va "orqaga" tugmasi filtrni
           saqlaydi. D4-T4 da SEO uchun kanonik `/kategoriya/<slug>/`
           yo'li qo'shilishi mumkin — o'shanda faqat shu metod o'zgaradi.
        """
        return f"{reverse('feed')}?category={self.slug}"


# ===========================================================================
# Muammo (D1-T3)
# ===========================================================================
class Generation(models.TextChoices):
    """Avlod tegi — mahsulotning asosiy ajratuvchi belgisi (reja 1-bo'lim).

    Kalitlar maketdagi CSS klasslariga (`badge-genz`, `badge-mil`,
    `badge-boom`) va shablondagi taqqoslashlarga MOS: o'zgartirilsa
    `_complaint_card.html` ham o'zgaradi.
    """

    GENZ = "genz", "Gen Z"
    MILLENNIAL = "millennial", "Millennial"
    BOOMER = "boomer", "Boomer"


class ComplaintStatus(models.TextChoices):
    OPEN = "open", "Ochiq"
    SOLVED = "solved", "Yechilgan"
    # Muallif savolini yopdi (masalan o'zi hal qildi yoki dolzarbligini
    # yo'qotdi). Yechim qabul qilinmagan, lekin yangi yechim ham kutilmaydi.
    CLOSED = "closed", "Yopilgan"


class Complaint(ContentModel, VotableModel):
    """Foydalanuvchi yozgan muammo (dard).

    ⚠️ `is_solved` MAYDON EMAS, XOSSA
       Rejada `is_solved` boolean edi. Uni `status` bilan birga saqlash
       ikkita haqiqat manbai yaratadi: `status="closed"` va
       `is_solved=True` bir vaqtda bo'lishi mumkin va qaysi biri to'g'ri
       ekani noma'lum. Shuning uchun `status` — yagona manba, `is_solved`
       esa undan hisoblanadi. Filtrlash `status` bo'yicha qilinadi
       (xossani ORM filtrlay olmaydi).
    """

    # ⚠️ MAYDON EMAS — ko'rinish to'ldiradigan vaqtinchalik atribut (D1-T13),
    #    xuddi `VotableModel.user_vote` kabi. Shablon
    #    `{{ complaint.saqlangan }}` deb o'qiydi.
    #
    #    Standart `False` ATAYLAB: obyekt boshqa joydan kelsa (Telegram
    #    avto-post, D5-T3) shablon "saqlangan" deb ko'rsatib qo'ymasin.
    saqlangan: bool = False

    # -- Muallif -----------------------------------------------------------
    # ⚠️ SET_NULL, CASCADE EMAS. Hisob o'chganda (D2-T8) jamoa yaratgan
    #    kontent — savol va uning ostidagi yechimlar — YO'QOLMASLIGI kerak;
    #    aks holda bitta ketgan odam o'nlab foydali muhokamani o'zi bilan
    #    olib ketadi. `author=None` "o'chirilgan hisob" degani.
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="muallif",
        on_delete=models.SET_NULL,
        null=True,
        related_name="complaints",
    )
    category = models.ForeignKey(
        Category,
        verbose_name="kategoriya",
        on_delete=models.PROTECT,
        related_name="complaints",
    )

    # -- Mazmun ------------------------------------------------------------
    title = models.CharField("sarlavha", max_length=150)
    description = models.TextField("tavsif", max_length=5000)
    slug = models.SlugField("URL nomi", max_length=170, editable=False)
    generation_tag = models.CharField(
        "avlod",
        max_length=12,
        choices=Generation.choices,
        blank=True,
        db_index=True,
        help_text="Ixtiyoriy — hamma ham o'zini avlodga bog'lamaydi.",
    )

    # -- Anonimlik (D1-T6) -------------------------------------------------
    is_anonymous = models.BooleanField(
        "anonim",
        default=False,
        help_text="Yoqilsa muallif hech qayerda ko'rsatilmaydi.",
    )
    # ⚠️ OCHIQ QAROR Q2 uchun BO'SH TAYYORLANGAN MAYDON.
    #    Hozircha barcha anonim postlar shunchaki "Anonim" deb ko'rsatiladi.
    #    Agar keyinchalik "bir odamning anonim postlari o'zaro bog'lanmasin"
    #    talabi paydo bo'lsa, har postga tasodifiy taxallus (masalan
    #    "Anonim kiyik") yoziladi. Maydonni HOZIR qo'shish arzon; keyin
    #    qo'shish esa mavjud million qatorga migratsiya degani.
    anon_handle = models.CharField(
        "anonim taxallus",
        max_length=40,
        blank=True,
        editable=False,
        help_text="Hozircha ishlatilmaydi (ochiq qaror Q2).",
    )

    # -- Holat -------------------------------------------------------------
    status = models.CharField(
        "holat",
        max_length=10,
        choices=ComplaintStatus.choices,
        default=ComplaintStatus.OPEN,
        db_index=True,
    )
    accepted_solution = models.ForeignKey(
        "solutions.Solution",
        verbose_name="qabul qilingan yechim",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        # ⚠️ `+` — teskari aloqa YO'Q. Aks holda Solution'da ikkita deyarli
        #    bir xil teskari nom paydo bo'lardi (`complaint` va
        #    `accepted_by_complaint`) va qaysi birini ishlatish noaniq
        #    bo'lardi. Haqiqiy manba — `Solution.is_accepted`.
        related_name="+",
    )

    # -- Denormalizatsiya --------------------------------------------------
    # ⚠️ Bularning hammasi KESH. Har biri so'rov bilan hisoblanishi mumkin,
    #    lekin lentadagi har karta uchun alohida COUNT/JOIN qilish
    #    20 ta karta = 40+ so'rov degani (D1-T14).
    views_count = models.PositiveIntegerField("ko'rishlar", default=0, editable=False)
    solutions_count = models.PositiveIntegerField(
        "yechimlar soni", default=0, editable=False
    )
    has_expert_answer = models.BooleanField(
        "ekspert javob bergan", default=False, editable=False
    )
    # ⚠️ `db_index` — "Qaynoq" saralashning butun ma'nosi shu. DESC uchun
    #    ALOHIDA indeks kerak emas: PostgreSQL btree'ni ikkala yo'nalishda
    #    ham skanerlaydi, ikkinchisi faqat disk va yozish yukini oshirardi.
    hot_score = models.FloatField("qaynoqlik", default=0.0, db_index=True)

    class Meta:
        verbose_name = "muammo"
        verbose_name_plural = "muammolar"
        ordering = ("-created_at",)
        constraints = [
            # ⚠️ `unique=True` EMAS. Yumshoq o'chirilgan post bazada qoladi
            #    va uning slug'ini BAND qilib turadi — sababi tashqaridan
            #    ko'rinmaydi. Qisman (partial) indeks faqat tirik qatorlarni
            #    qamraydi. Batafsil: apps/common/models.py, SoftDeleteModel.
            models.UniqueConstraint(
                fields=["slug"],
                condition=models.Q(deleted_at__isnull=True),
                name="complaint_slug_uniq_alive",
            ),
        ]
        indexes = [
            # Kategoriya bo'yicha filtrlangan "Qaynoq" lenta (D1-T7).
            models.Index(
                fields=["category", "hot_score"], name="complaint_cat_hot_idx"
            ),
        ]

    def __str__(self) -> str:
        return self.title

    # -- URL ---------------------------------------------------------------
    def get_absolute_url(self) -> str:
        return reverse("complaint_detail", kwargs={"slug": self.slug})

    # -- Slug --------------------------------------------------------------
    def _yangi_slug(self) -> str:
        """`sarlavha-a3f9c1d2` — o'qiladigan asos + tasodifiy quyruq.

        ⚠️ NEGA QUYRUQ KERAK
           Faqat sarlavhadan slug yasash ikki muammo beradi: (1) bir xil
           sarlavhali ikkinchi post yozib bo'lmaydi, (2) to'qnashuvni
           `-2`, `-3` bilan hal qilish yozishdan oldin SELECT talab qiladi
           va u poyga holatiga (race) ochiq. 4 bayt tasodif (~4,3 milliard
           variant) ikkalasini ham yopadi.

        ⚠️ KIRILL YOZUVI
           `slugify` lotin bo'lmagan belgilarni tashlab yuboradi, ya'ni
           to'liq kirillcha sarlavhadan bo'sh asos qoladi. Bunda `dard`
           zaxira so'zi ishlatiladi. To'liq yechim — D4-T2 (transliteratsiya).
        """
        asos = slugify(self.title)[:120].strip("-") or "dard"
        return f"{asos}-{secrets.token_hex(4)}"

    def save(self, *args, **kwargs) -> None:
        if not self.slug:
            self.slug = self._yangi_slug()
            # ⚠️ `update_fields` berilgan bo'lsa slug unga QO'SHILISHI kerak,
            #    aks holda yangi qiymat jimgina yo'qoladi.
            update_fields = kwargs.get("update_fields")
            if update_fields is not None:
                kwargs["update_fields"] = {*update_fields, "slug"}
        super().save(*args, **kwargs)

    # -- Anonimlik invarianti (D1-T6) --------------------------------------
    @property
    def public_author(self):
        """⚠️ MUALLIFGA YAGONA OMMAVIY KIRISH NUQTASI.

        Shablon, kontekst, API — hammasi SHU xossadan o'tishi shart.
        `complaint.author` to'g'ridan-to'g'ri ishlatilsa anonimlik jim
        ravishda buziladi va buni faqat foydalanuvchi sezadi.

        `None` qaytishining IKKI sababi bor va ikkalasi ham "ismni
        ko'rsatma" degani:
          · post anonim yozilgan;
          · muallif hisobini o'chirgan (D2-T8).
        """
        if self.is_anonymous:
            return None
        return self.author

    # -- Tahrirlash oynasi (D1-T9) -----------------------------------------
    @property
    def tahrirlash_oynasi_ochiqmi(self) -> bool:
        """Yozilganidan keyin `TAHRIRLASH_OYNASI` o'tmaganmi."""
        return timezone.now() - self.created_at <= TAHRIRLASH_OYNASI

    def tahrirlay_oladimi(self, user) -> bool:
        """Shu foydalanuvchi bu postni HOZIR tahrirlay oladimi.

        Uch shart, uchalasi ham ayrim sababga ega:

        1. **Muallif** — boshqa hech kim (moderator kontentni tahrirlamaydi,
           u yashiradi yoki o'chiradi; D2-T2).
        2. **30 daqiqa ichida** (D1-T9 qabul mezoni) — imlo xatosini
           tuzatish uchun yetarli, lekin postni butunlay boshqa narsaga
           aylantirish uchun emas.
        3. **Yechim kelmagan bo'lsa** — ⚠️ bu eng muhimi va vaqt
           chegarasidan mustaqil. Aks holda quyidagi suiiste'mol ochiq
           qolardi: zararsiz savol yoziladi, javoblar yig'iladi, keyin
           savol matni almashtiriladi — va o'nlab odamning javobi
           butunlay boshqa savolga "javob berayotgandek" ko'rinadi.
           Ularning nomidan aytilmagan gap aytilgan bo'lib qoladi.

        Keyinchalik (D2) tahrir tarixi qo'shilsa, 2-shart yumshatilishi
        mumkin — 3-shart esa qolishi kerak.
        """
        if not getattr(user, "is_authenticated", False):
            return False
        if self.author_id != user.pk:
            return False
        if self.solutions_count > 0:
            return False
        return self.tahrirlash_oynasi_ochiqmi

    # -- Hisoblanadigan holat ----------------------------------------------
    @property
    def is_solved(self) -> bool:
        """Maketdagi "Yechilgan" nishoni shuni o'qiydi."""
        return self.status == ComplaintStatus.SOLVED

    @property
    def is_closed(self) -> bool:
        """Muhokama tugagan (ko'rsatish uchun): yechilgan YOKI yopilgan."""
        return self.status in (ComplaintStatus.SOLVED, ComplaintStatus.CLOSED)

    @property
    def yangi_yechim_qabul_qiladimi(self) -> bool:
        """Bu muammoga hali yechim yozish mumkinmi.

        ⚠️ `is_closed` BILAN ADASHTIRMANG — bu farq jonli sinovda topildi.

        · `CLOSED` — muallif kutishni TO'XTATDI. Yangi javob endi kerak
          emas va uni yozgan odam vaqtini behuda sarflaydi.
        · `SOLVED` — javob topildi, LEKIN muhokama qimmatini yo'qotmaydi:
          keyinroq yaxshiroq javob kelishi mumkin va muallif qabul
          qilishni o'sha yechimga o'tkaza oladi.

        Ikkalasini birga to'sish o'z-o'ziga zid bo'lardi:
        `accept_solution()` ataylab BOSHQA yechimga o'tishni qo'llaydi
        (eskisidan karmani qaytarib), lekin yangi yechim umuman kela
        olmasa, o'sha yo'lga deyarli tushib bo'lmasdi.
        """
        return self.status != ComplaintStatus.CLOSED


# ===========================================================================
# Muammoga ovoz (D1-T5)
# ===========================================================================
class ComplaintVote(VoteModel):
    """Bitta foydalanuvchining bitta muammoga bergan ovozi.

    Ovoz berish mantig'i (yangi / bekor qilish / almashtirish) modelda
    emas, `apps.common.voting.cast_vote()` da — u tranzaksiya ichida
    sanoqchini ham yangilaydi.
    """

    complaint = models.ForeignKey(
        Complaint,
        verbose_name="muammo",
        on_delete=models.CASCADE,
        related_name="votes",
    )

    class Meta:
        verbose_name = "muammo ovozi"
        verbose_name_plural = "muammo ovozlari"
        constraints = [
            # ⚠️ QO'SHALOQ OVOZGA QARSHI HIMOYA BAZADA, KODDA EMAS.
            #    Kod darajasidagi `get_or_create` ikki bir vaqtli so'rovda
            #    ikkita qator yaratishi mumkin (ikkala tranzaksiya ham
            #    "yo'q ekan" deb ko'radi). Faqat DB cheklovi buni yopadi.
            models.UniqueConstraint(
                fields=["user", "complaint"],
                name="complaintvote_user_target_uniq",
                violation_error_message="Bu muammoga allaqachon ovoz bergansiz.",
            ),
        ]


# ===========================================================================
# Saqlanganlar / xatcho'p (D1-T13)
# ===========================================================================
class SavedComplaint(TimeStampedModel):
    """Foydalanuvchi keyinroq qaytmoqchi bo'lgan muammo.

    ⚠️ NEGA `SavedItem` EMAS, `SavedComplaint`
       Taskda "SavedItem: user, target" deb yozilgan — ya'ni umumiy
       (`ContentType`) model nazarda tutilgan. Bu yerda ovoz jadvallari
       bilan BIR XIL qaror qabul qilindi (ochiq qaror Q1): alohida
       jadval, chunki baza darajasidagi FK butunligi muhimroq —
       o'chirilgan post uchun yetim yozuv qolmaydi.

       Hozircha faqat muammo saqlanadi (maketda ham faqat unda "Saqlash"
       tugmasi bor). Yechim saqlash kerak bo'lsa — `SavedSolution`,
       xuddi `SolutionVote` kabi.

    ⚠️ YUMSHOQ O'CHIRISH YO'Q: xatcho'p — foydalanuvchining SHAXSIY
       ro'yxati, kontent emas. "Saqlanganlardan olib tashlash" degani
       aynan "yo'q qilish" — uni tarixda saqlash foydalanuvchi
       kutmaydigan xulq bo'lardi (va D2-T8 eksportida chiqib qolardi).
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="foydalanuvchi",
        on_delete=models.CASCADE,
        related_name="saved_complaints",
    )
    complaint = models.ForeignKey(
        Complaint,
        verbose_name="muammo",
        on_delete=models.CASCADE,
        related_name="saved_by",
    )

    class Meta:
        verbose_name = "saqlangan muammo"
        verbose_name_plural = "saqlangan muammolar"
        ordering = ("-created_at",)
        constraints = [
            # Qabul mezoni: unique_together(user, target).
            # ⚠️ Kodda `get_or_create` yetarli emas: ikki bir vaqtli so'rov
            #    ikkalasi ham "yo'q ekan" deb ko'radi.
            models.UniqueConstraint(
                fields=["user", "complaint"],
                name="savedcomplaint_user_target_uniq",
            ),
        ]
        indexes = [
            # "Saqlanganlarim" ro'yxati: yangisidan eskisiga.
            models.Index(fields=["user", "-created_at"], name="saved_user_vaqt_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} -> {self.complaint_id}"
