"""Foydalanuvchilar — modellar.

⚠️ Bu fayl loyihaning eng qaytarib bo'lmaydigan qismi. `AUTH_USER_MODEL`
   birinchi migratsiyada belgilanadi; keyinroq almashtirish amalda bazani
   noldan qurishni talab qiladi.
"""

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone

from .validators import USERNAME_HELP, validate_username


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
        ]

    def __str__(self) -> str:
        return self.username

    # -- Ko'rsatiladigan nom ----------------------------------------------
    @property
    def display_name(self) -> str:
        """Interfeysda ko'rsatiladigan nom.

        Telegram `first_name` beradi, lekin u ixtiyoriy va takrorlanishi
        mumkin — shuning uchun zaxira sifatida `username` ishlatiladi.
        """
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
    def can_write(self) -> bool:
        """Kontent yarata oladimi (dard, yechim, izoh, ovoz)."""
        return self.is_active and not self.is_currently_banned
