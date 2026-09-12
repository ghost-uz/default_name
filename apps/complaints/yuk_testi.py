"""Ovoz endpoint'iga yuk testi (D7-T5) — qo'shimcha paketsiz.

Viral post stsenariysi: ko'p odam bitta postga BIR VAQTDA ovoz beradi.
Task `nega` bo'limi: «TikTok'dan trafik kelsa yuk bir tekis emas, portlash
shaklida keladi. Sanoqchi yangilanishi eng zaif nuqta».

⚠️⚠️ NEGA LOCUST/K6 EMAS
   `requirements/base.txt` qoidasi: yangi paketdan oldin «buni stdlib yoki
   Django bilan qilib bo'ladimi?». Bu yerda — ha. Qabul mezoni ma'lumot
   BUTUNLIGI haqida («ovoz yo'qolmaydi, sanoq to'g'ri qoladi») va uni
   isbotlash uchun tarmoq emas, PARALLEL so'rovlar kerak. Thread'lar va
   Django `Client` to'liq yo'lni bosib o'tadi: middleware (CSRF
   tekshiruvidan tashqari), sessiya, tezlik cheklovi, ko'rinish,
   `cast_vote`, baza.

   Nimani O'LCHAMAYDI: WSGI server (gunicorn ishchilari) va tarmoq. Ular
   server bilan keladi (D0-T10); o'shanda HTTP darajasidagi vosita
   staging'da ishga tushiriladi (DEPLOY.md).

⚠️⚠️ HAR ODAMGA ALOHIDA IP (`REMOTE_ADDR`)
   Bitta mashinadan yuborilgan ovozlar bitta IP'dan kelardi va
   `TEZLIK_CHEKLOVLARI["ovoz"]["ip"]` ularning ko'pini 429 bilan
   qaytarardi — test viral trafikni emas, cheklovni o'lchagan bo'lardi.
   `ip_soni` berilsa odamlar shuncha IP orasida bo'linadi: bu CGNAT
   (bitta IP ortida ko'plab mobil abonent) stsenariysi.

⚠️ REJA DETERMINISTIK — tasodif yo'q: har `minus_har`-odam minus bosadi,
   har `qayta_har`-odam tugmani BIR VAQTDA IKKI marta bosadi. Bir xil
   parametrlar bir xil rejani beradi va natijalarni solishtirsa bo'ladi.

⚠️ Vaqtinchalik post, odamlar va sessiyalar oxirida O'CHIRILADI (`saqlash`
   berilmasa). Post test davomida lentada KO'RINADI — shuning uchun buyruq
   `DEBUG` o'chiq muhitda ruxsatsiz ishlamaydi.
"""

from __future__ import annotations

import copy
import queue
import secrets
import threading
import time
from collections import Counter
from dataclasses import dataclass

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.db import connections
from django.test import Client
from django.test.utils import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.common.models import VoteValue

from .models import Category, CategoryIcon, Complaint, ComplaintVote

# ⚠️ PostgreSQL standart `max_connections=100`: har ishchi O'Z ulanishini
#    ochadi, asosiy jarayon ham bittasini ushlaydi — zaxira qoldiriladi.
PARALLEL_CHEGARASI = 80

# Osilib qolgan ishchi (deadlock) buyruqni abadiy to'xtatmasin.
ISHCHI_MUDDATI_S = 600


@dataclass(frozen=True)
class _Bosish:
    odam_id: int
    mijoz: Client
    ip: str
    qiymat: int


@dataclass
class _Olchov:
    davomiylik_s: float
    holatlar: Counter[int]
    kechikishlar_ms: list[float]
    istisnolar: list[str]
    muvaffaqiyatli: Counter[int]  # odam_id -> 4xx/5xx olmagan bosishlar


@dataclass
class YukNatijasi:
    """Yuk testi natijasi: o'lchovlar VA butunlik tekshiruvi."""

    muammo_pk: int
    prefiks: str
    odamlar: int
    sorovlar: int
    parallel: int
    davomiylik_s: float
    holatlar: Counter[int]
    kechikishlar_ms: list[float]
    istisnolar: list[str]
    sanoq: tuple[int, int]
    qatorlar: tuple[int, int]
    mos_kelmagan_odamlar: int

    @property
    def xato_5xx(self) -> int:
        return sum(soni for kod, soni in self.holatlar.items() if kod >= 500)

    @property
    def cheklangan(self) -> int:
        """Tezlik cheklovi qaytargan so'rovlar (429)."""
        return self.holatlar.get(429, 0)

    @property
    def sanoq_togrimi(self) -> bool:
        """Keshlangan sanoqchilar ovoz jadvaliga TENGmi."""
        return self.sanoq == self.qatorlar

    @property
    def muvaffaqiyatli(self) -> bool:
        """Butunlik saqlandimi.

        ⚠️ 429 MUVAFFAQIYATSIZLIK EMAS — tezlik cheklovi o'z ishini qilgan.
           Butunlik degani: 5xx yo'q, istisno yo'q, sanoq qatorlarga teng va
           HAR odamning yakuniy ovozi uning o'tgan bosishlariga mos —
           ortiqcha ovoz ham, yo'qolgan ovoz ham yo'q.
        """
        return (
            self.xato_5xx == 0
            and not self.istisnolar
            and self.sanoq_togrimi
            and self.mos_kelmagan_odamlar == 0
        )

    @property
    def otkazuvchanlik(self) -> float:
        """So'rov / soniya."""
        return self.sorovlar / self.davomiylik_s if self.davomiylik_s > 0 else 0.0

    def kechikish(self, ulush: float) -> float:
        """Kechikish foizligi (ms): `0.5` — median, `0.95` — p95, `1.0` — eng sekini."""
        if not self.kechikishlar_ms:
            return 0.0
        tartib = sorted(self.kechikishlar_ms)
        return tartib[min(len(tartib) - 1, round(ulush * (len(tartib) - 1)))]


def soxta_ip(indeks: int, ip_soni: int | None) -> str:
    """`10.x.y.z`: har odamga alohida yoki `ip_soni` ta IP orasida (CGNAT)."""
    n = indeks if ip_soni is None else indeks % ip_soni
    return f"10.{(n >> 16) & 255}.{(n >> 8) & 255}.{n & 255}"


def ovoz_yuki(
    *,
    ovozlar: int = 1000,
    parallel: int = 50,
    minus_har: int = 5,
    qayta_har: int = 20,
    ip_soni: int | None = None,
    saqlash: bool = False,
) -> YukNatijasi:
    """`ovozlar` ta odam bitta vaqtinchalik postga BIR VAQTDA ovoz beradi.

    Qadamlar: post va odamlar (sessiyasi bilan) -> hamma ishchi bir vaqtda
    boshlaydi -> sanoqchilar ovoz jadvaliga va har odamning bosishlariga
    solishtiriladi -> tozalash.
    """
    if ovozlar < 1:
        raise ValueError("`ovozlar` kamida 1 bo'lishi kerak.")
    if not 1 <= parallel <= PARALLEL_CHEGARASI:
        raise ValueError(
            f"`parallel` 1..{PARALLEL_CHEGARASI} oralig'ida bo'lishi kerak "
            "(PostgreSQL ulanishlar chegarasi)."
        )
    if ip_soni is not None and ip_soni < 1:
        raise ValueError("`ip_soni` kamida 1 bo'lishi kerak.")

    prefiks = f"yuk_{secrets.token_hex(4)}_"
    muammo: Complaint | None = None
    yangi_kategoriya: Category | None = None
    sessiyalar: list[str] = []
    try:
        # ⚠️ `ALLOWED_HOSTS` — `Client` `testserver` nomidan so'raydi
        #    (`byudjet` buyrug'i bilan bir xil sabab).
        with override_settings(ALLOWED_HOSTS=["*"]):
            muammo, yangi_kategoriya = _post_yaratish(prefiks)
            rejalar, sessiyalar = _rejalar(
                prefiks,
                ovozlar=ovozlar,
                minus_har=minus_har,
                qayta_har=qayta_har,
                ip_soni=ip_soni,
            )
            olchov = _yurgizish(
                rejalar,
                manzil=reverse("dard_ovoz", args=[muammo.pk]),
                parallel=parallel,
            )
        return _tekshirish(
            muammo, rejalar, olchov, prefiks=prefiks, odamlar=ovozlar, parallel=parallel
        )
    finally:
        if not saqlash:
            _tozalash(
                prefiks=prefiks,
                muammo=muammo,
                kategoriya=yangi_kategoriya,
                sessiyalar=sessiyalar,
            )


def _post_yaratish(prefiks: str) -> tuple[Complaint, Category | None]:
    """Vaqtinchalik muallif va post. Kategoriya bor bo'lsa QAYTA ishlatiladi."""
    hozir = timezone.now()
    muallif = get_user_model().objects.create(
        username=f"{prefiks}muallif",
        rozilik_at=hozir,
        rozilik_versiyasi=settings.HUQUQIY_VERSIYA,
        yosh_tasdigi_at=hozir,
    )

    kategoriya = Category.objects.filter(is_active=True).order_by("order", "pk").first()
    yangi: Category | None = None
    if kategoriya is None:
        kategoriya = yangi = Category.objects.create(
            name=f"Yuk testi {prefiks}",
            slug=prefiks.rstrip("_").replace("_", "-"),
            icon=CategoryIcon.DOTS,
        )

    # korinish-istisno: YARATISH — yuk testi uchun vaqtinchalik post.
    muammo = Complaint.objects.create(
        author=muallif,
        category=kategoriya,
        title=f"Yuk testi {prefiks.rstrip('_')}: viral post",
        description="D7-T5 yuk testi uchun vaqtinchalik post. Test tugagach o'chiriladi.",
    )
    return muammo, yangi


def _rejalar(
    prefiks: str,
    *,
    ovozlar: int,
    minus_har: int,
    qayta_har: int,
    ip_soni: int | None,
) -> tuple[list[_Bosish], list[str]]:
    """Odamlar, ularning sessiyalari va bosishlar rejasi.

    ⚠️ Odamlar `bulk_create` bilan (1000 ta `save()` sozlash bosqichini
       daqiqalarga cho'zardi). Rozilik maydonlari SHART: `can_write` usiz
       `False` va ko'rinish har ovozni 403 bilan qaytarardi.
    """
    foydalanuvchi_modeli = get_user_model()
    hozir = timezone.now()
    odamlar = foydalanuvchi_modeli.objects.bulk_create(
        foydalanuvchi_modeli(
            username=f"{prefiks}{i}",
            rozilik_at=hozir,
            rozilik_versiyasi=settings.HUQUQIY_VERSIYA,
            yosh_tasdigi_at=hozir,
        )
        for i in range(ovozlar)
    )

    rejalar: list[_Bosish] = []
    sessiyalar: list[str] = []
    for i, odam in enumerate(odamlar):
        mijoz = Client(raise_request_exception=False)
        mijoz.force_login(odam)
        sessiyalar.append(mijoz.session.session_key or "")

        qiymat = VoteValue.DOWN if minus_har and i % minus_har == 0 else VoteValue.UP
        bosish = _Bosish(
            odam_id=odam.pk, mijoz=mijoz, ip=soxta_ip(i, ip_soni), qiymat=qiymat
        )
        rejalar.append(bosish)

        if qayta_har and i % qayta_har == qayta_har - 1:
            # ⚠️ IKKINCHI MIJOZ, o'sha sessiya: `Client` oqimlar orasida
            #    xavfsiz emas (cookie'lar umumiy lug'at), ikki bosish esa
            #    AYNAN parallel ketishi kerak.
            egizak = Client(raise_request_exception=False)
            egizak.cookies = copy.deepcopy(mijoz.cookies)
            rejalar.append(
                _Bosish(odam_id=odam.pk, mijoz=egizak, ip=bosish.ip, qiymat=qiymat)
            )
    return rejalar, sessiyalar


def _yurgizish(rejalar: list[_Bosish], *, manzil: str, parallel: int) -> _Olchov:
    """Hamma ishchi BIR VAQTDA boshlaydi (portlash) va navbatni bo'shatadi.

    ⚠️ `Barrier` — usiz birinchi ishchilar boshqalar ulanish ochib
       ulgurmasidan ovozlarning bir qismini ketma-ket berib qo'yardi va
       portlash o'lchanmasdi.

    ⚠️ Har ishchi O'Z DB ulanishini oxirida yopadi: Django ulanishni oqimga
       bog'laydi va yopilmagani `CONN_MAX_AGE` davomida ochiq qolardi.
    """
    navbat: queue.SimpleQueue[_Bosish] = queue.SimpleQueue()
    for bosish in rejalar:
        navbat.put(bosish)

    soni = min(parallel, len(rejalar))
    tosiq = threading.Barrier(soni)
    qulf = threading.Lock()
    olchov = _Olchov(0.0, Counter(), [], [], Counter())

    def ishchi() -> None:
        try:
            tosiq.wait()
            while True:
                try:
                    bosish = navbat.get_nowait()
                except queue.Empty:
                    return
                boshi = time.perf_counter()
                try:
                    javob = bosish.mijoz.post(
                        manzil,
                        {"qiymat": bosish.qiymat},
                        headers={"HX-Request": "true"},
                        REMOTE_ADDR=bosish.ip,
                    )
                except Exception as xato:
                    with qulf:
                        olchov.istisnolar.append(f"{type(xato).__name__}: {xato}")
                    continue
                ms = (time.perf_counter() - boshi) * 1000
                with qulf:
                    olchov.holatlar[javob.status_code] += 1
                    olchov.kechikishlar_ms.append(ms)
                    if javob.status_code < 400:
                        olchov.muvaffaqiyatli[bosish.odam_id] += 1
        finally:
            connections.close_all()

    oqimlar = [threading.Thread(target=ishchi, daemon=True) for _ in range(soni)]
    boshi = time.perf_counter()
    for oqim in oqimlar:
        oqim.start()
    for oqim in oqimlar:
        oqim.join(timeout=ISHCHI_MUDDATI_S)
    olchov.davomiylik_s = time.perf_counter() - boshi

    osilganlar = sum(1 for oqim in oqimlar if oqim.is_alive())
    if osilganlar:
        olchov.istisnolar.append(
            f"{osilganlar} ta ishchi {ISHCHI_MUDDATI_S} s da tugamadi (deadlock?)"
        )
    return olchov


def _tekshirish(
    muammo: Complaint,
    rejalar: list[_Bosish],
    olchov: _Olchov,
    *,
    prefiks: str,
    odamlar: int,
    parallel: int,
) -> YukNatijasi:
    """Sanoqchilar <-> ovoz jadvali <-> har odamning o'tgan bosishlari.

    ⚠️ Bitta odamning bosishlari BIR XIL qiymatda, ya'ni qaysi tartibda
       bajarilmasin natija bitta: toq sonli o'tgan bosish — ovoz bor, juft —
       ovoz yo'q (ikkinchi bosish qaytarib oladi). 429 olgan bosish
       hisobga KIRMAYDI.
    """
    # korinish-istisno: o'lchov — keshlangan sanoqchilarni o'qish.
    yangilangan = Complaint.all_objects.only("upvotes_cached", "downvotes_cached").get(
        pk=muammo.pk
    )
    haqiqiy = dict(
        ComplaintVote.objects.filter(complaint_id=muammo.pk).values_list(
            "user_id", "value"
        )
    )

    kutilgan: dict[int, int | None] = {}
    for bosish in rejalar:
        toqmi = olchov.muvaffaqiyatli[bosish.odam_id] % 2 == 1
        kutilgan[bosish.odam_id] = bosish.qiymat if toqmi else None
    mos_kelmagan = sum(
        1 for odam_id, qiymat in kutilgan.items() if haqiqiy.get(odam_id) != qiymat
    )

    plus = sum(1 for qiymat in haqiqiy.values() if qiymat == VoteValue.UP)
    return YukNatijasi(
        muammo_pk=muammo.pk,
        prefiks=prefiks,
        odamlar=odamlar,
        sorovlar=len(rejalar),
        parallel=parallel,
        davomiylik_s=olchov.davomiylik_s,
        holatlar=olchov.holatlar,
        kechikishlar_ms=olchov.kechikishlar_ms,
        istisnolar=olchov.istisnolar,
        sanoq=(yangilangan.upvotes_cached, yangilangan.downvotes_cached),
        qatorlar=(plus, len(haqiqiy) - plus),
        mos_kelmagan_odamlar=mos_kelmagan,
    )


def _tozalash(
    *,
    prefiks: str,
    muammo: Complaint | None,
    kategoriya: Category | None,
    sessiyalar: list[str],
) -> None:
    """Vaqtinchalik post, ovozlar, odamlar va sessiyalarni o'chiradi.

    ⚠️ Post QATTIQ o'chiriladi (`_base_manager`): `Complaint` yumshoq
       o'chiriladi va oddiy `delete()` qatorni bazada qoldirardi.
    """
    if muammo is not None:
        # korinish-istisno: tozalash — vaqtinchalik postni QATTIQ o'chirish.
        Complaint._base_manager.filter(pk=muammo.pk).delete()
    Session.objects.filter(session_key__in=[k for k in sessiyalar if k]).delete()
    get_user_model().objects.filter(username__startswith=prefiks).delete()
    if kategoriya is not None:
        kategoriya.delete()


def hisobot(natija: YukNatijasi) -> str:
    """Natija jadvali (Markdown).

    ⚠️ Faqat ASCII belgilar: Windows konsolida (cp1251/cp866) emoji va
       strelkalar `UnicodeEncodeError` bilan buyruqni yiqitardi.
    """
    holatlar = (
        ", ".join(f"{kod}: {soni}" for kod, soni in sorted(natija.holatlar.items()))
        or "-"
    )
    qatorlar = [
        ("odamlar", str(natija.odamlar)),
        ("so'rovlar (ikki marta bosish bilan)", str(natija.sorovlar)),
        ("parallel ishchilar", str(natija.parallel)),
        ("davomiylik", f"{natija.davomiylik_s:.2f} s"),
        ("o'tkazuvchanlik", f"{natija.otkazuvchanlik:.0f} so'rov/s"),
        (
            "kechikish p50 / p95 / max",
            f"{natija.kechikish(0.5):.0f} / {natija.kechikish(0.95):.0f} / "
            f"{natija.kechikish(1.0):.0f} ms",
        ),
        ("HTTP holatlari", holatlar),
        ("429 (tezlik cheklovi)", str(natija.cheklangan)),
        ("5xx", str(natija.xato_5xx)),
        ("istisnolar", str(len(natija.istisnolar))),
        ("sanoq plus / minus (kesh)", f"{natija.sanoq[0]} / {natija.sanoq[1]}"),
        (
            "qatorlar plus / minus (jadval)",
            f"{natija.qatorlar[0]} / {natija.qatorlar[1]}",
        ),
        ("kutilganidan farq qilgan odamlar", str(natija.mos_kelmagan_odamlar)),
        (
            "NATIJA",
            "OK - ovoz yo'qolmadi, sanoq to'g'ri"
            if natija.muvaffaqiyatli
            else "BUTUNLIK BUZILDI",
        ),
    ]
    matn = "| ko'rsatkich | qiymat |\n|---|---|\n" + "\n".join(
        f"| {nom} | {qiymat} |" for nom, qiymat in qatorlar
    )
    if natija.istisnolar:
        matn += "\n\nIstisnolar (birinchi 5):\n" + "\n".join(natija.istisnolar[:5])
    return matn
