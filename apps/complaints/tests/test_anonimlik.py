"""⚠️ ANONIMLIK INVARIANTI (D1-T6).

Anonimlik — funksiya emas, VA'DA. Bir marta buzilsa (bitta shablon, bitta
JSON javob, bitta admin ro'yxati) foydalanuvchi ishonchi qaytmaydi.

Shuning uchun bu yerdagi testlar "ishlayaptimi?" degan savolga emas,
"buzib bo'ladimi?" degan savolga javob beradi. Ular qasddan qattiq:
yangi kod muallif ismini ommaviy yo'lga chiqarsa, testlar yiqilishi shart.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from django.conf import settings
from django.template.loader import render_to_string

from apps.complaints.factories import AnonimComplaintFactory, ComplaintFactory
from apps.solutions.factories import SolutionFactory

TEMPLATES_DIR = Path(settings.BASE_DIR) / "templates"

# ⚠️ `\.author` — `.public_author` ga MOS KELMAYDI: u yerda "author" dan
#    oldin nuqta emas, pastki chiziq turadi. Ya'ni ruxsat etilgan yo'l
#    naqshdan o'zi tashqarida qoladi.
XOM_AUTHOR = re.compile(r"\.author\b(?!_id)")


# ===========================================================================
# Model darajasi
# ===========================================================================
@pytest.mark.django_db
def test_anonim_postda_public_author_NONE():
    """Qabul mezoni: `public_author` anonim bo'lsa `None` qaytaradi."""
    muammo = AnonimComplaintFactory()

    assert muammo.author is not None, "Karma haqiqiy hisobga yozilishi kerak"
    assert muammo.public_author is None


@pytest.mark.django_db
def test_oddiy_postda_public_author_MUALLIFNI_beradi():
    muammo = ComplaintFactory()
    assert muammo.public_author == muammo.author


@pytest.mark.django_db
def test_ochirilgan_hisob_ham_public_author_NONE():
    """⚠️ `None` ning IKKI sababi bor va ikkalasi ham "ismni ko'rsatma".

    Hisob o'chirilganda (D2-T8) `author=None` bo'ladi — shablon shu
    holatda ham yiqilmasligi kerak.
    """
    muammo = ComplaintFactory()
    muammo.author.delete()
    muammo.refresh_from_db()

    assert muammo.public_author is None


@pytest.mark.django_db
def test_anonim_yechimda_ham_ISHLAYDI():
    yechim = SolutionFactory(is_anonymous=True)
    assert yechim.author is not None
    assert yechim.public_author is None


@pytest.mark.django_db
def test_anonim_post_STR_da_ism_YOQ():
    """⚠️ `__str__` admin ro'yxatida, log'da, xato xabarida chiqadi.

    Uni "shunchaki debug" deb o'ylash oson — Sentry (D7-T1) esa uni
    tashqi xizmatga yuboradi.
    """
    muammo = AnonimComplaintFactory()
    assert muammo.author.username not in str(muammo)
    assert muammo.author.username not in repr(muammo)


# ===========================================================================
# Shablon darajasi — HAQIQIY RENDER
# ===========================================================================
@pytest.mark.django_db
def test_lenta_kartasi_anonim_postda_ISMNI_KORSATMAYDI():
    """⚠️ Eng muhim test: shablon HAQIQATAN render qilinadi.

    "public_author ishlatilgan" degan tekshiruv yetarli emas — kartada
    boshqa joyda (masalan avatar `title` atributida yoki `alt` matnida)
    ism qolib ketishi mumkin.
    """
    muammo = AnonimComplaintFactory()
    html = render_to_string("components/_complaint_card.html", {"complaint": muammo})

    assert muammo.author.username not in html
    assert "Anonim" in html


@pytest.mark.django_db
def test_lenta_kartasi_oddiy_postda_ISMNI_KORSATADI():
    """Teskari tomon ham qotirilsin: aks holda "hammasini yashirib
    qo'yish" testni yashil qilardi va mahsulot buzilardi."""
    muammo = ComplaintFactory()
    html = render_to_string("components/_complaint_card.html", {"complaint": muammo})

    assert muammo.author.username in html


# ===========================================================================
# Guard: kelajakdagi kod uchun
# ===========================================================================
def test_shablonlarda_XOM_author_ISHLATILMAYDI():
    """⚠️ Bu test kelajakdagi o'zgarishlar uchun yozilgan.

    `{{ complaint.author.username }}` yozish TO'G'RI ko'rinadi va oddiy
    postda to'g'ri ishlaydi ham — xato faqat anonim postda ko'rinadi,
    ya'ni aynan eng muhim holatda va aynan uni tekshirish esdan
    chiqqanda.

    Yagona ruxsat etilgan yo'l — `public_author`.
    """
    buzuqlar = []
    for yol in sorted(TEMPLATES_DIR.rglob("*.html")):
        matn = yol.read_text(encoding="utf-8")
        for m in XOM_AUTHOR.finditer(matn):
            qator = matn[: m.start()].count("\n") + 1
            # `{% comment %}` ichidagi izohlar hisobga olinmasin: ular
            # aynan shu qoidani TUSHUNTIRADI.
            parcha = matn[max(0, m.start() - 400) : m.start()]
            if parcha.count("{% comment %}") > parcha.count("{% endcomment %}"):
                continue
            buzuqlar.append(f"{yol.relative_to(TEMPLATES_DIR)}:{qator}")

    assert buzuqlar == [], (
        "Shablonda xom `.author` topildi — `public_author` ishlating:\n  "
        + "\n  ".join(buzuqlar)
    )
