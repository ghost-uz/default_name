"""Foydalanuvchi modeli invariantlari.

Bu testlar D0-T7 da pytest'ga o'tkaziladi, lekin qoidalar HOZIR qotirilishi
kerak — ular xavfsizlik va'dalari, qulaylik emas.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from .validators import validate_username

User = get_user_model()


class UsernameValidatorTests(TestCase):
    def test_shakl_qoidalari(self):
        for yaroqli in ["sardor", "Sardor_92", "a1b", "x" * 30]:
            with self.subTest(username=yaroqli):
                validate_username(yaroqli)  # xato ko'tarmasligi kerak

        for yaroqsiz in [
            "ab",  # juda qisqa
            "x" * 31,  # juda uzun
            "1sardor",  # raqam bilan boshlanadi
            "_sardor",  # pastki chiziq bilan boshlanadi
            "sardor-92",  # tire
            "sardor.92",  # nuqta
            "sardor 92",  # bo'sh joy
            "sardor@uz",  # @
        ]:
            with self.subTest(username=yaroqsiz):
                with self.assertRaises(ValidationError):
                    validate_username(yaroqsiz)

    def test_band_nomlar_rad_etiladi(self):
        for band in ["admin", "kirish", "ekspertlar", "moderator"]:
            with self.subTest(username=band):
                with self.assertRaises(ValidationError):
                    validate_username(band)

    def test_anonim_nomi_band(self):
        """⚠️ Taqlidga qarshi: 'Anonim' nomli hisob anonim postlar muallifi
        kabi ko'rinadi va anonimlik va'dasini buzadi (reja 14-bo'lim)."""
        for variant in ["anonim", "Anonim", "ANONIM", "anonymous"]:
            with self.subTest(username=variant):
                with self.assertRaises(ValidationError):
                    validate_username(variant)


class UsernameUniqueTests(TestCase):
    def test_registrga_sezgir_bolmagan_noyoblik(self):
        """⚠️ 'Sardor' va 'sardor' bir vaqtda mavjud bo'la OLMAYDI.

        Django'ning `unique=True` PostgreSQL'da registrga sezgir — bu
        cheklovsiz taqlid qilish mumkin bo'lardi. Kafolat DB darajasida
        (UniqueConstraint + Lower) beriladi, forma validatsiyasida emas:
        forma poyga holatidan himoya qilmaydi.
        """
        User.objects.create_user(username="Sardor", password="x")

        for taqlid in ["sardor", "SARDOR", "SaRdOr"]:
            with self.subTest(username=taqlid):
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        User.objects.create_user(username=taqlid, password="x")


class TelegramIdTests(TestCase):
    def test_bir_nechta_null_ruxsat(self):
        """Telegram'siz staff hisoblari bo'lishi mumkin.

        PostgreSQL unique indeksida bir nechta NULL ga ruxsat beriladi —
        aynan shu xulq kerak.
        """
        User.objects.create_user(username="staff_bir", password="x")
        User.objects.create_user(username="staff_ikki", password="x")
        self.assertEqual(User.objects.filter(telegram_id__isnull=True).count(), 2)

    def test_takroriy_telegram_id_rad_etiladi(self):
        User.objects.create_user(username="birinchi", password="x", telegram_id=12345)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                User.objects.create_user(
                    username="ikkinchi", password="x", telegram_id=12345
                )

    def test_katta_telegram_id(self):
        """Telegram ID 32-bitdan oshadi — BigInteger kerak."""
        katta = 8_000_000_000
        u = User.objects.create_user(username="katta", password="x", telegram_id=katta)
        u.refresh_from_db()
        self.assertEqual(u.telegram_id, katta)


class BanTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testchi", password="x")

    def test_standart_holatda_yoza_oladi(self):
        self.assertFalse(self.user.is_currently_banned)
        self.assertTrue(self.user.can_write)

    def test_doimiy_blok(self):
        self.user.is_banned = True
        self.user.banned_until = None
        self.assertTrue(self.user.is_currently_banned)
        self.assertFalse(self.user.can_write)

    def test_vaqtinchalik_blok_kuchda(self):
        self.user.is_banned = True
        self.user.banned_until = timezone.now() + timedelta(days=3)
        self.assertTrue(self.user.is_currently_banned)

    def test_muddati_otgan_blok_kuchda_emas(self):
        """Bayroq hali True bo'lsa ham, muddat o'tgan bo'lsa blok yo'q.

        Bayroqni fon vazifasi tozalaydi — tekshiruv har doim
        `is_currently_banned` orqali qilinishi kerak.
        """
        self.user.is_banned = True
        self.user.banned_until = timezone.now() - timedelta(minutes=1)
        self.assertFalse(self.user.is_currently_banned)
        self.assertTrue(self.user.can_write)

    def test_bloklangan_oqiy_oladi_lekin_yoza_olmaydi(self):
        """is_active va is_banned ATAYLAB alohida."""
        self.user.is_banned = True
        self.assertTrue(self.user.is_active)  # kira oladi -> o'qiy oladi
        self.assertFalse(self.user.can_write)  # lekin yoza olmaydi

    def test_ochirilgan_hisob_yoza_olmaydi(self):
        self.user.is_active = False
        self.assertFalse(self.user.can_write)


class DisplayNameTests(TestCase):
    def test_first_name_ustun(self):
        u = User.objects.create_user(
            username="sardor92", password="x", first_name="Sardor"
        )
        self.assertEqual(u.display_name, "Sardor")
        self.assertEqual(u.initial, "S")

    def test_first_name_bosh_bolsa_username(self):
        u = User.objects.create_user(username="sardor92", password="x")
        self.assertEqual(u.display_name, "sardor92")
        self.assertEqual(u.initial, "S")

    def test_faqat_boshliqdan_iborat_first_name(self):
        """Telegram bo'sh joylardan iborat ism qaytarishi mumkin."""
        u = User.objects.create_user(
            username="sardor92", password="x", first_name="   "
        )
        self.assertEqual(u.display_name, "sardor92")


class KarmaTests(TestCase):
    def test_standart_nol(self):
        u = User.objects.create_user(username="yangi", password="x")
        self.assertEqual(u.karma_cached, 0)

    def test_manfiy_karma_ruxsat(self):
        """Downvote karmani manfiyga tushirishi mumkin — cheklov yo'q."""
        u = User.objects.create_user(username="manfiy", password="x", karma_cached=-50)
        u.refresh_from_db()
        self.assertEqual(u.karma_cached, -50)
