"""Click integratsiyasi (D6-T2).

QABUL MEZONLARI VA ULARNI ISBOTLAYDIGAN TESTLAR

    «bir xil transaction_id ikki marta kelsa ikkinchisi e'tiborsiz
     qoldiriladi»
        -> `test_BIR_XIL_trans_id_IKKI_MARTA_kelsa_obuna_BIR_MARTA_uzayadi`
        -> `test_TAKRORIY_complete_MUVAFFAQIYAT_qaytaradi`
        -> `test_BOSHQA_trans_id_TOLANGAN_buyurtmaga_RAD_etiladi`

    «barcha so'rovlar jurnalga yoziladi»
        -> `test_IMZOSI_NOTOGRI_sorov_HAM_jurnalga_tushadi`
        -> `test_jurnalda_IMZONING_OZI_SAQLANMAYDI`
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.factories import ExpertProfileFactory
from apps.accounts.models import TasdiqHolati
from apps.common.models import JurnalOzgarmas
from apps.payments import click
from apps.payments.models import (
    ObunaHolati,
    Provayder,
    Subscription,
    Tolov,
    TolovHolati,
    TolovMaqsadi,
    TolovSorovi,
)

pytestmark = pytest.mark.django_db

SIR = "sinov-maxfiy-kalit"
XIZMAT = "12345"
SOTUVCHI = "67890"
NARX = "19000"


# ===========================================================================
# Yordamchilar
# ===========================================================================
@pytest.fixture(autouse=True)
def _click_sozlamalari(settings):
    """Har testda Click ULANGAN holatda bo'lsin.

    ⚠️ `CLICK_YOQILGANMI` sozlama yuklanganda hisoblanadi, ya'ni uni
       alohida berish SHART — kalitlarni o'zgartirish yetarli emas.
       Aynan shu narsa birinchi urinishda "tugma yo'q" bo'lib chiqdi.
    """
    settings.CLICK_SECRET_KEY = SIR
    settings.CLICK_SERVICE_ID = XIZMAT
    settings.CLICK_MERCHANT_ID = SOTUVCHI
    settings.OBUNA_NARXI = NARX
    settings.CLICK_YOQILGANMI = True


@pytest.fixture
def ekspert():
    """Tasdiqlangan ekspert — PRO ni faqat u sotib ola oladi."""
    return ExpertProfileFactory().user


@pytest.fixture
def tolov(ekspert):
    return Tolov.objects.create(
        user=ekspert,
        provayder=Provayder.CLICK,
        summa=Decimal(NARX),
        maqsad=TolovMaqsadi.OBUNA,
    )


def _post(
    tolov_id,
    *,
    amal: int,
    trans_id: str = "9001",
    summa: str | None = None,
    xato: str = "0",
    prepare_id: str | None = None,
    service_id: str = XIZMAT,
    kalit: str = SIR,
    imzolansinmi: bool = True,
) -> dict:
    """Click yuboradigan shakldagi POST. Imzo OXIRIDA qo'yiladi."""
    malumot = {
        "click_trans_id": trans_id,
        "service_id": service_id,
        "click_paydoc_id": "555000",
        "merchant_trans_id": str(tolov_id),
        "amount": summa if summa is not None else f"{Decimal(NARX):.2f}",
        "action": str(amal),
        "error": xato,
        "error_note": "",
        "sign_time": "2026-09-07 12:00:00",
    }
    if amal == click.AMAL_COMPLETE:
        malumot["merchant_prepare_id"] = (
            prepare_id if prepare_id is not None else str(tolov_id)
        )
    if imzolansinmi:
        malumot["sign_string"] = click.imzo_hisoblash(
            malumot, amal=amal, maxfiy_kalit=kalit
        )
    return malumot


def _yubor(client: Client, malumot: dict, *, amal: int):
    manzil = reverse(
        "click_prepare" if amal == click.AMAL_PREPARE else "click_complete"
    )
    return client.post(manzil, malumot)


def _tayyorla(client, tolov, *, trans_id: str = "9001"):
    return _yubor(client, _post(tolov.pk, amal=0, trans_id=trans_id), amal=0)


# ===========================================================================
# 1. Imzo — sof funksiya, bazasiz
# ===========================================================================
def test_TOGRI_imzo_otadi():
    malumot = _post(1, amal=click.AMAL_PREPARE)

    assert click.imzoni_tekshirish(malumot, amal=0, maxfiy_kalit=SIR) is True


def test_BUZILGAN_maydon_imzoni_YIQITADI():
    """Imzolangandan keyin summani o'zgartirish — eng aniq hujum."""
    malumot = _post(1, amal=click.AMAL_PREPARE)
    malumot["amount"] = "1.00"

    assert click.imzoni_tekshirish(malumot, amal=0, maxfiy_kalit=SIR) is False


def test_BOSHQA_KALIT_imzoni_YIQITADI():
    malumot = _post(1, amal=click.AMAL_PREPARE, kalit="boshqa-kalit")

    assert click.imzoni_tekshirish(malumot, amal=0, maxfiy_kalit=SIR) is False


def test_PREPARE_imzosi_COMPLETE_uchun_YARAMAYDI():
    """⚠️ Complete imzosiga `merchant_prepare_id` ham kiradi.

    Ikkalasini bir xil deb hisoblash "prepare so'rovini complete
    sifatida qayta yuborish" yo'lini ochardi.
    """
    malumot = _post(1, amal=click.AMAL_PREPARE)
    malumot["merchant_prepare_id"] = "1"

    assert click.imzoni_tekshirish(malumot, amal=1, maxfiy_kalit=SIR) is False


def test_summa_SHAKLI_imzoga_TASIR_qiladi():
    """⚠️⚠️ HUJJATLASHTIRUVCHI TEST: "19000" va "19000.00" — BOSHQA imzo.

    Shuning uchun imzo XOM satrlar ustidan hisoblanadi va summani
    `Decimal` ga aylantirib qaytarish MUMKIN EMAS. Bu xato faqat
    kasr qismi nol bo'lganda chiqadi — ya'ni testda emas, prodda.
    """
    butun = _post(1, amal=click.AMAL_PREPARE, summa="19000")
    kasrli = _post(1, amal=click.AMAL_PREPARE, summa="19000.00")

    assert butun["sign_string"] != kasrli["sign_string"]


def test_KATTA_HARFLI_imzo_ham_otadi():
    """Ba'zi provayder muhitlari hash'ni katta harfda yuboradi."""
    malumot = _post(1, amal=click.AMAL_PREPARE)
    malumot["sign_string"] = malumot["sign_string"].upper()

    assert click.imzoni_tekshirish(malumot, amal=0, maxfiy_kalit=SIR) is True


# ===========================================================================
# 2. Prepare
# ===========================================================================
def test_prepare_MUVAFFAQIYAT(client, tolov):
    javob = _tayyorla(client, tolov)
    natija = javob.json()
    tolov.refresh_from_db()

    assert javob.status_code == 200
    assert natija["error"] == click.MUVAFFAQIYAT
    # ⚠️ `merchant_prepare_id` = `Tolov.pk`. Complete o'shani qaytaradi
    #    va bog'lovchi halqa aynan shu.
    assert natija["merchant_prepare_id"] == tolov.pk
    assert tolov.holat == TolovHolati.TAYYOR
    assert tolov.provayder_trans_id == "9001"


def test_prepare_IMZO_NOTOGRI_bolsa_RAD_etiladi(client, tolov):
    malumot = _post(tolov.pk, amal=0, kalit="soxta-kalit")

    javob = _yubor(client, malumot, amal=0)
    tolov.refresh_from_db()

    assert javob.json()["error"] == click.IMZO_XATO
    # ⚠️ Eng muhimi: holat O'ZGARMAGAN. Imzosiz so'rov bazaga tegmasin.
    assert tolov.holat == TolovHolati.YANGI


def test_prepare_IMZOSIZ_sorov_RAD_etiladi(client, tolov):
    malumot = _post(tolov.pk, amal=0, imzolansinmi=False)

    javob = _yubor(client, malumot, amal=0)

    assert javob.json()["error"] == click.IMZO_XATO


def test_prepare_NOTOGRI_SUMMA_rad_etiladi(client, tolov):
    malumot = _post(tolov.pk, amal=0, summa="1.00")

    javob = _yubor(client, malumot, amal=0)
    tolov.refresh_from_db()

    assert javob.json()["error"] == click.SUMMA_XATO
    assert tolov.holat == TolovHolati.YANGI


def test_prepare_YOQ_buyurtmaga_rad_etiladi(client):
    javob = _yubor(client, _post(999999, amal=0), amal=0)

    assert javob.json()["error"] == click.BUYURTMA_TOPILMADI


def test_prepare_RAQAM_BOLMAGAN_buyurtma_raqami(client):
    """`merchant_trans_id` har doim ham raqam bo'lmasligi mumkin."""
    malumot = _post("abc", amal=0)

    javob = _yubor(client, malumot, amal=0)

    assert javob.json()["error"] == click.BUYURTMA_TOPILMADI


def test_prepare_BOSHQA_SERVICE_ID_rad_etiladi(client, tolov):
    """Bitta kabinetdagi boshqa xizmatning so'rovi bu yerga tushmasin."""
    malumot = _post(tolov.pk, amal=0, service_id="99999")

    javob = _yubor(client, malumot, amal=0)

    assert javob.json()["error"] == click.SOROV_XATOSI


def test_prepare_manziliga_COMPLETE_amali_kelsa_rad_etiladi(client, tolov):
    malumot = _post(tolov.pk, amal=click.AMAL_COMPLETE)

    javob = _yubor(client, malumot, amal=click.AMAL_PREPARE)

    assert javob.json()["error"] == click.AMAL_TOPILMADI


def test_prepare_TAKRORLANSA_BIR_XIL_natija(client, tolov):
    """⚠️ Click javobni olmasa qayta so'raydi — bu XATO EMAS."""
    birinchi = _tayyorla(client, tolov).json()
    ikkinchi = _tayyorla(client, tolov).json()

    assert birinchi == ikkinchi
    assert ikkinchi["error"] == click.MUVAFFAQIYAT


def test_prepare_TOLANGAN_buyurtmaga_RAD_etiladi(client, tolov):
    _tayyorla(client, tolov)
    _yubor(client, _post(tolov.pk, amal=1), amal=1)

    javob = _tayyorla(client, tolov, trans_id="9002")

    assert javob.json()["error"] == click.ALLAQACHON_TOLANGAN


def test_prepare_YANGI_urinishda_BOSHQA_trans_id_qabul_qilinadi(client, tolov):
    """⚠️ Odam to'lovni tashlab ketib qaytadan boshlashi ODATIY hol.

    Yangi urinish yangi `click_trans_id` bilan keladi; uni rad etish
    odamni "to'lay olmaydigan" holatga tushirardi.
    """
    _tayyorla(client, tolov, trans_id="9001")

    javob = _tayyorla(client, tolov, trans_id="9002")
    tolov.refresh_from_db()

    assert javob.json()["error"] == click.MUVAFFAQIYAT
    assert tolov.provayder_trans_id == "9002"


# ===========================================================================
# 3. Complete — xizmat shu yerda beriladi
# ===========================================================================
def test_complete_OBUNANI_BERADI(client, tolov, ekspert):
    _tayyorla(client, tolov)

    javob = _yubor(client, _post(tolov.pk, amal=1), amal=1)
    tolov.refresh_from_db()
    ekspert.refresh_from_db()

    assert javob.json()["error"] == click.MUVAFFAQIYAT
    assert javob.json()["merchant_confirm_id"] == tolov.pk
    assert tolov.holat == TolovHolati.TOLANDI
    assert tolov.tolangan_at is not None
    assert ekspert.has_pro is True


def test_complete_PRO_NISHONINI_yoqadi(client, tolov, ekspert):
    """⭐ D3-T5 qoidasi buzilmasin: nishon MALAKA + TO'LOV kesishmasi."""
    _tayyorla(client, tolov)
    _yubor(client, _post(tolov.pk, amal=1), amal=1)

    ekspert.refresh_from_db()
    assert ekspert.ekspert_profili.pro_faolmi is True


def test_TASDIQLANMAGAN_ekspert_TOLASA_HAM_nishon_YOQ(client):
    """⭐⭐ Pul bilan ishonch sotib olinmaydi (D3-T5).

    ⚠️ To'lovning O'ZI o'tadi (`has_pro` yoqiladi) — bu to'g'ri:
       odam to'ladi, pul keldi. Faqat NISHON berilmaydi.
       Shuning uchun ham sotib olish sahifasi uni umuman
       boshlatmaydi (`test_TASDIQLANMAGAN_odam_SOTIB_OLOLMAYDI`).
    """
    profil = ExpertProfileFactory(
        verification_status=TasdiqHolati.KUTILMOQDA, verified_at=None
    )
    buyurtma = Tolov.objects.create(
        user=profil.user, provayder=Provayder.CLICK, summa=Decimal(NARX)
    )
    _tayyorla(client, buyurtma)
    _yubor(client, _post(buyurtma.pk, amal=1), amal=1)

    profil.refresh_from_db()
    assert profil.user.has_pro is True
    assert profil.pro_faolmi is False


def test_complete_PREPARE_SIZ_rad_etiladi(client, tolov):
    """Prepare'siz kelgan Complete — protokol buzilgani."""
    javob = _yubor(client, _post(tolov.pk, amal=1), amal=1)
    tolov.refresh_from_db()

    assert javob.json()["error"] == click.TRANZAKSIYA_TOPILMADI
    assert tolov.holat == TolovHolati.YANGI


def test_complete_NOTOGRI_prepare_id_rad_etiladi(client, tolov):
    _tayyorla(client, tolov)

    javob = _yubor(client, _post(tolov.pk, amal=1, prepare_id="777"), amal=1)
    tolov.refresh_from_db()

    assert javob.json()["error"] == click.TRANZAKSIYA_TOPILMADI
    assert tolov.holat == TolovHolati.TAYYOR


def test_complete_MANFIY_xato_bilan_kelsa_BEKOR(client, tolov, ekspert):
    """Karta rad etdi / odam bekor qildi — Click buni `error < 0` deydi."""
    _tayyorla(client, tolov)

    malumot = _post(tolov.pk, amal=1, xato="-5017")
    malumot["error_note"] = "Kartada mablag' yetarli emas"
    malumot["sign_string"] = click.imzo_hisoblash(malumot, amal=1, maxfiy_kalit=SIR)
    javob = _yubor(client, malumot, amal=1)
    tolov.refresh_from_db()
    ekspert.refresh_from_db()

    assert javob.json()["error"] == click.BEKOR_QILINGAN
    assert tolov.holat == TolovHolati.BEKOR
    assert tolov.izoh == "Kartada mablag' yetarli emas"
    assert ekspert.has_pro is False


def test_BEKOR_qilingan_buyurtma_QAYTA_tolanmaydi(client, tolov):
    _tayyorla(client, tolov)
    malumot = _post(tolov.pk, amal=1, xato="-5017")
    malumot["sign_string"] = click.imzo_hisoblash(malumot, amal=1, maxfiy_kalit=SIR)
    _yubor(client, malumot, amal=1)

    javob = _yubor(client, _post(tolov.pk, amal=1, trans_id="9002"), amal=1)

    assert javob.json()["error"] == click.BEKOR_QILINGAN


def test_MANFIY_xato_TOLANGAN_obunani_TORTIB_OLMAYDI(client, tolov, ekspert):
    """⚠️ To'langan buyurtmaga kelgan "xato" — Click tomondagi chalkashlik.

    Obunani avtomatik tortib olish odamdan to'lagan xizmatini
    olib qo'yardi. Pulni qaytarish qarori ODAMNIKI.
    """
    _tayyorla(client, tolov)
    _yubor(client, _post(tolov.pk, amal=1), amal=1)

    malumot = _post(tolov.pk, amal=1, trans_id="9002", xato="-5017")
    malumot["sign_string"] = click.imzo_hisoblash(malumot, amal=1, maxfiy_kalit=SIR)
    _yubor(client, malumot, amal=1)

    tolov.refresh_from_db()
    ekspert.refresh_from_db()
    assert tolov.holat == TolovHolati.TOLANDI
    assert ekspert.has_pro is True


# ===========================================================================
# 4. ⭐⭐ QABUL MEZONI: IDEMPOTENTLIK
# ===========================================================================
def test_BIR_XIL_trans_id_IKKI_MARTA_kelsa_obuna_BIR_MARTA_uzayadi(
    client, tolov, ekspert
):
    """⭐⭐ D6-T2 ASOSIY QABUL MEZONI.

    Click javobni olmasa Complete'ni QAYTA yuboradi. Ikkinchi so'rov
    obunani yana 30 kunga uzaytirsa, tarmoq uzilishi mijozga bepul
    oy sovg'a qilardi.
    """
    _tayyorla(client, tolov)
    _yubor(client, _post(tolov.pk, amal=1), amal=1)
    birinchi = Subscription.objects.get(user=ekspert).expires_at

    _yubor(client, _post(tolov.pk, amal=1), amal=1)
    ikkinchi = Subscription.objects.get(user=ekspert).expires_at

    assert birinchi == ikkinchi
    assert Subscription.objects.filter(user=ekspert).count() == 1


def test_TAKRORIY_complete_MUVAFFAQIYAT_qaytaradi(client, tolov):
    """⚠️⚠️ TAKRORGA "XATO" DEYISH PULNI QAYTARIB YUBORARDI.

    Click muvaffaqiyatsiz javobni ko'rib tranzaksiyani bekor qiladi —
    odam esa xizmatni allaqachon olgan bo'lardi. Shuning uchun
    takroriy so'rovga ham `error = 0`.
    """
    _tayyorla(client, tolov)
    birinchi = _yubor(client, _post(tolov.pk, amal=1), amal=1).json()

    ikkinchi = _yubor(client, _post(tolov.pk, amal=1), amal=1).json()

    assert ikkinchi["error"] == click.MUVAFFAQIYAT
    assert ikkinchi == birinchi


def test_BOSHQA_trans_id_TOLANGAN_buyurtmaga_RAD_etiladi(client, tolov, ekspert):
    """⚠️⚠️ Bu TAKROR emas, IKKINCHI to'lov.

    Idempotentlik kaliti — `click_trans_id`, buyurtma raqami EMAS.
    Ikkalasini adashtirish obunani ikki marta uzaytirardi.
    """
    _tayyorla(client, tolov)
    _yubor(client, _post(tolov.pk, amal=1), amal=1)
    muddat = Subscription.objects.get(user=ekspert).expires_at

    javob = _yubor(client, _post(tolov.pk, amal=1, trans_id="9002"), amal=1)

    assert javob.json()["error"] == click.ALLAQACHON_TOLANGAN
    assert Subscription.objects.get(user=ekspert).expires_at == muddat


def test_BIR_XIL_trans_id_IKKI_BUYURTMAGA_yozilmaydi(client, ekspert):
    """⚠️ BAZA CHEKLOVI — oxirgi himoya (TOCTOU poygasi uchun).

    Ikkita webhook ayni paytda kelsa, ikkalasi ham "bunday tranzaksiya
    yo'q ekan" deb ko'rib yozardi. Noyoblik cheklovi buni yopadi.
    """
    birinchi = Tolov.objects.create(
        user=ekspert, provayder=Provayder.CLICK, summa=Decimal(NARX)
    )
    ikkinchi = Tolov.objects.create(
        user=ekspert, provayder=Provayder.CLICK, summa=Decimal(NARX)
    )
    _tayyorla(client, birinchi, trans_id="9001")

    javob = _tayyorla(client, ikkinchi, trans_id="9001")
    ikkinchi.refresh_from_db()

    assert javob.json()["error"] == click.ALLAQACHON_TOLANGAN
    assert ikkinchi.holat == TolovHolati.YANGI


def test_UZAYTIRISH_qolgan_muddat_USTIGA_qoshiladi(client, ekspert, settings):
    """⭐ D6-T1 qoidasi to'lov yo'lida ham saqlanadi."""
    Subscription.objects.create(
        user=ekspert,
        status=ObunaHolati.FAOL,
        expires_at=timezone.now() + timedelta(days=10),
    )
    buyurtma = Tolov.objects.create(
        user=ekspert, provayder=Provayder.CLICK, summa=Decimal(NARX)
    )
    _tayyorla(client, buyurtma)
    _yubor(client, _post(buyurtma.pk, amal=1), amal=1)

    qoldi = Subscription.objects.get(user=ekspert).tugashiga_kun
    assert qoldi >= 10 + settings.OBUNA_MUDDATI_KUN - 1


# ===========================================================================
# 5. ⭐ QABUL MEZONI: JURNAL
# ===========================================================================
def test_HAR_BIR_sorov_jurnalga_tushadi(client, tolov):
    _tayyorla(client, tolov)
    _yubor(client, _post(tolov.pk, amal=1), amal=1)

    assert TolovSorovi.objects.count() == 2
    assert set(TolovSorovi.objects.values_list("amal", flat=True)) == {
        "prepare",
        "complete",
    }


def test_IMZOSI_NOTOGRI_sorov_HAM_jurnalga_tushadi(client, tolov):
    """⚠️⚠️ ENG MUHIM JURNAL YOZUVI — AYNAN RAD ETILGANI.

    Nizoda ("pul yechildi, obuna berilmadi") kerak bo'ladigan qator
    shu. Faqat muvaffaqiyatli so'rovlarni yozadigan jurnal aynan
    kerakli paytda bo'sh bo'lardi.
    """
    _yubor(client, _post(tolov.pk, amal=0, kalit="soxta"), amal=0)

    yozuv = TolovSorovi.objects.get()
    assert yozuv.imzo_togrimi is False
    assert yozuv.natija == click.IMZO_XATO
    assert yozuv.merchant_trans_id == str(tolov.pk)
    # ⚠️ Imzo o'tmagani uchun buyurtmaga BOG'LANMAYDI — bu to'g'ri:
    #    imzosiz so'rov bazaga tegmaydi.
    assert yozuv.tolov_id is None


def test_jurnalda_IMZONING_OZI_SAQLANMAYDI(client, tolov):
    """⚠️⚠️ `sign_string` maxfiy kalit ishtirokidagi hash.

    Uni xom holda saqlash bazani qo'lga kiritgan odamga kalitni
    oflayn tanlash uchun tayyor material berardi.
    """
    _tayyorla(client, tolov)

    yozuv = TolovSorovi.objects.get()
    assert "sign_string" not in yozuv.xom
    # Qolgan maydonlar esa TURADI — dalil sifatida kerak.
    assert yozuv.xom["click_trans_id"] == "9001"
    assert yozuv.xom["amount"] == "19000.00"
    assert yozuv.imzo_togrimi is True


def test_jurnalda_JAVOB_ham_saqlanadi(client, tolov):
    """«Biz Click'ga nima dedik?» — nizodagi ikkinchi savol."""
    _tayyorla(client, tolov)

    yozuv = TolovSorovi.objects.get()
    assert yozuv.javob["error"] == click.MUVAFFAQIYAT
    assert yozuv.javob["merchant_prepare_id"] == tolov.pk


def test_jurnal_yozuvi_TAHRIRLANMAYDI(client, tolov):
    _tayyorla(client, tolov)
    yozuv = TolovSorovi.objects.get()
    yozuv.natija = 0

    with pytest.raises(JurnalOzgarmas, match="tahrirlanmaydi"):
        yozuv.save()


def test_jurnal_yozuvi_OCHIRILMAYDI(client, tolov):
    _tayyorla(client, tolov)

    with pytest.raises(JurnalOzgarmas, match="o'chirilmaydi"):
        TolovSorovi.objects.get().delete()


def test_jurnal_OMMAVIY_ozgartirilmaydi(client, tolov):
    """⚠️ Eng oson unutiladigan qatlam: `QuerySet.update()` model
    metodlarini UMUMAN chaqirmaydi.
    """
    _tayyorla(client, tolov)

    with pytest.raises(JurnalOzgarmas):
        TolovSorovi.objects.all().update(natija=0)
    with pytest.raises(JurnalOzgarmas):
        TolovSorovi.objects.all().delete()


def test_jurnal_TOLOV_ochirilsa_ham_QOLADI(client, tolov):
    """Jurnal to'lovdan MUSTAQIL yashaydi (dalil yo'qolmasin)."""
    _tayyorla(client, tolov)
    buyurtma_raqami = str(tolov.pk)
    tolov.delete()

    yozuv = TolovSorovi.objects.get()
    assert yozuv.tolov_id is None
    assert yozuv.merchant_trans_id == buyurtma_raqami


# ===========================================================================
# 6. Webhook xulqi
# ===========================================================================
def test_webhook_XATODA_HAM_200_qaytaradi(client, tolov):
    """⚠️⚠️ 4xx/5xx Click uchun "javob yo'q" degani.

    U so'rovni qayta yuboradi va bir necha urinishdan keyin
    tranzaksiyani bekor qiladi — ya'ni bizning "rad etdim"
    xabarimiz muvaffaqiyatli to'lovni ham yo'qotardi.
    """
    javob = _yubor(client, _post(tolov.pk, amal=0, kalit="soxta"), amal=0)

    assert javob.status_code == 200
    assert javob.json()["error"] == click.IMZO_XATO


def test_webhook_CSRF_TOKENSIZ_ishlaydi(tolov):
    """⚠️ Click brauzer emas: CSRF tokeni yo'q va bo'lishi ham mumkin emas.

    Bu test `enforce_csrf_checks=True` bilan ishlaydi, ya'ni
    `csrf_exempt` olib tashlansa DARHOL yiqiladi.
    """
    qattiq = Client(enforce_csrf_checks=True)

    javob = _yubor(qattiq, _post(tolov.pk, amal=0), amal=0)

    assert javob.status_code == 200
    assert javob.json()["error"] == click.MUVAFFAQIYAT


def test_webhook_GET_ni_QABUL_QILMAYDI(client):
    javob = client.get(reverse("click_prepare"))

    assert javob.status_code == 405


# ===========================================================================
# 7. Sotib olish oqimi (odam tomoni)
# ===========================================================================
def test_pro_sahifasi_MEHMONGA_ochiq(client):
    javob = client.get(reverse("pro"))

    assert javob.status_code == 200
    assert b"PRO" in javob.content


def test_NARX_sahifada_GURUHLANGAN_korinadi(client):
    """⚠️ `floatformat:"0g"` — `uz` lokali UZILMAS BO'SHLIQ qo'yadi.

    Oddiy `floatformat:"0"` `19000` berardi: maketdagi dizayndan
    (`149 000`) farq qilardi va katta sonda o'qilmasdi. Ajratgichni
    qo'lda qo'yish esa lokal bilimini takrorlardi — Django uni
    allaqachon biladi.
    """
    javob = client.get(reverse("pro"))

    assert "19 000" in javob.content.decode()


def test_TASDIQLANGAN_ekspert_CLICK_ga_yuboriladi(client, ekspert):
    client.force_login(ekspert)

    javob = client.post(reverse("pro_sotib_olish", args=["click"]))
    buyurtma = Tolov.objects.get()

    assert javob.status_code == 302
    manzil = javob["Location"]
    assert manzil.startswith("https://my.click.uz/services/pay")
    assert f"transaction_param={buyurtma.pk}" in manzil
    assert f"service_id={XIZMAT}" in manzil
    assert buyurtma.holat == TolovHolati.YANGI


def test_TASDIQLANMAGAN_odam_SOTIB_OLOLMAYDI(client, user):
    """⚠️⚠️ D6-T2 DA TOPILGAN NUQSON.

    Bugungi kodda PRO ayni bitta narsa beradi — `pro_faolmi` nishoni,
    u esa TASDIQLANGAN malakani talab qiladi. Tasdiqlanmagan odam
    to'lasa mutlaqo hech narsa olmasdi.
    """
    client.force_login(user)

    javob = client.post(reverse("pro_sotib_olish", args=["click"]))

    assert javob.status_code == 302
    assert Tolov.objects.exists() is False


def test_SUMMA_FORMADAN_olinmaydi(client, ekspert, settings):
    """⚠️ "PRO ni 1 so'mga sotib olish" — eng klassik teshik."""
    client.force_login(ekspert)

    client.post(
        reverse("pro_sotib_olish", args=["click"]), {"summa": "1", "amount": "1"}
    )

    assert Tolov.objects.get().summa == Decimal(settings.OBUNA_NARXI)


def test_KALITLAR_YOQ_bolsa_sotib_olish_TOXTAYDI(client, ekspert, settings):
    settings.CLICK_YOQILGANMI = False
    client.force_login(ekspert)

    javob = client.post(reverse("pro_sotib_olish", args=["click"]))

    assert javob.status_code == 302
    assert Tolov.objects.exists() is False


def test_sotib_olish_GET_bilan_ochilmaydi(client, ekspert):
    """⚠️ Sahifani oldindan yuklaydigan kengaytma buyurtma yasamasin."""
    client.force_login(ekspert)

    javob = client.get(reverse("pro_sotib_olish", args=["click"]))

    assert javob.status_code == 405
    assert Tolov.objects.exists() is False


def test_sotib_olish_MEHMONGA_yopiq(client):
    javob = client.post(reverse("pro_sotib_olish", args=["click"]))

    assert javob.status_code == 302
    assert "/kirish/" in javob["Location"]


# ===========================================================================
# 8. Natija sahifasi
# ===========================================================================
def test_natija_EGASIGA_korinadi(client, tolov, ekspert):
    client.force_login(ekspert)

    javob = client.get(reverse("tolov_natijasi", args=[tolov.pk]))

    assert javob.status_code == 200


def test_natija_BEGONAGA_404(client, tolov, other_user):
    """⚠️ 403 EMAS: begona buyurtmaning MAVJUDLIGI ham oshkor qilinmaydi."""
    client.force_login(other_user)

    javob = client.get(reverse("tolov_natijasi", args=[tolov.pk]))

    assert javob.status_code == 404


def test_natija_sahifasi_HOLATNI_OZGARTIRMAYDI(client, tolov, ekspert):
    """⚠️⚠️ Qaytish manzilini brauzerda qo'lda ochish MUMKIN.

    Unga ishonish "to'lamasdan PRO olish" degani bo'lardi.
    """
    client.force_login(ekspert)

    client.get(reverse("tolov_natijasi", args=[tolov.pk]))

    tolov.refresh_from_db()
    ekspert.refresh_from_db()
    assert tolov.holat == TolovHolati.YANGI
    assert ekspert.has_pro is False
