"""Kursor bo'yicha sahifalash (D1-T12)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.complaints.factories import CategoryFactory, ComplaintFactory
from apps.complaints.selectors import (
    SAHIFA_HAJMI,
    LentaFiltri,
    kursorni_oqish,
    lenta_sahifasi,
)

pytestmark = pytest.mark.django_db
HTMX = {"HTTP_HX_REQUEST": "true"}


def postlar_yaratish(soni: int) -> list:
    """Aniq vaqt farqi bilan — tartib bashorat qilinadigan bo'lsin."""
    boshlanish = timezone.now() - timedelta(hours=soni)
    return [
        ComplaintFactory(
            title=f"Muammo raqami {i}", created_at=boshlanish + timedelta(hours=i)
        )
        for i in range(soni)
    ]


# ===========================================================================
# Kursor mantiqi
# ===========================================================================
def test_birinchi_sahifa_toliq_va_kursor_beradi():
    postlar_yaratish(SAHIFA_HAJMI + 5)

    sahifa, kursor = lenta_sahifasi(LentaFiltri(sort="new"))

    assert len(sahifa) == SAHIFA_HAJMI
    assert kursor == sahifa[-1].pk


def test_OXIRGI_sahifada_kursor_YOQ():
    """Tugma faqat haqiqatan yana element bo'lsa ko'rinsin."""
    postlar_yaratish(SAHIFA_HAJMI)

    sahifa, kursor = lenta_sahifasi(LentaFiltri(sort="new"))

    assert len(sahifa) == SAHIFA_HAJMI
    assert kursor is None


def test_ikkinchi_sahifa_TAKRORLANMAYDI_va_tushib_qolmaydi():
    """⚠️ D1-T12 ning butun ma'nosi.

    OFFSET bilan: sahifalar orasida yangi post qo'shilsa hamma narsa
    bir pozitsiyaga suriladi va foydalanuvchi ALLAQACHON KO'RGAN postni
    yana ko'radi (yoki bittasi butunlay tushib qoladi).
    """
    hammasi = postlar_yaratish(SAHIFA_HAJMI + 7)
    kutilgan = [
        m.pk for m in sorted(hammasi, key=lambda m: (-m.created_at.timestamp(), -m.pk))
    ]

    birinchi, kursor = lenta_sahifasi(LentaFiltri(sort="new"))
    ikkinchi, oxirgi_kursor = lenta_sahifasi(LentaFiltri(sort="new"), after_pk=kursor)

    olingan = [m.pk for m in birinchi] + [m.pk for m in ikkinchi]
    assert olingan == kutilgan
    assert len(set(olingan)) == len(olingan)  # takror yo'q
    assert oxirgi_kursor is None


def test_yangi_post_qoshilsa_ikkinchi_sahifa_SURILMAYDI():
    """⚠️ Aynan OFFSET sahifalashining kasali.

    Birinchi sahifa olingandan KEYIN yangi post qo'shiladi. OFFSET 20
    bo'lsa, endi 21-element boshqa post bo'lardi va foydalanuvchi
    birinchi sahifada ko'rgan postni QAYTA ko'rardi.
    """
    postlar_yaratish(SAHIFA_HAJMI + 3)

    birinchi, kursor = lenta_sahifasi(LentaFiltri(sort="new"))
    birinchi_pklar = {m.pk for m in birinchi}

    ComplaintFactory(title="Sahifalar orasida qo'shilgan post")

    ikkinchi, _ = lenta_sahifasi(LentaFiltri(sort="new"), after_pk=kursor)

    assert not (birinchi_pklar & {m.pk for m in ikkinchi})


def test_kursor_FILTRLARNI_hisobga_oladi():
    moliya = CategoryFactory(slug="moliya")
    boshqa = CategoryFactory(slug="boshqa")
    for i in range(SAHIFA_HAJMI + 3):
        ComplaintFactory(category=moliya if i % 2 else boshqa)

    filtr = LentaFiltri(sort="new", category="moliya")
    birinchi, kursor = lenta_sahifasi(filtr)
    ikkinchi, _ = lenta_sahifasi(filtr, after_pk=kursor)

    assert all(m.category.slug == "moliya" for m in birinchi + ikkinchi)


def test_TENG_qiymatlarda_ham_takrorlanmaydi():
    """⚠️ Tenglikni uzish zanjiri: `hot_score` bir xil bo'lsa `created_at`,
    u ham teng bo'lsa `id` bo'yicha ajratiladi.

    Usiz teng ballli postlar sahifalar chegarasida yo'qolardi yoki
    ikkilanardi — va buni faqat haqiqiy ma'lumotda payqash mumkin.
    """
    bir_vaqt = timezone.now()
    for i in range(SAHIFA_HAJMI + 5):
        ComplaintFactory(title=f"Teng {i}", created_at=bir_vaqt, hot_score=1.0)

    filtr = LentaFiltri(sort="hot")
    birinchi, kursor = lenta_sahifasi(filtr)
    ikkinchi, _ = lenta_sahifasi(filtr, after_pk=kursor)

    pklar = [m.pk for m in birinchi + ikkinchi]
    assert len(pklar) == SAHIFA_HAJMI + 5
    assert len(set(pklar)) == len(pklar)


def test_barcha_saralashlarda_ishlaydi():
    postlar_yaratish(SAHIFA_HAJMI + 3)

    for sort in ("hot", "new", "top"):
        filtr = LentaFiltri(sort=sort)
        birinchi, kursor = lenta_sahifasi(filtr)
        ikkinchi, _ = lenta_sahifasi(filtr, after_pk=kursor)
        pklar = [m.pk for m in birinchi + ikkinchi]
        assert len(set(pklar)) == len(pklar), f"{sort} da takror bor"


def test_OCHIRILGAN_kursor_posti_sahifani_buzmaydi():
    """Kursor posti moderatsiya qilinishi mumkin — sahifalash to'xtamasin."""
    hammasi = postlar_yaratish(SAHIFA_HAJMI + 5)
    _, kursor = lenta_sahifasi(LentaFiltri(sort="new"))

    # Kursor posti o'chiriladi
    next(m for m in hammasi if m.pk == kursor).delete()

    ikkinchi, _ = lenta_sahifasi(LentaFiltri(sort="new"), after_pk=kursor)
    assert len(ikkinchi) == 5


def test_mavjud_bolmagan_kursor_BIRINCHI_sahifani_beradi():
    """404 dan ko'ra tushunarli xulq."""
    postlar_yaratish(3)
    sahifa, _ = lenta_sahifasi(LentaFiltri(sort="new"), after_pk=999999)
    assert len(sahifa) == 3


@pytest.mark.parametrize("xom", ["", "abc", "-5", "1.5", "<script>", None])
def test_notogri_kursor_500_BERMAYDI(rf, xom):
    """Bunday havolalar botlardan va qo'lda tahrirlangan URL'lardan keladi."""
    sorov = rf.get("/", {} if xom is None else {"after": xom})
    assert kursorni_oqish(sorov.GET) is None


# ===========================================================================
# Sahifa va HTMX
# ===========================================================================
def test_lentada_YANA_YUKLASH_tugmasi_chiqadi(client):
    postlar_yaratish(SAHIFA_HAJMI + 1)
    matn = client.get("/").content.decode()

    assert "Yana yuklash" in matn
    assert "yana-yuklash" in matn


def test_kam_post_bolsa_tugma_YOQ(client):
    postlar_yaratish(3)
    assert "Yana yuklash" not in client.get("/").content.decode()


def test_HTMX_sorovi_FAQAT_KARTALARNI_qaytaradi(client):
    """⚠️ Butun sahifani qaytarish yon panel va sarlavhani qaytadan
    qurish degani — bekorga trafik, va HTMX uni baribir tashlab
    yuborardi."""
    postlar_yaratish(SAHIFA_HAJMI + 3)
    _, kursor = lenta_sahifasi(LentaFiltri())

    javob = client.get("/", {"after": kursor}, **HTMX)
    matn = javob.content.decode()

    assert javob.status_code == 200
    assert javob.templates[0].name == "complaints/_feed_sahifa.html"
    assert "<!doctype html>" not in matn.lower()
    assert "<article" in matn


def test_JS_siz_havola_TOLIQ_sahifani_beradi(client):
    """Progressiv yaxshilanish: HTMX bo'lmasa oddiy havola ishlaydi."""
    postlar_yaratish(SAHIFA_HAJMI + 3)
    _, kursor = lenta_sahifasi(LentaFiltri())

    javob = client.get("/", {"after": kursor})  # HX-Request YO'Q

    assert javob.templates[0].name == "complaints/feed.html"
    assert len(javob.context["complaints"]) == 3


def test_yana_yuklash_havolasi_FILTRLARNI_saqlaydi(client):
    """⚠️ Usiz "Moliya + Gen Z" filtrida ikkinchi sahifa BUTUN lentani
    ko'rsatardi."""
    moliya = CategoryFactory(slug="moliya")
    for _ in range(SAHIFA_HAJMI + 2):
        ComplaintFactory(category=moliya, generation_tag="genz")

    matn = client.get(
        "/", {"sort": "new", "category": "moliya", "generation": "genz"}
    ).content.decode()

    assert "category=moliya" in matn
    assert "generation=genz" in matn
    assert "after=" in matn


def test_filtr_ozgarganda_kursor_TUSHIRILADI(client):
    """⚠️ Aks holda "Yangi" tabiga o'tganda eski kursor qolib,
    foydalanuvchi lentaning o'rtasiga tushardi."""
    postlar_yaratish(SAHIFA_HAJMI + 3)
    _, kursor = lenta_sahifasi(LentaFiltri())

    matn = client.get("/", {"after": kursor}).content.decode()

    # Tab havolalarida `after` bo'lmasligi kerak
    assert "?sort=new&amp;after=" not in matn
    assert "?sort=top&amp;after=" not in matn


def test_sahifalash_sorov_soni_BARQAROR(client, django_assert_max_num_queries):
    """Qabul mezoni: "20-sahifada ham so'rov vaqti barqaror".

    ⚠️ Vaqt mashinaga bog'liq, so'rov soni esa bog'liq emas — shuning
       uchun o'lchanadigan shakl shu. Kursor uchun +1 so'rov (kursor
       postini olish), OFFSET esa qo'shimcha so'rov qo'shmasdi, LEKIN
       har sahifada ko'proq QATOR o'qirdi.
    """
    postlar_yaratish(SAHIFA_HAJMI * 3)

    birinchi = client.get("/")
    kursor = birinchi.context["keyingi_kursor"]

    with django_assert_max_num_queries(6):
        client.get("/", {"after": kursor})
