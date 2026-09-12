"""Ovoz berish — parallel so'rovlar ostida ma'lumot butunligi (D7-T5).

QABUL MEZONI: «1000 parallel ovozda ma'lumot yo'qolmaydi va sanoq to'g'ri
qoladi».

⚠️⚠️ NEGA `transaction=True`
   Oddiy `django_db` testi butun testni BITTA tranzaksiyaga o'raydi: boshqa
   oqimdagi ulanish undagi ma'lumotni KO'RMAYDI, `select_for_update` va
   noyoblik cheklovlari esa hech qachon to'qnashmaydi. Ya'ni poyga holatini
   sinab bo'lmasdi — test yashil bo'lardi va hech narsani tekshirmasdi.

⚠️⚠️ HAR ISHCHI O'Z ULANISHINI YOPADI (`connections.close_all()`)
   Django ulanishni oqimga bog'laydi. Yopilmagan ulanish (`CONN_MAX_AGE=60`)
   seans oxirida test bazasini o'chirishga xalaqit beradi, `filterwarnings =
   error` ostida esa `ResourceWarning` testni yiqitardi.

⚠️ Ishchilar soni 16 — PostgreSQL'ning standart `max_connections=100`
   chegarasidan ancha past (CI'dagi xizmat konteyneri ham standart).
"""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable
from unittest import mock

import pytest
from django.db import connections, models

from apps.accounts.factories import TelegramUserFactory
from apps.common.models import VoteValue
from apps.common.voting import cast_vote
from apps.complaints.factories import ComplaintFactory
from apps.complaints.models import Complaint, ComplaintVote
from apps.gamification.models import KARMA_QIYMATLARI, KarmaEvent, KarmaReason
from apps.solutions.factories import SolutionFactory
from apps.solutions.models import Solution, SolutionVote
from apps.solutions.services import yechimga_ovoz

pytestmark = pytest.mark.django_db(transaction=True)

ISHCHILAR = 16


# ===========================================================================
# Yordamchilar
# ===========================================================================
def parallel_bajar(
    vazifalar: list[Callable[[], object]], *, ishchilar: int = ISHCHILAR
) -> list[Exception]:
    """Vazifalarni BIR VAQTDA bajaradi va yuzaga kelgan istisnolarni qaytaradi.

    ⚠️ `Barrier` — hamma ishchi tayyor bo'lgach BIRGA boshlaydi. Usiz birinchi
       ishchi o'z vazifalarini boshqalar ulanish ochib ulgurmasidan tugatib
       qo'yardi va poyga umuman yuz bermasdi.

    ⚠️ Osilib qolgan ishchi (deadlock) testni ABADIY to'xtatmasin — `join`
       muddatli va osilgani alohida xabar bilan yiqitiladi.
    """
    navbat: queue.SimpleQueue[Callable[[], object]] = queue.SimpleQueue()
    for vazifa in vazifalar:
        navbat.put(vazifa)

    soni = max(1, min(ishchilar, len(vazifalar)))
    tosiq = threading.Barrier(soni)
    xatolar: list[Exception] = []
    qulf = threading.Lock()

    def ishchi() -> None:
        try:
            tosiq.wait()
            while True:
                try:
                    vazifa = navbat.get_nowait()
                except queue.Empty:
                    return
                try:
                    vazifa()
                except Exception as xato:
                    with qulf:
                        xatolar.append(xato)
        finally:
            connections.close_all()

    oqimlar = [threading.Thread(target=ishchi, daemon=True) for _ in range(soni)]
    for oqim in oqimlar:
        oqim.start()
    for oqim in oqimlar:
        oqim.join(timeout=120)

    osilganlar = [oqim for oqim in oqimlar if oqim.is_alive()]
    assert not osilganlar, f"{len(osilganlar)} ta ishchi 120 s da tugamadi (deadlock?)"
    return xatolar


def _muammoga_bosish(muammo_pk: int, odam, qiymat: int) -> Callable[[], object]:
    """Bitta tugma bosishi — o'z oqimida posti QAYTA oladi (ko'rinish kabi)."""

    def vazifa() -> object:
        return cast_vote(
            target=Complaint.all_objects.get(pk=muammo_pk),
            vote_model=ComplaintVote,
            target_field="complaint",
            user=odam,
            value=qiymat,
        )

    return vazifa


def _yechimga_bosish(yechim_pk: int, odam, qiymat: int) -> Callable[[], object]:
    def vazifa() -> object:
        return yechimga_ovoz(
            solution=Solution.objects.get(pk=yechim_pk), user=odam, qiymat=qiymat
        )

    return vazifa


def _sanoq_qatorlarga_teng(obyekt, vote_model, maydon: str) -> tuple[int, int]:
    """Keshlangan sanoqchilar ovoz jadvaliga AYNAN tengmi. Qaytaradi: (↑, ↓)."""
    obyekt.refresh_from_db(
        fields=["upvotes_cached", "downvotes_cached", "score_cached"]
    )
    qatorlar = vote_model.objects.filter(**{maydon: obyekt})
    plus = qatorlar.filter(value=VoteValue.UP).count()
    minus = qatorlar.filter(value=VoteValue.DOWN).count()
    assert (obyekt.upvotes_cached, obyekt.downvotes_cached, obyekt.score_cached) == (
        plus,
        minus,
        plus - minus,
    )
    return plus, minus


# ===========================================================================
# 1. Qabul mezoni — viral post
# ===========================================================================
@pytest.mark.slow
def test_1000_PARALLEL_OVOZDA_hech_narsa_YOQOLMAYDI():
    """⭐⭐ QABUL MEZONI. 1000 xil odam bitta postga BIR VAQTDA ovoz beradi,
    har beshinchisi minus. Xato yo'q, 1000 ta qator, sanoq qatorlarga TENG.
    """
    muammo = ComplaintFactory()
    odamlar = TelegramUserFactory.create_batch(1000)
    vazifalar = [
        _muammoga_bosish(
            muammo.pk, odam, VoteValue.DOWN if i % 5 == 0 else VoteValue.UP
        )
        for i, odam in enumerate(odamlar)
    ]

    xatolar = parallel_bajar(vazifalar)

    assert xatolar == []
    assert _sanoq_qatorlarga_teng(muammo, ComplaintVote, "complaint") == (800, 200)


# ===========================================================================
# 2. Bir odam, bir vaqtdagi bosishlar — topilgan poyga
# ===========================================================================
def test_BIR_VAQTDAGI_ikki_bosish_500_BERMAYDI_va_KETMA_KETLIKKA_teng():
    """⭐⭐ TOPILGAN POYGA: mavjud ovoz tugmasi tez IKKI marta bosildi.

    A so'rovi ovoz qatorini qulflab O'CHIRADI. B so'rovi `INSERT` da
    noyoblik xatosini oladi va `select_for_update()` bilan A ni kutadi.
    A commit qilgach qator YO'Q — READ COMMITTED da o'chirilgan qator
    natijadan tushib qoladi va `.get()` `DoesNotExist` otardi:
    foydalanuvchiga 500, ikkinchi bosish esa yo'qolardi.

    To'g'ri natija KETMA-KETLIK bilan bir xil: birinchi bosish ovozni
    oladi, ikkinchisi uni qaytaradi.

    ⚠️ Poyga TASODIFGA qoldirilmaydi: A ning `delete()` i sekinlashtiriladi
       va B faqat A qatorni QULFLAGANDAN keyin boshlanadi.
    """
    muammo = ComplaintFactory()
    odam = TelegramUserFactory()
    _muammoga_bosish(muammo.pk, odam, VoteValue.UP)()

    asl_delete = ComplaintVote.delete
    qulflandi = threading.Event()

    def sekin_delete(self, *args, **kwargs):
        qulflandi.set()
        time.sleep(0.3)
        return asl_delete(self, *args, **kwargs)

    natijalar: dict[str, object] = {}

    def bosish(nom: str) -> Callable[[], None]:
        def vazifa() -> None:
            if nom == "B":
                assert qulflandi.wait(timeout=10), "A qatorni qulflamadi"
            natijalar[nom] = _muammoga_bosish(muammo.pk, odam, VoteValue.UP)()

        return vazifa

    with mock.patch.object(ComplaintVote, "delete", sekin_delete):
        xatolar = parallel_bajar([bosish("A"), bosish("B")], ishchilar=2)

    assert xatolar == []
    assert natijalar["A"].removed is True
    assert natijalar["B"].created is True
    assert _sanoq_qatorlarga_teng(muammo, ComplaintVote, "complaint") == (1, 0)


def test_BIR_ODAMNING_parallel_bosishlari_ostida_sanoq_TOGRI():
    """Bitta odamdan 60 ta bosish (↑ va ↓ aralash), 16 ta parallel oqimda.

    Qanday tartibda bajarilmasin: xato yo'q, qator 0 yoki 1 ta, sanoq
    qatorlarga teng. Yuqoridagi deterministik test ANIQ poygani ushlaydi,
    bu esa kutilmagan boshqa kesishmalar uchun.
    """
    muammo = ComplaintFactory()
    odam = TelegramUserFactory()
    vazifalar = [
        _muammoga_bosish(muammo.pk, odam, VoteValue.UP if i % 3 else VoteValue.DOWN)
        for i in range(60)
    ]

    xatolar = parallel_bajar(vazifalar)

    assert xatolar == []
    assert sum(_sanoq_qatorlarga_teng(muammo, ComplaintVote, "complaint")) <= 1


# ===========================================================================
# 3. Yechim ovozi va karma — ikkalasi birga yoki hech biri
# ===========================================================================
def test_KARMA_yozilmasa_OVOZ_ham_SAQLANMAYDI():
    """⭐⭐ TOPILGAN TESHIK: `yechimga_ovoz` ovozni va karmani IKKI alohida
    tranzaksiyada yozardi (`ATOMIC_REQUESTS` yoqilmagan). Ular orasidagi
    xato ovozni saqlab, muallif karmasini YO'QOTARDI — ya'ni sanoq bilan
    karma jurnali bir-biridan jimgina uzilardi.
    """
    yechim = SolutionFactory()
    odam = TelegramUserFactory()

    with (
        mock.patch(
            "apps.solutions.services.ovoz_karmasi",
            side_effect=RuntimeError("baza uzildi"),
        ),
        pytest.raises(RuntimeError),
    ):
        yechimga_ovoz(solution=yechim, user=odam, qiymat=VoteValue.UP)

    assert not SolutionVote.objects.filter(solution=yechim).exists()
    assert _sanoq_qatorlarga_teng(yechim, SolutionVote, "solution") == (0, 0)


def test_YECHIMGA_PARALLEL_ovozda_KARMA_sanoq_bilan_MOS():
    """200 odam bitta yechimga bir vaqtda ↑ bosadi, har to'rtinchisi tugmani
    IKKINCHI marta ham bosadi (qaytarib oladi). Sanoq qatorlarga, muallif
    karmasi esa plus ovozlar soniga mos bo'lishi SHART.
    """
    yechim = SolutionFactory()
    muallif = yechim.author
    odamlar = TelegramUserFactory.create_batch(200)

    vazifalar: list[Callable[[], object]] = []
    for i, odam in enumerate(odamlar):
        vazifalar.append(_yechimga_bosish(yechim.pk, odam, VoteValue.UP))
        if i % 4 == 0:
            vazifalar.append(_yechimga_bosish(yechim.pk, odam, VoteValue.UP))

    xatolar = parallel_bajar(vazifalar)

    assert xatolar == []
    plus, _ = _sanoq_qatorlarga_teng(yechim, SolutionVote, "solution")
    assert plus == 200 - 50

    ovoz_karmasi = KarmaEvent.objects.filter(user=muallif, solution=yechim).aggregate(
        jami=models.Sum("points", default=0)
    )["jami"]
    assert ovoz_karmasi == plus * KARMA_QIYMATLARI[KarmaReason.SOLUTION_UPVOTED]

    muallif.refresh_from_db(fields=["karma_cached"])
    assert (
        muallif.karma_cached
        == KarmaEvent.objects.filter(user=muallif).aggregate(
            jami=models.Sum("points", default=0)
        )["jami"]
    )
