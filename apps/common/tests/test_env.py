"""Muhit konfiguratsiyasi (D0-T4) testlari.

`.env` tahlilchisi o'z qo'limiz bilan yozilgan — demak uning chekka holatlari
ham o'z zimmamizda. Bu testlar aynan shu holatlarni qotiradi.
"""

import os
import tempfile
from pathlib import Path
from unittest import mock

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from config.settings.env import (
    database_from_url,
    env,
    env_bool,
    env_int,
    env_list,
    load_dotenv,
)


def _env_fayl(matn: str, *, encoding: str = "utf-8") -> Path:
    fayl = Path(tempfile.mkdtemp()) / ".env"
    fayl.write_text(matn, encoding=encoding)
    return fayl


class LoadDotenvTests(SimpleTestCase):
    def test_oddiy_kalitlar(self):
        fayl = _env_fayl("BIR=1\nIKKI=salom\n")
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(load_dotenv(fayl), 2)
            self.assertEqual(os.environ["BIR"], "1")
            self.assertEqual(os.environ["IKKI"], "salom")

    def test_fayl_yoq_bolsa_jim_otadi(self):
        """Docker'da .env kerak emas — qiymatlarni compose beradi."""
        self.assertEqual(load_dotenv("/mavjud/bolmagan/.env"), 0)

    def test_haqiqiy_muhit_ozgaruvchisi_USTUN(self):
        """⚠️ Eng muhim qoida.

        Obrazga xato bilan tushib qolgan eski .env prod bazasini
        almashtirib yubormasligi kerak.
        """
        fayl = _env_fayl("POSTGRES_HOST=eski-dev-baza\n")
        with mock.patch.dict(os.environ, {"POSTGRES_HOST": "prod-baza"}, clear=True):
            load_dotenv(fayl)
            self.assertEqual(os.environ["POSTGRES_HOST"], "prod-baza")

    def test_override_bilan_ustidan_yozadi(self):
        fayl = _env_fayl("A=fayldan\n")
        with mock.patch.dict(os.environ, {"A": "muhitdan"}, clear=True):
            load_dotenv(fayl, override=True)
            self.assertEqual(os.environ["A"], "fayldan")

    def test_izoh_va_bosh_qatorlar(self):
        fayl = _env_fayl("# izoh\n\n   \nA=1\n# yana izoh\nB=2\n")
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(load_dotenv(fayl), 2)

    def test_export_prefiksi(self):
        """Ba'zi qo'llanmalar `export KEY=value` ko'rinishida yozadi."""
        fayl = _env_fayl("export A=1\nexport  B=2\n")
        with mock.patch.dict(os.environ, {}, clear=True):
            load_dotenv(fayl)
            self.assertEqual(os.environ["A"], "1")
            self.assertEqual(os.environ["B"], "2")

    def test_qoshtirnoqlar(self):
        fayl = _env_fayl(
            "A=\"bo'sh joy bor\"\nB='bitta qoshtirnoq'\nC=\"qator\\nko'chdi\"\n"
        )
        with mock.patch.dict(os.environ, {}, clear=True):
            load_dotenv(fayl)
            self.assertEqual(os.environ["A"], "bo'sh joy bor")
            self.assertEqual(os.environ["B"], "bitta qoshtirnoq")
            self.assertEqual(os.environ["C"], "qator\nko'chdi")

    def test_bitta_qoshtirnoqda_kochirish_ishlamaydi(self):
        """Shell bilan bir xil xulq: '...' ichida \\n oddiy matn."""
        fayl = _env_fayl("A='matn\\nmatn'\n")
        with mock.patch.dict(os.environ, {}, clear=True):
            load_dotenv(fayl)
            self.assertEqual(os.environ["A"], "matn\\nmatn")

    def test_satr_ichidagi_izoh_kesiladi(self):
        fayl = _env_fayl("A=qiymat # bu izoh\n")
        with mock.patch.dict(os.environ, {}, clear=True):
            load_dotenv(fayl)
            self.assertEqual(os.environ["A"], "qiymat")

    def test_parolda_panjara_saqlanadi(self):
        """⚠️ Izoh kesish uchun oldida BO'SH JOY shart.

        Aks holda `parol#123` paroli `parol` ga aylanib qolardi va
        ulanish xatosining sababi ko'rinmasdi.
        """
        fayl = _env_fayl("POSTGRES_PASSWORD=parol#123\n")
        with mock.patch.dict(os.environ, {}, clear=True):
            load_dotenv(fayl)
            self.assertEqual(os.environ["POSTGRES_PASSWORD"], "parol#123")

    def test_qoshtirnoq_ichidagi_panjara_saqlanadi(self):
        fayl = _env_fayl('A="parol # bilan"\n')
        with mock.patch.dict(os.environ, {}, clear=True):
            load_dotenv(fayl)
            self.assertEqual(os.environ["A"], "parol # bilan")

    def test_bosh_qiymat(self):
        fayl = _env_fayl("SENTRY_DSN=\n")
        with mock.patch.dict(os.environ, {}, clear=True):
            load_dotenv(fayl)
            self.assertEqual(os.environ["SENTRY_DSN"], "")

    def test_teng_belgisi_qiymat_ichida(self):
        """Base64 va DSN qiymatlarida `=` uchraydi."""
        fayl = _env_fayl("KEY=abc=def==\n")
        with mock.patch.dict(os.environ, {}, clear=True):
            load_dotenv(fayl)
            self.assertEqual(os.environ["KEY"], "abc=def==")

    def test_BOM_bilan_fayl(self):
        """⚠️ Windows muharrirlari fayl boshiga BOM qo'yadi.

        BOM birinchi kalit nomiga yopishib qoladi va o'zgaruvchi
        "yo'q"dek ko'rinadi — sababini topish qiyin.
        """
        fayl = _env_fayl("DJANGO_SECRET_KEY=abc\n", encoding="utf-8-sig")
        with mock.patch.dict(os.environ, {}, clear=True):
            load_dotenv(fayl)
            self.assertIn("DJANGO_SECRET_KEY", os.environ)

    def test_CRLF_qator_ohirlari(self):
        """⚠️ Windows'da yozilgan .env fayli CRLF bilan keladi."""
        fayl = _env_fayl("A=1\r\nB=2\r\n")
        with mock.patch.dict(os.environ, {}, clear=True):
            load_dotenv(fayl)
            self.assertEqual(os.environ["A"], "1")
            self.assertEqual(os.environ["B"], "2")

    def test_yaroqsiz_qator_otkaziladi(self):
        fayl = _env_fayl("bu tengsiz qator\nA=1\n")
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(load_dotenv(fayl), 1)


class EnvHelperTests(SimpleTestCase):
    def test_env_majburiy_bolsa_yiqiladi(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ImproperlyConfigured):
                env("YOQ_BUNDAY_KALIT")

    def test_env_bool_variantlari(self):
        for xom, kutilgan in [
            ("1", True),
            ("true", True),
            ("TRUE", True),
            ("yes", True),
            ("on", True),
            ("ha", True),
            ("0", False),
            ("false", False),
            ("yo'q", False),
            ("", False),
        ]:
            with self.subTest(qiymat=xom):
                with mock.patch.dict(os.environ, {"X": xom}, clear=True):
                    self.assertEqual(env_bool("X"), kutilgan)

    def test_env_bool_bosh_qiymat_standartga_tushmaydi(self):
        """⚠️ `X=` (bo'sh) True bo'lib qolmasligi kerak."""
        with mock.patch.dict(os.environ, {"X": ""}, clear=True):
            self.assertFalse(env_bool("X", default=False))

    def test_env_int_yaroqsiz_qiymat_aniq_xato_beradi(self):
        with mock.patch.dict(os.environ, {"PORT": "sakkiz"}, clear=True):
            with self.assertRaises(ImproperlyConfigured) as ctx:
                env_int("PORT", 8000)
            self.assertIn("PORT", str(ctx.exception))

    def test_env_int_bosh_qiymatda_standart(self):
        with mock.patch.dict(os.environ, {"PORT": ""}, clear=True):
            self.assertEqual(env_int("PORT", 8000), 8000)

    def test_env_list(self):
        with mock.patch.dict(os.environ, {"H": "a.uz, b.uz ,, c.uz"}, clear=True):
            self.assertEqual(env_list("H"), ["a.uz", "b.uz", "c.uz"])

    def test_env_list_bosh_bolsa_bosh_royxat(self):
        with mock.patch.dict(os.environ, {"H": ""}, clear=True):
            self.assertEqual(env_list("H"), [])


class DatabaseUrlTests(SimpleTestCase):
    def test_toliq_url(self):
        d = database_from_url(
            "postgres://foydalanuvchi:parol@db.example.com:5433/dardbaza"
        )
        self.assertEqual(d["NAME"], "dardbaza")
        self.assertEqual(d["USER"], "foydalanuvchi")
        self.assertEqual(d["PASSWORD"], "parol")
        self.assertEqual(d["HOST"], "db.example.com")
        self.assertEqual(d["PORT"], "5433")

    def test_port_berilmasa_5432(self):
        d = database_from_url("postgres://u:p@host/baza")
        self.assertEqual(d["PORT"], "5432")

    def test_postgresql_sxemasi_ham_ishlaydi(self):
        d = database_from_url("postgresql://u:p@host/baza")
        self.assertEqual(d["NAME"], "baza")

    def test_maxsus_belgili_parol_ochiladi(self):
        """⚠️ Parolda @ : / bo'lsa URL'da %40 %3A %2F ko'rinishida keladi.

        Ochilmasa ulanish "parol noto'g'ri" deb yiqiladi va sabab
        ko'rinmaydi.
        """
        d = database_from_url("postgres://u:p%40ss%3Aword@host/baza")
        self.assertEqual(d["PASSWORD"], "p@ss:word")

    def test_postgres_bolmagan_sxema_rad_etiladi(self):
        """Loyiha PostgreSQL'ga xos imkoniyatlarga tayanadi (M4: FTS)."""
        with self.assertRaises(ImproperlyConfigured):
            database_from_url("mysql://u:p@host/baza")
        with self.assertRaises(ImproperlyConfigured):
            database_from_url("sqlite:///baza.db")

    def test_baza_nomisiz_url_rad_etiladi(self):
        with self.assertRaises(ImproperlyConfigured):
            database_from_url("postgres://u:p@host/")
