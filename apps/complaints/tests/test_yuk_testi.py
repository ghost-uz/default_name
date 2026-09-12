"""Ovoz yuk testi vositasi (D7-T5) — kichik hajmdagi tekshiruvlar.

⚠️ Bu testlar VOSITANING O'ZINI tekshiradi: butunlikni to'g'ri hisoblaydimi,
   ortidan tozalaydimi, IP'larni to'g'ri bo'ladimi. Parallel butunlikning
   O'ZI xizmat darajasida `test_ovoz_parallel.py` da sinaladi — vosita
   noto'g'ri hisoblasa, u yerdagi testlar baribir ushlaydi.
"""

from __future__ import annotations

from io import StringIO
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.complaints.models import Complaint, ComplaintVote
from apps.complaints.yuk_testi import PARALLEL_CHEGARASI, ovoz_yuki, soxta_ip

pytestmark = pytest.mark.django_db(transaction=True)


def _hisob() -> tuple[int, int, int, int]:
    return (
        get_user_model().objects.count(),
        Complaint.all_objects.count(),
        ComplaintVote.objects.count(),
        Session.objects.count(),
    )


def test_KICHIK_YUKDA_butunlik_saqlanadi_va_REJA_deterministik():
    """40 odam: har 5-chisi minus, har 4-chisi tugmani ikki marta bosadi.

    Ikki marta bosganlar (10 kishi) OVOZSIZ qoladi. Minus bosganlardan
    ikkitasi (15 va 35) ham ikki marta bosgan — ya'ni qatorlar: 24 plus,
    6 minus. Reja tasodifsiz, shuning uchun son ANIQ.
    """
    natija = ovoz_yuki(ovozlar=40, parallel=8, minus_har=5, qayta_har=4)

    assert natija.istisnolar == []
    assert natija.xato_5xx == 0
    assert natija.cheklangan == 0
    assert natija.sorovlar == 50
    assert natija.qatorlar == (24, 6)
    assert natija.sanoq_togrimi
    assert natija.mos_kelmagan_odamlar == 0
    assert natija.muvaffaqiyatli


def test_ORTIDAN_hech_narsa_QOLDIRMAYDI():
    oldin = _hisob()

    ovoz_yuki(ovozlar=10, parallel=4)

    assert _hisob() == oldin


def test_SAQLASH_berilsa_POST_QOLADI():
    natija = ovoz_yuki(ovozlar=5, parallel=2, saqlash=True)

    assert Complaint.all_objects.filter(pk=natija.muammo_pk).exists()


def test_CGNAT_stsenariysida_429_BUTUNLIKNI_buzmaydi(settings):
    """Bitta IP ortida 30 odam, IP chegarasi daqiqasiga 10: 20 tasi 429 oladi.

    ⚠️ Vaqt QOTIRILADI: tezlik cheklovi sobit oynali (daqiqa) va test oyna
       chegarasidan o'tib qolsa sanoq qayta boshlanib, son tasodifiy
       bo'lardi (D5-T4 dagi «devor soati» tuzog'i).
    """
    settings.TEZLIK_CHEKLOVLARI = {
        **settings.TEZLIK_CHEKLOVLARI,
        "ovoz": {"foydalanuvchi": "30/m", "ip": "10/m"},
    }

    with mock.patch("apps.common.ratelimit.time.time", return_value=1_800_000_000.0):
        natija = ovoz_yuki(ovozlar=30, parallel=6, qayta_har=0, ip_soni=1)

    assert natija.cheklangan == 20
    assert natija.holatlar[200] == 10
    assert sum(natija.qatorlar) == 10
    assert natija.muvaffaqiyatli


def test_SOXTA_IP_har_odamga_ALOHIDA_yoki_CGNAT_boyicha():
    assert len({soxta_ip(i, None) for i in range(70_000)}) == 70_000
    assert len({soxta_ip(i, 3) for i in range(1000)}) == 3


def test_PARALLEL_chegaradan_oshsa_RAD_etiladi():
    with pytest.raises(ValueError, match="parallel"):
        ovoz_yuki(ovozlar=10, parallel=PARALLEL_CHEGARASI + 1)


def test_BUYRUQ_DEBUG_ochiqda_RUXSATSIZ_ishlamaydi():
    """Test sozlamasida `DEBUG=False` — ya'ni prod bilan bir xil holat."""
    with pytest.raises(CommandError, match="prod-ham"):
        call_command("ovoz_yuk_testi", "--ovozlar", "5", stdout=StringIO())


def test_BUYRUQ_hisobot_CHIQARADI():
    chiqish = StringIO()

    call_command(
        "ovoz_yuk_testi",
        "--ovozlar",
        "12",
        "--parallel",
        "4",
        "--prod-ham",
        stdout=chiqish,
    )

    matn = chiqish.getvalue()
    assert "| NATIJA | OK" in matn
    assert "| 5xx | 0 |" in matn
