"""N+1 so'rovlar auditi (D1-T14).

⚠️ IKKI XIL TEKSHIRUV, IKKALASI HAM KERAK

  1. **Qat'iy son** (`assertNumQueries`) — so'rov soni jimgina o'sib
     ketmasin. Yangi `select_related` unutilsa yoki shablonga yangi
     bog'lanish qo'shilsa, bu test darhol yiqiladi.

  2. **Elementlar soniga bog'liqlik** — asosiy tekshiruv. Qat'iy son
     N+1 ni ISBOTLAMAYDI: u faqat bugungi holatni yozib qo'yadi. 5 ta
     va 50 ta karta bir xil so'rov soni bersa — bog'liqlik yo'qligi
     kafolatlanadi.

  Faqat birinchisi bo'lsa: kimdir N+1 qo'shib, sonni "tuzatib" qo'yadi
  va test yashil qolaveradi.
"""

from __future__ import annotations

import pytest
from django.test import Client

from apps.common.models import VoteValue
from apps.common.voting import cast_vote
from apps.complaints.factories import CategoryFactory, ComplaintFactory
from apps.complaints.models import ComplaintVote, SavedComplaint
from apps.solutions.factories import ExpertSolutionFactory, SolutionFactory
from apps.solutions.models import SolutionVote

pytestmark = pytest.mark.django_db

# Qabul mezoni: "lenta sahifasi <= 8 so'rov".
LENTA_CHEGARASI = 8
BATAFSIL_CHEGARASI = 10


def lenta_toldirish(*, soni: int, user=None, kategoriyalar: int = 4) -> list:
    """Har xil holatdagi postlar: ovozli, saqlangan, anonim, ekspert javobli."""
    katlar = [CategoryFactory(slug=f"kat-{i}") for i in range(kategoriyalar)]
    muammolar = [
        ComplaintFactory(
            category=katlar[i % kategoriyalar],
            is_anonymous=(i % 4 == 0),
        )
        for i in range(soni)
    ]
    if user is not None:
        for muammo in muammolar[: max(1, soni // 2)]:
            cast_vote(
                target=muammo,
                vote_model=ComplaintVote,
                target_field="complaint",
                user=user,
                value=VoteValue.UP,
            )
            SavedComplaint.objects.create(user=user, complaint=muammo)
    return muammolar


def sorovlar(mijoz: Client, yol: str, **kw) -> int:
    """So'rovlar sonini o'lchaydi (sessiya keshi ilitilgandan keyin)."""
    from django.db import connection, reset_queries
    from django.test.utils import CaptureQueriesContext

    mijoz.get(yol, kw)  # iliting: sessiya va contenttypes keshi
    reset_queries()
    with CaptureQueriesContext(connection) as ctx:
        javob = mijoz.get(yol, kw)
        assert javob.status_code == 200
    return len(ctx)


# ===========================================================================
# Lenta
# ===========================================================================
def test_lenta_sorov_soni_KARTALAR_SONIGA_BOGLIQ_EMAS(user):
    """⚠️ D1-T14 ning ASOSIY testi.

    Har kartada muallif, kategoriya, "men ovoz berganmanmi?" va
    "saqlaganmanmi?" bor. Ehtiyotsizlikda 20 karta = 80+ so'rov.

    Bu yerda son EMAS, BOG'LIQLIK tekshiriladi: kam va ko'p kartada
    so'rov soni AYNAN bir xil bo'lishi shart.
    """
    c = Client()
    c.force_login(user)

    lenta_toldirish(soni=3, user=user)
    kam = sorovlar(c, "/")

    lenta_toldirish(soni=20, user=user, kategoriyalar=6)
    kop = sorovlar(c, "/")

    assert kam == kop, (
        f"So'rov soni kartalar soniga bog'liq: {kam} -> {kop}. "
        "Shablonda `select_related` qamramaydigan bog'lanish bormi?"
    )


def test_lenta_chegaradan_oshmaydi(user):
    """Qabul mezoni: "lenta sahifasi <= 8 so'rov"."""
    c = Client()
    c.force_login(user)
    lenta_toldirish(soni=20, user=user)

    assert sorovlar(c, "/") <= LENTA_CHEGARASI


def test_MEHMON_uchun_ortiqcha_sorov_YOQ():
    """⚠️ Mehmon lentani eng ko'p ochadigan tur.

    Unda ovoz va saqlanganlar so'rovlari UMUMAN ketmasligi kerak —
    `user_votes_for` va `saqlangan_idlari` erta qaytadi.
    """
    lenta_toldirish(soni=20)
    mehmon = sorovlar(Client(), "/")

    # complaints + kategoriyalar. Sessiya/foydalanuvchi so'rovi yo'q.
    assert mehmon <= 3, f"Mehmon uchun {mehmon} so'rov — ortiqcha bor"


def test_filtrlangan_lenta_ham_barqaror(user):
    c = Client()
    c.force_login(user)
    lenta_toldirish(soni=20, user=user)

    oddiy = sorovlar(c, "/")
    filtrli = sorovlar(c, "/", sort="new", category="kat-1", generation="genz")

    assert filtrli == oddiy


def test_ikkinchi_sahifa_faqat_BITTA_qoshimcha_sorov(user):
    """⚠️ Kursor postini olish uchun bitta indeksli qidiruv.

    Bu OFFSET bilan solishtirganda ataylab qilingan almashuv: bitta
    arzon so'rov evaziga chuqur sahifalarda ham barqaror tezlik
    (D1-T12).
    """
    c = Client()
    c.force_login(user)
    muammolar = lenta_toldirish(soni=25, user=user)

    birinchi = sorovlar(c, "/")
    ikkinchi = sorovlar(c, "/", after=muammolar[5].pk)

    assert ikkinchi == birinchi + 1


# ===========================================================================
# Batafsil sahifa
# ===========================================================================
def batafsil_toldirish(*, yechimlar: int, user=None):
    muammo = ComplaintFactory()
    for i in range(yechimlar):
        fabrika = ExpertSolutionFactory if i % 3 == 0 else SolutionFactory
        yechim = fabrika(complaint=muammo, is_anonymous=(i % 5 == 0))
        if user is not None:
            cast_vote(
                target=yechim,
                vote_model=SolutionVote,
                target_field="solution",
                user=user,
                value=VoteValue.UP,
            )
    return muammo


def test_batafsil_sorov_soni_YECHIMLAR_SONIGA_BOGLIQ_EMAS(user):
    """Har yechimda muallif, karma, ekspert bayrog'i va ovoz holati bor."""
    c = Client()
    c.force_login(user)

    kam_muammo = batafsil_toldirish(yechimlar=2, user=user)
    kam = sorovlar(c, kam_muammo.get_absolute_url())

    kop_muammo = batafsil_toldirish(yechimlar=15, user=user)
    kop = sorovlar(c, kop_muammo.get_absolute_url())

    assert kam == kop, (
        f"So'rov soni yechimlar soniga bog'liq: {kam} -> {kop}. "
        "`select_related('author')` yoki ovoz to'plami tushib qolganmi?"
    )


def test_batafsil_chegaradan_oshmaydi(user):
    c = Client()
    c.force_login(user)
    muammo = batafsil_toldirish(yechimlar=15, user=user)

    assert sorovlar(c, muammo.get_absolute_url()) <= BATAFSIL_CHEGARASI


def test_MUALLIF_korinishi_BITTA_KAM_sorov_qiladi(user):
    """⚠️ Muallifga qo'shimcha narsalar ko'rinadi (qabul qilish tugmasi,
    tahrirlash havolasi) — ular so'rov QO'SHMAYDI.

    Aksincha, muallifda BITTA SO'ROV KAM bo'ladi: `views_count`
    yangilanmaydi, chunki muallifning o'z ko'rishlari sanalmaydi
    (aks holda post yozgan odam sanoqni o'zi shishirib qo'yardi).

    ⚠️ Bu testning birinchi versiyasi ikkalasini TENG deb kutgan edi va
       yiqildi — kod emas, TAXMIN noto'g'ri edi. Farqni tenglashtirish
       o'rniga uni qotirdik: shunda `views_count` mantiqi tasodifan
       o'zgarsa, bu test aytadi.
    """
    c = Client()
    c.force_login(user)

    ozimniki = ComplaintFactory(author=user)
    for _ in range(10):
        SolutionFactory(complaint=ozimniki)

    begona = batafsil_toldirish(yechimlar=10)

    ozi = sorovlar(c, ozimniki.get_absolute_url())
    boshqa = sorovlar(c, begona.get_absolute_url())

    assert ozi == boshqa - 1, (
        "Farq aynan bitta bo'lishi kerak: muallifda `views_count` "
        f"UPDATE'i ketmaydi. Olingan: o'ziniki={ozi}, begona={boshqa}"
    )


# ===========================================================================
# Saqlanganlar
# ===========================================================================
def test_saqlanganlar_sorov_soni_barqaror(user):
    c = Client()
    c.force_login(user)

    lenta_toldirish(soni=3, user=user)
    kam = sorovlar(c, "/saqlanganlar/")

    lenta_toldirish(soni=20, user=user, kategoriyalar=6)
    kop = sorovlar(c, "/saqlanganlar/")

    assert kam == kop


# ===========================================================================
# Qat'iy sonlar — jimgina o'sishga qarshi
# ===========================================================================
def test_QATIY_sonlar(user, django_assert_num_queries):
    """⚠️ Bu son O'ZGARSA — o'ylab ko'ring, keyin yangilang.

    Yuqoridagi testlar N+1 ni ushlaydi; bu esa "sekin o'sish"ni:
    har relizda bittadan so'rov qo'shilsa, bir yildan keyin lenta
    ikki barobar sekin bo'ladi va hech kim buni payqamaydi.

    Joriy holat (2026-08-29):
      lenta (kirgan) — 7 ta:
        1. muammolar (select_related: author, category)
        2. sessiya
        3. foydalanuvchi
        4. ovozlar (bitta to'plamli so'rov)
        5. saqlanganlar (bitta to'plamli so'rov)
        6. yon panel kategoriyalari (annotate)
        7. bloklangan mualliflar ro'yxati (D2-T11)

    ⚠️ 7-so'rov D2-T11 da qo'shildi va ONGLI qaror: bloklangan
       mualliflarni lentadan chiqarish uchun ro'yxat kerak. U BIR
       MARTA olinadi va so'rovga qiymat sifatida tushadi — ichma-ich
       `QuerySet` bo'lsa PostgreSQL uni har sahifada qayta bajarardi.
    """
    c = Client()
    c.force_login(user)
    lenta_toldirish(soni=20, user=user)
    c.get("/")  # sessiyani ilitamiz

    with django_assert_num_queries(7):
        c.get("/")
