"""`manage.py byudjet` — dasturchi vositasi (D7-T4)."""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command

from apps.common.tests.test_byudjet import _sayt_toldirish

pytestmark = pytest.mark.django_db


def _chiqish(**kw) -> str:
    chiqish = StringIO()
    call_command("byudjet", stdout=chiqish, **kw)
    return chiqish.getvalue()


def test_JADVAL_chiqadi(user):
    _sayt_toldirish(soni=5)

    matn = _chiqish()

    assert "| sahifa | so'rov | bayt | render | holat |" in matn
    for nom in ("lenta (mehmon)", "lenta (kirgan)", "dard (batafsil)", "qidiruv"):
        assert nom in matn


def test_BOSH_bazada_YIQILMAYDI():
    """⚠️ Buyruq ma'lumotsiz ham ishlashi kerak: u dasturchi vositasi
    va bo'sh bazada chaqirilishi ODATIY hol."""
    matn = _chiqish()

    assert "post yo'q" in matn
    assert "foydalanuvchi yo'q" in matn


def test_KIRGAN_sahifa_HAQIQATAN_kirgan_holda_olchanadi(user):
    """⚠️ Mehmon sifatida o'lchash YOLG'ON raqam berardi: ovozlar,
    saqlanganlar va bloklanganlar so'rovlari umuman ketmasdi."""
    _sayt_toldirish(soni=5)

    matn = _chiqish()

    qator = next(q for q in matn.splitlines() if q.startswith("| lenta (kirgan)"))
    mehmon = next(q for q in matn.splitlines() if q.startswith("| lenta (mehmon)"))
    sorov_kirgan = int(qator.split("|")[2].split("/")[0].strip())
    sorov_mehmon = int(mehmon.split("|")[2].split("/")[0].strip())

    assert sorov_kirgan > sorov_mehmon


def test_AKTIVLAR_ham_chiqadi(user):
    matn = _chiqish()

    assert "static/js/vendor/htmx.min.js" in matn


def test_STANDARTDA_YIQITMAYDI(user):
    """⚠️⚠️ Buyruq ATAYLAB hech qachon yiqitmaydi: vaqt o'lchovi
    deterministik emas va uni qat'iy darvoza qilish CI'ni yolg'on
    yiqitardi (`--qatiy` ochiq berilsagina)."""
    _sayt_toldirish(soni=5)

    # Istisno TASHLANMAYDI — `SystemExit` ham.
    assert _chiqish() != ""


# ⚠️⚠️ MODUL ICHIDAGI NOMNI patch QILING, MANBANI EMAS.
#    Buyruq `from apps.common.byudjet import RENDER_MS` qiladi, ya'ni
#    nom MODUL YUKLANISHIDA bog'lanadi. `apps.common.byudjet.RENDER_MS`
#    ni almashtirish buyruqqa TA'SIR QILMAYDI va test JIMGINA
#    ogohlantirishsiz o'tardi (birinchi urinishda aynan shunday bo'ldi).
BUYRUQ_RENDER_MS = "apps.common.management.commands.byudjet.RENDER_MS"


def test_GITHUB_bayrogi_XULOSAGA_yozadi(user, tmp_path, monkeypatch):
    xulosa = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(xulosa))
    monkeypatch.setattr(BUYRUQ_RENDER_MS, 0.0)

    _sayt_toldirish(soni=5)
    matn = _chiqish(github=True)

    assert "Ish faoliyati byudjeti" in xulosa.read_text(encoding="utf-8")
    # ⚠️ `::warning::` — GitHub buni annotatsiyaga aylantiradi.
    assert "::warning title=Byudjet::" in matn


def test_QATIY_bayrogi_ogohlantirishda_YIQITADI(user, monkeypatch):
    """⚠️ `--qatiy` — ixtiyoriy: kimdir byudjetni qat'iy darvoza
    qilmoqchi bo'lsa yo'l ochiq qoladi."""
    monkeypatch.setattr(BUYRUQ_RENDER_MS, 0.0)
    _sayt_toldirish(soni=5)

    with pytest.raises(SystemExit):
        _chiqish(qatiy=True)
