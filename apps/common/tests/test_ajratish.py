"""Qidiruv natijasini ajratib ko'rsatish (D4-T3).

⚠️ Bu modul HTML qaytaradi — ya'ni u loyihadagi XSS uchun eng jozibali
   joy. Ekranlash testlari shu sababli birinchi bo'limda.
"""

from __future__ import annotations

import pytest

from apps.common.ajratish import (
    SOZ_NAQSHI,
    ajratib_korsat,
    qidiruv_sozlari,
)
from apps.common.matn import qidiruv_uchun


# ===========================================================================
# 1. ⚠️ Ekranlash — eng muhim bo'lim
# ===========================================================================
def test_HTML_ekranlanadi():
    """⚠️ Matn foydalanuvchi yozgan. Ajratish funksiyasi HTML qaytargani
    uchun bu yerda unutilgan `escape()` to'g'ridan-to'g'ri XSS."""
    natija = ajratib_korsat("<script>alert(1)</script>", qidiruv_sozlari("alert"))

    assert "<script>" not in natija
    assert "&lt;script&gt;" in natija


def test_MOSLIKNING_OZI_ham_ekranlanadi():
    """⚠️ Nozikroq holat: ajratilayotgan so'zning O'ZI zararli matn
    ichida bo'lsa. `<mark>` ichiga xom matn qo'yish oson unutiladi.

    ⚠️ Kutilgan natija: `&lt;<mark>img</mark> src=x …&gt;` — burchak
       qavslar `<` va `>` teg tashqarisida ekranlanadi, `img` esa
       ajratiladi. Ya'ni HECH BIR haqiqiy teg hosil bo'lmaydi.
    """
    natija = ajratib_korsat("<img src=x onerror=alert(1)>", qidiruv_sozlari("img"))

    assert "<img" not in natija
    assert "&lt;" in natija and "&gt;" in natija
    assert "<mark>img</mark>" in natija
    # Javobda `<mark>` dan boshqa teg BO'LMASIN.
    assert natija.replace("<mark>", "").replace("</mark>", "").count("<") == 0


def test_faqat_mark_tegi_qoshiladi():
    natija = ajratib_korsat("Ipoteka olish", qidiruv_sozlari("ipoteka"))

    assert natija == "<mark>Ipoteka</mark> olish"


# ===========================================================================
# 2. Mosliklar
# ===========================================================================
def test_moslik_YOQ_bolsa_matn_ozgarmaydi():
    natija = ajratib_korsat("Ipoteka olish", qidiruv_sozlari("velosiped"))

    assert natija == "Ipoteka olish"


def test_bir_nechta_soz_ajratiladi():
    natija = ajratib_korsat("Ipoteka va bank krediti", qidiruv_sozlari("ipoteka bank"))

    assert natija == "<mark>Ipoteka</mark> va <mark>bank</mark> krediti"


def test_KIRILCHA_matn_LOTINCHA_sorov_bilan_ajratiladi():
    """⚠️⚠️ Aynan shu holat `SearchHeadline` da ISHLAMASDI: so'rov
    normallashtirilgan, matn esa xom — Postgres hech narsa topmasdi."""
    natija = ajratib_korsat("Ипотека олиш", qidiruv_sozlari("ipoteka"))

    assert natija == "<mark>Ипотека</mark> олиш"


def test_ASL_shakl_saqlanadi_normal_shakl_EMAS():
    """⚠️ Ekranda foydalanuvchi YOZGAN matn turishi kerak. Normal
    ustundan olingan headline "ipoteka" deb ko'rsatardi — bosh harfsiz
    va apostrofsiz."""
    natija = ajratib_korsat("KO'CHMAS mulk", qidiruv_sozlari("kochmas"))

    assert "KO&#x27;CHMAS" in natija


@pytest.mark.parametrize(
    "sorov", ["ko'chmas", "koʻchmas", "ko‘chmas", "kochmas", "кўчмас"]
)
def test_apostrof_variantlari_bilan_ham_ajratiladi(sorov):
    natija = ajratib_korsat("Ko'chmas mulk", qidiruv_sozlari(sorov))

    assert "<mark>" in natija


def test_apostrof_SOZ_BELGISI_ajratuvchi_EMAS():
    """⚠️ Aks holda "ko'chmas" ikkita so'zga bo'linardi va ularning
    hech biri "kochmas" ga mos kelmasdi — D4-T2 da qilingan ish
    ekranda yo'qolardi."""
    sozlar = [m.group() for m in SOZ_NAQSHI.finditer("ko'chmas mulk")]

    assert sozlar == ["ko'chmas", "mulk"]


def test_QISMAN_soz_ajratilmaydi():
    """⚠️ "ipo" so'rovi "ipoteka" ni ajratmaydi — bu to'g'ri xulq:
    `simple` konfiguratsiyasi ham to'liq lexema bo'yicha ishlaydi va
    natijada ham "ipo" hech narsa topmaydi. Ajratish qidiruv bilan
    IZCHIL bo'lishi kerak, undan "saxiyroq" emas."""
    natija = ajratib_korsat("Ipoteka olish", qidiruv_sozlari("ipo"))

    assert "<mark>" not in natija


# ===========================================================================
# 3. ⚠️ Asosiy faraz: so'z bo'yicha normallashtirish = butun matnniki
# ===========================================================================
@pytest.mark.parametrize(
    "matn",
    [
        "Европа bo'yicha savol",
        "берди javob",
        "цирк va абзац",
        "ЎЗБЕКИСТОН ғalaba маъно",
        "Ipoteka olish qiyinmi",
    ],
)
def test_SOZ_boyicha_normallashtirish_BUTUN_MATNNIKI_bilan_bir_xil(matn):
    """⚠️⚠️ Ajratish shu farazga QURILGAN: har so'z alohida
    normallashtiriladi va indeksdagi (butun matndan olingan) shakl bilan
    solishtiriladi.

    Faraz buzilsa ajratish jimgina to'xtaydi: natija ro'yxatda turadi,
    lekin nega mos kelgani ko'rinmaydi. `qidiruv_uchun()` ga
    kontekstga bog'liq YANGI qoida qo'shilsa (masalan "so'z oxirida")
    bu test darhol yiqiladi.
    """
    butun = qidiruv_uchun(matn).split()
    alohida = [qidiruv_uchun(m.group()) for m in SOZ_NAQSHI.finditer(matn)]

    assert butun == alohida


# ===========================================================================
# 4. Parcha (oyna)
# ===========================================================================
def test_UZUN_matndan_moslik_ATROFIDAGI_parcha_olinadi():
    matn = "bosh " * 60 + "IPOTEKA " + "oxir " * 60

    natija = ajratib_korsat(matn, qidiruv_sozlari("ipoteka"), oyna=120)

    assert "<mark>IPOTEKA</mark>" in natija
    assert natija.startswith("…")
    assert natija.endswith("…")
    assert len(natija) < len(matn)


def test_moslik_YOQ_bolsa_parcha_BOSHIDAN_olinadi():
    matn = "bir ikki uch tort besh olti yetti sakkiz toqqiz on " * 10

    natija = ajratib_korsat(matn, qidiruv_sozlari("velosiped"), oyna=60)

    assert natija.startswith("bir ikki")
    assert natija.endswith("…")


def test_QISQA_matn_kesilmaydi():
    natija = ajratib_korsat("Ipoteka olish", qidiruv_sozlari("ipoteka"), oyna=200)

    assert "…" not in natija


def test_bosh_matn_yiqilmaydi():
    assert ajratib_korsat("", qidiruv_sozlari("ipoteka")) == ""
    assert ajratib_korsat("Matn", frozenset()) == "Matn"


# ===========================================================================
# 5. So'rovni so'zlarga ajratish
# ===========================================================================
def test_sorov_sozlari_normallashtiriladi():
    assert qidiruv_sozlari("IPOTEKA Krediti") == {"ipoteka", "krediti"}


def test_websearch_sintaksisi_sozga_YOPISHMAYDI():
    """⚠️ So'rov AVVAL normallashtiriladi, KEYIN bo'linadi. Teskarisida
    `"ipoteka` (qo'shtirnoq bilan) hech narsaga mos kelmasdi va
    qo'shtirnoqli qidiruvda ajratish butunlay yo'qolardi."""
    assert qidiruv_sozlari('"ipoteka krediti"') == {"ipoteka", "krediti"}
    assert qidiruv_sozlari("ipoteka -bank") == {"ipoteka", "bank"}


def test_bosh_sorov_bosh_toplam():
    assert qidiruv_sozlari("") == frozenset()
    assert qidiruv_sozlari("   ") == frozenset()
