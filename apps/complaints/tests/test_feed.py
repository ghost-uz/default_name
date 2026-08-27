"""Lenta ko'rinishlari (D1-T7)."""

from __future__ import annotations

import pytest
from django.urls import reverse

from apps.common.models import ModerationStatus
from apps.complaints.factories import CategoryFactory, ComplaintFactory
from apps.complaints.models import ComplaintStatus, Generation
from apps.complaints.selectors import STANDART_SARALASH, filtrni_oqish

pytestmark = pytest.mark.django_db
LENTA = "/"


# ===========================================================================
# Filtrni o'qish — noto'g'ri kirish 500 BERMASLIGI kerak
# ===========================================================================
@pytest.mark.parametrize(
    "xom",
    ["", "hot", "new", "top", "solved", "HOT", "<script>", "../../etc", "0"],
)
def test_notogri_sort_STANDARTGA_qaytadi(xom, rf):
    """⚠️ Bunday havolalar doim keladi: botlar, eski xatcho'plar, qo'lda
    tahrirlangan URL. Ularning hech biri 500 bermasligi kerak."""
    filtr = filtrni_oqish(rf.get(LENTA, {"sort": xom}).GET)
    assert filtr.sort in ("hot", "new", "top", "solved")
    if xom not in ("hot", "new", "top", "solved"):
        assert filtr.sort == STANDART_SARALASH


def test_notogri_avlod_tashlanadi(rf):
    filtr = filtrni_oqish(rf.get(LENTA, {"generation": "boomerang"}).GET)
    assert filtr.generation == ""


def test_notogri_kategoriya_TASHLANMAYDI(rf):
    """⚠️ Kategoriya ATAYLAB tekshirilmaydi.

    Mavjud bo'lmagan slug so'rovni bo'sh qiladi va foydalanuvchi
    "topilmadi" ni ko'radi. Uni jimgina tashlab yuborish "hammasini
    ko'rsatish" degani bo'lardi — ya'ni foydalanuvchiga yolg'on.
    """
    filtr = filtrni_oqish(rf.get(LENTA, {"category": "yoq-bunday"}).GET)
    assert filtr.category == "yoq-bunday"


# ===========================================================================
# Sahifa
# ===========================================================================
def test_lenta_ochiladi(client):
    javob = client.get(LENTA)
    assert javob.status_code == 200
    assert javob.templates[0].name == "complaints/feed.html"


def test_qabul_mezoni_uchala_parametr_BIRGA_ishlaydi(client):
    """Qabul mezoni: `?sort=hot&category=moliya&generation=genz` ishlaydi."""
    moliya = CategoryFactory(slug="moliya")
    boshqa = CategoryFactory(slug="boshqa")

    kerakli = ComplaintFactory(
        category=moliya, generation_tag=Generation.GENZ, title="Kerakli post"
    )
    ComplaintFactory(category=boshqa, generation_tag=Generation.GENZ)
    ComplaintFactory(category=moliya, generation_tag=Generation.BOOMER)

    javob = client.get(
        LENTA, {"sort": "hot", "category": "moliya", "generation": "genz"}
    )

    assert javob.status_code == 200
    assert list(javob.context["complaints"]) == [kerakli]


def test_bosh_lentada_hamma_KORINADI(client):
    ComplaintFactory.create_batch(3)
    javob = client.get(LENTA)
    assert len(javob.context["complaints"]) == 3


def test_yechilgan_tabi_FILTRLAYDI(client):
    """⚠️ "Yechilgan" maketda saralash tabi, amalda esa filtr."""
    yechilgan = ComplaintFactory(status=ComplaintStatus.SOLVED)
    ComplaintFactory(status=ComplaintStatus.OPEN)

    javob = client.get(LENTA, {"sort": "solved"})
    assert list(javob.context["complaints"]) == [yechilgan]


def test_saralash_tartibi(client):
    past = ComplaintFactory(hot_score=1.0, title="Past")
    baland = ComplaintFactory(hot_score=99.0, title="Baland")

    qaynoq = client.get(LENTA, {"sort": "hot"}).context["complaints"]
    assert list(qaynoq) == [baland, past]

    yangi = client.get(LENTA, {"sort": "new"}).context["complaints"]
    assert list(yangi) == [baland, past]  # oxirgi yaratilgan birinchi


# ===========================================================================
# Ko'rinish invariantlari (D2-T3, D1-T6)
# ===========================================================================
def test_yashirilgan_post_lentaga_TUSHMAYDI(client):
    """⚠️ `visible()` — moderatsiya filtri ATAYLAB standart emas,
    shuning uchun har ommaviy so'rovda ochiq yozilishi shart."""
    ComplaintFactory(moderation_status=ModerationStatus.HIDDEN)
    ComplaintFactory(moderation_status=ModerationStatus.PENDING)
    korinadigan = ComplaintFactory()

    javob = client.get(LENTA)
    assert list(javob.context["complaints"]) == [korinadigan]


def test_ochirilgan_post_lentaga_TUSHMAYDI(client):
    ochirilgan = ComplaintFactory()
    ochirilgan.delete()
    qolgan = ComplaintFactory()

    javob = client.get(LENTA)
    assert list(javob.context["complaints"]) == [qolgan]


def test_anonim_post_lentada_ISMNI_KORSATMAYDI(client):
    """D1-T6 invarianti — endi HAQIQIY sahifada."""
    anonim = ComplaintFactory(is_anonymous=True)

    matn = client.get(LENTA).content.decode()
    assert anonim.author.username not in matn
    assert "Anonim" in matn


# ===========================================================================
# Holat URL'da (D1-T7 ning butun ma'nosi)
# ===========================================================================
def test_tab_havolasi_boshqa_filtrlarni_SAQLAYDI(client):
    """⚠️ Maketdagi `href="?sort=new"` boshqa parametrlarni yo'q qilardi:
    foydalanuvchi "Moliya + Gen Z" ni tanlab, tabni bosса filtri
    jimgina tushib ketardi."""
    CategoryFactory(slug="moliya")
    matn = client.get(
        LENTA, {"sort": "hot", "category": "moliya", "generation": "genz"}
    ).content.decode()

    assert "sort=new" in matn
    assert "category=moliya" in matn
    # "Yangi" tabi havolasida uchala parametr ham bo'lishi kerak
    assert "generation=genz" in matn


def test_hammasi_havolasi_filtrni_OCHIRADI(client):
    CategoryFactory(slug="moliya")
    matn = client.get(LENTA, {"category": "moliya"}).content.decode()
    # `{% lenta_url category='' %}` -> parametr butunlay yo'qoladi
    assert 'href="/"' in matn


def test_bosh_holatda_matn_FILTRGA_QARAB_ozgaradi(client):
    CategoryFactory(slug="moliya")

    bosh = client.get(LENTA).content.decode()
    assert "Birinchi dardni siz yozing" in bosh

    filtrli = client.get(LENTA, {"category": "moliya"}).content.decode()
    assert "Bu filtrda hech nima yo'q" in filtrli


# ===========================================================================
# Yon panel
# ===========================================================================
def test_yon_panel_sanogi_FAQAT_KORINADIGANLARNI_sanaydi(client):
    """⚠️ Oddiy `Count("complaints")` o'chirilgan va yashirilganlarni ham
    sanardi: yon panel "Moliya 3" deb yozardi, ochsangiz 1 ta chiqardi."""
    moliya = CategoryFactory(slug="moliya")
    ComplaintFactory(category=moliya)
    ComplaintFactory(category=moliya, moderation_status=ModerationStatus.HIDDEN)
    ochirilgan = ComplaintFactory(category=moliya)
    ochirilgan.delete()

    javob = client.get(LENTA)
    kategoriya = next(k for k in javob.context["kategoriyalar"] if k.slug == "moliya")
    assert kategoriya.postlar_soni == 1


def test_faolsiz_kategoriya_yon_panelda_YOQ(client):
    CategoryFactory(slug="eski", is_active=False)
    javob = client.get(LENTA)
    assert [k.slug for k in javob.context["kategoriyalar"]] == []


# ===========================================================================
# So'rov soni (D1-T14 ga tayyorgarlik)
# ===========================================================================
def test_lenta_sorov_soni_KARTALAR_SONIGA_BOGLIQ_EMAS(
    client, django_assert_max_num_queries
):
    """⚠️ N+1 ning klassik joyi: har kartada muallif, kategoriya va
    "men ovoz berganmanmi?" bor. Ehtiyotsizlikda 20 karta = 60+ so'rov.

    Bu yerda kirmagan foydalanuvchi tekshiriladi — u lentani eng ko'p
    ochadigan tur.
    """
    ComplaintFactory.create_batch(15)
    with django_assert_max_num_queries(4):
        assert client.get(LENTA).status_code == 200


def test_kirgan_foydalanuvchida_ham_sorov_soni_barqaror(
    auth_client, django_assert_max_num_queries
):
    ComplaintFactory.create_batch(15)
    # +1 ovozlar so'rovi, +2 sessiya/foydalanuvchi
    with django_assert_max_num_queries(8):
        assert auth_client.get(LENTA).status_code == 200


def test_sahifa_hajmi_cheklangan(client, settings):
    from apps.complaints.selectors import SAHIFA_HAJMI

    ComplaintFactory.create_batch(SAHIFA_HAJMI + 5)
    javob = client.get(LENTA)
    assert len(javob.context["complaints"]) == SAHIFA_HAJMI


def test_lenta_url_manzili_feed_nomi_bilan_bogliq():
    assert reverse("feed") == LENTA


def test_yon_panel_TARTIBI_order_boyicha(client):
    """⚠️ GOTCHA (jonli sahifada topildi): `annotate()` GROUP BY hosil
    qilganda Django 3.1 dan beri `Meta.ordering` ni JIMGINA tashlaydi.

    So'rovda `ORDER BY` umuman bo'lmaydi va PostgreSQL qatorlarni o'zi
    qulay tartibda qaytaradi — yon panel har deploy'da boshqacha
    ko'rinishi mumkin. Ogohlantirish ham, xato ham yo'q.

    Shu sababli tekshiruv SANOQQA emas, TARTIBGA qaraydi: sanoq testi
    bu xatoni ushlamagan edi.
    """
    CategoryFactory(name="Boshqa", slug="boshqa", order=100)
    CategoryFactory(name="Karyera", slug="karyera", order=10)
    CategoryFactory(name="Moliya", slug="moliya", order=30)

    javob = client.get(LENTA)
    assert [k.slug for k in javob.context["kategoriyalar"]] == [
        "karyera",
        "moliya",
        "boshqa",
    ]
