"""Postni ko'tarish — boost (D6-T4).

QABUL MEZONLARI VA ULARNI ISBOTLAYDIGAN TESTLAR

    «boost belgisi ochiq ko'rinadi»
        -> `test_JOYDAGI_kartada_PULLIK_JOY_belgisi_bor`
        -> `test_ORGANIK_orindagi_boostli_post_BELGISIZ_va_TAKRORLANMAYDI`

    «lentada boost ulushi cheklangan (har 5 postdan 1 tasi)»
        -> `test_ULUSH_qoidasi_HAMMA_kombinatsiyada` (sof funksiya)
        -> `test_JOYLAR_soni_CHEKLANGAN_va_ORTIQCHA_boost_CHIQMAYDI` (jonli lenta)

⚠️ Lenta testlarida boostli post `hot_score` i PAST qilib yaratiladi:
   aks holda u organik birinchi sahifaga tushadi va joyga (to'g'ri
   ravishda) umuman chiqmaydi — test esa noto'g'ri sababdan o'tardi.
"""

from __future__ import annotations

import base64
import json
import re
from datetime import timedelta
from decimal import Decimal
from unittest import mock

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.accounts.factories import BannedUserFactory
from apps.accounts.models import UserBlock
from apps.common.models import ModerationStatus
from apps.complaints.factories import CategoryFactory, ComplaintFactory
from apps.complaints.models import Complaint, ComplaintStatus
from apps.complaints.selectors import SAHIFA_HAJMI
from apps.complaints.tasks import hot_score_hisobla, hot_scorelarni_yangilash
from apps.payments import click, payme
from apps.payments.models import (
    BoostOrder,
    Provayder,
    Tolov,
    TolovHolati,
    TolovMaqsadi,
)
from apps.payments.selectors import boost_joylari_soni, boostlarni_joylash
from apps.payments.services import (
    _MAQSAD_BAJARUVCHILARI,
    _MAQSAD_BEKOR_QILUVCHILARI,
    _MAQSAD_TEKSHIRUVCHILARI,
    Sabab,
    _boostni_berish,
    _boostni_qaytarib_olish,
    boost_buyurtmasi_yaratish,
    kotarib_bolmaslik_sababi,
)
from apps.payments.views import PAYME_SABAB_KODI, SABAB_KODI

pytestmark = pytest.mark.django_db

SIR = "sinov-maxfiy-kalit"
XIZMAT = "12345"
PAYME_KALIT = "sinov-payme-kaliti"
NARX = "5000"
TIYIN = 500_000  # 5 000 so'm

# Ko'tarib bo'lmaydigan postlar — yaroqlilik VA lenta testlarida bir xil.
YAROQSIZ_POSTLAR = {
    "yashirilgan": {"moderation_status": ModerationStatus.HIDDEN},
    "tekshiruvda": {"moderation_status": ModerationStatus.PENDING},
    "yechilgan": {"status": ComplaintStatus.SOLVED},
    "yopilgan": {"status": ComplaintStatus.CLOSED},
    "inqiroz belgili": {"inqiroz_aniqlandi": True},
}


# ===========================================================================
# Yordamchilar
# ===========================================================================
@pytest.fixture(autouse=True)
def _sozlamalar(settings):
    """Ikkala provayder ULANGAN, boost qoidalari standart qiymatda.

    ⚠️ `*_YOQILGANMI` sozlama yuklanganda hisoblanadi — kalitlarni
       o'zgartirish yetarli emas, bayroqni ham berish SHART (D6-T2).
    """
    settings.CLICK_SECRET_KEY = SIR
    settings.CLICK_SERVICE_ID = XIZMAT
    settings.CLICK_MERCHANT_ID = "67890"
    settings.CLICK_YOQILGANMI = True
    settings.PAYME_SECRET_KEY = PAYME_KALIT
    settings.PAYME_MERCHANT_ID = "5e730e8e0b852a417aa49ceb"
    settings.PAYME_YOQILGANMI = True
    settings.BOOST_NARXI = NARX
    settings.BOOST_MUDDATI_KUN = 1
    settings.BOOST_BIRINCHI_JOY = 3
    settings.BOOST_ORALIQ = 5


def _boost(muammo, *, boshlanish=None, tugash=None) -> BoostOrder:
    """Webhook'siz tayyor boost qatori (sanalarsiz — to'lanmagan)."""
    tolov = Tolov.objects.create(
        user=muammo.author,
        provayder=Provayder.CLICK,
        summa=Decimal(NARX),
        maqsad=TolovMaqsadi.BOOST,
        holat=TolovHolati.TOLANDI,
    )
    return BoostOrder.objects.create(
        tolov=tolov, complaint=muammo, starts_at=boshlanish, ends_at=tugash
    )


def _faol(muammo) -> BoostOrder:
    hozir = timezone.now()
    return _boost(
        muammo,
        boshlanish=hozir - timedelta(hours=1),
        tugash=hozir + timedelta(hours=23),
    )


def _pastki_post(**kw) -> Complaint:
    """Organik birinchi sahifadan TASHQARIDAGI post (docstring'ga qarang)."""
    return ComplaintFactory(hot_score=-100.0, **kw)


def _organik(soni: int = SAHIFA_HAJMI, **kw) -> list[Complaint]:
    """Birinchi sahifani to'ldiradigan postlar — eng qaynog'i birinchi."""
    return [ComplaintFactory(hot_score=float(1000 - i), **kw) for i in range(soni)]


def _lenta(client, **params) -> list[Complaint]:
    javob = client.get(reverse("feed"), params)
    assert javob.status_code == 200
    return list(javob.context["complaints"])


def _buyurtma(muammo, provayder: str) -> Tolov:
    return boost_buyurtmasi_yaratish(
        user=muammo.author, muammo=muammo, provayder=provayder, summa=Decimal(NARX)
    )


def _click(client, tolov, *, amal: int) -> dict:
    """Click yuboradigan shakldagi so'rov; imzo OXIRIDA qo'yiladi."""
    malumot = {
        "click_trans_id": "7001",
        "service_id": XIZMAT,
        "click_paydoc_id": "555000",
        "merchant_trans_id": str(tolov.pk),
        "amount": f"{Decimal(NARX):.2f}",
        "action": str(amal),
        "error": "0",
        "error_note": "",
        "sign_time": "2026-09-11 12:00:00",
    }
    if amal == click.AMAL_COMPLETE:
        malumot["merchant_prepare_id"] = str(tolov.pk)
    malumot["sign_string"] = click.imzo_hisoblash(malumot, amal=amal, maxfiy_kalit=SIR)
    manzil = reverse(
        "click_prepare" if amal == click.AMAL_PREPARE else "click_complete"
    )
    return client.post(manzil, malumot).json()


def _payme(client, metod: str, params: dict) -> dict:
    sarlavha = "Basic " + base64.b64encode(f"Paycom:{PAYME_KALIT}".encode()).decode()
    return client.post(
        reverse("payme_webhook"),
        data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": metod, "params": params}),
        content_type="application/json",
        headers={"Authorization": sarlavha},
    ).json()


# ===========================================================================
# 1. Joylash — sof funksiya
# ===========================================================================
def test_ULUSH_qoidasi_HAMMA_kombinatsiyada():
    """⭐⭐ QABUL MEZONI: «lentada boost ulushi cheklangan».

    Organik 0..25 va boost 0..6 ning HAR kombinatsiyasi: ketma-ket
    istalgan 5 kartada ko'pi bilan bitta boost, organik tartib va
    to'liqlik saqlanadi, birinchi ikkita karta organik, boost hech
    qachon oxirida emas.
    """
    for organik_soni in range(26):
        for boost_soni in range(7):
            organik = [("o", i) for i in range(organik_soni)]
            boostlar = [("b", i) for i in range(boost_soni)]
            natija = boostlarni_joylash(organik, boostlar)
            belgilar = [tur == "b" for tur, _ in natija]
            holat = f"organik={organik_soni}, boost={boost_soni}: {natija}"

            for boshi in range(len(belgilar)):
                assert sum(belgilar[boshi : boshi + 5]) <= 1, holat
            assert [x for x in natija if x[0] == "o"] == organik, holat
            assert not any(belgilar[:2]), holat
            if natija:
                assert natija[-1][0] == "o", holat


def test_standart_JOYLAR_3_8_13_18_va_SAHIFADA_24_karta():
    natija = boostlarni_joylash(list(range(SAHIFA_HAJMI)), ["b"] * boost_joylari_soni())

    assert [i + 1 for i, x in enumerate(natija) if x == "b"] == [3, 8, 13, 18]
    assert len(natija) == SAHIFA_HAJMI + 4


def test_QISQA_royxatda_boost_OXIRGA_yopishtirilmaydi():
    assert boostlarni_joylash(["o1", "o2"], ["b"]) == ["o1", "o2"]
    assert boostlarni_joylash(["o1", "o2", "o3"], ["b"]) == ["o1", "o2", "b", "o3"]


def test_JOYLAR_soni_SAHIFA_HAJMIDAN_hisoblanadi(settings):
    assert boost_joylari_soni() == SAHIFA_HAJMI // 5

    settings.BOOST_ORALIQ = 10

    assert boost_joylari_soni() == SAHIFA_HAJMI // 10


# ===========================================================================
# 2. «Faol» ta'rifi — model
# ===========================================================================
def test_FAOL_chegarasi_BOSHLANISH_kiradi_TUGASH_kirmaydi():
    """`faol()` va `faolmi` — BITTA ta'rif, chegaralari bir xil."""
    hozir = timezone.now()
    boshlanishda = _boost(
        ComplaintFactory(), boshlanish=hozir, tugash=hozir + timedelta(hours=1)
    )
    tugashda = _boost(
        ComplaintFactory(), boshlanish=hozir - timedelta(hours=1), tugash=hozir
    )
    tolanmagan = _boost(ComplaintFactory())

    with mock.patch("django.utils.timezone.now", return_value=hozir):
        assert set(BoostOrder.objects.faol()) == {boshlanishda}
        assert boshlanishda.faolmi is True
        assert tugashda.faolmi is False
        assert tolanmagan.faolmi is False


# ===========================================================================
# 3. Berish va qaytarib olish — servis
# ===========================================================================
def test_BUYURTMA_Tolov_va_BoostOrder_ni_BIRGA_yaratadi():
    muammo = ComplaintFactory()

    tolov = _buyurtma(muammo, Provayder.CLICK)

    assert tolov.maqsad == TolovMaqsadi.BOOST
    assert tolov.boost.complaint == muammo
    assert tolov.boost.starts_at is None


def test_BERISH_oraliqni_HOZIRDAN_1_kunga_ochadi():
    boost = _boost(ComplaintFactory())

    assert _boostni_berish(boost.tolov) == 1

    boost.refresh_from_db()
    assert boost.faolmi
    assert boost.ends_at - boost.starts_at == timedelta(days=1)


def test_FAOL_boost_USTIGA_tolov_OXIRIDAN_davom_etadi():
    """⭐ Erta to'lagan odam qolgan soatlarini yo'qotmaydi (obuna qoidasi)."""
    muammo = ComplaintFactory()
    birinchi = _faol(muammo)
    ikkinchi = _boost(muammo)

    _boostni_berish(ikkinchi.tolov)

    ikkinchi.refresh_from_db()
    assert ikkinchi.starts_at == birinchi.ends_at
    assert ikkinchi.navbatdami


def test_TUGAGAN_boostdan_keyin_HOZIRDAN_boshlanadi():
    muammo = ComplaintFactory()
    hozir = timezone.now()
    _boost(
        muammo, boshlanish=hozir - timedelta(days=3), tugash=hozir - timedelta(days=2)
    )
    yangi = _boost(muammo)

    _boostni_berish(yangi.tolov)

    yangi.refresh_from_db()
    assert yangi.starts_at >= hozir
    assert yangi.faolmi


def test_BOSHQA_postning_boosti_NAVBATGA_tasir_qilmaydi():
    _faol(ComplaintFactory())
    yangi = _boost(ComplaintFactory())

    _boostni_berish(yangi.tolov)

    yangi.refresh_from_db()
    assert yangi.faolmi


def test_QAYTARISH_faol_oraliqni_DARHOL_yopadi_qator_QOLADI():
    boost = _faol(ComplaintFactory())

    _boostni_qaytarib_olish(boost.tolov)

    boost.refresh_from_db()
    assert boost.faolmi is False
    assert boost.ends_at <= timezone.now()


def test_QAYTARISH_navbatdagini_NOL_uzunlikka_tushiradi():
    muammo = ComplaintFactory()
    _faol(muammo)
    navbat = _boost(muammo)
    _boostni_berish(navbat.tolov)

    _boostni_qaytarib_olish(navbat.tolov)

    navbat.refresh_from_db()
    assert navbat.ends_at == navbat.starts_at
    with mock.patch("django.utils.timezone.now", return_value=navbat.starts_at):
        assert not BoostOrder.objects.faol().filter(pk=navbat.pk).exists()
    # ⚠️ Sotib olish sahifasi uni «ko'tarilgan ... gacha» deb ko'rsatmasin.
    assert not BoostOrder.objects.tugamagan().filter(pk=navbat.pk).exists()


def test_QAYTARISH_TUGAGAN_oraliqqa_TEGMAYDI():
    hozir = timezone.now()
    tugash = hozir - timedelta(days=1)
    boost = _boost(
        ComplaintFactory(), boshlanish=hozir - timedelta(days=2), tugash=tugash
    )

    _boostni_qaytarib_olish(boost.tolov)

    boost.refresh_from_db()
    assert boost.ends_at == tugash


def test_QAYTARISH_tolanmagan_buyurtmada_YIQILMAYDI():
    boost = _boost(ComplaintFactory())

    _boostni_qaytarib_olish(boost.tolov)

    boost.refresh_from_db()
    assert boost.ends_at is None


# ===========================================================================
# 4. Kim, qaysi postni ko'tara oladi
# ===========================================================================
def test_MUALLIF_ochiq_postini_KOTARA_OLADI():
    muammo = ComplaintFactory()

    assert kotarib_bolmaslik_sababi(user=muammo.author, muammo=muammo) is None


def test_BEGONA_postni_kotara_OLMAYDI(user):
    assert kotarib_bolmaslik_sababi(user=user, muammo=ComplaintFactory()) is not None


@pytest.mark.parametrize("nom", YAROQSIZ_POSTLAR)
def test_YAROQSIZ_postni_kotarib_BOLMAYDI(nom):
    muammo = ComplaintFactory(**YAROQSIZ_POSTLAR[nom])

    assert kotarib_bolmaslik_sababi(user=muammo.author, muammo=muammo) is not None


def test_OCHIRILGAN_postni_kotarib_BOLMAYDI():
    """⚠️ `is_publicly_visible` o'chirilganlikni KO'RMAYDI — alohida shart."""
    muammo = ComplaintFactory()
    muammo.delete()

    assert kotarib_bolmaslik_sababi(user=muammo.author, muammo=muammo) is not None


def test_CHEKLANGAN_muallif_kotara_OLMAYDI():
    muammo = ComplaintFactory(author=BannedUserFactory())

    assert kotarib_bolmaslik_sababi(user=muammo.author, muammo=muammo) is not None


def test_JORIY_SHARTLARGA_rozilik_bermagan_muallif_kotara_OLMAYDI():
    """⭐ D2-T10: shartlar yangilangach qayta rozilik bermagan odam."""
    muammo = ComplaintFactory()
    muammo.author.rozilik_versiyasi = "eski-versiya"

    assert kotarib_bolmaslik_sababi(user=muammo.author, muammo=muammo) is not None


def test_INQIROZ_sababi_matnda_AYTILMAYDI():
    """⭐⭐ D2-T6: aniqlangan post muallifi HECH QANDAY ogohlantirish olmaydi."""
    muammo = ComplaintFactory(inqiroz_aniqlandi=True)

    sabab = kotarib_bolmaslik_sababi(user=muammo.author, muammo=muammo)

    assert sabab is not None
    assert "inqiroz" not in sabab.lower()
    assert "xavf" not in sabab.lower()


# ===========================================================================
# 5. Lenta — joylar, belgi, invariantlar
# ===========================================================================
def test_JOYDAGI_kartada_PULLIK_JOY_belgisi_bor(client):
    """⭐⭐ QABUL MEZONI: «boost belgisi ochiq ko'rinadi»."""
    kotarilgan = _pastki_post()
    _faol(kotarilgan)
    _organik()

    royxat = _lenta(client)
    matn = client.get(reverse("feed")).content.decode()

    assert royxat[2].pk == kotarilgan.pk
    assert royxat[2].kotarilgan is True
    assert matn.count("Ko'tarilgan — pullik joy") == 1


def test_ORGANIK_orindagi_boostli_post_BELGISIZ_va_TAKRORLANMAYDI(client):
    """Organik o'rnini o'zi olgan post pullik joyni ham, belgini ham olmaydi."""
    organik = _organik()
    _faol(organik[0])

    royxat = _lenta(client)

    assert [m.pk for m in royxat] == [m.pk for m in organik]
    assert not any(m.kotarilgan for m in royxat)
    assert "pullik joy" not in client.get(reverse("feed")).content.decode()


def test_JOYLAR_soni_CHEKLANGAN_va_ORTIQCHA_boost_CHIQMAYDI(client):
    """10 ta faol boost, 4 ta joy — qolganlari bu safar ko'rinmaydi (navbat)."""
    for _ in range(10):
        _faol(_pastki_post())
    _organik()

    royxat = _lenta(client)

    assert [i + 1 for i, m in enumerate(royxat) if m.kotarilgan] == [3, 8, 13, 18]
    assert len(royxat) == SAHIFA_HAJMI + 4
    assert len({m.pk for m in royxat}) == len(royxat)


def test_KURSOR_oxirgi_ORGANIK_postdan(client):
    """⭐⭐ Kursor boost postidan qurilsa, ikkinchi sahifa buzilardi."""
    _faol(_pastki_post())
    organik = _organik(SAHIFA_HAJMI + 5)
    oxirgi_organik = organik[SAHIFA_HAJMI - 1]

    javob = client.get(reverse("feed"))
    assert javob.context["keyingi_kursor"] == oxirgi_organik.pk

    ikkinchi = _lenta(client, after=oxirgi_organik.pk)
    assert [m.pk for m in ikkinchi[:5]] == [m.pk for m in organik[SAHIFA_HAJMI:]]


def test_IKKINCHI_sahifada_JOY_YOQ(client):
    """⚠️ Boost faqat BIRINCHI sahifada.

    ⚠️ Boostli post ATAYLAB birinchi sahifadagi organik post: ikkinchi
       sahifaning organik ro'yxatida u YO'Q, ya'ni joy ruxsat etilsa u
       albatta joyga tushardi. Pastki post bilan esa bu test BUZILGAN
       kodda ham o'tardi: u ikkinchi sahifaning organik qismida turadi
       va nomzodlardan baribir chiqariladi. Yangi shaklni mutatsiya
       tasdiqlagan (`boost_joyi_bormi` dan `after_pk` sharti olib
       tashlanganda bu test yiqiladi).
    """
    organik = _organik(SAHIFA_HAJMI + 5)
    _faol(organik[0])

    ikkinchi = _lenta(client, after=organik[SAHIFA_HAJMI - 1].pk)

    assert not any(m.kotarilgan for m in ikkinchi)
    assert organik[0].pk not in [m.pk for m in ikkinchi]


@pytest.mark.parametrize("sort", ["new", "top", "solved"])
def test_QAYNOQDAN_boshqa_saralashda_JOY_YOQ(client, sort):
    _faol(_pastki_post())
    _organik()

    assert not any(m.kotarilgan for m in _lenta(client, sort=sort))


def test_KATEGORIYA_filtrida_faqat_MOS_boost(client):
    moliya = CategoryFactory(slug="moliya")
    talim = CategoryFactory(slug="talim")
    mos = _pastki_post(category=moliya)
    _faol(mos)
    _faol(_pastki_post(category=talim))
    _organik(category=moliya)

    royxat = _lenta(client, category="moliya")

    assert {m.pk for m in royxat if m.kotarilgan} == {mos.pk}


@pytest.mark.parametrize("nom", YAROQSIZ_POSTLAR)
def test_YAROQSIZ_postning_boosti_JOYGA_chiqmaydi(client, nom):
    """⭐ Pullik joy ko'rinish invariantini (D2-T3) chetlab o'tmaydi."""
    _faol(_pastki_post(**YAROQSIZ_POSTLAR[nom]))
    _organik()

    assert not any(m.kotarilgan for m in _lenta(client))


@pytest.mark.parametrize("nom", ["tugagan", "navbatda", "tolanmagan"])
def test_FAOL_BOLMAGAN_boost_JOYGA_chiqmaydi(client, nom):
    muammo = _pastki_post()
    hozir = timezone.now()
    if nom == "tugagan":
        _boost(
            muammo,
            boshlanish=hozir - timedelta(days=2),
            tugash=hozir - timedelta(days=1),
        )
    elif nom == "navbatda":
        _boost(
            muammo,
            boshlanish=hozir + timedelta(hours=1),
            tugash=hozir + timedelta(days=1),
        )
    else:
        _boost(muammo)
    _organik()

    assert not any(m.kotarilgan for m in _lenta(client))


def test_BLOKLANGAN_muallifning_boosti_BLOKLAGANGA_chiqmaydi(client, user):
    """⭐ Pullik joy foydalanuvchining o'z blokini chetlab o'tmaydi (D2-T11)."""
    kotarilgan = _pastki_post()
    _faol(kotarilgan)
    _organik()
    UserBlock.objects.create(user=user, blocked=kotarilgan.author)
    client.force_login(user)

    assert not any(m.kotarilgan for m in _lenta(client))


def test_boost_sorovi_BOOSTLAR_SONIGA_bogliq_EMAS(client):
    """D1-T14 naqshi: bitta va o'nta faol boost — bir xil so'rov soni."""
    _organik()
    _faol(_pastki_post())

    def olchov() -> int:
        client.get(reverse("feed"))  # iliting
        with CaptureQueriesContext(connection) as sorovlar:
            assert client.get(reverse("feed")).status_code == 200
        return len(sorovlar)

    bitta = olchov()
    for _ in range(9):
        _faol(_pastki_post())

    assert olchov() == bitta


def test_BOOST_hot_score_ga_TEGMAYDI():
    """⭐⭐ Task tavsifidan ONGLI chekinish — sabab `BoostOrder` docstring'ida.

    Pullik ball kanal avto-postiga (D5-T3) belgisiz reklama bo'lib
    tushardi va lenta kursorini (D1-T12) siljitardi.
    """
    muammo = ComplaintFactory()
    _faol(muammo)

    hot_scorelarni_yangilash()

    muammo.refresh_from_db()
    assert muammo.hot_score == hot_score_hisobla(
        score=muammo.score_cached, created_at=muammo.created_at
    )


# ===========================================================================
# 6. Batafsil sahifadagi tugma
# ===========================================================================
def _tugma_bormi(client, muammo) -> bool:
    matn = client.get(muammo.get_absolute_url()).content.decode()
    return reverse("kotarish", args=[muammo.pk]) in matn


def test_MUALLIFGA_KOTARISH_tugmasi_CHIQADI(client):
    muammo = ComplaintFactory()
    client.force_login(muammo.author)

    assert _tugma_bormi(client, muammo)


def test_BEGONAGA_tugma_YOQ(client, user):
    client.force_login(user)

    assert not _tugma_bormi(client, ComplaintFactory())


def test_TOLOV_ULANMAGAN_bolsa_tugma_YOQ(client, settings):
    settings.CLICK_YOQILGANMI = False
    settings.PAYME_YOQILGANMI = False
    muammo = ComplaintFactory()
    client.force_login(muammo.author)

    assert not _tugma_bormi(client, muammo)


def test_YECHILGAN_postda_tugma_YOQ(client):
    muammo = ComplaintFactory(status=ComplaintStatus.SOLVED)
    client.force_login(muammo.author)

    assert not _tugma_bormi(client, muammo)


def test_YOZISH_formasida_SOXTA_boost_tugmasi_YOQ(auth_client):
    """⭐ Maketdagi `data-toast` tugmasi serverga hech narsa yubormasdi."""
    matn = auth_client.get(reverse("complaint_create")).content.decode()

    assert "beta versiyada" not in matn
    assert "5 000 so'm — Ko'tarish" not in matn


# ===========================================================================
# 7. Sotib olish sahifasi va buyurtma
# ===========================================================================
def test_KOTARISH_sahifasi_MEHMONNI_kirishga_yuboradi(client):
    javob = client.get(reverse("kotarish", args=[ComplaintFactory().pk]))

    assert javob.status_code == 302


def test_BEGONA_postning_sahifasi_404(client, user):
    client.force_login(user)

    javob = client.get(reverse("kotarish", args=[ComplaintFactory().pk]))

    assert javob.status_code == 404


def test_YASHIRILGAN_OZ_postining_sahifasi_404(client):
    muammo = ComplaintFactory(moderation_status=ModerationStatus.HIDDEN)
    client.force_login(muammo.author)

    assert client.get(reverse("kotarish", args=[muammo.pk])).status_code == 404


def test_sahifada_NARX_QOIDALAR_va_OCHIQ_RAQAM(client):
    """⭐⭐ Sotuv cheklanmagan — joylar band ekani TO'LOVDAN OLDIN aytiladi."""
    for _ in range(5):
        _faol(ComplaintFactory())
    muammo = ComplaintFactory()
    client.force_login(muammo.author)

    matn = client.get(reverse("kotarish", args=[muammo.pk])).content.decode()

    assert re.search(r"5\s000", matn)
    assert "navbat bilan" in matn
    assert "pullik joy" in matn
    assert 'content="noindex, nofollow"' in matn
    assert reverse("kotarish_sotib_olish", args=[muammo.pk, "click"]) in matn


def test_KOTARIB_BOLMAYDIGAN_postda_SABAB_bor_TUGMA_yoq(client):
    muammo = ComplaintFactory(status=ComplaintStatus.SOLVED)
    client.force_login(muammo.author)

    matn = client.get(reverse("kotarish", args=[muammo.pk])).content.decode()

    assert "Yechilgan yoki yopilgan" in matn
    assert reverse("kotarish_sotib_olish", args=[muammo.pk, "click"]) not in matn


def test_FAOL_boostli_postda_TUGASH_vaqti_va_UZAYTIRISH(client):
    muammo = ComplaintFactory()
    _faol(muammo)
    client.force_login(muammo.author)

    matn = client.get(reverse("kotarish", args=[muammo.pk])).content.decode()

    assert "Post ko'tarilgan" in matn
    assert "Muddatni uzaytirish" in matn


def test_SOTIB_OLISH_buyurtma_yaratib_CLICKga_yuboradi(client, settings):
    muammo = ComplaintFactory()
    client.force_login(muammo.author)

    javob = client.post(
        reverse("kotarish_sotib_olish", args=[muammo.pk, "click"]), {"summa": "1"}
    )

    assert javob.status_code == 302
    assert javob["Location"].startswith(settings.CLICK_TOLOV_MANZILI)
    tolov = Tolov.objects.get()
    assert tolov.maqsad == TolovMaqsadi.BOOST
    # ⚠️ Formadagi "1" E'TIBORSIZ — summa sozlamadan.
    assert tolov.summa == Decimal(NARX)
    assert tolov.boost.complaint == muammo


def test_YECHILGAN_postga_BUYURTMA_yaratilmaydi(client):
    muammo = ComplaintFactory(status=ComplaintStatus.SOLVED)
    client.force_login(muammo.author)

    javob = client.post(reverse("kotarish_sotib_olish", args=[muammo.pk, "click"]))

    assert javob.status_code == 302
    assert javob["Location"] == reverse("kotarish", args=[muammo.pk])
    assert not Tolov.objects.exists()


def test_BEGONA_postga_SOTIB_OLISH_404(client, user):
    client.force_login(user)

    javob = client.post(
        reverse("kotarish_sotib_olish", args=[ComplaintFactory().pk, "click"])
    )

    assert javob.status_code == 404
    assert not Tolov.objects.exists()


def test_GET_bilan_sotib_olib_BOLMAYDI(client):
    muammo = ComplaintFactory()
    client.force_login(muammo.author)

    javob = client.get(reverse("kotarish_sotib_olish", args=[muammo.pk, "click"]))

    assert javob.status_code == 405


def test_NOMALUM_provayder_500_BERMAYDI(client):
    muammo = ComplaintFactory()
    client.force_login(muammo.author)

    javob = client.post(
        reverse("kotarish_sotib_olish", args=[muammo.pk, "boshqa-tizim"])
    )

    assert javob.status_code == 302
    assert not Tolov.objects.exists()


# ===========================================================================
# 8. Webhook'lar orqali to'liq oqim
# ===========================================================================
def test_CLICK_toliq_oqim_POSTNI_KOTARADI(client):
    muammo = ComplaintFactory()
    tolov = _buyurtma(muammo, Provayder.CLICK)

    assert _click(client, tolov, amal=click.AMAL_PREPARE)["error"] == click.MUVAFFAQIYAT
    assert (
        _click(client, tolov, amal=click.AMAL_COMPLETE)["error"] == click.MUVAFFAQIYAT
    )

    tolov.refresh_from_db()
    assert tolov.berilgan_kun == 1
    assert BoostOrder.objects.faol().filter(complaint=muammo).exists()


def test_CLICK_TAKRORIY_complete_oraliqni_IKKI_MARTA_bermaydi(client):
    muammo = ComplaintFactory()
    tolov = _buyurtma(muammo, Provayder.CLICK)
    _click(client, tolov, amal=click.AMAL_PREPARE)
    _click(client, tolov, amal=click.AMAL_COMPLETE)
    birinchi = BoostOrder.objects.get(tolov=tolov).ends_at

    assert (
        _click(client, tolov, amal=click.AMAL_COMPLETE)["error"] == click.MUVAFFAQIYAT
    )

    assert BoostOrder.objects.get(tolov=tolov).ends_at == birinchi


def test_CLICK_PREPARE_yashirilgan_postda_RAD_PUL_YECHILMAYDI(client):
    """⭐⭐ Buyurtma bilan to'lov orasida post yashirildi."""
    muammo = ComplaintFactory()
    tolov = _buyurtma(muammo, Provayder.CLICK)
    Complaint.all_objects.filter(pk=muammo.pk).update(
        moderation_status=ModerationStatus.HIDDEN
    )

    javob = _click(client, tolov, amal=click.AMAL_PREPARE)

    assert javob["error"] == click.BEKOR_QILINGAN
    tolov.refresh_from_db()
    assert tolov.holat == TolovHolati.YANGI


def test_PAYME_pul_QAYTARILSA_boost_DARHOL_tugaydi(client):
    muammo = ComplaintFactory()
    tolov = _buyurtma(muammo, Provayder.PAYME)
    hisob = {payme.ACCOUNT_MAYDONI: str(tolov.pk)}

    yaratish = {"id": "b1", "time": 1757000000000, "amount": TIYIN, "account": hisob}
    assert "result" in _payme(client, payme.CREATE, yaratish)
    assert "result" in _payme(client, payme.PERFORM, {"id": "b1"})
    assert BoostOrder.objects.faol().filter(complaint=muammo).exists()

    javob = _payme(client, payme.CANCEL, {"id": "b1", "reason": 5})

    assert javob["result"]["state"] == payme.HOLAT_QAYTARILDI
    assert not BoostOrder.objects.faol().filter(complaint=muammo).exists()


def test_PAYME_CHECK_PERFORM_yechilgan_postda_RAD_va_DATA_bilan(client):
    """⭐ `account` xatosi — javobda `data` MAJBURIY (D6-T3)."""
    muammo = ComplaintFactory()
    tolov = _buyurtma(muammo, Provayder.PAYME)
    Complaint.all_objects.filter(pk=muammo.pk).update(status=ComplaintStatus.SOLVED)

    javob = _payme(
        client,
        payme.CHECK_PERFORM,
        {"amount": TIYIN, "account": {payme.ACCOUNT_MAYDONI: str(tolov.pk)}},
    )

    assert javob["error"]["code"] == payme.BUYURTMA_YAKUNLANGAN
    assert javob["error"]["data"] == payme.ACCOUNT_MAYDONI


def test_NATIJA_sahifasi_BOOST_uchun_POSTGA_qaytaradi(client):
    muammo = ComplaintFactory()
    tolov = _buyurtma(muammo, Provayder.CLICK)
    _click(client, tolov, amal=click.AMAL_PREPARE)
    _click(client, tolov, amal=click.AMAL_COMPLETE)
    client.force_login(muammo.author)

    matn = client.get(reverse("tolov_natijasi", args=[tolov.pk])).content.decode()

    assert "Postingiz ko'tarildi" in matn
    assert muammo.get_absolute_url() in matn
    assert "PRO obunangiz" not in matn


# ===========================================================================
# 9. Qo'riqchilar
# ===========================================================================
def test_UCHALA_maqsad_lugati_HAR_maqsadni_qamraydi():
    """⭐⭐ Yangi maqsad qo'shilib lug'atlardan biri unutilsa, webhook
    `KeyError` bilan yiqilardi — Click/Payme uchun bu «javob yo'q».
    """
    kutilgan = set(TolovMaqsadi.values)

    assert set(_MAQSAD_BAJARUVCHILARI) == kutilgan
    assert set(_MAQSAD_BEKOR_QILUVCHILARI) == kutilgan
    assert set(_MAQSAD_TEKSHIRUVCHILARI) == kutilgan


def test_HAR_SABAB_provayder_kodiga_AYLANADI():
    """⭐ Yangi `Sabab` qo'shilib jadval unutilsa, webhook 500 berardi."""
    assert set(PAYME_SABAB_KODI) == set(Sabab)
    # ⚠️ Click'da `BAND` hech qachon otilmaydi (`almashtirishga_ruxsat=True`).
    assert set(SABAB_KODI) == set(Sabab) - {Sabab.BAND}
