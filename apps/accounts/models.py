"""Foydalanuvchilar — modellar.

⚠️ Bu fayl loyihaning eng qaytarib bo'lmaydigan qismi. `AUTH_USER_MODEL`
   birinchi migratsiyada belgilanadi; keyinroq almashtirish amalda bazani
   noldan qurishni talab qiladi.
"""

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone

from .validators import USERNAME_HELP, validate_username

# ⚠️ Qabul mezonidagi AYNAN shu matn (D2-T8).
OCHIRILGAN_NOM = "O'chirilgan foydalanuvchi"


class User(AbstractUser):
    """Dard.uz foydalanuvchisi.

    `AbstractUser` dan meros olinadi (`AbstractBaseUser` emas), chunki:
    - staff'ga admin paneliga kirish uchun parol autentifikatsiyasi kerak;
    - moderatsiya (M2) Django ruxsatlar va guruhlar tizimiga tayanadi.

    Oddiy foydalanuvchilar parol ishlatmaydi — ular Telegram orqali kiradi
    (D1-T1). Ularda `password` bo'sh (`set_unusable_password`) bo'ladi.
    """

    # -- Kimlik ------------------------------------------------------------
    username = models.CharField(
        "foydalanuvchi nomi",
        max_length=30,
        unique=True,
        validators=[validate_username],
        help_text=USERNAME_HELP,
        error_messages={"unique": "Bu foydalanuvchi nomi band."},
    )

    # Telegram ID 32-bitdan oshadi -> BigInteger.
    # null=True: Telegram'siz staff hisoblari uchun. PostgreSQL'da unique
    # indeks bir nechta NULL ga ruxsat beradi — aynan shu kerak.
    telegram_id = models.BigIntegerField(
        "Telegram ID",
        unique=True,
        null=True,
        blank=True,
        db_index=True,
    )

    bio = models.TextField("o'zi haqida", max_length=500, blank=True)

    # -- Nomni bir marta o'zgartirish (D1-T1 mahsulot qarori) --------------
    # Telegram'dan kirganda nom AVTOMATIK yasaladi ("1 soniyada kirish"
    # va'dasi), lekin foydalanuvchi uni KEYINCHALIK BIR MARTA
    # o'zgartira oladi. Sabab: avtomatik nom ba'zan chiroyli chiqmaydi
    # (kirillcha ism -> `dard_8f3a91`), lekin cheksiz o'zgartirish
    # taqlid va chalkashlik uchun eshik ochadi.
    #
    # ⚠️ ALOHIDA JADVAL EMAS, IKKI MAYDON: o'zgartirish BIR MARTA
    #    bo'lgani uchun har foydalanuvchida ko'pi bilan BITTA eski nom
    #    bo'ladi. Tarix jadvali ortiqcha JOIN va migratsiya degani.
    oldingi_username = models.CharField(
        "oldingi nom",
        max_length=30,
        blank=True,
        editable=False,
        help_text="Eski havolalar (/@eski/) shu orqali yangisiga yo'naltiriladi.",
    )
    username_ozgartirilgan = models.DateTimeField(
        "nom o'zgartirilgan",
        null=True,
        blank=True,
        editable=False,
        help_text="To'ldirilgan bo'lsa — nom allaqachon bir marta o'zgartirilgan.",
    )

    # -- Gamifikatsiya -----------------------------------------------------
    # ⚠️ DENORMALIZATSIYA. Haqiqiy manba — KarmaEvent jurnali (D3-T1).
    #    Bu maydonni QO'LDA o'zgartirmang: u SUM(KarmaEvent.points) dan
    #    hisoblanadi va istalgan vaqtda qayta tiklanishi mumkin bo'lishi kerak.
    # db_index: reyting uchun ORDER BY karma_cached DESC (D3-T3).
    # Alohida DESC indeks KERAK EMAS — PostgreSQL btree indeksni ikkala
    # yo'nalishda ham skanerlaydi, ikkinchisi faqat disk va yozish yukini
    # oshirardi.
    karma_cached = models.IntegerField("karma (keshlangan)", default=0, db_index=True)

    # ⚠️ Bu ham keshlangan bayroq. Haqiqiy manba — tasdiqlangan ExpertProfile
    #    (D3-T5). Bu yerda saqlanishi lentada har kartada JOIN qilmaslik uchun.
    is_expert = models.BooleanField("ekspert", default=False, db_index=True)

    # -- Moderatsiya -------------------------------------------------------
    # `is_active` (Django'niki) va `is_banned` ATAYLAB alohida:
    #   is_active=False  -> umuman kira olmaydi (o'chirilgan hisob)
    #   is_banned=True   -> KIRADI va O'QIYDI, lekin yoza olmaydi
    # Bloklangan odamni butunlay quvish uni platformadan tashqarida
    # boshqa hisob ochishga undaydi; o'qishga ruxsat berish esa arzon.
    is_banned = models.BooleanField("bloklangan", default=False)
    banned_until = models.DateTimeField(
        "blok tugashi",
        null=True,
        blank=True,
        help_text="Bo'sh bo'lsa — doimiy blok. D2-T11 (uch ogohlantirish) ishlatadi.",
    )
    ban_reason = models.CharField("blok sababi", max_length=200, blank=True)

    # -- Rozilik va yosh (D2-T10) -----------------------------------------
    # ⚠️ QABUL MEZONI: "rozilik sanasi saqlanadi".
    #
    # ⚠️ VERSIYA HAM SAQLANADI, faqat sana emas. Shartlar o'zgarganda
    #    "roziman" degan yozuv qaysi MATNGA tegishli ekani ma'lum
    #    bo'lishi kerak — aks holda jurnal "rozi bo'lgan" deydi-yu,
    #    nimaga rozi bo'lgani noma'lum qoladi. Versiya o'zgarsa
    #    foydalanuvchi qayta rozilik beradi.
    rozilik_at = models.DateTimeField(
        "rozilik sanasi", null=True, blank=True, editable=False
    )
    rozilik_versiyasi = models.CharField(
        "rozilik versiyasi", max_length=20, blank=True, editable=False
    )
    # ⚠️ ALOHIDA maydon: yosh tasdig'i shartlarga rozilikdan boshqa
    #    narsa. Ular bitta katakchaga qo'shilsa, keyin "16+ ekanini
    #    tasdiqlaganmi?" degan savolga aniq javob bo'lmasdi.
    yosh_tasdigi_at = models.DateTimeField(
        "yosh tasdig'i", null=True, blank=True, editable=False
    )

    # -- Hisobni o'chirish (D2-T8) -----------------------------------------
    # ⚠️⚠️ QATOR O'CHIRILMAYDI, ANONIMLASHTIRILADI.
    #
    #    Sabab qabul mezonida: "o'chirilgan foydalanuvchining kontenti
    #    QOLADI". Qator o'chirilsa `author` `NULL` bo'lardi va bitta
    #    muhokamadagi ikki xil odam bir xil "muallifsiz" ko'rinardi —
    #    o'quvchi ularni bir odam deb o'ylashi mumkin.
    #
    # ⚠️ NEGA BITTA UMUMIY "sentinel" FOYDALANUVCHI EMAS (reja shuni
    #    taklif qilgandi): u holda BARCHA o'chirilgan hisoblarning
    #    kontenti bitta muallifga tegishli bo'lib qolardi. Bir suhbatda
    #    ikki xil odam bir xil nom bilan chiqib, "o'zi bilan o'zi
    #    gaplashayotgan" odam taassurotini berardi. Har hisobga o'z
    #    o'rindoshi qolgani to'g'riroq va D2-T11 (uch ogohlantirish)
    #    uchun ham zarur.
    ochirilgan_at = models.DateTimeField(
        "hisob o'chirilgan",
        null=True,
        blank=True,
        editable=False,
        db_index=True,
        help_text="To'ldirilgan bo'lsa: shaxsiy ma'lumot tozalangan, kontent qolgan.",
    )

    class Meta:
        verbose_name = "foydalanuvchi"
        verbose_name_plural = "foydalanuvchilar"
        constraints = [
            # ⚠️ TAQLIDGA QARSHI: `unique=True` PostgreSQL'da registrga
            # sezgir — "Sardor" va "sardor" ikkalasi ham yaratilishi mumkin
            # bo'lardi. Bu funksional indeks buni DB darajasida yopadi.
            models.UniqueConstraint(
                Lower("username"),
                name="accounts_user_username_ci_uniq",
                violation_error_message="Bu foydalanuvchi nomi band.",
            ),
            # ⚠️ Eski nom ham BAND bo'lib qoladi — aks holda nom
            #    o'zgartirilgandan keyin uni boshqa odam olib, eski
            #    havolalar (/@eski/) o'sha odamga olib borardi. Bu
            #    taqlid uchun tayyor mexanizm bo'lardi.
            #
            #    Qisman indeks: bo'sh qiymat ko'p qatorda takrorlanadi.
            models.UniqueConstraint(
                Lower("oldingi_username"),
                condition=~models.Q(oldingi_username=""),
                name="accounts_user_oldingi_username_ci_uniq",
                violation_error_message="Bu foydalanuvchi nomi band.",
            ),
        ]

    def __str__(self) -> str:
        return self.username

    # -- Ko'rsatiladigan nom ----------------------------------------------
    @property
    def ochirilganmi(self) -> bool:
        return self.ochirilgan_at is not None

    @property
    def display_name(self) -> str:
        """Interfeysda ko'rsatiladigan nom.

        Telegram `first_name` beradi, lekin u ixtiyoriy va takrorlanishi
        mumkin — shuning uchun zaxira sifatida `username` ishlatiladi.

        ⚠️ O'chirilgan hisob uchun QABUL MEZONIDAGI matn qaytadi. Bu
           yerda qaytarilishi muhim: shablonlar shu xossani ishlatadi,
           ya'ni bitta joyda tuzatilsa hamma joyda to'g'ri bo'ladi.
        """
        if self.ochirilganmi:
            return OCHIRILGAN_NOM
        return self.first_name.strip() or self.username

    @property
    def initial(self) -> str:
        """Harf-avatar uchun bitta belgi (maket rasm ishlatmaydi)."""
        return self.display_name[:1].upper()

    # -- Blok holati -------------------------------------------------------
    @property
    def is_currently_banned(self) -> bool:
        """Blok HOZIR kuchdami?

        Vaqtinchalik blok muddati o'tgan bo'lsa `is_banned` bayrog'i hali
        `True` turishi mumkin — uni fon vazifasi tozalaydi. Shuning uchun
        tekshiruv har doim shu xossa orqali qilinsin, bayroqqa to'g'ridan-
        to'g'ri qaralmasin.
        """
        if not self.is_banned:
            return False
        if self.banned_until is None:
            return True  # doimiy
        return timezone.now() < self.banned_until

    @property
    def nomni_ozgartira_oladimi(self) -> bool:
        """Nomni o'zgartirish imkoni HALI ISHLATILMAGANMI.

        Interfeys (D3-T4 profil sozlamalari) shu xossaga qaraydi;
        haqiqiy himoya esa `services.usernameni_ozgartirish()` da.
        """
        return self.username_ozgartirilgan is None

    @property
    def rozilik_bormi(self) -> bool:
        """Joriy versiyaga rozilik berilganmi (D2-T10).

        ⚠️ Versiya SOLISHTIRILADI: eski matnga berilgan rozilik yangi
           matnni qoplamaydi. Shartlar o'zgarganda foydalanuvchi qayta
           o'qib, qayta rozilik beradi.
        """
        from django.conf import settings

        return (
            self.rozilik_at is not None
            and self.rozilik_versiyasi == settings.HUQUQIY_VERSIYA
        )

    @property
    def can_write(self) -> bool:
        """Kontent yarata oladimi (dard, yechim, izoh, ovoz).

        ⚠️ ROZILIK HAM SHART (D2-T10): shartlarni qabul qilmagan odam
           kontent yoza olmasligi kerak. O'QISH esa ochiq qoladi —
           saytni ko'rish uchun hech narsa talab qilinmaydi.
        """
        return self.is_active and not self.is_currently_banned and self.rozilik_bormi


# ===========================================================================
# Ma'lumot eksporti (D2-T8)
# ===========================================================================
class EksportHolati(models.TextChoices):
    NAVBATDA = "navbatda", "Tayyorlanmoqda"
    TAYYOR = "tayyor", "Tayyor"
    XATO = "xato", "Xato"


class MalumotEksporti(models.Model):
    """Foydalanuvchining o'z ma'lumotlari nusxasi (JSON).

    ⚠️ NEGA FON VAZIFASIDA (task tavsifi shuni talab qiladi)
       Faol foydalanuvchida yuzlab post, yechim va ovoz bo'lishi mumkin.
       So'rov ichida yig'ilsa sahifa o'nlab soniya osilib turardi va
       gunicorn ishchisi band bo'lardi.

    ⚠️ NEGA EMAIL EMAS (boshqa loyihalarda odatiy yo'l)
       Bu yerda kirish FAQAT Telegram orqali va foydalanuvchida email
       YO'Q. Xat yuborish yo'li umuman mavjud emas, shuning uchun
       natija saqlanadi va foydalanuvchi uni o'zi yuklab oladi.

    ⚠️ EKSPORT MUDDATLI. Ichida shaxsiy ma'lumot bor va u bazada
       cheksiz turishi kerak emas — `muddat` dan keyin fon vazifasi
       o'chiradi (`tasks.eskirgan_eksportlarni_ochirish`).
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="foydalanuvchi",
        on_delete=models.CASCADE,
        related_name="eksportlar",
    )
    holat = models.CharField(
        "holat",
        max_length=16,
        choices=EksportHolati.choices,
        default=EksportHolati.NAVBATDA,
    )
    malumot = models.JSONField("ma'lumot", null=True, blank=True, editable=False)
    xato = models.TextField("xato", blank=True, editable=False)

    created_at = models.DateTimeField("so'ralgan", auto_now_add=True, db_index=True)
    tayyor_at = models.DateTimeField("tayyor bo'lgan", null=True, blank=True)
    muddat = models.DateTimeField("amal qilish muddati", db_index=True)

    class Meta:
        verbose_name = "ma'lumot eksporti"
        verbose_name_plural = "ma'lumot eksportlari"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.user_id} eksporti ({self.holat})"

    @property
    def yuklab_olsa_boladimi(self) -> bool:
        return self.holat == EksportHolati.TAYYOR and self.muddat > timezone.now()


# ===========================================================================
# Foydalanuvchilar o'zaro bloklashi (D2-T11)
# ===========================================================================
class UserBlock(models.Model):
    """Bir foydalanuvchi ikkinchisini ko'rmaslikni tanlagan.

    ⚠️ MODERATOR BLOKIDAN BUTUNLAY BOSHQA NARSA.
       `User.is_banned` — platformaning qarori: odam YOZA olmaydi.
       `UserBlock` — foydalanuvchining o'z qarori: u boshqa odamning
       kontentini KO'RMAYDI. Bloklangan odam bundan xabardor emas va
       hech qanday cheklov olmaydi.

    ⚠️ BIR TOMONLAMA. A B ni bloklasa, B A ni ko'raverali. Ikki
       tomonlama qilish "meni bloklashdi" degan signalni beradi va
       bu tortishuvni kuchaytiradi — bloklashdan maqsad esa aksincha.

    ⚠️ Bu MUAMMOLARNI YO'QOTMAYDI: bloklangan odamning posti lentadan
       chiqadi, lekin muhokamada uning javobi bo'lgan post baribir
       ko'rinadi (javobning o'zi yashiriladi). To'liq "yo'q qilish"
       muhokamani tushunarsiz qilardi.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="kim bloklagan",
        on_delete=models.CASCADE,
        related_name="bloklaganlari",
    )
    blocked = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="kim bloklangan",
        on_delete=models.CASCADE,
        related_name="bloklanganlari",
    )
    created_at = models.DateTimeField("bloklangan vaqt", auto_now_add=True)

    class Meta:
        verbose_name = "foydalanuvchi bloki"
        verbose_name_plural = "foydalanuvchi bloklari"
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["user", "blocked"],
                name="userblock_uniq",
                violation_error_message="Bu foydalanuvchi allaqachon bloklangan.",
            ),
            # ⚠️ O'zini bloklash — mantiqsiz va interfeysda tushunarsiz
            #    holat yaratardi (o'z postlari lentadan yo'qolardi).
            models.CheckConstraint(
                condition=~models.Q(user=models.F("blocked")),
                name="userblock_ozini_bloklamaydi",
                violation_error_message="O'zingizni bloklay olmaysiz.",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} -> {self.blocked_id}"
