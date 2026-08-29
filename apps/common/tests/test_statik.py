"""`{% static_v %}` — kesh buzuvchi statik teg (D1-T8)."""

from __future__ import annotations

import re

from django.template import Context, Template
from django.test import SimpleTestCase, TestCase, override_settings

SHABLON = Template("{% load statik %}{% static_v 'js/app.js' %}")


def render() -> str:
    return SHABLON.render(Context({}))


class StaticVTests(SimpleTestCase):
    @override_settings(DEBUG=True)
    def test_DEBUG_da_versiya_qoshiladi(self):
        """⚠️ Bu tegning butun sababi: `runserver` statik faylga
        `Cache-Control` yubormaydi, brauzer esa sarlavhasiz EVRISTIK
        keshlaydi va tahrirlangan JS'ni QAYTA SO'RAMAYDI.

        Xato ko'rinishi chalg'ituvchi bo'ladi — kodda yangi mantiq
        turadi, brauzerda esa eski xulq. Manzil o'zgarsa kesh ham
        o'zgaradi.
        """
        manzil = render()
        self.assertTrue(manzil.startswith("/static/js/app.js?v="))
        self.assertRegex(manzil, r"\?v=\d+$")

    @override_settings(DEBUG=False)
    def test_PRODDA_hech_nima_QOSHILMAYDI(self):
        """Prodda fayllar hash bilan nomlanadi va nginx ularni
        `immutable, max-age=31536000` bilan beradi — qo'shimcha parametr
        faqat keshni buzardi."""
        self.assertEqual(render(), "/static/js/app.js")

    @override_settings(DEBUG=True)
    def test_versiya_fayl_VAQTIDAN_olinadi(self):
        """Tasodifiy son EMAS: aks holda har so'rovda yangi manzil
        bo'lardi va kesh butunlay ishlamasdi (dev'da ham sekin)."""
        birinchi = render()
        ikkinchi = render()
        self.assertEqual(birinchi, ikkinchi)

    @override_settings(DEBUG=True)
    def test_topilmagan_fayl_XATO_BERMAYDI(self):
        """Shablon tegi yo'q fayl uchun sahifani yiqitmasin — statik
        manzil baribir qaytadi va 404 brauzer konsolida ko'rinadi."""
        matn = Template("{% load statik %}{% static_v 'yoq/bunday.js' %}").render(
            Context({})
        )
        self.assertEqual(matn, "/static/yoq/bunday.js")


@override_settings(DEBUG=True)
class BaseShablonidaTests(TestCase):
    """⚠️ `SimpleTestCase` DAN `TestCase` GA O'TDI (D1-T1).

    `/kirish/` ilgari maketning statik sahifasi edi. Endi u haqiqiy
    ko'rinish: sessiyani o'qiydi va `request.user` ni yuklaydi, ya'ni
    BAZAGA TEGADI. Xato ko'rinishi chalg'ituvchi —
    `DatabaseOperationForbidden` statik fayllarga umuman aloqasi
    yo'qdek tuyuladi.
    """

    def test_barcha_statik_havolalar_versiyalangan(self):
        """⚠️ Bittasi unutilsa aynan o'sha fayl eski holicha keshlanadi —
        va u odatda eng ko'p tahrirlanadigan fayl bo'ladi.

        ⚠️ MAVJUD BO'LMAGAN FAYLLAR HISOBGA OLINMAYDI — bu testning
           birinchi versiyasi CI'da yiqilgan edi.

           `static/css/app.css` — Tailwind CHIQISHI va u `.gitignore` da
           (manba `tailwind/input.css`). Ya'ni toza checkout'da fayl
           YO'Q, `static_v` esa bunday holatda versiyasiz manzil
           qaytaradi — bu to'g'ri xulq (sahifa yiqilmasin).

           Ya'ni xato KODDA emas, TESTDA edi: u lokal muhit haqidagi
           taxminni ("hamma statik fayl mavjud") qotirib qo'ygan.
           Bunday testlar mahalliy mashinada doim yashil bo'ladi.
        """
        from django.contrib.staticfiles import finders
        from django.test import Client

        matn = Client().get("/kirish/").content.decode()
        havolalar = re.findall(r'(?:src|href)="/static/([^"?]+)', matn)
        self.assertTrue(havolalar, "Statik havola topilmadi — test eskirgan")

        mavjudlar = [h for h in havolalar if finders.find(h)]
        self.assertTrue(
            mavjudlar,
            "Tekshiriladigan mavjud statik fayl topilmadi — test ma'nosini "
            "yo'qotdi (masalan barcha fayllar qurilma chiqishiga aylangan)",
        )

        matnda = re.findall(r'(?:src|href)="(/static/[^"]+)"', matn)
        versiyasiz = [
            h for h in matnda if "?v=" not in h and finders.find(h[len("/static/") :])
        ]
        self.assertEqual(
            versiyasiz,
            [],
            f"`{{% static %}}` `{{% static_v %}}` ga almashtirilmagan: {versiyasiz}",
        )


# ===========================================================================
# Tailwind build'i shablonlardan ORQADA QOLMASIN (D2-T1 da topilgan)
# ===========================================================================
class TailwindBuildTests(SimpleTestCase):
    """⚠️ D2-T1 DA TOPILGAN XATO: yangi shablondagi sinf CSS'DA YO'Q EDI.

    Shikoyat formasi `space-y-5` bilan yozildi, lekin `npm run build`
    ishlatilmadi. Tailwind sinflarni SHABLONLARNI SKANER QILIB yaratadi
    — ya'ni qurilmagan sinf CSS'ga umuman tushmaydi.

    ⚠️ NEGA XAVFLI: hech narsa xato bermaydi. Sahifa ochiladi, HTML'da
       `class="space-y-5"` turadi, hamma test yashil — faqat oradagi
       bo'shliq yo'q. Brauzerda ham "biroz siqiq" bo'lib ko'rinadi,
       ya'ni ko'z bilan ham osongina o'tkazib yuboriladi. Bu yerda u
       `getBoundingClientRect()` bilan o'lchagandagina topildi.

    ⚠️ CHEKLOV (bilib qo'yilgan): bu test SHABLONDAGI sinflarni
       tekshiradi. `tailwind/input.css` tahrirlanib qurilmasa, eski
       `app.css` da komponent sinflari BOR bo'lgani uchun test o'tadi.
       U holat kamroq xavfli: stil yozayotgan odam natijani darhol
       ko'radi. To'liq kafolat — CI'da qayta qurib `git diff` qilish.
    """

    # `{% ... %}` / `{{ ... }}` olib tashlanadi: aks holda shablon
    # sintaksisi sinf nomi bo'lib ko'rinadi.
    SHABLON_SINTAKSISI = re.compile(r"\{%.*?%\}|\{\{.*?\}\}", re.DOTALL)
    CLASS_ATRIBUTI = re.compile(r'class="([^"]*)"')

    # Stil emas, HOOK bo'lgan sinflar — CSS'da bo'lishi SHART EMAS.
    HOOK_SINFLARI = {
        # HTMX nishoni: `hx-target="closest .yana-yuklash"`.
        "yana-yuklash",
    }

    # ⚠️ DINAMIK QO'SHIMCHA: `class="stagger-{{ index }}"` shablon
    #    sintaksisi olib tashlangach `stagger-` bo'lib qoladi. Bunday
    #    tokenni tekshirib bo'lmaydi — qiymat ish vaqtida ma'lum
    #    bo'ladi. Cheklov bilib qo'yilgan: dinamik sinflar bu guard
    #    qamrovidan tashqarida (ular `input.css` da qo'lda yoziladi).
    DINAMIK_QOSHIMCHALAR = ("-", ":", "/")

    def sinflar(self) -> set[str]:
        from pathlib import Path

        from django.conf import settings

        topilgan: set[str] = set()
        for yol in (Path(settings.BASE_DIR) / "templates").rglob("*.html"):
            matn = self.SHABLON_SINTAKSISI.sub(" ", yol.read_text(encoding="utf-8"))
            for m in self.CLASS_ATRIBUTI.finditer(matn):
                topilgan.update(m.group(1).split())
        return {
            s
            for s in topilgan - self.HOOK_SINFLARI
            if not s.endswith(self.DINAMIK_QOSHIMCHALAR)
        }

    @staticmethod
    def eskeyp(sinf: str) -> str:
        r"""Tailwind CSS selektorida maxsus belgilarni `\` bilan yozadi.

        `lg:grid-cols-[minmax(0,1fr)_300px]`
            -> `.lg\:grid-cols-\[minmax\(0\,1fr\)_300px\]`
        """
        return "".join(b if (b.isalnum() or b in "-_") else "\\" + b for b in sinf)

    def test_shablondagi_HAR_BIR_sinf_qurilgan_CSS_da_BOR(self):
        from pathlib import Path

        from django.conf import settings

        yol = Path(settings.BASE_DIR) / "static/css/app.css"
        self.assertTrue(
            yol.exists(),
            f"{yol} yo'q — `npm run build` ishlatilmagan. "
            "(CI'da bu qadam 'Tailwind CSS' nomi bilan turadi.)",
        )
        css = yol.read_text(encoding="utf-8")

        yoq = sorted(s for s in self.sinflar() if f".{self.eskeyp(s)}" not in css)

        self.assertEqual(
            yoq,
            [],
            "Bu sinflar shablonda ishlatilgan, lekin qurilgan CSS'da YO'Q — "
            "ya'ni ular HECH QANDAY ta'sir qilmaydi.\n"
            "`npm run build` ishlating.\n  " + "\n  ".join(yoq),
        )
