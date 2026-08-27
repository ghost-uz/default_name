"""Shablonlar bo'yicha guard testlar (D0-T6).

Bu testlar dizaynni tekshirmaydi — ular TAKRORLANADIGAN XATOLARNI ushlaydi.
Har biri bir marta haqiqatan yuz bergan muammoni qotiradi.
"""

import re
from pathlib import Path

from django.conf import settings
from django.test import Client, SimpleTestCase, override_settings

TEMPLATES_DIR = Path(settings.BASE_DIR) / "templates"
HTML_IZOH = re.compile(r"<!--(.*?)-->", re.DOTALL)


class ShablonSintaksisTests(SimpleTestCase):
    def test_HTML_izohlari_ichida_shablon_tegi_YOQ(self):
        """⚠️ Django HTML izohini KO'RMAYDI.

        `<!-- Django: {% url 'vote' c.pk %} -->` ko'rinishidagi
        hujjatlashtirish izohi baribir bajariladi va NoReverseMatch beradi.
        Yopilmagan `{% if %}` esa butun sahifani buzadi.

        To'g'ri yo'l: `{% comment %}` — u ichidagini TAHLIL QILMAYDI.
        """
        buzuqlar = []
        for yol in sorted(TEMPLATES_DIR.rglob("*.html")):
            matn = yol.read_text(encoding="utf-8")
            for m in HTML_IZOH.finditer(matn):
                ichi = m.group(1)
                if "{%" in ichi or "{{" in ichi:
                    qator = matn[: m.start()].count("\n") + 1
                    buzuqlar.append(f"{yol.relative_to(TEMPLATES_DIR)}:{qator}")

        self.assertEqual(
            buzuqlar,
            [],
            "HTML izohi ichida shablon sintaksisi topildi. "
            "`{% comment %}` ishlating:\n  " + "\n  ".join(buzuqlar),
        )

    def test_maket_nisbiy_havolalari_qolmagan(self):
        """Maketdagi `href="index.html"` kabi havolalar `{% url %}` ga
        aylantirilgan bo'lishi kerak — aks holda 404 beradi."""
        qolgan = []
        namuna = re.compile(r'href="(?!http|#|mailto|\{)[a-z_]+\.html"')
        for yol in sorted(TEMPLATES_DIR.rglob("*.html")):
            matn = yol.read_text(encoding="utf-8")
            for m in namuna.finditer(matn):
                qator = matn[: m.start()].count("\n") + 1
                qolgan.append(f"{yol.relative_to(TEMPLATES_DIR)}:{qator} {m.group(0)}")
        self.assertEqual(
            qolgan, [], "Maket havolalari qolgan:\n  " + "\n  ".join(qolgan)
        )


@override_settings(ALLOWED_HOSTS=["testserver"])
class SahifaRenderTests(SimpleTestCase):
    """Har bir sahifa render bo'lishi kerak.

    Bu testlar ma'lumotlar bazasiga tegmaydi (SimpleTestCase) — maket
    ko'rinishlari statik. M1 da ular haqiqiy ko'rinishlar bilan
    almashtirilganda testlar TransactionTestCase ga o'tadi.
    """

    YOLLAR = [
        "/",
        "/tanishuv/",
        "/yozish/",
        "/kategoriyalar/",
        "/ekspertlar/",
        "/kirish/",
        "/dard/namuna/",
        "/@sardor92/",
    ]

    def test_barcha_sahifalar_200_qaytaradi(self):
        c = Client()
        for yol in self.YOLLAR:
            with self.subTest(yol=yol):
                self.assertEqual(c.get(yol).status_code, 200)

    def test_shablon_sintaksisi_HTML_ga_sizib_chiqmaydi(self):
        """⚠️ Ko'p qatorli izoh noto'g'ri yopilsa, xom `{% ... %}`
        foydalanuvchiga KO'RINADI. Bu jim sodir bo'ladi — sahifa
        200 qaytaradi, lekin ichida kod matni turadi."""
        c = Client()
        for yol in self.YOLLAR:
            with self.subTest(yol=yol):
                matn = c.get(yol).content.decode()
                self.assertNotIn("{%", matn)
                self.assertNotIn("{{", matn)

    def test_inline_skriptlarda_nonce_bor(self):
        """D2-T9 da CSP yoqilganda nonce'siz skript bloklanadi.

        Mavzu skripti bloklansa sahifa har yuklanishda oq bo'lib
        "chaqnaydi" — buni keyin topish qiyin.
        """
        c = Client()
        matn = c.get("/").content.decode()
        # <script> teglari (src'siz, ya'ni inline) nonce bilan bo'lsin
        inline = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>", matn)
        self.assertTrue(
            inline, "Inline skript topilmadi — test eskirgan bo'lishi mumkin"
        )
        for teg in inline:
            self.assertIn("nonce=", teg, f"nonce yo'q: {teg}")

    def test_nonce_har_sorovda_YANGI(self):
        """Takrorlanuvchi nonce CSP'ni ma'nosiz qiladi."""
        c = Client()
        n1 = re.search(r'nonce="([^"]+)"', c.get("/").content.decode()).group(1)
        n2 = re.search(r'nonce="([^"]+)"', c.get("/").content.decode()).group(1)
        self.assertNotEqual(n1, n2)

    def test_har_sahifada_bitta_h1(self):
        """SEO va ekran o'quvchilar uchun (heading-hierarchy)."""
        c = Client()
        for yol in self.YOLLAR:
            with self.subTest(yol=yol):
                matn = c.get(yol).content.decode()
                self.assertEqual(matn.count("<h1"), 1)

    def test_skip_link_har_sahifada(self):
        """Klaviatura foydalanuvchilari navigatsiyani o'tkazib yubora olsin."""
        c = Client()
        for yol in self.YOLLAR:
            with self.subTest(yol=yol):
                self.assertIn('class="skip-link"', c.get(yol).content.decode())
