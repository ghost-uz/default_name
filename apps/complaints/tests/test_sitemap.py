"""sitemap.xml va robots.txt (D4-T5)."""

from __future__ import annotations

import re
from xml.etree import ElementTree

import pytest
from django.conf import settings
from django.urls import reverse

from apps.common.models import ModerationStatus
from apps.complaints.factories import CategoryFactory, ComplaintFactory
from apps.complaints.models import ComplaintStatus

pytestmark = pytest.mark.django_db

NS = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def sitemap_yozuvlari(mijoz) -> list[dict[str, str]]:
    """`<url>` elementlarini lug'atlar ro'yxatiga aylantiradi."""
    javob = mijoz.get(reverse("sitemap"))
    assert javob.status_code == 200

    # ⚠️ `S314` (XXE) BU YERDA QO'LLANMAYDI va `defusedxml` qo'shilmadi:
    #    XML tashqaridan kelmaydi — uni AYNAN SINALAYOTGAN ko'rinish
    #    hozirgina yasadi. Ishonchsiz XML uchun qoida to'g'ri, lekin bu
    #    yerda u faqat test uchun yangi bog'liqlik talab qilardi.
    ildiz = ElementTree.fromstring(javob.content)  # noqa: S314
    yozuvlar = []
    for url in ildiz.findall("s:url", NS):
        yozuv = {}
        for bola in url:
            # `{namespace}loc` -> `loc`
            yozuv[bola.tag.rsplit("}", 1)[-1]] = (bola.text or "").strip()
        yozuvlar.append(yozuv)
    return yozuvlar


def manzillar(mijoz) -> list[str]:
    return [y["loc"] for y in sitemap_yozuvlari(mijoz)]


# ===========================================================================
# 1. ⚠️ Ko'rinish invarianti — D4-T5 ning butun ma'nosi
# ===========================================================================
def test_YASHIRILGAN_post_sitemapda_YOQ(anonymous_client):
    """⚠️⚠️ D4-T5 qabul mezoni: "sitemap `visible()` manageridan
    foydalanadi".

    Yashirilgan post sitemap'ga tushsa, Google uni indekslaydi va
    yashirishning MA'NOSI QOLMAYDI: sahifa saytda ko'rinmaydi, lekin
    qidiruv natijasida turadi. Indeksdan chiqarish haftalar oladi.
    """
    yashirin = ComplaintFactory(
        title="Yashirin post", moderation_status=ModerationStatus.HIDDEN
    )
    ochiq = ComplaintFactory(title="Ochiq post")

    barcha = manzillar(anonymous_client)

    assert any(ochiq.slug in m for m in barcha)
    assert not any(yashirin.slug in m for m in barcha)


def test_OCHIRILGAN_post_sitemapda_YOQ(anonymous_client):
    """⚠️ Alohida holat: `moderation_status` teginilmagan, faqat
    `deleted_at` qo'yilgan."""
    ochirilgan = ComplaintFactory(title="O'chirilgan post")
    ochirilgan.delete()

    assert not any(ochirilgan.slug in m for m in manzillar(anonymous_client))


def test_TEKSHIRUVDAGI_post_ham_sitemapda_YOQ(anonymous_client):
    """⚠️ `PENDING` — avtomatik filtr (D2-T5) shubhali deb belgilagan
    kontent. U saytda KO'RINADI, lekin `visible()` dan o'tmaydi."""
    kutilyapti = ComplaintFactory(
        title="Navbatdagi post", moderation_status=ModerationStatus.PENDING
    )

    assert not any(kutilyapti.slug in m for m in manzillar(anonymous_client))


def test_FAOL_BOLMAGAN_kategoriya_sitemapda_YOQ(anonymous_client):
    """`is_active=False` — "yangi post uchun taklif qilma" degani, ya'ni
    uni qidiruv tizimiga ham taklif qilish noto'g'ri."""
    CategoryFactory(slug="faol", name="Faol", is_active=True)
    CategoryFactory(slug="faolmas", name="Faolmas", is_active=False)

    barcha = manzillar(anonymous_client)

    assert any("category=faol" in m for m in barcha)
    assert not any("category=faolmas" in m for m in barcha)


def test_PROFIL_sahifalari_sitemapda_YOQ(anonymous_client, user):
    """⚠️ Yupqa (thin) kontent, minglab bo'lishi mumkin, va sitemap
    foydalanuvchi nomlarining to'liq ro'yxatini skraperlarga tayyor
    holda berardi."""
    ComplaintFactory(author=user)

    assert not any(user.username in m for m in manzillar(anonymous_client))


# ===========================================================================
# 2. ⚠️⚠️ Sitemap va kanonik MOS bo'lishi
# ===========================================================================
def test_SITEMAPDAGI_HAR_MANZIL_OZ_KANONIGIGA_teng(anonymous_client):
    """⚠️⚠️ ENG MUHIM TEKSHIRUV — boshqa loyihada aynan shu buzilgan.

    Sitemap `/?category=moliya` ni bergan, kanonik esa faqat
    `request.path` dan qurilib bosh sahifani ko'rsatgan. Search Console
    barcha kategoriya sahifalarini "Duplicate, not canonical" deb rad
    etgan: sitemap ish bermagan, faqat ogohlantirish yaratgan.

    Bu test ikkalasini bir-biriga BOG'LAYDI — biri o'zgarsa, ikkinchisi
    ham o'zgarishi kerak bo'ladi.
    """
    CategoryFactory(slug="moliya", name="Moliya")
    ComplaintFactory(title="Ipoteka olish", status=ComplaintStatus.SOLVED)

    tekshirildi = 0
    for manzil in manzillar(anonymous_client):
        # `http://testserver/yo'l?param` -> `/yo'l?param`
        nisbiy = re.sub(r"^https?://[^/]+", "", manzil)

        javob = anonymous_client.get(nisbiy)
        assert javob.status_code == 200, f"{nisbiy} -> {javob.status_code}"

        moslik = re.search(
            r'<link rel="canonical" href="([^"]*)"', javob.content.decode()
        )
        assert moslik, f"{nisbiy} da kanonik yo'q"
        assert moslik.group(1) == manzil, (
            f"sitemap `{manzil}` beradi, sahifa esa `{moslik.group(1)}` ga "
            "kanoniklashadi — Google buni 'Duplicate, not canonical' deydi"
        )
        tekshirildi += 1

    assert tekshirildi >= 10, f"faqat {tekshirildi} manzil sinaldi — juda kam"


# ===========================================================================
# 3. Sitemap mazmuni
# ===========================================================================
def test_yechilgan_post_USTUVORROQ(anonymous_client):
    """Yechilgan muammoda SAVOL ham, JAVOB ham bor — aynan shunday
    sahifa Google natijasida foydali bo'ladi."""
    yechilgan = ComplaintFactory(title="Yechilgan", status=ComplaintStatus.SOLVED)
    ochiq = ComplaintFactory(title="Ochiq", status=ComplaintStatus.OPEN)

    yozuvlar = {
        y["loc"]: y["priority"]
        for y in sitemap_yozuvlari(anonymous_client)
        if "priority" in y
    }
    yechilgan_p = next(v for k, v in yozuvlar.items() if yechilgan.slug in k)
    ochiq_p = next(v for k, v in yozuvlar.items() if ochiq.slug in k)

    assert float(yechilgan_p) > float(ochiq_p)


def test_lastmod_beriladi(anonymous_client):
    """⚠️ `changefreq` va `priority` — tavsiya; `lastmod` esa qayta
    skanerlash tartibini haqiqatan o'zgartiradi."""
    muammo = ComplaintFactory(title="Post")

    yozuv = next(
        y for y in sitemap_yozuvlari(anonymous_client) if muammo.slug in y["loc"]
    )

    assert yozuv["lastmod"]


def test_statik_sahifalar_bor(anonymous_client):
    barcha = manzillar(anonymous_client)

    for yol in ("/", "/kategoriyalar/", "/ekspertlar/", "/shartlar/"):
        assert any(m.endswith(yol) for m in barcha), f"{yol} sitemapda yo'q"


def test_QIDIRUV_sahifasi_sitemapda_YOQ(anonymous_client):
    """U `noindex` da (D4-T3) — sitemap'ga qo'shish qarama-qarshi
    signal bo'lardi."""
    assert not any("/qidiruv/" in m for m in manzillar(anonymous_client))


# ===========================================================================
# 4. robots.txt
# ===========================================================================
def test_robots_ochiladi(anonymous_client):
    javob = anonymous_client.get(reverse("robots"))

    assert javob.status_code == 200
    assert javob["Content-Type"].startswith("text/plain")


def test_robots_SITEMAP_havolasini_beradi(anonymous_client):
    """⚠️ Mutlaq manzil: `Sitemap:` qatorida nisbiy yo'l ishlamaydi."""
    matn = anonymous_client.get(reverse("robots")).content.decode()

    assert "Sitemap: http://testserver/sitemap.xml" in matn


def test_robots_ADMIN_manzilini_OSHKOR_QILMAYDI(anonymous_client, settings):
    """⚠️⚠️ `robots.txt` — OMMAVIY fayl.

    Unga `Disallow: /maxfiy-admin/` deb yozish admin panel manzilini
    butun dunyoga E'LON QILISH degani. `DJANGO_ADMIN_URL` aynan shuning
    uchun sozlanadigan qilingan: standart `/admin/` eng ko'p
    skanerlanadigan yo'l. Uni robots.txt ga yozish o'sha himoyani BIR
    QATORDA yo'q qilardi.
    """
    settings.ADMIN_URL = "juda-maxfiy-panel"

    matn = anonymous_client.get(reverse("robots")).content.decode()

    assert "juda-maxfiy-panel" not in matn
    assert "admin" not in matn.lower()


@pytest.mark.parametrize(
    "yol", ["/qidiruv/", "/moderatsiya/", "/hisob/", "/kirish/", "/ovoz/"]
)
def test_robots_shaxsiy_yollarni_taqiqlaydi(anonymous_client, yol):
    matn = anonymous_client.get(reverse("robots")).content.decode()

    assert f"Disallow: {yol}" in matn


def test_robots_LENTANI_taqiqlamaydi(anonymous_client):
    """⚠️ Oson qilinadigan xato: `Disallow: /` yozib qo'yish butun
    saytni indeksdan chiqaradi."""
    matn = anonymous_client.get(reverse("robots")).content.decode()

    assert "Disallow: /\n" not in matn
    assert "Disallow: /dard/" not in matn


def test_ADMIN_URL_sozlamasi_hali_ham_ishlaydi():
    """Guard: `ADMIN_URL` sozlamasi mavjudligini qotiradi — u robots
    testining sababi."""
    assert settings.ADMIN_URL
