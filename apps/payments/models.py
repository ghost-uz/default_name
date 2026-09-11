"""To'lovlar — modellar (D6-T1).

⚠️⚠️ NEGA OBUNA ALOHIDA MODEL, `User` DAGI SANA EMAS
   Task `nega` bo'limi: «PRO tekshiruvi kod bo'ylab tarqalsa, muddati
   tugagan obuna qayerdadir ishlab qolaveradi». Sana maydonini modelga
   qo'yish aynan shunga olib boradi — har chaqiruv joyi o'zicha
   `pro_until > now()` yozadi va biri albatta unutiladi yoki
   noto'g'ri yoziladi.

   Yagona kirish nuqtasi — `User.has_pro` (qabul mezoni). Guard test
   manba kodida `expires_at` / `status` ni `apps/payments/` dan
   TASHQARIDA taqqoslashni taqiqlaydi (D2-T3 ko'rinish invarianti va
   D2-T7 audit guard'i bilan bir xil naqsh).

⚠️⚠️ IKKI XIL «PRO» — BITTA SO'Z, IKKI BOSHQA TUSHUNCHA

   | | `User.has_pro` | `ExpertProfile.pro_faolmi` |
   |---|---|---|
   | Ma'nosi | TO'LOV amalda | PRO **nishoni** ko'rsatiladi |
   | Kimga tegishli | har qanday foydalanuvchi | faqat ekspert |
   | Sharti | faol obuna | tasdiqlangan malaka **VA** `has_pro` |

   Ikkinchisi birinchisining ISTE'MOLCHISI, parallel manba EMAS.
   D3-T5 dagi qoida kuchda qoladi: tasdiqlanmagan odam pul to'lab
   «Tasdiqlangan PRO» nishonini ololmaydi — aks holda pul bilan
   ishonch sotib olinardi.

   Oddiy foydalanuvchi ham PRO bo'la oladi: `ExpertProfile.contact_visible`
   yordam matni buni allaqachon nazarda tutgan («PRO obunachilar siz
   bilan bog'lana olishi uchun»).
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.common.models import (
    OzgarmasJurnal,
    OzgarmasJurnalQuerySet,
    TimeStampedModel,
)


class ObunaRejasi(models.TextChoices):
    """⚠️ Qiymatlar bazaga yoziladi — o'zgartirilmaydi, yangisi qo'shiladi."""

    PRO = "pro", "PRO"


class ObunaHolati(models.TextChoices):
    """⚠️ «BEKOR QILINGAN» holati ATAYLAB YO'Q.

    Bekor qilish = `auto_renew = False`, holat esa `FAOL` bo'lib
    QOLAVERADI. Odam to'lagan muddati uchun xizmatni oladi; bekor
    qilish tugmasi allaqachon to'langan narsani tortib olmaydi.
    Muddat tugagach vazifa uni `TUGAGAN` ga o'tkazadi.
    """

    FAOL = "faol", "Faol"
    TUGAGAN = "tugagan", "Muddati tugagan"


class Subscription(TimeStampedModel):
    """Foydalanuvchining PRO obunasi (D6-T1).

    ⚠️ `OneToOne` — JORIY holat. To'lovlar TARIXI bu yerda emas:
       u D6-T2/T3 dagi tranzaksiya jadvalida bo'ladi va idempotentlik
       ham o'sha yerda ta'minlanadi (`transaction_id` noyob).
       Bu yerda tarix saqlashga urinish ikkita yarim-manba yasardi.

    ⚠️ QATOR HAR FOYDALANUVCHI UCHUN YARATILMAYDI — hech qachon
       to'lamagan odamda u umuman yo'q (`BildirishnomaSozlamasi` bilan
       bir xil qaror, D5-T4). `has_pro` buni `getattr(..., None)` bilan
       hal qiladi.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        verbose_name="foydalanuvchi",
        on_delete=models.CASCADE,
        related_name="obuna",
    )
    plan = models.CharField(
        "reja",
        max_length=16,
        choices=ObunaRejasi.choices,
        default=ObunaRejasi.PRO,
    )
    status = models.CharField(
        "holat",
        max_length=16,
        choices=ObunaHolati.choices,
        default=ObunaHolati.FAOL,
        db_index=True,
    )
    started_at = models.DateTimeField("boshlangan vaqt", default=timezone.now)
    expires_at = models.DateTimeField("tugash vaqti", db_index=True)
    auto_renew = models.BooleanField(
        "avtomatik yangilanadi",
        default=False,
        help_text="O'chirilsa obuna joriy muddat oxirida tugaydi.",
    )

    class Meta:
        verbose_name = "obuna"
        verbose_name_plural = "obunalar"
        ordering = ("-expires_at", "-id")
        indexes = [
            # Celery vazifasi: muddati o'tgan FAOL qatorlar.
            models.Index(fields=["status", "expires_at"], name="obuna_muddat_idx"),
        ]

    def __str__(self) -> str:
        return (
            f"{self.user_id}: {self.get_plan_display()} -> {self.expires_at:%Y-%m-%d}"
        )

    @property
    def faolmi(self) -> bool:
        """⚠️⚠️ IKKALA SHART HAM TEKSHIRILADI — `status` YOLG'IZ YETARLI EMAS.

        `status` ni `TUGAGAN` ga o'tkazadigan Celery vazifasi kuniga bir
        marta ishlaydi. Muddat tugagan payt bilan vazifaning keyingi
        ishga tushishi orasida `status` hamon `FAOL` turadi — faqat
        unga qarasak, obuna bir kungacha BEPUL uzayardi.

        Ya'ni vazifa — TOZALASH, HAQIQAT MANBAI emas. Guard test
        buni vazifani UMUMAN ishlatmasdan tekshiradi.
        """
        return self.status == ObunaHolati.FAOL and self.expires_at > timezone.now()

    @property
    def tugashiga_kun(self) -> int:
        """Necha kun qolgani (o'tib ketgan bo'lsa 0)."""
        qoldi = self.expires_at - timezone.now()
        return max(0, qoldi.days)


# ===========================================================================
# To'lov (D6-T2) — provayderdan MUSTAQIL yadro
# ===========================================================================
class Provayder(models.TextChoices):
    """⚠️ FAQAT HAQIQIY TO'LOV TIZIMLARI.

    Admin qo'lda bergan obuna bu yerga TUSHMAYDI: u `Subscription`
    admin'ida yaratiladi (D6-T1 ataylab shunday qoldirgan — provayder
    yiqilganda yoki apellyatsiyada odamga obunani berish yo'li kerak).

    "Qo'lda" degan provayder qo'shish `Tolov` ni HAQIQIY pul harakati
    yozuvi bo'lishdan to'xtatardi: qatorlarning bir qismi pulga,
    bir qismi qarorga ishora qilardi va hisobot ikkalasini qo'shib
    yuborardi.
    """

    CLICK = "click", "Click"
    PAYME = "payme", "Payme"


class TolovMaqsadi(models.TextChoices):
    """Pul NIMA UCHUN to'landi.

    ⚠️⚠️ BU MODELNING KENGAYISH NUQTASI. D6-T4 (boost) shu yo'l bilan
       qo'shildi: bu yerda bitta qiymat, `services` dagi UCHTA lug'atga
       bittadan funksiya (berish, qaytarib olish, tayyorlashda tekshirish)
       — `click.py`/`payme.py` protokol kodiga UMUMAN tegilmadi. Uchala
       lug'at kalitlarining bir xilligini test qo'riqlaydi.

       Teskari yo'l (har maqsad uchun alohida webhook) ikkita imzo
       tekshiruvi, ikkita idempotentlik va ikkita jurnal degani edi.
    """

    OBUNA = "obuna", "PRO obuna"
    BOOST = "boost", "Postni ko'tarish"


class TolovHolati(models.TextChoices):
    """⚠️ HOLATLAR KETMA-KETLIGI: YANGI -> TAYYOR -> TOLANDI.

    `TAYYOR` (Click'ning "prepare"i) ATAYLAB alohida holat: usiz
    "Complete keldi, lekin Prepare kelmagan" holatini ajratib
    bo'lmasdi — u esa protokol buzilgani yoki so'rov soxtaligining
    eng aniq belgisi.
    """

    YANGI = "yangi", "Yaratildi"
    TAYYOR = "tayyor", "Tasdiqlashga tayyor"
    TOLANDI = "tolandi", "To'landi"
    BEKOR = "bekor", "Bekor qilindi"


class Tolov(TimeStampedModel):
    """Bitta to'lov urinishi = bitta buyurtma (D6-T2).

    ⚠️⚠️ NEGA `Subscription` DAN ALOHIDA
       `Subscription` — JORIY holat (bitta qator, bitta odam).
       `Tolov` — TARIX (har urinish uchun qator). D6-T1 buni oldindan
       yozib qo'ygan: «To'lovlar TARIXI bu yerda emas... idempotentlik
       ham o'sha yerda ta'minlanadi».

       Ikkalasini birlashtirish "obuna qachon va necha marta
       uzaytirilgan?" savolini javobsiz qoldirardi — u esa nizoda
       (mijoz: "men to'ladim") birinchi so'raladigan savol.

    ⚠️⚠️ IDEMPOTENTLIK BAZA DARAJASIDA
       `(provayder, provayder_trans_id)` — NOYOB. Qabul mezoni «bir xil
       transaction_id ikki marta kelsa ikkinchisi e'tiborsiz
       qoldiriladi» dasturiy tekshiruv bilan ham bajarilardi, lekin
       ikkita webhook AYNI PAYTDA kelganda ikkalasi ham "yo'q ekan"
       deb ko'rib, ikkalasi ham yozardi (TOCTOU). Baza cheklovi shu
       poygani yopadi.

       Bo'sh `provayder_trans_id` cheklovdan CHIQARILGAN: hali
       Click'ga bormagan buyurtmalar ko'p bo'ladi va ular bir-biriga
       xalaqit bermasin.

    ⚠️ `user` CASCADE — `Subscription` bilan bir xil. Amalda u hech
       qachon ishlamaydi: D2-T8 hisobni O'CHIRMAYDI, anonimlashtiradi.
       To'lov so'rovlari jurnali (`TolovSorovi`) esa baribir ALOHIDA
       yashaydi va hisob bilan ketmaydi.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="foydalanuvchi",
        on_delete=models.CASCADE,
        related_name="tolovlar",
    )
    maqsad = models.CharField(
        "maqsad",
        max_length=16,
        choices=TolovMaqsadi.choices,
        default=TolovMaqsadi.OBUNA,
    )
    provayder = models.CharField("provayder", max_length=16, choices=Provayder.choices)
    # ⚠️ `DecimalField`, `FloatField` EMAS. Pul ustidagi ikkilik kasr
    #    arifmetikasi 0.1 + 0.2 != 0.3 beradi va bu farq hisobotda
    #    yig'ilib boradi. So'm butun bo'lsa ham kasr o'rni QOLDIRILADI:
    #    Click summani "10000.00" shaklida yuboradi.
    summa = models.DecimalField("summa", max_digits=12, decimal_places=2)
    holat = models.CharField(
        "holat",
        max_length=16,
        choices=TolovHolati.choices,
        default=TolovHolati.YANGI,
        db_index=True,
    )
    provayder_trans_id = models.CharField(
        "provayder tranzaksiyasi",
        max_length=64,
        blank=True,
        help_text="Click: click_trans_id. Idempotentlik kaliti.",
    )
    # ⚠️⚠️ UCHTA VAQT UCHTA BOSHQA SAVOLGA JAVOB BERADI va ularni
    #    qo'shib yuborish mumkin emas:
    #      `created_at`        — buyurtma yaratildi (odam tugmani bosdi)
    #      `tayyorlangan_at`   — PROVAYDER tranzaksiyani ro'yxatga oldi
    #                            (Click: Prepare, Payme: CreateTransaction)
    #      `tolangan_at`       — pul yechildi
    #    Ular orasida soatlar bo'lishi mumkin: odam buyurtma yaratib,
    #    ertasiga to'lashi odatiy hol.
    #
    # ⚠️⚠️ Payme `create_time` ni `CheckTransaction` da QAYTARIB so'raydi
    #    va u TAKRORIY so'rovda ham BIR XIL bo'lishi shart. Shuning
    #    uchun u HISOBLANMAYDI — bazadan o'qiladi.
    tayyorlangan_at = models.DateTimeField(
        "provayder ro'yxatga oldi", null=True, blank=True
    )
    tolangan_at = models.DateTimeField("to'langan vaqt", null=True, blank=True)
    bekor_at = models.DateTimeField("bekor qilingan vaqt", null=True, blank=True)
    # ⚠️ Provayderning bekor qilish SABABI (Payme: 1-5, `4` = taymaut).
    #    Payme uni `CheckTransaction` javobida kutadi, ya'ni uni
    #    saqlamasdan iloji yo'q — hisoblab topib bo'lmaydi.
    bekor_kodi = models.IntegerField("bekor sababi (provayder)", null=True, blank=True)
    # ⚠️⚠️ QANCHA KUN BERILGANI. Pul qaytarilganda AYNAN shuncha kun
    #    qaytarib olinadi. Sozlamadagi joriy qiymatga tayanish xato
    #    bo'lardi: narx yoki muddat o'zgargan bo'lsa, kompensatsiya
    #    berilgandan boshqa songa teng bo'lardi va farq jimgina
    #    yig'ilib borardi (D3-T1 karma kompensatsiyasidagi bilan bir
    #    xil mulohaza).
    berilgan_kun = models.IntegerField("berilgan kun", null=True, blank=True)
    izoh = models.CharField("izoh", max_length=200, blank=True)

    class Meta:
        verbose_name = "to'lov"
        verbose_name_plural = "to'lovlar"
        ordering = ("-created_at", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=["provayder", "provayder_trans_id"],
                condition=~models.Q(provayder_trans_id=""),
                name="tolov_provayder_trans_noyob",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "-created_at"], name="tolov_odam_idx"),
            models.Index(fields=["holat", "-created_at"], name="tolov_holat_idx"),
        ]

    def __str__(self) -> str:
        return f"#{self.pk} {self.get_provayder_display()} {self.summa} — {self.holat}"

    @property
    def tolanganmi(self) -> bool:
        return self.holat == TolovHolati.TOLANDI

    @property
    def yakunlanganmi(self) -> bool:
        """Boshqa o'zgarmaydigan holatdami (to'langan yoki bekor)."""
        return self.holat in {TolovHolati.TOLANDI, TolovHolati.BEKOR}

    @property
    def qaytarilganmi(self) -> bool:
        """Pul YECHILGANDAN KEYIN bekor qilinganmi (Payme `-2`).

        ⚠️⚠️ ALOHIDA HOLAT MAYDONI QO'SHILMADI. "To'lovdan oldin bekor"
           va "to'lovdan keyin bekor" farqi allaqachon ma'lumotda bor:
           `tolangan_at` to'ldirilganmi. Ikkinchi maydon qo'shish uni
           `holat` bilan sinxron saqlashni talab qilardi va bir kuni
           ular bir-biriga zid bo'lib qolardi.
        """
        return self.holat == TolovHolati.BEKOR and self.tolangan_at is not None


class TolovSorovi(OzgarmasJurnal):
    """Provayderdan kelgan HAR BIR so'rov — o'zgarmas jurnal (D6-T2).

    ⚠️⚠️ QABUL MEZONI: «barcha so'rovlar jurnalga yoziladi».
       BARCHASI degani imzosi noto'g'rilari ham, tanish bo'lmagan
       buyurtmaga kelganlari ham. Nizoda ("pul yechildi, obuna
       berilmadi") yagona dalil shu jadval bo'ladi va u yerda faqat
       muvaffaqiyatli so'rovlar turgan bo'lsa, aynan kerakli qator
       yo'q bo'lardi.

    ⚠️⚠️ `sign_string` SAQLANMAYDI (`click.MAXFIY_MAYDONLAR`).
       U maxfiy kalit ishtirokidagi MD5. Qolgan maydonlar shu qatorda
       yotgani uchun, bazani qo'lga kiritgan odamga faqat kalitni
       oflayn tanlash qolardi. O'rniga `imzo_togrimi` bayrogi qoladi —
       nizo uchun kerakli ma'lumot aynan shu, xom hash emas.

    ⚠️ `tolov` — `SET_NULL`. Jurnal to'lovdan MUSTAQIL yashashi kerak:
       "qaysi buyurtmaga kelgani" `merchant_trans_id` satrida
       nusxalangan (`AuditLog.actor_nomi` bilan bir xil qaror).
    """

    created_at = models.DateTimeField("vaqt", auto_now_add=True, db_index=True)
    provayder = models.CharField("provayder", max_length=16, choices=Provayder.choices)
    amal = models.CharField(
        "amal",
        max_length=32,
        help_text="Click: prepare / complete. Payme: metod nomi.",
    )
    tolov = models.ForeignKey(
        Tolov,
        verbose_name="to'lov",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sorovlar",
    )
    merchant_trans_id = models.CharField("buyurtma (nusxa)", max_length=64, blank=True)
    provayder_trans_id = models.CharField(
        "provayder tranzaksiyasi", max_length=64, blank=True
    )
    # ⚠️ `GenericIPAddressField` EMAS: proksi buzilganda bu yerga
    #    umuman IP bo'lmagan satr kelishi mumkin va jurnalga YOZISH
    #    validatsiya xatosi bilan yiqilardi — ya'ni dalil yo'qolardi.
    ip = models.CharField("IP", max_length=45, blank=True)
    imzo_togrimi = models.BooleanField("imzo to'g'ri", default=False)
    natija = models.IntegerField("qaytarilgan kod", default=0)
    xom = models.JSONField("kelgan ma'lumot", default=dict, blank=True)
    javob = models.JSONField("qaytarilgan javob", default=dict, blank=True)

    objects = OzgarmasJurnalQuerySet.as_manager()

    class Meta:
        verbose_name = "to'lov so'rovi"
        verbose_name_plural = "to'lov so'rovlari jurnali"
        ordering = ("-created_at", "-pk")
        indexes = [
            models.Index(
                fields=["provayder", "-created_at"], name="tolovjurnal_prov_idx"
            ),
            models.Index(fields=["tolov", "-created_at"], name="tolovjurnal_tolov_idx"),
        ]

    def __str__(self) -> str:
        return (
            f"{self.provayder}/{self.amal} #{self.merchant_trans_id} -> {self.natija}"
        )


# ===========================================================================
# Boost — postni ko'tarish (D6-T4)
# ===========================================================================
class BoostOrderQuerySet(models.QuerySet):
    def faol(self) -> BoostOrderQuerySet:
        """HOZIR lentada joy olishi mumkin bo'lganlar.

        ⚠️⚠️ YAGONA TA'RIF — `BoostOrder.faolmi` bilan aynan bir xil shart
           va ikkalasining chegaralari test bilan qotirilgan: `starts_at`
           KIRADI, `ends_at` KIRMAYDI (D6-T1 dagi `Subscription.faolmi`
           naqshi).

        ⚠️ HOLAT MAYDONI YO'Q — faqat vaqt oralig'i. To'lanmagan
           buyurtmada ikkala sana `NULL` (hech qachon faol emas), pul
           qaytarilganda oraliq `now` da YOPILADI
           (`services._boostni_qaytarib_olish`). Alohida `holat` maydoni
           ikkinchi haqiqat manbai bo'lardi.
        """
        hozir = timezone.now()
        return self.filter(starts_at__lte=hozir, ends_at__gt=hozir)

    def tugamagan(self) -> BoostOrderQuerySet:
        """Hali tugamaganlar: faol VA navbatda turganlar (sotib olish sahifasi).

        ⚠️ Nol uzunlikdagi oraliq CHIQARILADI: navbatda turganda puli
           qaytarilgan boost (`starts_at == ends_at`, ikkalasi kelajakda)
           «hali tugamagan» bo'lib ko'rinardi va sahifa hech narsa
           ko'tarilmagan postga «ko'tarilgan ... gacha» deb yozardi.
        """
        return self.filter(ends_at__gt=timezone.now()).filter(
            ends_at__gt=models.F("starts_at")
        )


class BoostOrder(TimeStampedModel):
    """Postni «Qaynoq» lentasida ko'tarish buyurtmasi (D6-T4).

    ⚠️⚠️ BOOST `hot_score` GA QO'SHILMAYDI — task tavsifidan ONGLI chekinish.
       Tavsif: «faol boost hot_score'ga qo'shiladi». Qabul mezoni esa:
       «lentada boost ulushi cheklangan (har 5 postdan 1 tasi)».
       Qo'shimcha ball ulushni KAFOLATLAY OLMAYDI — o'nta boost bo'lsa,
       o'ntasi ham tepaga chiqadi. Ulushni faqat AJRATILGAN JOYLAR
       kafolatlaydi (`payments.selectors`).

       Ikkinchi sabab: `hot_score` uch joyda qayta ishlatiladi — lenta
       kursori (D1-T12), Telegram kanal avto-posti (D5-T3) va qayta
       hisoblash vazifasi (D1-T11). Pullik ball kanalga BELGISIZ reklama
       bo'lib tushardi, boost tugagach esa kursor chegaralari siljirdi.

    ⚠️ `amount` VA `user` MAYDONLARI YO'Q (tavsifdagi ro'yxatdan
       chekinish): ikkalasi `tolov` da bor (`tolov.summa`, `tolov.user`).
       Nusxa — ikkinchi haqiqat manbai, to'lov yozuvi esa pul
       harakatining YAGONA dalili (D6-T2).

    ⚠️ Buyurtma TO'LOVDAN OLDIN yaratiladi (sanalar `NULL`): webhook
       qaysi postni ko'tarishni aynan shu qatordan biladi. `Tolov` ga
       `complaint` FK qo'shish esa provayderdan mustaqil yadroni bitta
       maqsadga bog'lab qo'yardi.

    ⚠️ HAR TO'LOV — ALOHIDA QATOR. Faol boost ustiga yana to'lansa, yangi
       oraliq eskisining OXIRIDAN boshlanadi (obuna bilan bir xil qoida:
       erta to'lagan odam vaqtini yo'qotmasin). Pul qaytarilsa FAQAT
       o'sha to'lovning oralig'i yopiladi.
    """

    tolov = models.OneToOneField(
        Tolov,
        verbose_name="to'lov",
        on_delete=models.CASCADE,
        related_name="boost",
    )
    complaint = models.ForeignKey(
        "complaints.Complaint",
        verbose_name="muammo",
        on_delete=models.CASCADE,
        related_name="boostlar",
    )
    starts_at = models.DateTimeField("boshlanishi", null=True, blank=True)
    ends_at = models.DateTimeField("tugashi", null=True, blank=True)

    objects = BoostOrderQuerySet.as_manager()

    class Meta:
        verbose_name = "ko'tarish"
        verbose_name_plural = "ko'tarishlar"
        ordering = ("-created_at", "-id")
        indexes = [
            # Lenta so'rovi (`faol()`): hozir ochiq oraliqlar. `ends_at`
            # birinchi — tugagan qatorlar vaqt o'tgan sari ko'payadi va
            # indeks ularni birinchi ustunning o'zida kesib tashlaydi.
            models.Index(fields=["ends_at", "starts_at"], name="boost_faol_idx"),
        ]

    def __str__(self) -> str:
        return f"#{self.pk}: muammo {self.complaint_id}"

    @property
    def faolmi(self) -> bool:
        """`BoostOrderQuerySet.faol()` bilan AYNAN bir xil shart."""
        if self.starts_at is None or self.ends_at is None:
            return False
        return self.starts_at <= timezone.now() < self.ends_at

    @property
    def navbatdami(self) -> bool:
        """To'langan, lekin shu postning oldingi boosti tugashini kutyapti."""
        return self.starts_at is not None and self.starts_at > timezone.now()
