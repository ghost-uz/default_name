"""Ish faoliyati byudjeti — QAT'IY tekshiruv (D7-T4).

⚠️⚠️ FAQAT DETERMINISTIK O'LCHAMLAR BU YERDA YIQITADI.
   Render vaqti va Lighthouse — `manage.py byudjet` va CI'ning
   ogohlantiruvchi ishida (sabab `apps/common/byudjet.py` da).
"""

from __future__ import annotations

import time
import warnings

import pytest
from django.db import connection, reset_queries
from django.test import Client
from django.test.utils import CaptureQueriesContext

from apps.common.byudjet import AKTIVLAR, RENDER_MS, SAHIFALAR, aktiv_hajmi
from apps.complaints.factories import CategoryFactory, ComplaintFactory
from apps.solutions.factories import SolutionFactory

pytestmark = pytest.mark.django_db


def _sayt_toldirish(*, soni: int = 20) -> str:
    """⚠️ BYUDJET REALISTIK SAHIFADA o'lchanadi.

    Bo'sh lentada so'rov soni ham, hajm ham kichkina — unda byudjet
    hech narsani ushlamasdi va yashil bo'lib turaverardi. Shuning
    uchun sahifalar to'ldirilgan holda o'lchanadi.
    """
    katlar = [CategoryFactory(slug=f"byudjet-{i}") for i in range(4)]
    birinchi = None
    for i in range(soni):
        muammo = ComplaintFactory(
            category=katlar[i % len(katlar)],
            is_anonymous=(i % 4 == 0),
            title=f"Ipoteka olish qiyinmi {i}",
        )
        if i % 3 == 0:
            SolutionFactory(complaint=muammo)
        if birinchi is None:
            # ⚠️ Batafsil sahifa uchun YECHIMLARI BOR post kerak —
            #    bo'sh muhokamada byudjet hech narsani ushlamasdi.
            SolutionFactory.create_batch(5, complaint=muammo)
            birinchi = muammo
    assert birinchi is not None
    return birinchi.slug


def _mijoz(sahifa, user, *, manzil: str) -> Client:
    c = Client()
    if sahifa.kirgan:
        c.force_login(user)
        # ⚠️ Sessiya keshini ILITAMIZ: birinchi so'rov sessiyani
        #    yaratadi va o'lchovga begona so'rov qo'shardi.
        c.get(manzil)
    return c


@pytest.mark.parametrize("sahifa", SAHIFALAR, ids=lambda s: s.nom)
def test_SOROV_byudjeti(sahifa, user):
    """⚠️⚠️ Bu son OSHSA — o'ylab ko'ring, keyin jadvalni yangilang.

    Oshirish oson va shuning uchun xavfli: har relizda bittadan so'rov
    qo'shilsa, bir yildan keyin sayt ikki barobar sekin bo'ladi va
    hech kim buni payqamaydi (task `nega` bo'limi).
    """
    slug = _sayt_toldirish()
    manzil = sahifa.manzil(slug=slug)
    c = _mijoz(sahifa, user, manzil=manzil)
    reset_queries()

    with CaptureQueriesContext(connection) as sorovlar:
        javob = c.get(manzil)

    assert javob.status_code == 200
    assert len(sorovlar) <= sahifa.sorovlar, (
        f"{sahifa.nom}: {len(sorovlar)} ta so'rov "
        f"(byudjet {sahifa.sorovlar}).\n"
        "  Yangi so'rov ONGLI qaror bo'lsa `apps/common/byudjet.py` "
        "dagi jadvalni yangilang va SABABINI commit xabarida yozing."
    )


@pytest.mark.parametrize("sahifa", SAHIFALAR, ids=lambda s: s.nom)
def test_HAJM_byudjeti(sahifa, user):
    """⚠️ Javob hajmi — Lighthouse «Performance» ballining eng katta
    tarkibiy qismi, lekin brauzersiz va tebranishsiz o'lchanadi."""
    slug = _sayt_toldirish()
    manzil = sahifa.manzil(slug=slug)
    c = _mijoz(sahifa, user, manzil=manzil)

    javob = c.get(manzil)

    assert javob.status_code == 200
    hajm = len(javob.content)
    assert hajm <= sahifa.bayt, (
        f"{sahifa.nom}: {hajm:,} bayt (byudjet {sahifa.bayt:,}).\n"
        "  Sahifaga og'ir narsa qo'shildimi? Inline SVG, katta jadval "
        "yoki sahifalash chegarasi o'zgardimi?"
    )


@pytest.mark.parametrize("nisbiy,chegara", AKTIVLAR)
def test_AKTIV_byudjeti(nisbiy, chegara):
    """⚠️ Aktiv HAR SAHIFADA yuklanadi — uning o'sishi hamma joyga
    tegadi va uni hech kim o'lchamaydi.

    ⚠️ Fayl yo'q bo'lsa test O'TKAZIB YUBORILADI, yiqilmaydi:
       `app.css` qurilish artefakti va toza checkout'da mavjud emas.
       CI uni testdan OLDIN quradi.
    """
    hajm = aktiv_hajmi(nisbiy)
    if hajm is None:
        pytest.skip(f"{nisbiy} qurilmagan (`npm run build`)")

    assert hajm <= chegara, (
        f"{nisbiy}: {hajm:,} bayt (byudjet {chegara:,}).\n"
        "  Tailwind bundle o'sdimi? Yangi vendor kutubxona qo'shildimi?"
    )


def test_JADVAL_bosh_emas():
    """⚠️ Jadval bo'shab qolsa hamma byudjet testi JIMGINA o'tardi."""
    assert len(SAHIFALAR) >= 4
    assert len(AKTIVLAR) >= 2


def test_HAR_SAHIFA_NOYOB_nomga_ega():
    """⚠️ Nom xato xabarida ko'rsatiladi — takrorlansa qaysi qator
    buzilganini topib bo'lmasdi."""
    nomlar = [s.nom for s in SAHIFALAR]
    assert len(nomlar) == len(set(nomlar))


# ===========================================================================
# ⚠️ Render vaqti — OGOHLANTIRADI, yiqitmaydi
# ===========================================================================
def _github_xulosa(matn: str) -> None:
    """GitHub Actions bosqich xulosasiga yozadi (CI'dan tashqarida jim).

    ⚠️ `::warning::` ni stdout'ga yozish YARAMAYDI: pytest stdout'ni
       ushlaydi va annotatsiya GitHub'ga yetib bormasdi. Fayl yozish
       esa ushlanmaydi.
    """
    import os
    import pathlib

    yol = os.environ.get("GITHUB_STEP_SUMMARY")
    if not yol:
        return
    with pathlib.Path(yol).open("a", encoding="utf-8") as f:
        f.write(matn + "\n")


@pytest.mark.parametrize("sahifa", SAHIFALAR, ids=lambda s: s.nom)
def test_RENDER_vaqti(sahifa, user):
    """⚠️⚠️ IKKI CHEGARA: OGOHLANTIRISH va FALOKAT.

    Vaqt — yagona deterministik BO'LMAGAN o'lcham: CI runner'i boshqa
    ishlar bilan band bo'lishi mumkin. Uni `RENDER_MS` da qat'iy
    ushlash CI'ni yolg'on yiqitardi va uchinchi yolg'ondan keyin hech
    kim ogohlantirishga qaramaydi.

    Shuning uchun:
      • `RENDER_MS` (300 ms) — OGOHLANTIRISH (CI xulosasida ko'rinadi);
      • `FALOKAT_MS` (10 barobar) — QAT'IY, chunki bunday sekinlashuvni
        runner shovqini bilan izohlab bo'lmaydi.

    ⚠️ Ikkinchi chegara ATAYLAB: chegarasiz test HECH QACHON yiqila
       olmasdi — bu seansda ikki marta uchragan «yiqila olmaydigan
       test» tuzog'i.
    """
    falokat_ms = RENDER_MS * 10

    slug = _sayt_toldirish()
    manzil = sahifa.manzil(slug=slug)
    c = _mijoz(sahifa, user, manzil=manzil)
    c.get(manzil)  # keshni ilitamiz

    boshi = time.perf_counter()
    javob = c.get(manzil)
    ms = (time.perf_counter() - boshi) * 1000

    assert javob.status_code == 200

    if ms > RENDER_MS:
        xabar = f"{sahifa.nom}: render {ms:.0f} ms (chegara {RENDER_MS} ms)"
        warnings.warn(xabar, stacklevel=1)
        _github_xulosa(f"⚠️ **Byudjet**: {xabar}")

    assert ms < falokat_ms, (
        f"{sahifa.nom}: render {ms:.0f} ms — {falokat_ms} ms falokat "
        "chegarasidan oshdi. Bu runner shovqini EMAS."
    )
