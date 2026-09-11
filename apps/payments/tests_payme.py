"""Payme Merchant API integratsiyasi (D6-T3).

⚠️⚠️ QABUL MEZONI: «Payme sandbox testlari to'liq o'tadi».
   Sandbox OCHIQ HTTPS endpoint va `TEST_KEY` talab qiladi — ya'ni uni
   kodda YOPIB BO'LMAYDI (D0-T10 bilan bir xil holat: server yo'q).

   Shuning uchun bu yerda sandbox HUJJATDA TASVIRLANGAN ikkala
   ssenariysi takrorlangan:

     1. TASDIQLANMAGAN tranzaksiya: yaratish -> bekor qilish,
        + noto'g'ri avtorizatsiya, noto'g'ri summa, mavjud bo'lmagan
          hisob;
     2. TASDIQLANGAN tranzaksiya: yaratish -> bajarish -> bekor qilish.

   Sandbox'ning o'zi kalitlar olingach ishga tushiriladi; kod tomon
   tayyor.

⚠️ Payme HAR so'rovni takroran yuborishi mumkin. Shuning uchun
   deyarli har testning "ikkinchi marta" juftligi bor.
"""

from __future__ import annotations

import base64
import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.factories import ExpertProfileFactory
from apps.payments import payme
from apps.payments.models import (
    Provayder,
    Subscription,
    Tolov,
    TolovHolati,
    TolovSorovi,
)
from apps.payments.services import (
    _MAQSAD_BAJARUVCHILARI,
    _MAQSAD_BEKOR_QILUVCHILARI,
)

pytestmark = pytest.mark.django_db

KALIT = "sinov-payme-kaliti"
SOTUVCHI = "5e730e8e0b852a417aa49ceb"
NARX = "19000"
TIYIN = 1900000  # 19 000 so'm


@pytest.fixture(autouse=True)
def _payme_sozlamalari(settings):
    settings.PAYME_SECRET_KEY = KALIT
    settings.PAYME_MERCHANT_ID = SOTUVCHI
    settings.OBUNA_NARXI = NARX
    settings.PAYME_YOQILGANMI = True
    settings.CLICK_YOQILGANMI = False


@pytest.fixture
def ekspert():
    return ExpertProfileFactory().user


@pytest.fixture
def tolov(ekspert):
    return Tolov.objects.create(
        user=ekspert, provayder=Provayder.PAYME, summa=Decimal(NARX)
    )


def _sarlavha(kalit: str = KALIT) -> str:
    return "Basic " + base64.b64encode(f"Paycom:{kalit}".encode()).decode()


def _sorov(client, metod: str, params: dict, *, kalit: str = KALIT, sorov_id=1):
    return client.post(
        reverse("payme_webhook"),
        data=json.dumps(
            {"jsonrpc": "2.0", "id": sorov_id, "method": metod, "params": params}
        ),
        content_type="application/json",
        headers={"Authorization": _sarlavha(kalit)},
    )


def _hisob(tolov) -> dict:
    return {payme.ACCOUNT_MAYDONI: str(tolov.pk)}


def _yaratish(client, tolov, *, trans_id="p001"):
    return _sorov(
        client,
        payme.CREATE,
        {
            "id": trans_id,
            "time": 1757000000000,
            "amount": TIYIN,
            "account": _hisob(tolov),
        },
    )


def _bajarish(client, *, trans_id="p001"):
    return _sorov(client, payme.PERFORM, {"id": trans_id})


def _bekor(client, *, trans_id="p001", sabab=1):
    return _sorov(client, payme.CANCEL, {"id": trans_id, "reason": sabab})


# ===========================================================================
# 1. Protokol — sof funksiyalar, bazasiz
# ===========================================================================
def test_TOGRI_avtorizatsiya_otadi():
    assert payme.avtorizatsiya_togrimi(_sarlavha(), kalit=KALIT) is True


def test_BOSHQA_KALIT_avtorizatsiyadan_otmaydi():
    assert payme.avtorizatsiya_togrimi(_sarlavha("boshqa"), kalit=KALIT) is False


def test_BOSHQA_LOGIN_avtorizatsiyadan_otmaydi():
    """⚠️ `Paycom` login ham tekshiriladi, faqat parol emas."""
    xom = base64.b64encode(f"Boshqa:{KALIT}".encode()).decode()

    assert payme.avtorizatsiya_togrimi(f"Basic {xom}", kalit=KALIT) is False


def test_SOZLANMAGAN_kalit_HAMMASINI_rad_etadi():
    """⚠️⚠️ Bo'sh kalit = yopiq eshik.

    Aks holda sozlanmagan server HAR QANDAY so'rovni qabul qilardi —
    va bu eng yomon paytda, prodga birinchi chiqishda ochilardi.
    """
    assert payme.avtorizatsiya_togrimi(_sarlavha(""), kalit="") is False


def test_BUZUQ_sarlavha_avtorizatsiyadan_otmaydi():
    assert payme.avtorizatsiya_togrimi("Basic ???", kalit=KALIT) is False
    assert payme.avtorizatsiya_togrimi("Bearer abc", kalit=KALIT) is False
    assert payme.avtorizatsiya_togrimi("", kalit=KALIT) is False


def test_SUMMA_TIYINGA_aylanadi():
    """⚠️⚠️ 19 000 so'm = 1 900 000 tiyin.

    Adashsa mijozdan 100 barobar kam yoki ko'p yechiladi va ikkala
    son ham "to'g'ri ko'rinadi".
    """
    assert payme.tiyinga(Decimal("19000")) == 1900000
    assert payme.somga(1900000) == Decimal("19000")


def test_TIYIN_kasr_qismini_YOQOTMAYDI():
    assert payme.somga(1900050) == Decimal("19000.50")
    assert payme.tiyinga(Decimal("19000.50")) == 1900050


def test_BOSH_vaqt_NOL_ga_aylanadi():
    """⚠️ Payme bo'lmagan vaqt uchun `0` kutadi, `null` emas."""
    assert payme.vaqtga_ms(None) == 0


def test_tolov_manzili_BASE64_va_TIYINDA(tolov):
    manzil = payme.tolov_manzili(
        asos="https://checkout.paycom.uz",
        merchant_id=SOTUVCHI,
        tolov_id=tolov.pk,
        summa=Decimal(NARX),
        qaytish_manzili="https://dard.uz/tolov/1/natija/",
    )
    kodlangan = manzil.rsplit("/", 1)[-1]
    ochilgan = base64.b64decode(kodlangan).decode()

    assert f"m={SOTUVCHI}" in ochilgan
    assert f"ac.order_id={tolov.pk}" in ochilgan
    assert f"a={TIYIN}" in ochilgan


# ===========================================================================
# 2. Umumiy xatolar
# ===========================================================================
def test_GET_bilan_kelsa_MINUS_32300(client):
    """⚠️ `405` EMAS: Payme bu holat uchun O'Z kodini belgilagan."""
    javob = client.get(reverse("payme_webhook"))

    assert javob.status_code == 200
    assert javob.json()["error"]["code"] == payme.USUL_POST_EMAS


def test_BUZUQ_JSON_minus_32700(client):
    javob = client.post(
        reverse("payme_webhook"),
        data="{buzuq",
        content_type="application/json",
        headers={"Authorization": _sarlavha()},
    )

    assert javob.json()["error"]["code"] == payme.JSON_XATO


def test_LUGAT_BOLMAGAN_tana_minus_32600(client):
    javob = client.post(
        reverse("payme_webhook"),
        data="[1, 2, 3]",
        content_type="application/json",
        headers={"Authorization": _sarlavha()},
    )

    assert javob.json()["error"]["code"] == payme.SOROV_NOTOGRI


def test_NOTOGRI_avtorizatsiya_minus_32504(client, tolov):
    """⭐ Sandbox ssenariysi: «noto'g'ri avtorizatsiya»."""
    javob = _sorov(
        client,
        payme.CHECK_PERFORM,
        {"amount": TIYIN, "account": _hisob(tolov)},
        kalit="soxta",
    )

    assert javob.json()["error"]["code"] == payme.HUQUQ_YETARLI_EMAS
    # Hech narsa o'zgarmagan.
    tolov.refresh_from_db()
    assert tolov.holat == TolovHolati.YANGI


def test_NOMALUM_metod_minus_32601(client):
    javob = _sorov(client, "YoqMetod", {})

    assert javob.json()["error"]["code"] == payme.METOD_TOPILMADI


def test_XATO_javobida_XABAR_UCH_TILDA(client):
    """⚠️ Payme bu matnni foydalanuvchiga O'Z ilovasida ko'rsatadi."""
    javob = _sorov(client, "YoqMetod", {})
    xabar = javob.json()["error"]["message"]

    assert set(xabar) == {"ru", "uz", "en"}


def test_javob_SOROV_ID_sini_qaytaradi(client, tolov):
    javob = _sorov(
        client,
        payme.CHECK_PERFORM,
        {"amount": TIYIN, "account": _hisob(tolov)},
        sorov_id=777,
    )

    assert javob.json()["id"] == 777


# ===========================================================================
# 3. CheckPerformTransaction
# ===========================================================================
def test_check_perform_RUXSAT(client, tolov):
    javob = _sorov(
        client, payme.CHECK_PERFORM, {"amount": TIYIN, "account": _hisob(tolov)}
    )

    assert javob.json()["result"] == {"allow": True}


def test_check_perform_HECH_NARSA_YOZMAYDI(client, tolov):
    """⚠️ Payme uni summa kiritilayotganda ham chaqiradi."""
    _sorov(client, payme.CHECK_PERFORM, {"amount": TIYIN, "account": _hisob(tolov)})
    tolov.refresh_from_db()

    assert tolov.holat == TolovHolati.YANGI
    assert tolov.tayyorlangan_at is None


def test_check_perform_YOQ_hisob_minus_31050(client):
    """⭐ Sandbox ssenariysi: «mavjud bo'lmagan hisob»."""
    javob = _sorov(
        client,
        payme.CHECK_PERFORM,
        {"amount": TIYIN, "account": {payme.ACCOUNT_MAYDONI: "999999"}},
    )
    xato = javob.json()["error"]

    assert xato["code"] == payme.BUYURTMA_TOPILMADI
    # ⚠️ `data` MAJBURIY: Payme uni foydalanuvchiga "shu maydon
    #    xato" deb ko'rsatadi.
    assert xato["data"] == payme.ACCOUNT_MAYDONI


def test_check_perform_RAQAM_BOLMAGAN_hisob_minus_31050(client):
    javob = _sorov(
        client,
        payme.CHECK_PERFORM,
        {"amount": TIYIN, "account": {payme.ACCOUNT_MAYDONI: "abc"}},
    )

    assert javob.json()["error"]["code"] == payme.BUYURTMA_TOPILMADI


def test_check_perform_HISOBSIZ_sorov_minus_31050(client):
    javob = _sorov(client, payme.CHECK_PERFORM, {"amount": TIYIN})

    assert javob.json()["error"]["code"] == payme.BUYURTMA_TOPILMADI


def test_check_perform_NOTOGRI_SUMMA_minus_31001(client, tolov):
    """⭐ Sandbox ssenariysi: «noto'g'ri summa»."""
    javob = _sorov(
        client, payme.CHECK_PERFORM, {"amount": 100, "account": _hisob(tolov)}
    )

    assert javob.json()["error"]["code"] == payme.SUMMA_XATO


def test_check_perform_SOM_da_yuborilgan_summa_RAD_etiladi(client, tolov):
    """⚠️⚠️ TIYIN/SO'M chalkashligining aynan o'zi.

    `19000` (so'm) yuborilsa u `190` so'm deb o'qiladi va rad
    etiladi — bu TO'G'RI xulq va shu test uni qotiradi.
    """
    javob = _sorov(
        client, payme.CHECK_PERFORM, {"amount": 19000, "account": _hisob(tolov)}
    )

    assert javob.json()["error"]["code"] == payme.SUMMA_XATO


def test_check_perform_TOLANGAN_buyurtma_minus_31051(client, tolov):
    _yaratish(client, tolov)
    _bajarish(client)

    javob = _sorov(
        client, payme.CHECK_PERFORM, {"amount": TIYIN, "account": _hisob(tolov)}
    )

    assert javob.json()["error"]["code"] == payme.BUYURTMA_YAKUNLANGAN


# ===========================================================================
# 4. CreateTransaction — sandbox 1-ssenariy
# ===========================================================================
def test_create_MUVAFFAQIYAT(client, tolov):
    javob = _yaratish(client, tolov)
    natija = javob.json()["result"]
    tolov.refresh_from_db()

    assert natija["state"] == payme.HOLAT_YARATILDI
    assert natija["transaction"] == str(tolov.pk)
    assert natija["create_time"] > 0
    assert tolov.holat == TolovHolati.TAYYOR
    assert tolov.provayder_trans_id == "p001"


def test_create_TAKRORLANSA_AYNAN_BIR_XIL_javob(client, tolov):
    """⭐⭐ `create_time` HAM bir xil bo'lishi shart.

    U bazadan o'qiladi, hisoblanmaydi — aks holda har takroriy
    so'rovda boshqa vaqt qaytardi va sandbox aynan shuni ushlaydi.
    """
    birinchi = _yaratish(client, tolov).json()

    ikkinchi = _yaratish(client, tolov).json()

    assert birinchi == ikkinchi


def test_create_BOSHQA_tranzaksiya_RAD_etiladi(client, tolov):
    """⚠️⚠️ CLICK'DAN FARQ QILADIGAN JOY.

    Click'da yangi urinish yangi `click_trans_id` bilan keladi va
    bu NORMAL. Payme'da esa bir buyurtmada bir vaqtda bitta
    tranzaksiya bo'ladi — ikkinchisi `-31008` bilan rad etiladi.

    Xizmat qatlami buni BILMAYDI: farq `almashtirishga_ruxsat`
    argumentida va uni ADAPTER tanlaydi.
    """
    _yaratish(client, tolov, trans_id="p001")

    javob = _yaratish(client, tolov, trans_id="p002")
    tolov.refresh_from_db()

    assert javob.json()["error"]["code"] == payme.AMAL_BAJARILMAYDI
    assert tolov.provayder_trans_id == "p001"


def test_create_YOQ_buyurtma_minus_31050(client, tolov):
    javob = _sorov(
        client,
        payme.CREATE,
        {
            "id": "p001",
            "amount": TIYIN,
            "account": {payme.ACCOUNT_MAYDONI: "999999"},
        },
    )
    xato = javob.json()["error"]

    assert xato["code"] == payme.BUYURTMA_TOPILMADI
    assert xato["data"] == payme.ACCOUNT_MAYDONI


def test_create_NOTOGRI_SUMMA_minus_31001(client, tolov):
    javob = _sorov(
        client,
        payme.CREATE,
        {"id": "p001", "amount": 1, "account": _hisob(tolov)},
    )

    assert javob.json()["error"]["code"] == payme.SUMMA_XATO


def test_create_MUDDATI_OTGAN_tranzaksiya_BEKOR_qilinadi(client, tolov):
    """⭐⭐ 12 SOATLIK OYNA — Payme qoidasi, MERCHANT bajaradi.

    Buni qilmasak, yarim yil oldin ochilgan to'lov sahifasi bugun
    ham muvaffaqiyatli yakunlanardi.
    """
    _yaratish(client, tolov)
    Tolov.objects.filter(pk=tolov.pk).update(
        tayyorlangan_at=timezone.now() - timedelta(hours=13)
    )

    javob = _yaratish(client, tolov)
    tolov.refresh_from_db()

    assert javob.json()["error"]["code"] == payme.AMAL_BAJARILMAYDI
    assert tolov.holat == TolovHolati.BEKOR
    assert tolov.bekor_kodi == payme.SABAB_TAYMAUT


# ===========================================================================
# 5. PerformTransaction — sandbox 2-ssenariy
# ===========================================================================
def test_perform_OBUNANI_BERADI(client, tolov, ekspert):
    _yaratish(client, tolov)

    javob = _bajarish(client)
    natija = javob.json()["result"]
    tolov.refresh_from_db()
    ekspert.refresh_from_db()

    assert natija["state"] == payme.HOLAT_BAJARILDI
    assert natija["perform_time"] > 0
    assert tolov.holat == TolovHolati.TOLANDI
    assert ekspert.has_pro is True


def test_perform_TAKRORLANSA_obuna_BIR_MARTA_uzayadi(client, tolov, ekspert):
    """⭐⭐ Payme javobni olmasa qayta so'raydi."""
    _yaratish(client, tolov)
    _bajarish(client)
    birinchi = Subscription.objects.get(user=ekspert).expires_at

    javob = _bajarish(client)

    assert javob.json()["result"]["state"] == payme.HOLAT_BAJARILDI
    assert Subscription.objects.get(user=ekspert).expires_at == birinchi


def test_perform_TAKRORDA_AYNAN_BIR_XIL_javob(client, tolov):
    _yaratish(client, tolov)
    birinchi = _bajarish(client).json()

    ikkinchi = _bajarish(client).json()

    assert birinchi == ikkinchi


def test_perform_YOQ_tranzaksiya_minus_31003(client):
    javob = _bajarish(client, trans_id="yoq")

    assert javob.json()["error"]["code"] == payme.TRANZAKSIYA_TOPILMADI


def test_perform_BEKOR_qilingandan_keyin_minus_31008(client, tolov):
    _yaratish(client, tolov)
    _bekor(client)

    javob = _bajarish(client)

    assert javob.json()["error"]["code"] == payme.AMAL_BAJARILMAYDI


def test_perform_MUDDATI_OTGAN_tranzaksiyani_BEKOR_qiladi(client, tolov, ekspert):
    """⭐⭐ Eskirgan tranzaksiya bajarilmaydi va SABABI `4` bo'ladi."""
    _yaratish(client, tolov)
    Tolov.objects.filter(pk=tolov.pk).update(
        tayyorlangan_at=timezone.now() - timedelta(hours=13)
    )

    javob = _bajarish(client)
    tolov.refresh_from_db()
    ekspert.refresh_from_db()

    assert javob.json()["error"]["code"] == payme.AMAL_BAJARILMAYDI
    assert tolov.holat == TolovHolati.BEKOR
    assert tolov.bekor_kodi == payme.SABAB_TAYMAUT
    assert ekspert.has_pro is False


# ===========================================================================
# 6. CancelTransaction — ikkala ssenariyning oxiri
# ===========================================================================
def test_cancel_BAJARILMAGAN_tranzaksiya_MINUS_BIR(client, tolov, ekspert):
    """⭐ Sandbox 1-ssenariy: yaratish -> bekor qilish."""
    _yaratish(client, tolov)

    javob = _bekor(client, sabab=1)
    natija = javob.json()["result"]
    tolov.refresh_from_db()
    ekspert.refresh_from_db()

    assert natija["state"] == payme.HOLAT_BEKOR
    assert natija["cancel_time"] > 0
    assert tolov.holat == TolovHolati.BEKOR
    assert ekspert.has_pro is False


def test_cancel_BAJARILGANDAN_KEYIN_MINUS_IKKI(client, tolov):
    """⭐⭐ Sandbox 2-ssenariy oxiri: pul QAYTARILDI.

    Bizda «bekor» bitta holat, Payme'da ikkita: `-1` (pul
    yechilmagan) va `-2` (yechilgan va qaytarilgan). Farq
    `tolangan_at` da yozilgan.
    """
    _yaratish(client, tolov)
    _bajarish(client)

    javob = _bekor(client, sabab=5)
    tolov.refresh_from_db()

    assert javob.json()["result"]["state"] == payme.HOLAT_QAYTARILDI
    assert tolov.qaytarilganmi is True
    assert tolov.bekor_kodi == 5


def test_PUL_QAYTARILSA_obuna_kunlari_QAYTARIB_OLINADI(
    client, tolov, ekspert, settings
):
    """⭐⭐⭐ Aks holda "to'la -> PRO ol -> pulni qaytar -> PRO qolsin".

    ⚠️ D6-T2 dagi «to'langan buyurtma bekor qilinmaydi» qoidasi
       CLICK ning ADASHGAN xabari haqida edi. Payme'ning bajarilgan
       tranzaksiyaga kelgan `CancelTransaction` i esa ANIQ
       ko'rsatma: pul mijozga qaytarildi.
    """
    _yaratish(client, tolov)
    _bajarish(client)
    tolangandan_keyin = Subscription.objects.get(user=ekspert).expires_at

    _bekor(client, sabab=5)

    keyin = Subscription.objects.get(user=ekspert).expires_at
    kutilgan = tolangandan_keyin - timedelta(days=settings.OBUNA_MUDDATI_KUN)
    assert keyin == kutilgan
    ekspert.refresh_from_db()
    assert ekspert.has_pro is False


def test_cancel_TAKRORLANSA_obuna_IKKI_MARTA_qisqarmaydi(client, tolov, ekspert):
    """⭐⭐ Payme bekor qilishni ham qayta yuboradi."""
    _yaratish(client, tolov)
    _bajarish(client)
    _bekor(client, sabab=5)
    birinchi = Subscription.objects.get(user=ekspert).expires_at

    javob = _bekor(client, sabab=5)

    assert javob.json()["result"]["state"] == payme.HOLAT_QAYTARILDI
    assert Subscription.objects.get(user=ekspert).expires_at == birinchi


def test_cancel_YOQ_tranzaksiya_minus_31003(client):
    javob = _bekor(client, trans_id="yoq")

    assert javob.json()["error"]["code"] == payme.TRANZAKSIYA_TOPILMADI


def test_cancel_YAROQSIZ_sabab_NOL_bolib_yoziladi(client, tolov):
    """⚠️ Sababni o'qib bo'lmagani uchun BEKOR QILISHNI rad etish
    mijozning pulini muzlatib qo'yardi.
    """
    _yaratish(client, tolov)

    javob = _sorov(client, payme.CANCEL, {"id": "p001", "reason": "nima_bu"})
    tolov.refresh_from_db()

    assert javob.json()["result"]["state"] == payme.HOLAT_BEKOR
    assert tolov.bekor_kodi == 0


# ===========================================================================
# 7. CheckTransaction
# ===========================================================================
def test_check_YARATILGAN_holatni_qaytaradi(client, tolov):
    yaratildi = _yaratish(client, tolov).json()["result"]

    javob = _sorov(client, payme.CHECK, {"id": "p001"}).json()["result"]

    assert javob["state"] == payme.HOLAT_YARATILDI
    assert javob["create_time"] == yaratildi["create_time"]
    assert javob["perform_time"] == 0
    assert javob["cancel_time"] == 0
    assert javob["reason"] is None


def test_check_QAYTARILGAN_tranzaksiya_MINUS_IKKI_va_SABAB(client, tolov):
    _yaratish(client, tolov)
    _bajarish(client)
    _bekor(client, sabab=5)

    javob = _sorov(client, payme.CHECK, {"id": "p001"}).json()["result"]

    assert javob["state"] == payme.HOLAT_QAYTARILDI
    assert javob["reason"] == 5
    assert javob["perform_time"] > 0
    assert javob["cancel_time"] > 0


def test_check_YOQ_tranzaksiya_minus_31003(client):
    javob = _sorov(client, payme.CHECK, {"id": "yoq"})

    assert javob.json()["error"]["code"] == payme.TRANZAKSIYA_TOPILMADI


# ===========================================================================
# 8. GetStatement
# ===========================================================================
def test_statement_DAVR_ichidagini_qaytaradi(client, tolov):
    _yaratish(client, tolov)
    _bajarish(client)
    hozir = payme.vaqtga_ms(timezone.now())

    javob = _sorov(
        client, payme.STATEMENT, {"from": hozir - 60_000, "to": hozir + 60_000}
    ).json()["result"]

    assert len(javob["transactions"]) == 1
    yozuv = javob["transactions"][0]
    assert yozuv["id"] == "p001"
    assert yozuv["amount"] == TIYIN
    assert yozuv["state"] == payme.HOLAT_BAJARILDI
    assert yozuv["account"] == {payme.ACCOUNT_MAYDONI: str(tolov.pk)}


def test_statement_DAVRDAN_TASHQARIDAGINI_qaytarmaydi(client, tolov):
    _yaratish(client, tolov)
    hozir = payme.vaqtga_ms(timezone.now())

    javob = _sorov(
        client, payme.STATEMENT, {"from": hozir + 60_000, "to": hozir + 120_000}
    ).json()["result"]

    assert javob["transactions"] == []


def test_statement_CLICK_tolovlarini_QAYTARMAYDI(client, tolov, ekspert):
    """⚠️ Solishtirish faqat PAYME tranzaksiyalari bo'yicha boradi."""
    click_tolovi = Tolov.objects.create(
        user=ekspert,
        provayder=Provayder.CLICK,
        summa=Decimal(NARX),
        provayder_trans_id="c999",
        holat=TolovHolati.TAYYOR,
        tayyorlangan_at=timezone.now(),
    )
    _yaratish(client, tolov)
    hozir = payme.vaqtga_ms(timezone.now())

    javob = _sorov(
        client, payme.STATEMENT, {"from": hozir - 60_000, "to": hozir + 60_000}
    ).json()["result"]

    raqamlar = [t["id"] for t in javob["transactions"]]
    assert raqamlar == ["p001"]
    assert str(click_tolovi.pk) not in [t["transaction"] for t in javob["transactions"]]


# ===========================================================================
# 9. Jurnal
# ===========================================================================
def test_HAR_BIR_sorov_jurnalga_tushadi(client, tolov):
    _sorov(client, payme.CHECK_PERFORM, {"amount": TIYIN, "account": _hisob(tolov)})
    _yaratish(client, tolov)
    _bajarish(client)

    amallar = list(TolovSorovi.objects.values_list("amal", flat=True))
    assert sorted(amallar) == sorted([payme.CHECK_PERFORM, payme.CREATE, payme.PERFORM])


def test_AVTORIZATSIYASIZ_sorov_HAM_jurnalga_tushadi(client, tolov):
    """⭐ Nizoda eng kerakli qator aynan rad etilgani."""
    _sorov(
        client,
        payme.CHECK_PERFORM,
        {"amount": TIYIN, "account": _hisob(tolov)},
        kalit="soxta",
    )

    yozuv = TolovSorovi.objects.get()
    assert yozuv.imzo_togrimi is False
    assert yozuv.natija == payme.HUQUQ_YETARLI_EMAS
    assert yozuv.merchant_trans_id == str(tolov.pk)


def test_jurnalda_KALIT_saqlanmaydi(client, tolov):
    """⚠️⚠️ Basic-auth sarlavhasi TANADA emas, ya'ni jurnalga
    tushmasligi tabiiy — lekin buni test QOTIRADI: kelajakda
    sarlavhalarni ham yozishga qaror qilinsa, bu test yiqiladi.
    """
    _yaratish(client, tolov)

    yozuv = TolovSorovi.objects.get()
    assert KALIT not in json.dumps(yozuv.xom)
    assert "Paycom" not in json.dumps(yozuv.xom)


def test_jurnalda_TRANZAKSIYA_raqami_bor(client, tolov):
    _yaratish(client, tolov)

    yozuv = TolovSorovi.objects.get()
    assert yozuv.provayder_trans_id == "p001"
    assert yozuv.provayder == Provayder.PAYME


# ===========================================================================
# 10. Sotib olish oqimi
# ===========================================================================
def test_PAYME_tugmasi_checkout_ga_yuboradi(client, ekspert):
    client.force_login(ekspert)

    javob = client.post(reverse("pro_sotib_olish", args=["payme"]))
    buyurtma = Tolov.objects.get()

    assert javob.status_code == 302
    assert javob["Location"].startswith("https://checkout.paycom.uz/")
    assert buyurtma.provayder == Provayder.PAYME
    ochilgan = base64.b64decode(javob["Location"].rsplit("/", 1)[-1]).decode()
    assert f"ac.order_id={buyurtma.pk}" in ochilgan
    assert f"a={TIYIN}" in ochilgan


def test_YOQILMAGAN_provayder_tugmasi_ISHLAMAYDI(client, ekspert, settings):
    settings.PAYME_YOQILGANMI = False
    client.force_login(ekspert)

    javob = client.post(reverse("pro_sotib_olish", args=["payme"]))

    assert javob.status_code == 302
    assert Tolov.objects.exists() is False


def test_NOMALUM_provayder_500_BERMAYDI(client, ekspert):
    """⚠️ Manzilni qo'lda terib server xatosini chiqarib bo'lmasin."""
    client.force_login(ekspert)

    javob = client.post(reverse("pro_sotib_olish", args=["boshqa-tizim"]))

    assert javob.status_code == 302
    assert Tolov.objects.exists() is False


def test_pro_sahifasida_FAQAT_YOQILGAN_provayder(client, ekspert, settings):
    settings.CLICK_YOQILGANMI = False
    settings.PAYME_YOQILGANMI = True
    client.force_login(ekspert)

    matn = client.get(reverse("pro")).content.decode()

    assert "Payme orqali to'lash" in matn
    assert "Click orqali to'lash" not in matn


# ===========================================================================
# 11. Qo'riqchi
# ===========================================================================
def test_HAR_MAQSADNING_QAYTARISH_yoli_BOR():
    """⭐⭐ Yangi maqsad qo'shilib, qaytarish unutilsa — pul
    qaytarilgan xizmat ishlab qolaverardi va buni faqat mijoz
    payqardi (D6-T4 boost aynan shu xavf ostida).
    """
    assert set(_MAQSAD_BAJARUVCHILARI) == set(_MAQSAD_BEKOR_QILUVCHILARI)
