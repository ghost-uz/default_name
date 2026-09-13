"""Kontekstual reklama joylari (D6-T6).

QABUL MEZONLARI VA ULARNI ISBOTLAYDIGAN TESTLAR

    «'Reklama' yorlig'i majburiy»
        -> `test_YORLIQ_blok_ichida_BOR`
        -> `test_YORLIQ_sarlavhadan_OLDIN_keladi`
        -> `test_yorliqsiz_reklama_KORSATILMAYDI` (komponent darajasida)

    «inqirozli kontent sahifasida reklama KO'RSATILMAYDI»
        -> `test_INQIROZLI_muammo_sahifasida_reklama_YOQ`
        -> `test_inqirozli_YECHIM_ham_reklamani_YOPADI`
        -> `test_selektor_INQIROZDA_hech_narsa_qaytarmaydi` (sof funksiya)

⚠️ Inqiroz qoidasi UCH darajada sinaladi: selektorda (sof funksiya),
   ko'rinishda (kontekst) va sahifada (HTML). Faqat oxirgisi bo'lsa,
   qoida boshqa sahifaga ko'chirilganda jimgina yo'qolardi.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib import admin
from django.core.cache import cache
from django.db import connection
from django.template.loader import render_to_string
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape

from apps.complaints.factories import CategoryFactory, ComplaintFactory
from apps.reklama.admin import AdSlotAdmin
from apps.reklama.factories import AdSlotFactory
from apps.reklama.models import AdSlot
from apps.reklama.selectors import sahifa_reklamasi
from apps.reklama.services import (
    YIGISH_OYNALARI,
    bosishni_qayd_etish,
    joriy_oyna,
    korsatish_kaliti,
    korsatishlarni_yigish,
    korsatishni_qayd_etish,
)
from apps.reklama.tasks import korsatishlarni_yigish_vazifasi
from apps.solutions.factories import SolutionFactory

pytestmark = pytest.mark.django_db

YORLIQ = "Reklama"
BLOK_BELGISI = 'aria-labelledby="reklama-h"'


# ===========================================================================
# Yordamchilar
# ===========================================================================
def _sahifa(muammo, mijoz: Client | None = None) -> str:
    javob = (mijoz or Client()).get(muammo.get_absolute_url())
    assert javob.status_code == 200
    return javob.content.decode()


def _reklama_bloki(matn: str) -> str | None:
    """Sahifadagi reklama bloki, yoki `None`.

    ⚠️ Blok AJRATIB OLINADI: «Reklama» so'zi sahifaning boshqa joyida
       ham uchrashi mumkin (masalan shikoyat sababi «Spam yoki
       reklama»). Butun sahifa bo'ylab `in` tekshiruvi shu sababdan
       YOLG'ON O'TARDI.
    """
    boshi = matn.find(BLOK_BELGISI)
    if boshi == -1:
        return None
    return matn[boshi : matn.find("</section>", boshi)]


# ===========================================================================
# 1. ⚠️⚠️ «REKLAMA» YORLIG'I — birinchi qabul mezoni
# ===========================================================================
def test_YORLIQ_blok_ichida_BOR():
    """Reklama ko'rinsa, yorliq ham ko'rinadi.

    ⚠️ TUZOQ: o'zbekcha matnda APOSTROF ko'p (`bo'yicha`), Django esa
       uni `&#x27;` ga aylantiradi. Xom satr bilan solishtirish
       YIQILADI — va sababi «reklama chiqmadi» deb noto'g'ri
       o'qilardi. Shuning uchun `escape()` orqali solishtiriladi.
    """
    muammo = ComplaintFactory()
    AdSlotFactory(sarlavha="Ipoteka bo'yicha maslahat")

    blok = _reklama_bloki(_sahifa(muammo))

    assert blok is not None, "Reklama bloki sahifada umuman yo'q"
    assert YORLIQ in blok
    assert escape("Ipoteka bo'yicha maslahat") in blok


def test_YORLIQ_sarlavhadan_OLDIN_keladi():
    """⚠️ Tartib MUHIM: yorliq matndan KEYIN tursa, odam avval
    reklamani o'qib, keyin uning reklama ekanini bilardi."""
    muammo = ComplaintFactory()
    AdSlotFactory(sarlavha="Bank xizmatlari")

    blok = _reklama_bloki(_sahifa(muammo))
    assert blok is not None

    assert blok.index(YORLIQ) < blok.index("Bank xizmatlari")


def test_yorliqsiz_reklama_KORSATILMAYDI():
    """⚠️ Guard KOMPONENT darajasida — sahifada emas.

    Sabab: shablon boshqa sahifaga (masalan kategoriya ro'yxati)
    ulanganda ham yorliq u bilan birga keladi. Sahifa darajasidagi
    test buni kafolatlamasdi.
    """
    reklama = AdSlotFactory(sarlavha="Sinov sarlavhasi")

    html = render_to_string("components/_reklama.html", {"reklama": reklama})

    assert "Sinov sarlavhasi" in html
    assert YORLIQ in html


def test_reklama_YOQ_bolsa_blok_UMUMAN_chizilmaydi():
    """Bo'sh ramka «reklama joyi bo'sh» degan taassurot berardi."""
    muammo = ComplaintFactory()

    assert _reklama_bloki(_sahifa(muammo)) is None


# ===========================================================================
# 2. ⚠️⚠️ INQIROZ — ikkinchi qabul mezoni
# ===========================================================================
def test_selektor_INQIROZDA_hech_narsa_qaytarmaydi():
    """Sof funksiya darajasida: mos reklama BOR, lekin bayroq qo'yilgan."""
    kategoriya = CategoryFactory()
    AdSlotFactory(kategoriya=kategoriya)

    assert sahifa_reklamasi(kategoriya_id=kategoriya.pk, inqiroz=True) is None
    # Nazorat: bayroqsiz o'sha so'rov reklama TOPADI — ya'ni test
    # «umuman reklama yo'q» degan noto'g'ri sababdan o'tmayapti.
    assert sahifa_reklamasi(kategoriya_id=kategoriya.pk, inqiroz=False) is not None


def test_INQIROZLI_muammo_sahifasida_reklama_YOQ():
    """⚠️⚠️ D6-T6 ning eng muhim testi.

    O'ziga zarar yetkazish haqida yozgan odamning sahifasida pullik
    blok turishi — mahsulotning eng qo'pol xatosi bo'lardi.
    """
    muammo = ComplaintFactory(inqiroz_aniqlandi=True)
    AdSlotFactory(sarlavha="Kredit taklifi")

    matn = _sahifa(muammo)

    assert _reklama_bloki(matn) is None
    assert "Kredit taklifi" not in matn


def test_inqirozli_YECHIM_ham_reklamani_YOPADI():
    """⚠️ Oson unutiladigan holat: postning O'ZI toza, javoblardan
    birida belgi bor. Yordam bloki shunda ham chiqadi (D2-T6) — demak
    reklama ham chiqmasligi kerak."""
    muammo = ComplaintFactory()
    SolutionFactory(complaint=muammo, inqiroz_aniqlandi=True)
    AdSlotFactory(sarlavha="Kredit taklifi")

    matn = _sahifa(muammo)

    assert _reklama_bloki(matn) is None
    assert "Kredit taklifi" not in matn


def test_inqirozsiz_sahifada_reklama_CHIQADI():
    """Teskari tomoni: qoidani ortiqcha keng qo'llab yubormadikmi."""
    muammo = ComplaintFactory()
    SolutionFactory(complaint=muammo)
    AdSlotFactory(sarlavha="Kredit taklifi")

    assert "Kredit taklifi" in _sahifa(muammo)


# ===========================================================================
# 3. Maqsadlash — kategoriya bo'yicha
# ===========================================================================
def test_KATEGORIYAGA_mos_reklama_tanlanadi():
    uy_joy = CategoryFactory(slug="uy-joy")
    reklama = AdSlotFactory(kategoriya=uy_joy)

    assert sahifa_reklamasi(kategoriya_id=uy_joy.pk, inqiroz=False) == reklama


def test_BOSHQA_kategoriya_reklamasi_CHIQMAYDI():
    """Kontekstual reklamaning butun ma'nosi shu."""
    uy_joy = CategoryFactory(slug="uy-joy")
    talim = CategoryFactory(slug="talim")
    AdSlotFactory(kategoriya=talim)

    assert sahifa_reklamasi(kategoriya_id=uy_joy.pk, inqiroz=False) is None


def test_UMUMIY_reklama_hamma_kategoriyada_chiqadi():
    """`kategoriya=None` — maqsadsiz reklama."""
    umumiy = AdSlotFactory(kategoriya=None)
    birinchi = CategoryFactory(slug="birinchi")
    ikkinchi = CategoryFactory(slug="ikkinchi")

    assert sahifa_reklamasi(kategoriya_id=birinchi.pk, inqiroz=False) == umumiy
    assert sahifa_reklamasi(kategoriya_id=ikkinchi.pk, inqiroz=False) == umumiy


def test_MAQSADLI_reklama_UMUMIYDAN_ustun():
    """⚠️ Ikkalasi ham mos kelganda mavzuga yaqinrog'i tanlanadi —
    kontekstual reklamaning qiymati aynan shunda."""
    uy_joy = CategoryFactory(slug="uy-joy")
    maqsadli = AdSlotFactory(kategoriya=uy_joy)
    AdSlotFactory(kategoriya=None)

    # Tasodifiy tartib bor — bir necha marta tekshiramiz.
    for _ in range(8):
        assert sahifa_reklamasi(kategoriya_id=uy_joy.pk, inqiroz=False) == maqsadli


def test_kategoriyasiz_sahifada_FAQAT_umumiy_reklama():
    """Kategoriyasi noma'lum sahifa maqsadli reklamani OLMAYDI."""
    uy_joy = CategoryFactory(slug="uy-joy")
    AdSlotFactory(kategoriya=uy_joy)

    assert sahifa_reklamasi(kategoriya_id=None, inqiroz=False) is None

    umumiy = AdSlotFactory(kategoriya=None)
    assert sahifa_reklamasi(kategoriya_id=None, inqiroz=False) == umumiy


def test_BITTA_reklama_qaytariladi():
    """Yon panelda ikkita reklama ketma-ket tursa sahifa reklama
    lentasiga o'xshab qolardi."""
    muammo = ComplaintFactory()
    AdSlotFactory.create_batch(3, kategoriya=None)

    matn = _sahifa(muammo)

    assert matn.count(BLOK_BELGISI) == 1


# ===========================================================================
# 4. Faollik va muddat
# ===========================================================================
def test_model_standart_holatda_NOFAOL():
    """⚠️ Adminda yaratilgan zahoti saytga chiqib ketadigan reklama
    «hali tayyor emas» holatini umuman qoldirmasdi."""
    assert AdSlot._meta.get_field("faolmi").default is False


def test_NOFAOL_reklama_chiqmaydi():
    kategoriya = CategoryFactory()
    AdSlotFactory(kategoriya=kategoriya, faolmi=False)

    assert sahifa_reklamasi(kategoriya_id=kategoriya.pk, inqiroz=False) is None


def test_MUDDATI_TUGAGAN_reklama_chiqmaydi():
    kategoriya = CategoryFactory()
    AdSlotFactory(kategoriya=kategoriya, tugash=timezone.now() - timedelta(minutes=1))

    assert sahifa_reklamasi(kategoriya_id=kategoriya.pk, inqiroz=False) is None


def test_HALI_BOSHLANMAGAN_reklama_chiqmaydi():
    kategoriya = CategoryFactory()
    AdSlotFactory(kategoriya=kategoriya, boshlanish=timezone.now() + timedelta(hours=1))

    assert sahifa_reklamasi(kategoriya_id=kategoriya.pk, inqiroz=False) is None


def test_MUDDATSIZ_reklama_chiqadi():
    """Bo'sh sanalar — «hoziroq va muddatsiz». Shartnoma muddati
    bo'lmagan reklama uchun sun'iy sana yozdirish kerak emas."""
    kategoriya = CategoryFactory()
    reklama = AdSlotFactory(kategoriya=kategoriya, boshlanish=None, tugash=None)

    assert sahifa_reklamasi(kategoriya_id=kategoriya.pk, inqiroz=False) == reklama


def test_oyna_ICHIDAGI_reklama_chiqadi():
    kategoriya = CategoryFactory()
    reklama = AdSlotFactory(
        kategoriya=kategoriya,
        boshlanish=timezone.now() - timedelta(days=1),
        tugash=timezone.now() + timedelta(days=1),
    )

    assert sahifa_reklamasi(kategoriya_id=kategoriya.pk, inqiroz=False) == reklama


# ===========================================================================
# 5. Ko'rsatishlar — kesh va yig'ish
# ===========================================================================
def test_korsatish_KESHDA_sanaladi_BAZAGA_yozilmaydi():
    """⚠️⚠️ Batafsil sahifa ko'p ochiladi. Har ochilishda `UPDATE`
    qilinsa, o'qish sahifasi YOZISH sahifasiga aylanardi."""
    reklama = AdSlotFactory()

    korsatishni_qayd_etish(reklama.pk)
    korsatishni_qayd_etish(reklama.pk)

    reklama.refresh_from_db()
    assert reklama.korsatishlar == 0  # baza TEGILMAGAN
    assert cache.get(korsatish_kaliti(reklama.pk, joriy_oyna())) == 2


def test_sahifa_ochilganda_korsatish_sanaladi():
    muammo = ComplaintFactory()
    reklama = AdSlotFactory()

    _sahifa(muammo)

    assert cache.get(korsatish_kaliti(reklama.pk, joriy_oyna())) == 1


def test_INQIROZLI_sahifada_korsatish_ham_sanalmaydi():
    """Reklama chiqmagan bo'lsa, ko'rsatish ham bo'lmagan."""
    muammo = ComplaintFactory(inqiroz_aniqlandi=True)
    reklama = AdSlotFactory()

    _sahifa(muammo)

    assert cache.get(korsatish_kaliti(reklama.pk, joriy_oyna())) is None


def test_YIGISH_keshdagi_sanoqni_bazaga_kochiradi():
    reklama = AdSlotFactory()
    otgan = joriy_oyna() - 1
    cache.set(korsatish_kaliti(reklama.pk, otgan), 7)

    assert korsatishlarni_yigish() == 7

    reklama.refresh_from_db()
    assert reklama.korsatishlar == 7
    # Kalit o'chirilgan — ikkinchi yurish qo'shib yubormaydi.
    assert cache.get(korsatish_kaliti(reklama.pk, otgan)) is None
    assert korsatishlarni_yigish() == 0


def test_YIGISH_joriy_oynani_TEGMAYDI():
    """⚠️⚠️ Poyga himoyasi: joriy oyna hali TO'LIB turibdi.

    Yig'uvchi uni o'qib-o'chirsa, o'sha lahzada kelgan ko'rsatish
    ikkalasining orasiga tushib YO'QOLARDI — va buni hech kim
    payqamasdi, chunki sanoq shunchaki bir oz kam bo'lardi.
    """
    reklama = AdSlotFactory()
    kalit = korsatish_kaliti(reklama.pk, joriy_oyna())
    cache.set(kalit, 5)

    assert korsatishlarni_yigish() == 0

    reklama.refresh_from_db()
    assert reklama.korsatishlar == 0
    assert cache.get(kalit) == 5  # kalit JOYIDA


def test_YIGISH_bir_nechta_otgan_oynani_yigadi():
    """Vazifa bir-ikki marta o'tkazib yuborilsa ham sanoq yo'qolmaydi."""
    reklama = AdSlotFactory()
    joriy = joriy_oyna()
    for siljish in range(1, YIGISH_OYNALARI + 1):
        cache.set(korsatish_kaliti(reklama.pk, joriy - siljish), 2)

    assert korsatishlarni_yigish() == 2 * YIGISH_OYNALARI

    reklama.refresh_from_db()
    assert reklama.korsatishlar == 2 * YIGISH_OYNALARI


def test_YIGISH_mavjud_sanoqqa_QOSHADI():
    """`F()` bilan — o'qib-yozish poygasi bo'lmasin."""
    reklama = AdSlotFactory(korsatishlar=10)
    cache.set(korsatish_kaliti(reklama.pk, joriy_oyna() - 1), 3)

    korsatishlarni_yigish()

    reklama.refresh_from_db()
    assert reklama.korsatishlar == 13


def test_celery_vazifasi_yigishni_chaqiradi():
    reklama = AdSlotFactory()
    cache.set(korsatish_kaliti(reklama.pk, joriy_oyna() - 1), 4)

    assert korsatishlarni_yigish_vazifasi() == 4


class _YiqiluvchiKesh:
    """Har chaqiruvda yiqiladigan soxta kesh."""

    def add(self, *args, **kwargs):
        raise RuntimeError("Redis o'chdi")

    def incr(self, *args, **kwargs):
        raise RuntimeError("Redis o'chdi")


def test_KESH_nosozligi_sahifani_YIQITMAYDI(monkeypatch):
    """⚠️ FAIL OPEN: reklama sanog'i yo'qolgani sahifani yiqitadigan
    sabab emas (D2-T4 dagi tezlik cheklovi bilan bir xil qaror).

    ⚠️⚠️ PATCH AYNAN SHU MODULGA QO'YILADI, kesh OBYEKTIGA emas.
       Birinchi urinish `...services.cache.add` ni almashtirgandi — u
       esa Django'ning UMUMIY kesh proxy'sini o'zgartiradi va butun
       loyihaga tegadi. Natijada sahifa boshqa sababdan yiqildi
       (`oxshash_muammolar` ham `cache.add` chaqiradi), test esa
       «fail open ishlamayapti» degan YOLG'ON xulosa berardi.
    """
    muammo = ComplaintFactory()
    AdSlotFactory(sarlavha="Bank xizmatlari")

    monkeypatch.setattr("apps.reklama.services.cache", _YiqiluvchiKesh())

    matn = _sahifa(muammo)

    assert "Bank xizmatlari" in matn  # reklama BARIBIR ko'rsatildi
    assert _reklama_bloki(matn) is not None


# ===========================================================================
# 6. Bosish — yo'naltirish va hisob
# ===========================================================================
def test_bosish_YONALTIRADI_va_sanaydi():
    reklama = AdSlotFactory(manzil="https://example.uz/ipoteka")

    javob = Client().get(reverse("reklama_bosildi", args=[reklama.pk]))

    assert javob.status_code == 302
    assert javob["Location"] == "https://example.uz/ipoteka"

    reklama.refresh_from_db()
    assert reklama.bosishlar == 1


def test_bosish_BAZAGA_darhol_yoziladi():
    """⚠️ Ko'rsatishdan farqli: bosish kam uchraydi va aynan shu son
    reklama beruvchi bilan hisob-kitobda ishlatiladi."""
    reklama = AdSlotFactory()

    bosishni_qayd_etish(reklama.pk)
    bosishni_qayd_etish(reklama.pk)

    reklama.refresh_from_db()
    assert reklama.bosishlar == 2


def test_MANZIL_bazadan_olinadi_sorovdan_EMAS():
    """⚠️⚠️ OCHIQ YO'NALTIRISH (open redirect) himoyasi.

    `?url=` parametrini qabul qiladigan sayt hujumchiga o'z domenida
    ishonchli ko'rinadigan havola yasash imkonini beradi. Bu yerda
    parametr shunchaki E'TIBORSIZ qoldiriladi.
    """
    reklama = AdSlotFactory(manzil="https://example.uz/ipoteka")

    javob = Client().get(
        reverse("reklama_bosildi", args=[reklama.pk]),
        {"url": "https://zararli.example/fishing"},
    )

    assert javob["Location"] == "https://example.uz/ipoteka"


def test_NOFAOL_reklamaga_bosish_404():
    """Muddati tugagan shartnomaning havolasi saytda yashab qolmasin."""
    reklama = AdSlotFactory(faolmi=False)

    javob = Client().get(reverse("reklama_bosildi", args=[reklama.pk]))

    assert javob.status_code == 404


def test_MUDDATI_TUGAGAN_reklamaga_bosish_404():
    reklama = AdSlotFactory(tugash=timezone.now() - timedelta(minutes=1))

    javob = Client().get(reverse("reklama_bosildi", args=[reklama.pk]))

    assert javob.status_code == 404


def test_bosish_faqat_GET():
    reklama = AdSlotFactory()

    javob = Client().post(reverse("reklama_bosildi", args=[reklama.pk]))

    assert javob.status_code == 405


# ===========================================================================
# 7. Shablon — xavfsizlik va SEO
# ===========================================================================
def test_havolada_SPONSORED_NOFOLLOW_NOOPENER():
    """⚠️ `sponsored nofollow` — Google talabi (pullik havola reyting
    uzatmasin). `noopener` — yangi oynadagi sahifa bizning
    `window.opener` imizga tegmasin."""
    muammo = ComplaintFactory()
    AdSlotFactory()

    blok = _reklama_bloki(_sahifa(muammo))
    assert blok is not None

    assert 'rel="sponsored nofollow noopener"' in blok
    assert 'target="_blank"' in blok


def test_havola_BIZNING_endpoint_orqali():
    """To'g'ridan-to'g'ri tashqi manzil qo'yilsa bosish sanalmasdi."""
    muammo = ComplaintFactory()
    reklama = AdSlotFactory(manzil="https://example.uz/ipoteka")

    blok = _reklama_bloki(_sahifa(muammo))
    assert blok is not None

    assert reverse("reklama_bosildi", args=[reklama.pk]) in blok
    assert "https://example.uz/ipoteka" not in blok


def test_reklama_matni_EKRANLANADI():
    """Reklama matnini staff kiritadi, lekin xato bitta bo'lsa yetadi."""
    muammo = ComplaintFactory()
    AdSlotFactory(sarlavha="<script>alert(1)</script>")

    matn = _sahifa(muammo)

    assert "<script>alert(1)</script>" not in matn
    assert "&lt;script&gt;" in matn


def test_sahifada_UCHINCHI_TOMON_skripti_yoq():
    """⚠️ Maxfiylik siyosati (9-bo'lim) reklama tarmog'i YO'Q deb
    va'da qiladi. Blokda tashqi `src` bo'lsa, bu va'da buzilardi."""
    muammo = ComplaintFactory()
    AdSlotFactory()

    blok = _reklama_bloki(_sahifa(muammo))
    assert blok is not None

    assert "<script" not in blok
    assert "<iframe" not in blok
    assert "<img" not in blok


def test_maxfiylik_sahifasida_REKLAMA_bolimi_bor(client):
    """⚠️ Mahsulot o'zgardi — siyosat ham o'zgarishi SHART.

    Yorliq va'dasi hamda «reklama tarmog'i yo'q» bandi foydalanuvchiga
    aytilmasa, yorliqning o'zi yetarli bo'lmasdi.
    """
    matn = client.get(reverse("maxfiylik")).content.decode()

    assert "9. Reklama" in matn
    assert "Reklama tarmog'i yo'q" in matn
    assert "Inqiroz belgilari aniqlangan sahifada reklama umuman" in matn


# ===========================================================================
# 8. So'rov byudjeti
# ===========================================================================
def test_reklama_tanlash_BITTA_sorov():
    """⚠️ Batafsil sahifa byudjeti 8 so'rov (`apps/common/byudjet.py`) va
    reklama undan BITTASINI oladi.

    ⚠️ Reklama soni ahamiyatsiz: tanlash bazada bo'ladi, Python'da
       emas. Aks holda har yangi reklama sahifani sekinlashtirardi.
    """
    kategoriya = CategoryFactory()
    AdSlotFactory.create_batch(10, kategoriya=None)
    AdSlotFactory(kategoriya=kategoriya)

    with CaptureQueriesContext(connection) as sorovlar:
        sahifa_reklamasi(kategoriya_id=kategoriya.pk, inqiroz=False)

    assert len(sorovlar) == 1


def test_reklama_YOQ_bolsa_ham_sorov_KETADI():
    """⚠️ ONGLI QARORNI QOTIRADI: so'rov bo'sh jadvalda ham bo'ladi.

    Ya'ni bu xarajat DOIMIY va byudjetda shunday hisoblangan. Kimdir
    keyinchalik «reklama yo'q ekan, so'rov ham yo'q» deb o'ylab
    byudjetni pasaytirmasin.
    """
    kategoriya = CategoryFactory()

    with CaptureQueriesContext(connection) as sorovlar:
        assert sahifa_reklamasi(kategoriya_id=kategoriya.pk, inqiroz=False) is None

    assert len(sorovlar) == 1


def test_INQIROZDA_bazaga_UMUMAN_borilmaydi():
    """⚠️ Inqiroz tekshiruvi ORM'dan OLDIN turadi: qoidani bajarish
    uchun so'rov kerak emas — va eng og'ir sahifada bitta so'rov
    tejaladi."""
    kategoriya = CategoryFactory()
    AdSlotFactory(kategoriya=kategoriya)

    with CaptureQueriesContext(connection) as sorovlar:
        assert sahifa_reklamasi(kategoriya_id=kategoriya.pk, inqiroz=True) is None

    assert len(sorovlar) == 0


# ===========================================================================
# 9. Model va admin
# ===========================================================================
def test_SANOQCHILAR_tahrirlanmaydi():
    """⚠️ Ular O'LCHOV, tahrir qilinadigan maydon emas. Qo'lda
    «tuzatilgan» ko'rsatish soni hisob-kitobni asossiz qilardi."""
    assert not AdSlot._meta.get_field("korsatishlar").editable
    assert not AdSlot._meta.get_field("bosishlar").editable

    admin_obj = AdSlotAdmin(AdSlot, admin.site)
    assert "korsatishlar" in admin_obj.readonly_fields
    assert "bosishlar" in admin_obj.readonly_fields


def test_ctr_hisobi():
    reklama = AdSlotFactory(korsatishlar=200, bosishlar=5)

    assert reklama.ctr == 2.5


def test_ctr_korsatishsiz_NOL():
    """Nolga bo'lish — eng oson unutiladigan holat."""
    assert AdSlotFactory(korsatishlar=0, bosishlar=0).ctr == 0.0


def test_str_ichki_nomni_beradi():
    assert str(AdSlotFactory(nom="Uy-joy — sentabr")) == "Uy-joy — sentabr"
