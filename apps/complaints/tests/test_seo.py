"""Kanonik manzil, Open Graph metalari va OG rasm vazifasi (D4-T4)."""

from __future__ import annotations

import re

import pytest
from django.test import Client
from django.urls import URLPattern, URLResolver, get_resolver, reverse
from django.urls.exceptions import NoReverseMatch

from apps.common.models import ModerationStatus
from apps.complaints.factories import CategoryFactory, ComplaintFactory
from apps.complaints.models import Complaint
from apps.complaints.tasks import og_rasmni_yangilash

pytestmark = pytest.mark.django_db


def matn(javob) -> str:
    return javob.content.decode()


def meta(sahifa: str, xossa: str) -> str | None:
    """`<meta property="og:title" content="...">` dan qiymatni oladi."""
    moslik = re.search(
        rf'<meta (?:property|name)="{re.escape(xossa)}" content="([^"]*)"', sahifa
    )
    return moslik.group(1) if moslik else None


def kanonik(sahifa: str) -> str | None:
    moslik = re.search(r'<link rel="canonical" href="([^"]*)"', sahifa)
    return moslik.group(1) if moslik else None


# ===========================================================================
# 1. Kanonik manzil
# ===========================================================================
def test_lentada_kanonik_bor_va_MUTLAQ(anonymous_client):
    """⚠️ Nisbiy kanonik rasman ruxsat etilgan, lekin ijtimoiy tarmoq
    skanerlari va ba'zi vositalar uni noto'g'ri o'qiydi."""
    url = kanonik(matn(anonymous_client.get("/")))

    assert url == "http://testserver/"


def test_muammo_sahifasi_OZ_kanonigiga_ega(anonymous_client):
    """⚠️ D4-T4 qabul mezoni: "har muammo sahifasi o'z canonical URL'iga
    ega"."""
    muammo = ComplaintFactory(title="Ipoteka olish")

    url = kanonik(matn(anonymous_client.get(muammo.get_absolute_url())))

    assert url == f"http://testserver{muammo.get_absolute_url()}"


def test_KATEGORIYA_parametri_kanonikda_QOLADI(anonymous_client):
    """⚠️⚠️ Bu qoidaning narxi jonli loyihada ko'rilgan: kanonik faqat
    `request.path` dan qurilsa, kategoriya sahifasi bosh sahifaga
    kanoniklashardi va Search Console uni "Duplicate, not canonical"
    deb indeksdan chiqarardi."""
    CategoryFactory(slug="moliya", name="Moliya")

    url = kanonik(matn(anonymous_client.get("/", {"category": "moliya"})))

    assert url == "http://testserver/?category=moliya"


@pytest.mark.parametrize(
    ("parametrlar", "kutilgan"),
    [
        # Saralash — bir xil kontent, boshqa tartib.
        ({"sort": "new"}, "http://testserver/"),
        # Avlod — qolsa 8×3 = 24 ta yupqa sahifa hosil bo'lardi.
        ({"generation": "genz"}, "http://testserver/"),
        # Sahifalash.
        ({"after": "5"}, "http://testserver/"),
        # Aralash: faqat `category` qoladi.
        (
            {"category": "moliya", "sort": "top", "generation": "genz", "after": "9"},
            "http://testserver/?category=moliya",
        ),
    ],
)
def test_kanonik_ORTIQCHA_parametrlarni_tashlaydi(
    anonymous_client, parametrlar, kutilgan
):
    CategoryFactory(slug="moliya", name="Moliya")

    assert kanonik(matn(anonymous_client.get("/", parametrlar))) == kutilgan


def test_TAKRORIY_parametr_bitta_qiymatga_keladi(anonymous_client):
    """⚠️ `?category=a&category=b` bir xil sahifaga ikki xil kanonik
    berishi mumkin edi."""
    sahifa = matn(anonymous_client.get("/?category=moliya&category=huquq"))

    assert kanonik(sahifa) == "http://testserver/?category=huquq"


def test_QIDIRUV_sahifasida_kanonik_YOQ(anonymous_client):
    """⚠️ Sahifa `noindex` da. "Meni indekslama" va "haqiqiy manzilim
    mana bu" — qarama-qarshi signal."""
    sahifa = matn(anonymous_client.get("/qidiruv/", {"q": "ipoteka"}))

    assert kanonik(sahifa) is None
    assert meta(sahifa, "robots") == "noindex, follow"


def test_HAR_OMMAVIY_sahifada_kanonik_YOKI_noindex_BOR(anonymous_client, user):
    """⚠️ GUARD: yangi sahifa qo'shilganda SEO metalari unutilmasin.

    Ikkalasidan biri bo'lishi SHART: yo sahifa indekslanadi (kanonik
    bilan), yo indekslanmaydi (`noindex` bilan). Ikkalasi ham
    bo'lmasa — Google sahifani o'zi qanday tushunsa shunday
    indekslaydi va bu har doim yomon variant.
    """
    muammo = ComplaintFactory(title="Ipoteka")
    qiymatlar = {"slug": muammo.slug, "pk": muammo.pk, "username": user.username}

    c = Client()
    c.force_login(user)
    tekshirildi = 0

    for nom, ns, konvertorlar in _yollar():
        toliq = f"{ns}:{nom}" if ns else nom
        try:
            yol = reverse(toliq, kwargs={k: qiymatlar[k] for k in konvertorlar})
        except (KeyError, NoReverseMatch):
            continue

        javob = c.get(yol)
        if javob.status_code != 200 or "text/html" not in javob.get("Content-Type", ""):
            continue

        sahifa = matn(javob)
        tekshirildi += 1
        assert kanonik(sahifa) or "noindex" in (meta(sahifa, "robots") or ""), (
            f"`{yol}` da na kanonik, na `noindex` bor"
        )

    assert tekshirildi >= 6, f"faqat {tekshirildi} sahifa sinaldi — juda kam"


def _yollar(resolver=None, namespace=None):
    resolver = resolver or get_resolver()
    for p in resolver.url_patterns:
        if isinstance(p, URLResolver):
            ns = p.namespace or namespace
            if ns == "admin":
                continue
            yield from _yollar(p, ns)
        elif isinstance(p, URLPattern) and p.name:
            yield p.name, namespace, dict(p.pattern.converters)


# ===========================================================================
# 2. Open Graph metalari
# ===========================================================================
def test_muammo_sahifasida_OG_metalari(anonymous_client):
    muammo = ComplaintFactory(
        title="Ipoteka olish qiyinmi", description="Bankdan kredit oldim."
    )

    sahifa = matn(anonymous_client.get(muammo.get_absolute_url()))

    assert meta(sahifa, "og:title") == "Ipoteka olish qiyinmi"
    assert meta(sahifa, "og:type") == "article"
    assert meta(sahifa, "og:site_name") == "Dard.uz"
    assert meta(sahifa, "twitter:card") == "summary_large_image"
    assert "Bankdan kredit" in (meta(sahifa, "og:description") or "")


def test_og_sarlavhada_sayt_nomi_TAKRORLANMAYDI(anonymous_client):
    """⚠️ `<title>` da " — Dard.uz" bor, `og:title` da bo'lmasligi kerak:
    sayt nomi kartada `og:site_name` orqali alohida ko'rsatiladi."""
    muammo = ComplaintFactory(title="Ipoteka olish")

    sahifa = matn(anonymous_client.get(muammo.get_absolute_url()))

    assert meta(sahifa, "og:title") == "Ipoteka olish"
    assert "— Dard.uz</title>" in sahifa


def test_lentada_STANDART_og_metalari(anonymous_client):
    sahifa = matn(anonymous_client.get("/"))

    assert meta(sahifa, "og:type") == "website"
    assert "og-default" in (meta(sahifa, "og:image") or "")


def test_og_rasm_MUTLAQ_manzilda(anonymous_client):
    """⚠️ Telegram va Facebook skanerlari nisbiy manzilni umuman
    yuklamaydi — karta rasmsiz qoladi."""
    sahifa = matn(anonymous_client.get("/"))

    assert (meta(sahifa, "og:image") or "").startswith("http://testserver/")


def test_og_rasm_olchamlari_ELON_qilinadi(anonymous_client):
    """⚠️ Skaner rasmni yuklamasdan kartani rejalashtira olsin: usiz
    rasm ko'pincha faqat IKKINCHI ulashishda chiqadi."""
    sahifa = matn(anonymous_client.get("/"))

    assert meta(sahifa, "og:image:width") == "1200"
    assert meta(sahifa, "og:image:height") == "630"


def test_muammoning_OZ_rasmi_ishlatiladi(anonymous_client):
    muammo = ComplaintFactory(title="Ipoteka olish")
    og_rasmni_yangilash(muammo.pk)
    muammo.refresh_from_db()

    sahifa = matn(anonymous_client.get(muammo.get_absolute_url()))

    assert muammo.og_rasm.url in (meta(sahifa, "og:image") or "")


def test_rasm_YOQ_bolsa_STANDARTGA_qaytadi(anonymous_client):
    """⚠️ Post yozilgan zahoti rasm yo'q (vazifa navbatda) — bu NORMAL
    holat va karta baribir rasmli bo'lishi kerak."""
    muammo = ComplaintFactory(title="Ipoteka olish")
    assert not muammo.og_rasm

    sahifa = matn(anonymous_client.get(muammo.get_absolute_url()))

    assert "og-default" in (meta(sahifa, "og:image") or "")


def test_ANONIM_postda_muallif_OG_metalariga_TUSHMAYDI(anonymous_client, user):
    """⚠️ D1-T6 invarianti ijtimoiy tarmoqda ham amal qiladi."""
    muammo = ComplaintFactory(title="Anonim savol", author=user, is_anonymous=True)

    sahifa = matn(anonymous_client.get(muammo.get_absolute_url()))

    for xossa in ("og:title", "og:description", "og:image"):
        assert user.username not in (meta(sahifa, xossa) or "")


# ===========================================================================
# 3. OG rasm vazifasi
# ===========================================================================
def test_vazifa_rasm_yasaydi():
    muammo = ComplaintFactory(title="Ipoteka olish")

    og_rasmni_yangilash(muammo.pk)

    muammo.refresh_from_db()
    assert muammo.og_rasm
    assert muammo.og_rasm.name.startswith("og/")
    assert muammo.og_rasm.size > 1000


def test_fayl_nomida_MAZMUN_HASHI_bor():
    """⚠️ Ijtimoiy tarmoqlar `og:image` ni MANZIL bo'yicha keshlaydi.
    Nom o'zgarmasa, sarlavha tahrirlangandan keyin ham Telegram ESKI
    rasmni ko'rsatishda davom etardi."""
    muammo = ComplaintFactory(title="Ipoteka olish")
    og_rasmni_yangilash(muammo.pk)
    muammo.refresh_from_db()
    eski_nom = muammo.og_rasm.name

    muammo.title = "Butunlay boshqa sarlavha"
    muammo.save(update_fields=["title"])
    og_rasmni_yangilash(muammo.pk)
    muammo.refresh_from_db()

    assert muammo.og_rasm.name != eski_nom


def test_MAZMUN_ozgarmasa_qayta_YOZILMAYDI():
    """⚠️ Teskari tomoni: har saqlashda yangi fayl to'planmasin."""
    muammo = ComplaintFactory(title="Ipoteka olish")
    og_rasmni_yangilash(muammo.pk)
    muammo.refresh_from_db()
    nom = muammo.og_rasm.name

    natija = og_rasmni_yangilash(muammo.pk)

    muammo.refresh_from_db()
    assert natija == "o'zgarmadi"
    assert muammo.og_rasm.name == nom


def test_ESKI_fayl_ochiriladi():
    """⚠️ Aks holda `media/og/` da yetim fayl to'planardi."""
    from django.core.files.storage import default_storage

    muammo = ComplaintFactory(title="Ipoteka olish")
    og_rasmni_yangilash(muammo.pk)
    muammo.refresh_from_db()
    eski_nom = muammo.og_rasm.name

    muammo.title = "Yangi sarlavha"
    muammo.save(update_fields=["title"])
    og_rasmni_yangilash(muammo.pk)

    assert not default_storage.exists(eski_nom)


def test_YOQ_muammo_bilan_yiqilmaydi():
    """⚠️ Fon vazifasi: post vazifa navbatda turganda o'chirilgan
    bo'lishi mumkin. Istisno navbatni band qilardi."""
    assert og_rasmni_yangilash(999999) == "topilmadi"


def test_YASHIRILGAN_post_uchun_ham_yasaladi():
    """⚠️ Tiklangandan keyin rasm DARHOL kerak bo'ladi va uni qayta
    yasashni hech kim eslamaydi. Rasmning o'zi hech qayerda
    ko'rsatilmaydi: `og:image` yashirilgan postda render bo'lmaydi."""
    muammo = ComplaintFactory(
        title="Yashirin post", moderation_status=ModerationStatus.HIDDEN
    )

    og_rasmni_yangilash(muammo.pk)

    muammo.refresh_from_db()
    assert muammo.og_rasm


def test_OMMAVIY_buyruq_hammasini_yasaydi():
    """⚠️ Brend yoki maket o'zgarganda eski kartalar eski ko'rinishda
    qolib ketadi va ular ijtimoiy tarmoqda YILLAB aylanib yuradi."""
    from django.core.management import call_command

    muammolar = [ComplaintFactory(title=f"Dard {i}") for i in range(3)]

    call_command("og_rasmlarni_yangilash", verbosity=0)

    for muammo in muammolar:
        muammo.refresh_from_db()
        assert muammo.og_rasm


def test_OMMAVIY_buyruq_faqat_yoqlar_rejimi():
    """⚠️ Sovuq start (D7-T7) uchun: `bulk_create` bilan kiritilgan
    postlarda rasm yo'q, mavjudlariga esa tegish shart emas."""
    from django.core.management import call_command

    bor = ComplaintFactory(title="Rasmi bor")
    og_rasmni_yangilash(bor.pk)
    bor.refresh_from_db()
    eski_nom = bor.og_rasm.name

    yoq = ComplaintFactory(title="Rasmi yoq")

    call_command("og_rasmlarni_yangilash", "--faqat-yoqlar", verbosity=0)

    bor.refresh_from_db()
    yoq.refresh_from_db()
    assert bor.og_rasm.name == eski_nom
    assert yoq.og_rasm


def test_post_YARATILGANDA_vazifa_ishga_tushadi(auth_client):
    """⚠️ Uchidan-uchiga: forma orqali yozilgan post rasmga ega
    bo'lishi kerak (testda Celery EAGER rejimida)."""
    kat = CategoryFactory()

    javob = auth_client.post(
        reverse("complaint_create"),
        {
            "title": "Formadan yozilgan dard",
            "description": "Bu yerda yetarlicha uzun matn bor va u haqiqiy postga o'xshaydi.",
            "category": kat.pk,
            "generation_tag": "genz",
            "vaqt_belgisi": "",
            "website": "",
        },
        follow=True,
    )

    assert javob.status_code == 200
    muammo = Complaint.objects.get(title="Formadan yozilgan dard")
    assert muammo.og_rasm, "OG rasm yasalmadi — vazifa chaqirilmadimi?"
