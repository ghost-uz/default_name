"""To'liq matnli qidiruv (D4-T1).

⚠️ BU YERDAGI XATOLARNING KO'PI JIM: qidiruv buzilganda istisno
   chiqmaydi, log toza qoladi va natija shunchaki bo'sh bo'ladi.
   Shuning uchun testlar "yiqilmadimi?" emas, "TOPDIMI?" deb so'raydi.
"""

from __future__ import annotations

import time

import pytest
from django.core.management import call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.common.matn import normallashtir, qidiruv_uchun
from apps.common.models import ModerationStatus
from apps.complaints.factories import CategoryFactory, ComplaintFactory
from apps.complaints.models import Complaint
from apps.complaints.selectors import (
    LentaFiltri,
    qidiruv_queryset,
    taxminiy_natijalar,
)

pytestmark = pytest.mark.django_db


def sarlavhalar(qs) -> list[str]:
    return [m.title for m in qs]


# ===========================================================================
# 1. Normallashtirish — bazasiz
# ===========================================================================
@pytest.mark.parametrize(
    ("xom", "kutilgan"),
    [
        ("IPOTEKA", "ipoteka"),
        ("  Ipoteka   olish  ", "ipoteka olish"),
        ("Ipoteka\n\tolish", "ipoteka olish"),
        ("café", "cafe"),
        # ⚠️ D4-T1 da bu "елка" edi (`unaccent` qiladigan ish). D4-T2
        #    transliteratsiyani AKSENTDAN OLDIN qo'ydi, ya'ni `ё` endi
        #    `е` ga aylanib ulgurmaydi — batafsil `matn.py` da.
        ("ёлка", "yolka"),
        ("", ""),
        ("   ", ""),
    ],
)
def test_qidiruv_normallashtirish(xom, kutilgan):
    assert qidiruv_uchun(xom) == kutilgan


def test_qidiruv_normallashtirish_None_bilan_yiqilmaydi():
    """Bo'sh `TextField` bazadan `None` bo'lib kelishi mumkin."""
    assert qidiruv_uchun(None) == ""  # type: ignore[arg-type]


def test_IKKI_normallashtirish_ATAYLAB_boshqacha():
    """⚠️ `normallashtir()` (D2-T6) apostrofni SAQLAYDI — inqiroz kalit
    so'zlari aynan shu shaklda yozilgan va ro'yxatda qismiy moslik
    qidiriladi. Qidiruv esa apostrofni O'CHIRADI (D4-T2).

    Ularni "soddalashtirib" birlashtirish taklifi kelsa: bittasi
    ikkinchisini buzadi. Shu yerda qotirilgan.
    """
    assert normallashtir("O‘ZIMNI O‘LDIR") == "o'zimni o'ldir"
    assert qidiruv_uchun("O‘ZIMNI O‘LDIR") == "ozimni oldir"


# ===========================================================================
# 2. Indeks ustunlari — yozishning HAR yo'li
# ===========================================================================
def test_saqlashda_qidiruv_ustunlari_toldiriladi():
    muammo = ComplaintFactory(title="Ipoteka OLISH", description="Bank KREDITI")

    assert muammo.qidiruv_sarlavha == "ipoteka olish"
    assert muammo.qidiruv_tavsif == "bank krediti"


def test_tahrirlashda_yangilanadi():
    muammo = ComplaintFactory(title="Eski sarlavha")
    muammo.title = "Yangi sarlavha"
    muammo.save()

    muammo.refresh_from_db()
    assert muammo.qidiruv_sarlavha == "yangi sarlavha"


def test_update_fields_title_bilan_ham_yangilanadi():
    """⚠️ `update_fields` berilganda hisoblanadigan ustun unga
    QO'SHILMASA, yangi qiymat jimgina yo'qoladi — slug bilan bir xil
    tuzoq (D1-T3)."""
    muammo = ComplaintFactory(title="Eski")
    muammo.title = "Yangi"
    muammo.save(update_fields=["title"])

    muammo.refresh_from_db()
    assert muammo.qidiruv_sarlavha == "yangi"


def test_update_fields_hot_score_matnni_QAYTA_YOZMAYDI():
    """⚠️ D1-T11 fon vazifasi har 10 daqiqada ishlaydi. Butun matnni har
    safar qayta yozish bekorga yozish yuki bo'lardi."""
    muammo = ComplaintFactory()

    with CaptureQueriesContext(connection) as sorovlar:
        muammo.save(update_fields=["hot_score"])

    sql = " ".join(s["sql"] for s in sorovlar)
    assert "qidiruv_sarlavha" not in sql


def test_bulk_create_ham_toldiradi():
    """⚠️ ENG XAVFLI YO'L: `bulk_create` `save()` ni chaqirmaydi va signal
    ham yubormaydi. Usiz post lentada ko'rinardi, qidiruvda esa YO'Q
    bo'lardi — hech qanday xatosiz. D7-T7 (sovuq start) aynan shu
    yo'ldan yuradi."""
    kat = CategoryFactory()
    Complaint.objects.bulk_create(
        [
            Complaint(category=kat, title="Ommaviy IPOTEKA", description="Tavsif"),
            Complaint(category=kat, title="Ikkinchi", description="Bank KREDITI"),
        ]
    )

    yozilgan = Complaint.objects.get(title="Ommaviy IPOTEKA")
    assert yozilgan.qidiruv_sarlavha == "ommaviy ipoteka"
    # ⚠️ Eng muhimi: baza tsvector'ni HAQIQATAN hisoblaganmi.
    assert sarlavhalar(qidiruv_queryset("ipoteka")) == ["Ommaviy IPOTEKA"]


def test_bulk_create_SLUGNI_ham_yasaydi():
    """⚠️ D1-T3 dan beri ochiq turgan teshik — bu test uni topdi.

    `save()` chaqirilmagani uchun slug ham yasalmaydi va ikkinchi yozuv
    `complaint_slug_uniq_alive` cheklovini buzadi (`Key (slug)=()`).
    Ya'ni D7-T7 sovuq starti bitta postdan keyin yiqilardi.
    """
    kat = CategoryFactory()
    Complaint.objects.bulk_create(
        [
            Complaint(category=kat, title="Birinchi", description="Matn"),
            Complaint(category=kat, title="Ikkinchi", description="Matn"),
        ]
    )

    sluglar = set(Complaint.objects.values_list("slug", flat=True))
    assert len(sluglar) == 2
    assert "" not in sluglar


def test_bulk_update_title_bilan_toldiradi():
    muammo = ComplaintFactory(title="Eski sarlavha")
    muammo.title = "Ipoteka masalasi"

    Complaint.objects.bulk_update([muammo], ["title"])

    assert sarlavhalar(qidiruv_queryset("ipoteka")) == ["Ipoteka masalasi"]


def test_bulk_update_hot_score_matnga_TEGMAYDI():
    muammo = ComplaintFactory(title="Sarlavha")
    muammo.hot_score = 5.0

    with CaptureQueriesContext(connection) as sorovlar:
        Complaint.objects.bulk_update([muammo], ["hot_score"])

    sql = " ".join(s["sql"] for s in sorovlar)
    assert "qidiruv_sarlavha" not in sql


def test_slug_yasash_bilan_BIRGA_ishlaydi():
    """Ikkalasi ham `save()` da `update_fields` ga qo'shiladi — biri
    ikkinchisini bosib ketmasligi kerak."""
    muammo = Complaint(category=CategoryFactory(), title="Ipoteka", description="Matn")
    muammo.save()

    assert muammo.slug
    assert muammo.qidiruv_sarlavha == "ipoteka"


# ===========================================================================
# 3. Qidiruv natijalari
# ===========================================================================
def test_sarlavha_boyicha_topadi():
    ComplaintFactory(title="Ipoteka olish qiyinmi", description="Boshqa matn")
    ComplaintFactory(title="Mashina sotib olish", description="Boshqa matn")

    assert sarlavhalar(qidiruv_queryset("ipoteka")) == ["Ipoteka olish qiyinmi"]


def test_tavsif_boyicha_ham_topadi():
    ComplaintFactory(title="Uy masalasi", description="Bankda ipoteka ochdim")

    assert sarlavhalar(qidiruv_queryset("ipoteka")) == ["Uy masalasi"]


def test_SARLAVHADAGI_moslik_yuqori_turadi():
    """⚠️ Vaznlarning butun ma'nosi shu (A > B). Usiz uzun tavsifda bir
    marta uchragan so'z sarlavhada turgan so'z bilan teng bo'lardi."""
    ComplaintFactory(title="Umumiy savol", description="Menda ipoteka bor edi")
    ComplaintFactory(title="Ipoteka shartlari", description="Umumiy matn")

    assert sarlavhalar(qidiruv_queryset("ipoteka"))[0] == "Ipoteka shartlari"


def test_katta_harf_va_bosh_joy_farq_qilmaydi():
    ComplaintFactory(title="Ipoteka olish")

    assert qidiruv_queryset("  IPOTEKA  ").count() == 1


def test_ikki_soz_IKKALASINI_ham_talab_qiladi():
    """`websearch` bo'sh joyni VA deb o'qiydi — aniqlik uchun to'g'ri
    tanlov: "ipoteka bank" so'ragan odam ikkalasi haqidagi postni
    kutadi."""
    ComplaintFactory(title="Ipoteka va bank")
    ComplaintFactory(title="Faqat ipoteka")

    assert sarlavhalar(qidiruv_queryset("ipoteka bank")) == ["Ipoteka va bank"]


def test_qoshtirnoqli_ibora_ANIQ_tartibni_talab_qiladi():
    """`websearch` ning `plain` dan ustunligi — bepul keladigan imkoniyat."""
    ComplaintFactory(title="Ipoteka krediti haqida", description="Matn")
    ComplaintFactory(title="Krediti ipoteka teskari", description="Matn")

    natija = sarlavhalar(qidiruv_queryset('"ipoteka krediti"'))

    assert natija == ["Ipoteka krediti haqida"]


def test_bosh_sorov_BOSH_natija():
    """⚠️ "Hammasini ko'rsatish" YOLG'ON bo'lardi: odam hech narsa
    so'ramagan."""
    ComplaintFactory(title="Ipoteka")

    assert qidiruv_queryset("").count() == 0
    assert qidiruv_queryset("   ").count() == 0


@pytest.mark.parametrize(
    "buzuq",
    ["((", "&", "!", "|", ":*", "a:*b", '"', "'", chr(92), "-", "<script>", "&&&"],
)
def test_buzuq_kiritma_500_BERMAYDI(buzuq):
    """⚠️ Bunday so'rovlar botlardan va qo'lda tahrirlangan URL'lardan
    DOIM keladi. `raw` turi ularda `ProgrammingError` berardi —
    `websearch` bermaydi."""
    ComplaintFactory(title="Ipoteka")

    assert qidiruv_queryset(buzuq).count() >= 0


# ===========================================================================
# 3b. Ikki alifbo va apostrof — uchidan-uchiga (D4-T2)
# ===========================================================================
def test_KIRILCHA_sorov_LOTINCHA_postni_topadi():
    """⚠️ D4-T2 qabul mezoni, indeks bilan birga tekshiriladi.

    Normallashtirish testlari (`apps/common/tests/test_matn.py`) faqat
    funksiyani sinaydi. Bu test esa ustunlar, tsvector va so'rov —
    uchalasi ham BIR XIL normal shaklda ekanini isbotlaydi.
    """
    ComplaintFactory(title="Ipoteka olish qiyinmi")

    assert sarlavhalar(qidiruv_queryset("ипотека")) == ["Ipoteka olish qiyinmi"]


def test_LOTINCHA_sorov_KIRILCHA_postni_topadi():
    """Teskari yo'nalish — kontent kirillcha yozilgan holat."""
    ComplaintFactory(title="Ипотека олиш қийинми")

    assert sarlavhalar(qidiruv_queryset("ipoteka")) == ["Ипотека олиш қийинми"]


@pytest.mark.parametrize(
    "sorov",
    ["ko'chmas", "koʻchmas", "ko‘chmas", "ko`chmas", "kochmas", "кўчмас"],
)
def test_APOSTROFNING_har_varianti_bir_xil_natija_beradi(sorov):
    """⚠️⚠️ Qidiruv foydalanuvchining KLAVIATURASIGA bog'liq
    bo'lmasligi kerak — D4-T2 ning butun ma'nosi shu."""
    ComplaintFactory(title="Ko'chmas mulk masalasi")

    assert sarlavhalar(qidiruv_queryset(sorov)) == ["Ko'chmas mulk masalasi"]


def test_APOSTROFSIZ_yozilgan_post_ham_topiladi():
    """Teskari tomon: kontent apostrofsiz yozilgan, so'rov apostrofli."""
    ComplaintFactory(title="Kochmas mulk masalasi")

    assert sarlavhalar(qidiruv_queryset("ko'chmas")) == ["Kochmas mulk masalasi"]


# ===========================================================================
# 4. Ko'rinish invarianti (D2-T3)
# ===========================================================================
def test_YASHIRILGAN_post_qidiruvda_YOQ():
    ComplaintFactory(
        title="Ipoteka yashirin", moderation_status=ModerationStatus.HIDDEN
    )
    ComplaintFactory(title="Ipoteka ochiq")

    assert sarlavhalar(qidiruv_queryset("ipoteka")) == ["Ipoteka ochiq"]


def test_OCHIRILGAN_post_qidiruvda_YOQ():
    ochirilgan = ComplaintFactory(title="Ipoteka ochirilgan")
    ochirilgan.delete()
    ComplaintFactory(title="Ipoteka ochiq")

    assert sarlavhalar(qidiruv_queryset("ipoteka")) == ["Ipoteka ochiq"]


def test_BLOKLANGAN_muallif_qidiruvda_ham_chiqmaydi(user, other_user):
    """D2-T11: blok lentada ishlagani kabi qidiruvda ham ishlashi kerak."""
    ComplaintFactory(title="Ipoteka bloklangandan", author=other_user)
    ComplaintFactory(title="Ipoteka boshqadan", author=user)

    natija = qidiruv_queryset("ipoteka", bloklanganlar=[other_user.pk])

    assert sarlavhalar(natija) == ["Ipoteka boshqadan"]


def test_kategoriya_filtri_qidiruv_bilan_birga_ishlaydi():
    moliya = CategoryFactory(slug="moliya", name="Moliya")
    ComplaintFactory(title="Ipoteka moliyada", category=moliya)
    ComplaintFactory(title="Ipoteka boshqada")

    natija = qidiruv_queryset("ipoteka", filtr=LentaFiltri(category="moliya"))

    assert sarlavhalar(natija) == ["Ipoteka moliyada"]


# ===========================================================================
# 5. Xato yozilgan so'rov — trigram
# ===========================================================================
def test_XATO_yozilgan_soz_taklif_beradi():
    """⚠️ D4-T1 tavsifidagi "pg_trgm xato yozuvlar uchun": bitta harf
    xato bo'lsa tsvector HECH NARSA topmaydi."""
    ComplaintFactory(title="Ipoteka olish qiyinmi")

    assert qidiruv_queryset("ipotaka").count() == 0  # asosiy qidiruv topmaydi
    assert sarlavhalar(taxminiy_natijalar("ipotaka")) == ["Ipoteka olish qiyinmi"]


def test_ALOQASIZ_soz_taklif_BERMAYDI():
    """⚠️ Chegara pasaytirilsa "hech narsa topilmadi" o'rniga aloqasiz
    takliflar chiqadi — bu yomonroq: foydalanuvchi qidiruv umuman
    ishlamayapti deb o'ylaydi."""
    ComplaintFactory(title="Ipoteka olish qiyinmi")

    assert list(taxminiy_natijalar("velosiped")) == []


def test_taklif_soni_chegaralangan():
    for i in range(8):
        ComplaintFactory(title=f"Ipoteka masalasi {i}")

    assert len(list(taxminiy_natijalar("ipotaka", soni=3))) == 3


def test_YASHIRILGAN_post_taklifda_ham_YOQ():
    """⚠️ Oson unutiladigan ikkinchi yo'l: asosiy qidiruvda filtr bor,
    taklifda esa yo'q — yashirin kontent aynan shu yerdan sizib
    chiqadi."""
    ComplaintFactory(
        title="Ipoteka yashirin", moderation_status=ModerationStatus.HIDDEN
    )

    assert list(taxminiy_natijalar("ipotaka")) == []


def test_bosh_sorov_taklif_ham_BERMAYDI():
    ComplaintFactory(title="Ipoteka")

    assert list(taxminiy_natijalar("")) == []


# ===========================================================================
# 6. Qayta indekslash buyrug'i
# ===========================================================================
def test_buyruq_ESKIRGAN_yozuvni_topadi_va_tuzatadi():
    """⚠️ Ustunlar SAQLANGAN qiymat: `qidiruv_uchun()` o'zgarganda eski
    yozuvlar eski shaklda qoladi. Buyruq — yagona tuzatish yo'li
    (D4-T2 aynan shu yo'ldan o'tadi)."""
    muammo = ComplaintFactory(title="Ipoteka olish")
    # Normallashtirish qoidalari o'zgargan holatni taqlid qilamiz.
    Complaint.all_objects.filter(pk=muammo.pk).update(qidiruv_sarlavha="eskirgan matn")

    assert qidiruv_queryset("ipoteka").count() == 0  # indeks buzilgan

    call_command("qidiruvni_yangilash", verbosity=0)

    assert qidiruv_queryset("ipoteka").count() == 1


def test_buyruq_tekshir_rejimida_YOZMAYDI():
    muammo = ComplaintFactory(title="Ipoteka olish")
    Complaint.all_objects.filter(pk=muammo.pk).update(qidiruv_sarlavha="eskirgan")

    call_command("qidiruvni_yangilash", "--tekshir", verbosity=0)

    muammo.refresh_from_db()
    assert muammo.qidiruv_sarlavha == "eskirgan"


# ===========================================================================
# 7. Konfiguratsiya guardi
# ===========================================================================
def test_INDEKS_va_SOROV_konfiguratsiyasi_bir_xil():
    """⚠️⚠️ Eng jim buziladigan joy: `search_vector` `'simple'` bilan
    qurilgan; so'rov boshqa konfiguratsiya bilan yuborilsa PostgreSQL
    xato BERMAYDI, shunchaki hech narsa topmaydi.

    ⚠️ Tekshiruv MODEL EMAS, BAZA ustidan. Django ifodasining `str()` i
       konfiguratsiyani umuman ko'rsatmaydi (`CombinedSearchVector`
       uni yashiradi), va undan ham muhimi: haqiqiy savol "bazada
       nima turibdi?" — ya'ni migratsiya qo'llanganmi. Model ustidan
       tekshiruv qo'llanmagan migratsiyani ham yashil deb ko'rsatardi.
    """
    with connection.cursor() as kursor:
        kursor.execute(
            """
            SELECT pg_get_expr(d.adbin, d.adrelid)
            FROM pg_attrdef d
            JOIN pg_attribute a
              ON a.attrelid = d.adrelid AND a.attnum = d.adnum
            WHERE d.adrelid = 'complaints_complaint'::regclass
              AND a.attname = 'search_vector'
            """
        )
        qator = kursor.fetchone()

    assert qator, "`search_vector` GENERATED ustuni bazada topilmadi"
    assert "'simple'::regconfig" in qator[0], "indeks konfiguratsiyasi o'zgargan"

    sql = str(qidiruv_queryset("ipoteka").query)
    assert "simple" in sql, "so'rov konfiguratsiyasi o'zgargan"


# ===========================================================================
# 8. Ish unumdorligi — D4-T1 qabul mezoni
# ===========================================================================
def test_10_MING_postda_qidiruv_200ms_dan_TEZ():
    """⚠️ D4-T1 qabul mezoni: "10 ming postda qidiruv <200ms".

    ⚠️ Sun'iy ma'lumot ATAYLAB YOMON HOLAT: barcha sarlavhalar bitta
       kichik lug'atdan olinadi, ya'ni ko'p yozuv so'rovga mos keladi va
       PostgreSQL indeks o'rniga ketma-ket skanerlashni tanlashi mumkin.
       Haqiqiy ma'lumotda so'rov faqat tezroq bo'ladi.
    """
    kat = CategoryFactory()
    sozlar = ["ipoteka", "kredit", "ijara", "maosh", "viza", "soliq", "meros"]

    Complaint.objects.bulk_create(
        [
            Complaint(
                category=kat,
                title=f"{sozlar[i % len(sozlar)]} masalasi {i}",
                description=" ".join(sozlar) * 5,
            )
            for i in range(10_000)
        ],
        batch_size=1000,
    )

    boshi = time.perf_counter()
    natija = list(qidiruv_queryset("ipoteka")[:20])
    ketgan_ms = (time.perf_counter() - boshi) * 1000

    assert natija, "10 ming postda hech narsa topilmadi — indeks buzilganmi?"
    assert ketgan_ms < 200, f"qidiruv {ketgan_ms:.0f} ms davom etdi (chegara 200 ms)"
