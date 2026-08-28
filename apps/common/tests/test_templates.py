"""Shablonlar bo'yicha guard testlar (D0-T6).

Bu testlar dizaynni tekshirmaydi — ular TAKRORLANADIGAN XATOLARNI ushlaydi.
Har biri bir marta haqiqatan yuz bergan muammoni qotiradi.
"""

import re
from pathlib import Path

from django.conf import settings
from django.contrib.messages import constants as message_constants
from django.contrib.messages.storage.base import Message
from django.template.loader import render_to_string
from django.test import (
    Client,
    RequestFactory,
    SimpleTestCase,
    TestCase,
    override_settings,
)

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
class SahifaRenderTests(TestCase):
    """Har bir sahifa render bo'lishi kerak.

    ⚠️ `SimpleTestCase` DAN `TestCase` GA O'TDI (D1-T7).
       Ilgari barcha sahifalar maketning statik ko'rinishlari edi va
       bazaga tegmasdi. `/` haqiqiy lentaga aylanishi bilan ular
       `RuntimeError: Database access not allowed` bera boshladi —
       xato ko'rinishi chalg'ituvchi, chunki sabab BOSHQA faylda
       (apps/complaints/views.py) edi.

       Testlarning MA'NOSI o'zgarmadi va ular endi haqiqiy sahifani ham
       qamrab oladi: nonce, bitta h1, skip-link, shablon sintaksisi
       sizib chiqmasligi. Aynan shu qiymat uchun ular o'chirilmadi.
    """

    @classmethod
    def setUpTestData(cls):
        """⚠️ D1-T9/T10 dan keyin bu testlar HAQIQIY ma'lumot talab qiladi.

        Ilgari barcha yo'llar maketning statik sahifalari edi. Endi
        `/dard/<slug>/` mavjud postni, `/yozish/` esa kirgan
        foydalanuvchini talab qiladi. Testlar o'chirilmadi — aksincha,
        ular endi haqiqiy sahifalarni ham qoplaydi (nonce, bitta h1,
        skip-link, shablon sintaksisi sizib chiqmasligi).
        """
        from apps.accounts.factories import TelegramUserFactory
        from apps.complaints.factories import ComplaintFactory

        cls.muammo = ComplaintFactory()
        cls.chetdan = TelegramUserFactory()

    def yollar(self):
        return [
            "/",
            "/tanishuv/",
            "/yozish/",
            "/kategoriyalar/",
            "/ekspertlar/",
            "/kirish/",
            f"/dard/{self.muammo.slug}/",
            "/@sardor92/",
        ]

    def yol_mijozi(self, yol: str) -> Client:
        """⚠️ `/kirish/` KIRGAN foydalanuvchini lentaga yo'naltiradi (302).

        D1-T1 dan keyin u haqiqiy ko'rinish: kirgan odamga kirish
        sahifasini ko'rsatish ma'nosiz. Shuning uchun uni MEHMON
        sifatida ochamiz, qolganini esa kirgan foydalanuvchi sifatida.
        """
        return Client() if yol == "/kirish/" else self.mijoz()

    def mijoz(self) -> Client:
        """Kirgan foydalanuvchi — `/yozish/` login talab qiladi.

        ⚠️ Post MUALLIFI sifatida EMAS, chetdan kelgan foydalanuvchi
           sifatida: shunda sahifa ko'pchilik ko'radigan holatda bo'ladi
           (tahrirlash va qabul qilish tugmalari chiqmaydi). Muallif
           ko'rinishini D1-T9/T10 testlari alohida qoplaydi.
        """
        c = Client()
        c.force_login(self.chetdan)
        return c

    def test_barcha_sahifalar_200_qaytaradi(self):
        for yol in self.yollar():
            c = self.yol_mijozi(yol)
            with self.subTest(yol=yol):
                self.assertEqual(c.get(yol).status_code, 200)

    def test_shablon_sintaksisi_HTML_ga_sizib_chiqmaydi(self):
        """⚠️ Ko'p qatorli izoh noto'g'ri yopilsa, xom `{% ... %}`
        foydalanuvchiga KO'RINADI. Bu jim sodir bo'ladi — sahifa
        200 qaytaradi, lekin ichida kod matni turadi."""
        for yol in self.yollar():
            c = self.yol_mijozi(yol)
            with self.subTest(yol=yol):
                matn = c.get(yol).content.decode()
                self.assertNotIn("{%", matn)
                self.assertNotIn("{{", matn)

    def test_inline_skriptlarda_nonce_bor(self):
        """D2-T9 da CSP yoqilganda nonce'siz skript bloklanadi.

        Mavzu skripti bloklansa sahifa har yuklanishda oq bo'lib
        "chaqnaydi" — buni keyin topish qiyin.
        """
        c = self.mijoz()
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
        c = self.mijoz()
        n1 = re.search(r'nonce="([^"]+)"', c.get("/").content.decode()).group(1)
        n2 = re.search(r'nonce="([^"]+)"', c.get("/").content.decode()).group(1)
        self.assertNotEqual(n1, n2)

    def test_har_sahifada_bitta_h1(self):
        """SEO va ekran o'quvchilar uchun (heading-hierarchy)."""
        for yol in self.yollar():
            c = self.yol_mijozi(yol)
            with self.subTest(yol=yol):
                matn = c.get(yol).content.decode()
                self.assertEqual(matn.count("<h1"), 1)

    def test_skip_link_har_sahifada(self):
        """Klaviatura foydalanuvchilari navigatsiyani o'tkazib yubora olsin."""
        for yol in self.yollar():
            c = self.yol_mijozi(yol)
            with self.subTest(yol=yol):
                self.assertIn('class="skip-link"', c.get(yol).content.decode())


class XabarlarTests(TestCase):
    """⚠️ D2-T1 DA TOPILGAN XATO — `messages` HECH QACHON KO'RSATILMAGAN.

    D1-T9 dan beri kodda 6 ta `messages.success(...)` chaqiruvi bor edi
    ("Dardingiz e'lon qilindi", "Yechim qabul qilindi", ...), lekin
    `base.html` da ularni chiqaradigan blok YO'Q edi. Hammasi jimgina
    yo'qolardi: foydalanuvchi hech qanday tasdiq ko'rmasdi.

    ⚠️ NEGA UZOQ VAQT KO'RINMADI — sabab takrorlanuvchan:
       `INSTALLED_APPS`, middleware va `messages` kontekst-protsessori
       BOSHIDANOQ to'g'ri sozlangan edi. `messages.success()` xatosiz
       ishlaydi, `response.context["messages"]` ham to'ladi. Yagona
       uzilgan halqa — HTML. Ya'ni "sozlama to'g'ri" degani "xususiyat
       ishlaydi" degani emas.

    Shuning uchun bu yerdagi testlar RENDER QILINGAN HTML ni tekshiradi.
    """

    def test_flash_xabar_HTML_ga_chiqadi(self):
        so_rov = RequestFactory().get("/")
        matn = render_to_string(
            "base.html",
            {"messages": [Message(message_constants.SUCCESS, "SINOVXABARIMATNI")]},
            request=so_rov,
        )

        self.assertIn(
            "SINOVXABARIMATNI",
            matn,
            "base.html `messages` ni ko'rsatmayapti — "
            "`components/_messages.html` include qilinganmi?",
        )

    def test_xabar_darajasi_MARKUPDA_ajratiladi(self):
        """Muvaffaqiyat va xato bir xil ko'rinmasin (rang + `data-message`)."""
        so_rov = RequestFactory().get("/")
        chiqishlar = {}
        for daraja, nom in (
            (message_constants.SUCCESS, "success"),
            (message_constants.ERROR, "error"),
        ):
            chiqishlar[nom] = render_to_string(
                "base.html",
                {"messages": [Message(daraja, "XABAR")]},
                request=so_rov,
            )
            self.assertIn(f'data-message="{nom}"', chiqishlar[nom])

        self.assertNotEqual(chiqishlar["success"], chiqishlar["error"])

    def test_xabar_ekran_oquvchiga_ELON_qilinadi(self):
        """`role="status"` — fokusni o'g'irlamasdan e'lon qiladi."""
        matn = render_to_string(
            "base.html",
            {"messages": [Message(message_constants.INFO, "XABAR")]},
            request=RequestFactory().get("/"),
        )
        self.assertIn('role="status"', matn)

    def test_xabarsiz_sahifada_BOSH_blok_qolmaydi(self):
        """Xabar yo'q bo'lsa markup ham bo'lmasin (bo'sh joy qoldirmasin)."""
        matn = render_to_string("base.html", {}, request=RequestFactory().get("/"))
        self.assertNotIn('role="status"', matn)
