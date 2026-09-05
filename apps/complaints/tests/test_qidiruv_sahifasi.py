"""Qidiruv sahifasi va filtrlar (D4-T3)."""

from __future__ import annotations

import pytest
from django.test import Client
from django.urls import reverse

from apps.common.models import ModerationStatus
from apps.complaints.factories import CategoryFactory, ComplaintFactory
from apps.complaints.models import ComplaintStatus, Generation

pytestmark = pytest.mark.django_db

QIDIRUV = "/qidiruv/"


def matn(javob) -> str:
    return javob.content.decode()


# ===========================================================================
# 1. Sahifa ochiladi
# ===========================================================================
def test_sorovsiz_sahifa_ochiladi(anonymous_client):
    """⚠️ Bo'sh `q` — normal holat (sarlavhadagi formadan Enter). 500
    yoki 404 bo'lmasligi kerak."""
    javob = anonymous_client.get(QIDIRUV)

    assert javob.status_code == 200
    assert "Nimani qidiryapsiz?" in matn(javob)


def test_natija_topiladi(anonymous_client):
    """⚠️ Tekshiruv sarlavhaning MOS KELMAGAN qismi bo'yicha: mos so'z
    `<mark>` bilan o'ralgani uchun butun sarlavha satr sifatida
    javobda BO'LMAYDI ("<mark>Ipoteka</mark> olish qiyinmi")."""
    ComplaintFactory(title="Ipoteka olish qiyinmi")
    ComplaintFactory(title="Mashina sotib olish")

    sahifa = matn(anonymous_client.get(QIDIRUV, {"q": "ipoteka"}))

    assert "olish qiyinmi" in sahifa
    assert "Mashina sotib olish" not in sahifa


def test_natijalar_soni_korsatiladi(anonymous_client):
    """⚠️ Lentada `COUNT(*)` ataylab yo'q, qidiruvda ataylab bor: "12 ta
    natija" — so'rov qanchalik aniq bo'lganini ko'rsatadigan signal."""
    for i in range(3):
        ComplaintFactory(title=f"Ipoteka masalasi {i}")

    sahifa = matn(anonymous_client.get(QIDIRUV, {"q": "ipoteka"}))

    assert "3 ta natija topildi" in sahifa


# ===========================================================================
# 2. Ajratib ko'rsatish
# ===========================================================================
def test_topilgan_soz_AJRATILADI(anonymous_client):
    ComplaintFactory(title="Ipoteka olish qiyinmi")

    sahifa = matn(anonymous_client.get(QIDIRUV, {"q": "ipoteka"}))

    assert "<mark>Ipoteka</mark>" in sahifa


def test_KIRILCHA_post_LOTINCHA_sorovda_ham_ajratiladi(anonymous_client):
    """⚠️ `SearchHeadline` da ishlamaydigan holat (`ajratish.py` izohi)."""
    ComplaintFactory(title="Ипотека олиш")

    sahifa = matn(anonymous_client.get(QIDIRUV, {"q": "ipoteka"}))

    assert "<mark>Ипотека</mark>" in sahifa


def test_LENTADA_ajratish_YOQ(anonymous_client):
    """⚠️ Bitta karta shabloni ikkala sahifaga xizmat qiladi. Lentada
    `ajratilgan_*` bo'sh bo'lishi va karta asl matnga qaytishi kerak."""
    ComplaintFactory(title="Ipoteka olish")

    sahifa = matn(anonymous_client.get("/"))

    assert "Ipoteka olish" in sahifa
    assert "<mark>" not in sahifa


def test_sarlavhadagi_HTML_ekranlanadi(anonymous_client):
    """⚠️ Ajratish HTML qaytaradi — uchidan-uchiga tekshiruv."""
    ComplaintFactory(title="<script>alert(1)</script> ipoteka")

    sahifa = matn(anonymous_client.get(QIDIRUV, {"q": "ipoteka"}))

    assert "<script>alert(1)</script>" not in sahifa
    assert "&lt;script&gt;" in sahifa


# ===========================================================================
# 3. Filtrlar
# ===========================================================================
def test_kategoriya_filtri(anonymous_client):
    moliya = CategoryFactory(slug="moliya", name="Moliya")
    ComplaintFactory(title="Ipoteka ANIQMOLIYA", category=moliya)
    ComplaintFactory(title="Ipoteka ANIQBOSHQA")

    sahifa = matn(anonymous_client.get(QIDIRUV, {"q": "ipoteka", "category": "moliya"}))

    assert "ANIQMOLIYA" in sahifa
    assert "ANIQBOSHQA" not in sahifa


def test_avlod_filtri(anonymous_client):
    ComplaintFactory(title="Ipoteka ANIQYOSH", generation_tag=Generation.GENZ)
    ComplaintFactory(title="Ipoteka ANIQKATTA", generation_tag=Generation.BOOMER)

    sahifa = matn(anonymous_client.get(QIDIRUV, {"q": "ipoteka", "generation": "genz"}))

    assert "ANIQYOSH" in sahifa
    assert "ANIQKATTA" not in sahifa


def test_holat_filtri(anonymous_client):
    ComplaintFactory(title="Ipoteka ANIQYECHIM", status=ComplaintStatus.SOLVED)
    ComplaintFactory(title="Ipoteka ANIQOCHIQ", status=ComplaintStatus.OPEN)

    sahifa = matn(anonymous_client.get(QIDIRUV, {"q": "ipoteka", "status": "solved"}))

    assert "ANIQYECHIM" in sahifa
    assert "ANIQOCHIQ" not in sahifa


def test_NOTOGRI_holat_TASHLANADI(anonymous_client):
    """⚠️ `generation` bilan bir xil ishlov: yopiq ro'yxat, noma'lum
    qiymat 500 bermaydi va filtr umuman qo'llanmaydi."""
    ComplaintFactory(title="Ipoteka ANIQOCHIQ")

    javob = anonymous_client.get(QIDIRUV, {"q": "ipoteka", "status": "<script>"})

    assert javob.status_code == 200
    assert "ANIQOCHIQ" in matn(javob)


def test_filtr_HAVOLASI_sorovni_saqlaydi(anonymous_client):
    """⚠️ `lenta_url` boshqa parametrlarni saqlaydi. Usiz kategoriya
    tanlanganda `q` tushib ketardi va foydalanuvchi bo'sh sahifaga
    tushardi."""
    CategoryFactory(slug="moliya", name="Moliya")
    ComplaintFactory(title="Ipoteka masalasi")

    sahifa = matn(anonymous_client.get(QIDIRUV, {"q": "ipoteka"}))

    assert "q=ipoteka" in sahifa
    assert "category=moliya" in sahifa


# ===========================================================================
# 4. Bo'sh natija va takliflar (qabul mezoni)
# ===========================================================================
def test_XATO_yozilganda_TAKLIF_beriladi(anonymous_client):
    """⚠️ D4-T3 qabul mezoni: "natija topilmasa taklif beriladi"."""
    ComplaintFactory(title="Ipoteka olish qiyinmi")

    sahifa = matn(anonymous_client.get(QIDIRUV, {"q": "ipotaka"}))

    assert "Balki shuni qidirgandirsiz?" in sahifa
    # ⚠️ Taklif ro'yxatida sarlavha AJRATILMAYDI (u boshqa so'rov uchun
    #    havola), shuning uchun to'liq matn bo'yicha tekshiriladi.
    assert "Ipoteka olish qiyinmi" in sahifa


def test_natija_BOR_bolsa_taklif_KORSATILMAYDI(anonymous_client):
    """⚠️ Taklif topilgan javobdan chalg'itardi."""
    ComplaintFactory(title="Ipoteka olish qiyinmi")

    sahifa = matn(anonymous_client.get(QIDIRUV, {"q": "ipoteka"}))

    assert "Balki shuni qidirgandirsiz?" not in sahifa


def test_ALOQASIZ_sorovda_taklif_ham_YOQ(anonymous_client):
    ComplaintFactory(title="Ipoteka olish qiyinmi")

    sahifa = matn(anonymous_client.get(QIDIRUV, {"q": "velosiped"}))

    assert "Hech narsa topilmadi" in sahifa
    assert "Balki shuni qidirgandirsiz?" not in sahifa


def test_filtr_tufayli_bosh_bolsa_BOSHQA_matn(anonymous_client):
    """⚠️ "Hech narsa topilmadi" bu yerda YOLG'ON bo'lardi: natija bor,
    faqat filtr uni chiqarmayapti. Foydalanuvchi so'rovni o'zgartirishga
    urinardi — aslida filtrni kengaytirishi kerak edi."""
    ComplaintFactory(title="Ipoteka masalasi")

    sahifa = matn(
        anonymous_client.get(QIDIRUV, {"q": "ipoteka", "generation": "boomer"})
    )

    assert "Bu filtrda hech nima yo'q" in sahifa


# ===========================================================================
# 5. Ko'rinish invarianti (D2-T3)
# ===========================================================================
def test_YASHIRILGAN_post_qidiruv_sahifasida_YOQ(anonymous_client):
    ComplaintFactory(
        title="Ipoteka yashirin", moderation_status=ModerationStatus.HIDDEN
    )

    sahifa = matn(anonymous_client.get(QIDIRUV, {"q": "ipoteka"}))

    assert "Ipoteka yashirin" not in sahifa


def test_YASHIRILGAN_post_TAKLIFDA_ham_YOQ(anonymous_client):
    """⚠️ Ikkinchi yo'l — oson unutiladigani."""
    ComplaintFactory(
        title="Ipoteka yashirin", moderation_status=ModerationStatus.HIDDEN
    )

    sahifa = matn(anonymous_client.get(QIDIRUV, {"q": "ipotaka"}))

    assert "Ipoteka yashirin" not in sahifa


def test_qidiruv_sahifasi_NOINDEX(anonymous_client):
    """⚠️ Qidiruv natijalari cheksiz kombinatsiya beradi (`q` × filtr ×
    sahifa). Indekslansa sayt o'z-o'zi bilan raqobatlashadigan minglab
    sifatsiz sahifa hosil qilardi — D4-T4/T5 uchun ham muhim."""
    sahifa = matn(anonymous_client.get(QIDIRUV, {"q": "ipoteka"}))

    assert 'name="robots" content="noindex, follow"' in sahifa


# ===========================================================================
# 6. Sahifalash va buzuq kiritma
# ===========================================================================
def test_sahifalash_ishlaydi(anonymous_client):
    for i in range(25):
        ComplaintFactory(title=f"Ipoteka masalasi {i}")

    birinchi = matn(anonymous_client.get(QIDIRUV, {"q": "ipoteka"}))
    ikkinchi = matn(anonymous_client.get(QIDIRUV, {"q": "ipoteka", "sahifa": "2"}))

    assert "Keyingi" in birinchi
    assert "1 / 2" in birinchi
    assert "2 / 2" in ikkinchi
    assert "Oldingi" in ikkinchi


@pytest.mark.parametrize("sahifa", ["abc", "0", "-1", "999", "", "1e5"])
def test_NOTOGRI_sahifa_raqami_500_BERMAYDI(anonymous_client, sahifa):
    """⚠️ `get_page()` `page()` o'rniga — bunday havolalar botlardan va
    qo'lda tahrirlangan URL'lardan doim keladi (D1-T7 bilan bir xil
    mantiq)."""
    ComplaintFactory(title="Ipoteka masalasi")

    javob = anonymous_client.get(QIDIRUV, {"q": "ipoteka", "sahifa": sahifa})

    assert javob.status_code == 200


def test_filtr_ozgarganda_sahifa_BOSHIDAN(anonymous_client):
    """⚠️ 3-sahifada turib kategoriyani almashtirgan foydalanuvchi yangi
    filtrning 3-sahifasiga tushardi — ko'pincha bo'sh sahifaga."""
    CategoryFactory(slug="moliya", name="Moliya")
    for i in range(25):
        ComplaintFactory(title=f"Ipoteka masalasi {i}")

    sahifa = matn(anonymous_client.get(QIDIRUV, {"q": "ipoteka", "sahifa": "2"}))

    assert "sahifa=2&amp;category=moliya" not in sahifa
    assert "category=moliya" in sahifa


def test_JUDA_UZUN_sorov_chegaralanadi(anonymous_client):
    """⚠️ Cheksiz so'rov `websearch_to_tsquery` ni ham, trigramni ham
    sekinlashtiradi va bunday so'rovlar odamdan emas — skriptdan
    keladi."""
    javob = anonymous_client.get(QIDIRUV, {"q": "ipoteka " * 500})

    assert javob.status_code == 200


# ===========================================================================
# 7. Sarlavhadagi forma — D4-T3 gacha ochiq turgan xato
# ===========================================================================
def test_SARLAVHADAGI_forma_qidiruvga_yuboradi(anonymous_client):
    """⚠️⚠️ D4-T3 gacha forma `{% url 'feed' %}` ga yuborardi va lenta
    `q` ni JIMGINA e'tiborsiz qoldirardi: Enter bosilardi, sahifa
    yangilanardi va o'sha lenta qaytardi.

    Bu "qidiruv ishlamayapti" ning eng yomon shakli — hech qanday
    belgi bermaydigani.
    """
    sahifa = matn(anonymous_client.get("/"))

    assert f'action="{reverse("qidiruv")}"' in sahifa


def test_qidiruv_manzili_ozbekcha():
    """URL'lar o'zbekcha (config/urls.py qoidasi, SEO uchun)."""
    assert reverse("qidiruv") == QIDIRUV


# ===========================================================================
# 8. Bloklangan muallif (D2-T11)
# ===========================================================================
def test_BLOKLANGAN_muallif_qidiruvda_chiqmaydi(user, other_user):
    from apps.accounts.models import UserBlock

    ComplaintFactory(title="Ipoteka ANIQBLOK", author=other_user)
    ComplaintFactory(title="Ipoteka ANIQOCHIQ", author=user)
    UserBlock.objects.create(user=user, blocked=other_user)

    c = Client()
    c.force_login(user)
    sahifa = matn(c.get(QIDIRUV, {"q": "ipoteka"}))

    assert "ANIQOCHIQ" in sahifa
    assert "ANIQBLOK" not in sahifa
