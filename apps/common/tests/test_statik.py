"""`{% static_v %}` — kesh buzuvchi statik teg (D1-T8)."""

from __future__ import annotations

import re

from django.template import Context, Template
from django.test import SimpleTestCase, override_settings

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
class BaseShablonidaTests(SimpleTestCase):
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
