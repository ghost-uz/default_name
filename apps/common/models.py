"""Umumiy — barcha ilovalar meros oladigan abstrakt modellar.

⚠️ ARXITEKTURA QOIDASI: `common` eng quyi qatlam va boshqa ilovalarni
   IMPORT QILMAYDI. `settings.AUTH_USER_MODEL` esa istisno emas — u
   satrli (lazy) havola, ya'ni import bog'liqligi yaratmaydi. Django shu
   bilvositalikni aynan har qanday ilova foydalanuvchi modeliga ishora
   qila olishi uchun kiritgan.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


# ===========================================================================
# 1. Vaqt belgilari
# ===========================================================================
class TimeStampedModel(models.Model):
    """`created_at` va `updated_at`."""

    # `auto_now_add` EMAS, `default=timezone.now`.
    # Sabab: D7-T7 (sovuq start) uchun 50-100 ta muammo qo'lda kiritiladi va
    # ular orqaga sanalangan bo'lishi kerak — hammasi bir daqiqada yaratilgan
    # ko'rinsa lenta g'alati bo'ladi. `auto_now_add` berilgan qiymatni JIM
    # e'tiborsiz qoldiradi.
    # `editable=False` — formaga va admin tahririga tushmaydi, ya'ni
    # foydalanuvchi uni soxtalashtira olmaydi.
    created_at = models.DateTimeField(
        "yaratilgan", default=timezone.now, editable=False, db_index=True
    )
    updated_at = models.DateTimeField("yangilangan", auto_now=True)

    class Meta:
        abstract = True

    # ⚠️ `auto_now` FAQAT `save()` da ishlaydi. `QuerySet.update()` uni
    #    chetlab o'tadi — ommaviy yangilashda `updated_at` ni QO'LDA bering:
    #        qs.update(is_solved=True, updated_at=timezone.now())


# ===========================================================================
# 2. Yumshoq o'chirish (soft delete)
# ===========================================================================
class SoftDeleteQuerySet(models.QuerySet):
    """`delete()` ni yumshoq o'chirishga aylantiradi."""

    def alive(self) -> SoftDeleteQuerySet:
        return self.filter(deleted_at__isnull=True)

    def dead(self) -> SoftDeleteQuerySet:
        return self.filter(deleted_at__isnull=False)

    def delete(self):
        """Ommaviy yumshoq o'chirish.

        ⚠️ `update()` ishlatiladi — bu tez, lekin `pre_delete`/`post_delete`
        signallarini ISHGA TUSHIRMAYDI va `save()` ni chaqirmaydi.
        Signalga tayanadigan mantiq bo'lsa, elementlarni birma-bir o'chiring.
        """
        return super().update(deleted_at=timezone.now())

    def hard_delete(self):
        """Haqiqiy o'chirish — bazadan butunlay yo'q qiladi.

        Faqat huquqiy talab yoki GDPR-ga o'xshash so'rovda ishlatiladi
        (D2-T8). Moderatsiya uchun EMAS.
        """
        return super().delete()

    def restore(self):
        return super().update(deleted_at=None)


class AliveManager(models.Manager.from_queryset(SoftDeleteQuerySet)):  # type: ignore[misc]
    """Standart menejer — o'chirilganlarni KO'RSATMAYDI."""

    def get_queryset(self) -> SoftDeleteQuerySet:
        return super().get_queryset().filter(deleted_at__isnull=True)


class AllObjectsManager(models.Manager.from_queryset(SoftDeleteQuerySet)):  # type: ignore[misc]
    """O'chirilganlar bilan birga hammasi — audit va tiklash uchun."""


class SoftDeleteModel(models.Model):
    """Yozuvni bazadan o'chirmasdan "o'chirilgan" deb belgilaydi.

    Nega jismonan o'chirmaymiz: o'chirilgan kontent ustidan nizo chiqsa
    (yoki huquqiy so'rov kelsa) uni ko'rsatish kerak bo'ladi. Yo'q qilingan
    qatorni qaytarib bo'lmaydi.

    Menejerlar:
        objects      -> faqat tirik yozuvlar (STANDART)
        all_objects  -> hammasi

    ⚠️ FILTRLASH STANDART BO'YICHA YOQILGAN, chunki "o'chirilgan" hamma
       uchun yo'q degani. Moderatsiya bilan solishtiring (pastda) — u
       ataylab standart emas.

    ⚠️⚠️ NOYOBLIK TUZOG'I (D1-T3 da uchraydi)
       Yumshoq o'chirilgan yozuv bazada QOLADI, ya'ni uning `unique=True`
       maydonlari BAND bo'lib turaveradi. Masalan `Complaint.slug` noyob
       bo'lsa, o'chirilgan postning slug'ini boshqa hech kim ishlata
       olmaydi — va sababi tashqaridan ko'rinmaydi ("bu sarlavha band"
       deydi, lekin bunday post yo'q).

       Yechim — qisman (partial) noyob indeks:

           class Meta:
               constraints = [
                   models.UniqueConstraint(
                       fields=["slug"],
                       condition=models.Q(deleted_at__isnull=True),
                       name="complaint_slug_uniq_alive",
                   )
               ]

       Ya'ni maydonda `unique=True` YOZILMAYDI, o'rniga shu cheklov
       ishlatiladi.
    """

    deleted_at = models.DateTimeField(
        "o'chirilgan", null=True, blank=True, editable=False, db_index=True
    )
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="kim o'chirdi",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",  # teskari aloqa kerak emas
        editable=False,
    )

    objects = AliveManager()
    all_objects = AllObjectsManager()

    class Meta:
        abstract = True

    # ⚠️ `base_manager_name` ATAYLAB belgilanmagan.
    #    Django uni bermaganda o'zi filtrsiz `Manager()` yasaydi, ya'ni
    #    oldinga FK bo'ylab yurish (`solution.complaint`) o'chirilgan
    #    ota-yozuvni ham topa oladi. Aks holda `RelatedObjectDoesNotExist`
    #    chiqib, sababi tushunarsiz bo'lardi.
    #    Teskari aloqa (`complaint.solutions.all()`) esa `objects` ga
    #    tayanadi va o'chirilganlarni chiqarmaydi — bu kerakli xulq.

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def delete(self, using=None, keep_parents=False, *, user=None):
        """Yumshoq o'chirish. Haqiqiy o'chirish uchun `hard_delete()`."""
        self.deleted_at = timezone.now()
        self.deleted_by = user
        self.save(using=using, update_fields=["deleted_at", "deleted_by"])
        return (0, {})  # Django'ning delete() qaytarish shakli

    def hard_delete(self, using=None, keep_parents=False):
        return super().delete(using=using, keep_parents=keep_parents)

    def restore(self, *, save: bool = True) -> None:
        self.deleted_at = None
        self.deleted_by = None
        if save:
            self.save(update_fields=["deleted_at", "deleted_by"])


# ===========================================================================
# 3. Moderatsiya
# ===========================================================================
class ModerationStatus(models.TextChoices):
    VISIBLE = "visible", "Ko'rinadi"
    PENDING = "pending", "Tekshiruvda"
    HIDDEN = "hidden", "Yashirilgan"
    REMOVED = "removed", "Qoidabuzarlik uchun olib tashlangan"


class ModeratedQuerySet(models.QuerySet):
    def visible(self) -> ModeratedQuerySet:
        """⚠️ OMMAVIY KO'RINISHLAR UCHUN YAGONA KIRISH NUQTASI (D2-T3).

        Lenta, qidiruv, profil, sitemap, RSS, Telegram avto-post — hammasi
        shu metoddan o'tishi SHART. Bitta unutilgan so'rov (masalan
        `sitemap.xml`) yashirilgan kontentni Google'ga beradi va yashirish
        ma'nosini yo'qotadi.

        ⚠️ BU QOIDA IKKI GUARD BILAN MAJBURLANADI (D2-T3):
           `apps/common/tests/test_korinish_invarianti.py`

           1. Ish vaqtida — URLconf'dagi BARCHA yo'llar avtomatik
              aylanadi va yashirin marker javobda yo'qligi tekshiriladi.
              Yangi ko'rinish avtomatik qamrab olinadi.
           2. Manba kodida — `Complaint.objects` / `Solution.objects`
              `visible()` siz ishlatilgan joy topiladi. Ataylab qilingan
              istisnoga `# korinish-istisno: <sabab>` izohi qo'yiladi.

           Ikkalasi ham HAQIQATAN ISHLASHI tekshirilgan: kod ataylab
           buzilib, har biri xatoni topgani tasdiqlangan.
        """
        return self.filter(moderation_status=ModerationStatus.VISIBLE)

    def under_review(self) -> ModeratedQuerySet:
        return self.filter(moderation_status=ModerationStatus.PENDING)


class ModeratedManager(models.Manager.from_queryset(ModeratedQuerySet)):  # type: ignore[misc]
    """Filtrlamaydi — faqat `visible()` / `under_review()` metodlarini beradi.

    ⚠️ Menejer AJRALMAS: usiz `ModeratedModel` dan yolg'iz meros olgan
    modelda `.visible()` bo'lmaydi va Django jim ravishda oddiy `Manager`
    beradi. U holda D2-T3 dagi "yagona kirish nuqtasi" qoidasi buziladi.
    """


class ModeratedModel(models.Model):
    """Kontentning moderatsiya holati.

    ⚠️ SOFT DELETE'DAN FARQI: bu filtr STANDART BO'YICHA QO'LLANMAYDI.

    Sabab — yashirilgan kontentni ko'rishi KERAK bo'lganlar bor:
      · muallif   — posti yashirilganini bilishi kerak, aks holda u
                    "yo'qolgan" bo'lib ko'rinadi va foydalanuvchi ishonchi
                    yo'qoladi;
      · moderator — qarorni ko'rib chiqish uchun;
      · audit     — nima bo'lganini tiklash uchun.

    Shuning uchun `visible()` ATAYLAB ixtiyoriy va har bir ommaviy
    so'rovda ochiq yoziladi — "unutilgan filtr" ko'rinib turadi.
    """

    moderation_status = models.CharField(
        "moderatsiya holati",
        max_length=16,
        choices=ModerationStatus.choices,
        # Standart VISIBLE = KEYINGI moderatsiya (post-moderation).
        # Oldindan tekshirish (pre-moderation) 24/7 moderator talab qiladi
        # va rejadagi "1 soniyada yozish" tuyg'usini yo'q qiladi.
        # Avtomatik filtrlar (D2-T5, D2-T6) shubhalilarni PENDING ga o'tkazadi.
        default=ModerationStatus.VISIBLE,
        db_index=True,
    )
    moderation_note = models.CharField(
        "moderator izohi",
        max_length=300,
        blank=True,
        help_text="Foydalanuvchiga ko'rsatiladi — sababsiz yashirish shikoyat keltiradi.",
    )

    objects = ModeratedManager()

    class Meta:
        abstract = True

    @property
    def is_publicly_visible(self) -> bool:
        return self.moderation_status == ModerationStatus.VISIBLE


# ===========================================================================
# 4. Birlashtirilgan asos — Complaint va Solution shundan meros oladi
# ===========================================================================
class ContentQuerySet(SoftDeleteQuerySet, ModeratedQuerySet):  # type: ignore[override]
    """Ikkala aralashmaning so'rov metodlari bir joyda.

    `type: ignore[misc]` — django-stubs cheklovi: ikkita QuerySet dan
    meros olinganda `as_manager()` ning qaytish tipi ikki ota-sinfda
    turlicha chiqadi. Ish vaqtida muammo yo'q (MRO to'g'ri ishlaydi),
    bu faqat statik tahlil chegarasi.
    """


class ContentAliveManager(models.Manager.from_queryset(ContentQuerySet)):  # type: ignore[misc]
    def get_queryset(self) -> ContentQuerySet:
        return super().get_queryset().filter(deleted_at__isnull=True)


class ContentAllManager(models.Manager.from_queryset(ContentQuerySet)):  # type: ignore[misc]
    pass


class ContentModel(TimeStampedModel, SoftDeleteModel, ModeratedModel):
    """Foydalanuvchi yaratadigan kontent uchun umumiy asos.

    Ishlatilishi: `Complaint` (D1-T3), `Solution` (D1-T4).

    Ommaviy ro'yxat uchun har doim:
        Complaint.objects.visible()
    """

    # ⚠️ `type: ignore[misc]` — django-stubs cheklovi, kod xatosi emas.
    #    Plagin `SoftDeleteModel.objects` ni SINF o'zgaruvchisi qilib
    #    materializatsiya qiladi, bu yerdagi qayta belgilash esa nusxa
    #    o'zgaruvchisi bo'lib ko'rinadi. Ish vaqtida bu Django'ning
    #    odatiy menejer merosxo'rligi. Fayldagi menejer sinflarida ham
    #    xuddi shu izoh turibdi.
    #
    #    ⚠️ Bu xato `Complaint`/`Solution` paydo bo'lgunicha KO'RINMAGAN:
    #       plagin abstrakt modelni faqat unda konkret voris bo'lganda
    #       to'liq ishlab chiqadi. Ya'ni "mypy toza edi" degani "muammo
    #       yo'q edi" degani emas.
    objects = ContentAliveManager()  # type: ignore[misc]
    all_objects = ContentAllManager()  # type: ignore[misc]

    class Meta:
        abstract = True


# ===========================================================================
# 5. Ovoz berish (D1-T5)
# ===========================================================================
class VoteValue(models.IntegerChoices):
    """Ovoz qiymati.

    Butun son (`+1`/`-1`), matn emas — sabab: sanoqchini `Sum(value)` bilan
    tiklash va "qarama-qarshi ovozga o'tish 2 birlik" mantig'i arifmetikaga
    tayanadi. Matn bo'lsa har joyda `if` yozish kerak bo'lardi.
    """

    UP = 1, "Foydali"
    DOWN = -1, "Foydali emas"


class VotableModel(models.Model):
    """Ovoz beriladigan kontent uchun keshlangan sanoqchilar.

    ⚠️ NEGA IKKITA SANOQCHI, BITTA EMAS
       Faqat `score` saqlansa, 10 ta "+1" va 8 ta "-1" olgan qizg'in post
       bilan hech kim ovoz bermagan post BIR XIL (score=2) ko'rinadi.
       Moderatsiya (M2) uchun aynan shu farq muhim — bahsli kontentni
       shundan topiladi.

    ⚠️ NEGA `score_cached` GENERATED FIELD
       Uchinchi ustunni QO'LDA yangilash uchinchi drift manbai bo'lardi:
       yangilash yo'llaridan biri (masalan admin, yoki fon vazifasi) uni
       unutsa, saralash jimgina noto'g'ri bo'lib qoladi va buni hech kim
       sezmaydi. GENERATED ustunni PostgreSQL O'ZI hisoblaydi — u
       sanoqchilardan farq QILA OLMAYDI. Indekslash ham mumkin, ya'ni
       "Eng yaxshi" saralashi tez ishlaydi.

       Cheklov: bu ustunga yozib bo'lmaydi (`obj.score_cached = 5` ->
       xato). Bu ayb emas, xususiyat — haqiqiy manba sanoqchilar.

    ⚠️ HAQIQIY MANBA — OVOZ JADVALI
       Bu maydonlar KESH. Har biri `ComplaintVote` / `SolutionVote`
       jadvalidan qayta hisoblanishi mumkin bo'lishi SHART (D7-T3 tiklash
       mashqi shuni talab qiladi). Ularni `F()` ifodasisiz yangilamang.
    """

    # ⚠️ MAYDON EMAS — ko'rinish to'ldiradigan vaqtinchalik atribut (D1-T8).
    #    Shablon `{{ complaint.user_vote }}` deb o'qiydi: `1`, `-1` yoki
    #    `None`. Django faqat `Field` nusxalarini maydon deb hisoblaydi,
    #    shuning uchun bu migratsiyaga TUSHMAYDI.
    #
    #    Nega lug'at shablonga berilmaydi: Django shablon tili lug'atni
    #    o'zgaruvchi kalit bilan indekslay olmaydi (`user_votes[c.pk]`
    #    ishlamaydi). Atribut esa lentada ham, HTMX qayta renderida ham
    #    bir xil yo'l bo'ladi.
    #
    #    Standart `None` ATAYLAB: obyekt boshqa joydan kelsa (masalan
    #    Telegram avto-post, D5-T3) shablon `AttributeError` bermasin.
    user_vote: int | None = None

    upvotes_cached = models.PositiveIntegerField(
        "foydali ovozlar", default=0, editable=False
    )
    downvotes_cached = models.PositiveIntegerField(
        "foydali emas ovozlar", default=0, editable=False
    )
    score_cached = models.GeneratedField(
        verbose_name="ball",
        expression=models.F("upvotes_cached") - models.F("downvotes_cached"),
        output_field=models.IntegerField(),
        # PostgreSQL faqat STORED generated ustunni qo'llaydi (VIRTUAL emas).
        db_persist=True,
        db_index=True,
    )

    class Meta:
        abstract = True


class VoteModel(TimeStampedModel):
    """Bitta ovoz. `ComplaintVote` va `SolutionVote` shundan meros oladi.

    ⚠️ NEGA ALOHIDA JADVALLAR, `ContentType` EMAS (ochiq qaror Q1)
       Ovoz — loyihadagi eng ko'p YOZILADIGAN jadval. Umumiy `Vote`
       jadvalida noyoblik `(user, content_type, object_id)` bo'yicha
       bo'lardi: indeks kengroq, JOIN qimmatroq va eng muhimi — baza
       darajasida FK butunligi YO'Q (o'chirilgan postning ovozlari
       yetim bo'lib qoladi va ularni faqat qo'lda tozalash mumkin).

       Alohida jadvalda `ON DELETE CASCADE` shu ishni bepul bajaradi.
       Narxi — ikkita deyarli bir xil model; bu abstrakt asos uni
       kamaytiradi.

    ⚠️ NOYOBLIK CHEKLOVI ABSTRAKTDA EMAS, KONKRET MODELDA
       Cheklov maqsad maydonini (`complaint` / `solution`) nomlashi kerak,
       u esa faqat konkret modelda mavjud.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="foydalanuvchi",
        on_delete=models.CASCADE,
        # Foydalanuvchi o'chsa ovozlari ham ketadi — ular shaxsga bog'liq
        # va sanoqchilar D2-T8 da qayta hisoblanadi.
        related_name="%(class)ss",
    )
    value = models.SmallIntegerField("qiymat", choices=VoteValue.choices)

    class Meta:
        abstract = True

    def __str__(self) -> str:
        return f"{self.user_id}: {self.value:+d}"
