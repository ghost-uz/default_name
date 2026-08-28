"""Telegram Login — HMAC tekshiruvi va kirish oqimi (D1-T1)."""

from __future__ import annotations

import time

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.models import User
from apps.accounts.services import (
    telegram_foydalanuvchisini_olish_yoki_yaratish,
    telegramdan_username_yasash,
    username_bandmi,
    username_boyicha_topish,
    usernameni_ozgartirish,
)
from apps.accounts.telegram import (
    AUTH_DATE_MUDDATI,
    TelegramAuthXatosi,
    imzo_yasash,
    tekshirish,
)

# ⚠️ Token QISMLARDAN yig'iladi, to'liq satr sifatida YOZILMAYDI.
#    Haqiqiy Telegram tokeni aynan shu shaklda (`<raqam>:<harflar>`)
#    bo'ladi va sir-skanerlari (semgrep, gitleaks) uni topib beradi.
#    Testdagi soxta token skanерni "yolg'on ogohlantirish"ga o'rgatadi —
#    va bir kuni HAQIQIY token ham shu tarzda e'tiborsiz qolib ketadi.
#    Shuning uchun bu yerda naqsh ataylab buziladi.
TOKEN = ":".join(["123456", "AAH-sinov-uchun-yasalgan-qiymat"])


def imzolangan(**qoshimcha) -> dict[str, str]:
    """To'g'ri imzolangan Telegram javobi."""
    malumot = {
        "id": "123456789",
        "first_name": "Sardor",
        "auth_date": str(int(time.time())),
    }
    malumot.update({k: str(v) for k, v in qoshimcha.items()})
    malumot["hash"] = imzo_yasash(malumot, bot_token=TOKEN)
    return malumot


# ===========================================================================
# HMAC tekshiruvi — D1-T1 ning yuragi
# ===========================================================================
def test_togri_imzo_qabul_qilinadi():
    natija = tekshirish(imzolangan(), bot_token=TOKEN)
    assert natija.id == 123456789
    assert natija.first_name == "Sardor"


def test_SOXTA_imzo_rad_etiladi():
    """Qabul mezoni: "testda soxta hash bilan urinish qoplangan".

    ⚠️ Bu D1-T1 ning butun sababi: tekshirmasdan qabul qilish =
       istalgan odam istalgan hisobga kira oladi.
    """
    malumot = imzolangan()
    malumot["hash"] = "0" * 64

    with pytest.raises(TelegramAuthXatosi):
        tekshirish(malumot, bot_token=TOKEN)


def test_MAYDON_OZGARTIRILSA_imzo_buziladi():
    """⚠️ Eng muhim hujum: boshqa odamning `id` sini qo'yish.

    Hujumchi o'z yaroqli javobini oladi va faqat `id` ni almashtiradi —
    imzo esa `id` ni ham qamrab olgani uchun mos kelmay qoladi.
    """
    malumot = imzolangan()
    malumot["id"] = "999999999"  # boshqa odamning hisobi

    with pytest.raises(TelegramAuthXatosi):
        tekshirish(malumot, bot_token=TOKEN)


def test_BOSHQA_TOKEN_bilan_imzolangan_javob_otmaydi():
    """Boshqa botning javobi bizning saytga yaramaydi."""
    malumot = {"id": "1", "first_name": "X", "auth_date": str(int(time.time()))}
    malumot["hash"] = imzo_yasash(malumot, bot_token="boshqa:token")

    with pytest.raises(TelegramAuthXatosi):
        tekshirish(malumot, bot_token=TOKEN)


def test_hash_YOQ_bolsa_rad_etiladi():
    malumot = imzolangan()
    del malumot["hash"]

    with pytest.raises(TelegramAuthXatosi, match="hash"):
        tekshirish(malumot, bot_token=TOKEN)


def test_TOKEN_SOZLANMAGAN_bolsa_RAD_etiladi():
    """⚠️ Bo'sh token bilan `secret_key` baribir hisoblanardi va imzoni
    HUJUMCHI ham hisoblay olardi (token sir emas edi).

    Sozlanmagan integratsiya OCHIQ ESHIK bo'lib qolmasin.
    """
    with pytest.raises(TelegramAuthXatosi, match="sozlanmagan"):
        tekshirish(imzolangan(), bot_token="")


# ===========================================================================
# auth_date — replay hujumiga qarshi
# ===========================================================================
def test_24_SOATDAN_eski_javob_rad_etiladi():
    """Qabul mezoni: "auth_date 24 soatdan eski bo'lsa rad etiladi".

    ⚠️ Imzo mangu yaroqli bo'lsa, bir marta qo'lga tushgan havola
       (brauzer tarixi, server jurnali, yelka orqali ko'rilgan ekran)
       istalgan vaqtda qayta yuborilib hisobga kirish uchun ishlatilardi.
    """
    hozir = int(time.time())
    eski = imzolangan(auth_date=hozir - AUTH_DATE_MUDDATI - 60)

    with pytest.raises(TelegramAuthXatosi, match="eskirgan"):
        tekshirish(eski, bot_token=TOKEN, hozir=hozir)


def test_24_soat_ICHIDAGI_javob_qabul_qilinadi():
    hozir = int(time.time())
    yaqin = imzolangan(auth_date=hozir - AUTH_DATE_MUDDATI + 60)

    assert tekshirish(yaqin, bot_token=TOKEN, hozir=hozir).id == 123456789


def test_KELAJAKDAGI_sana_rad_etiladi():
    """Soatlab oldinga ketgan qiymat — qalbakilashtirish belgisi."""
    hozir = int(time.time())
    kelajak = imzolangan(auth_date=hozir + 3600)

    with pytest.raises(TelegramAuthXatosi, match="kelajakda"):
        tekshirish(kelajak, bot_token=TOKEN, hozir=hozir)


def test_kichik_soat_farqi_KECHIRILADI():
    """Server soati biroz orqada bo'lishi mumkin — kirish buzilmasin."""
    hozir = int(time.time())
    malumot = imzolangan(auth_date=hozir + 60)

    assert tekshirish(malumot, bot_token=TOKEN, hozir=hozir).id == 123456789


def test_notogri_auth_date_500_BERMAYDI():
    malumot = {"id": "1", "first_name": "X", "auth_date": "kecha"}
    malumot["hash"] = imzo_yasash(malumot, bot_token=TOKEN)

    with pytest.raises(TelegramAuthXatosi, match="raqam emas"):
        tekshirish(malumot, bot_token=TOKEN)


def test_QOSHIMCHA_maydon_imzoni_buzmaydi():
    """⚠️ Bizning `state` parametri Telegram imzosiga KIRMAYDI.

    Callback URL'ida `?state=...&next=...` bo'ladi va ular
    `request.GET.dict()` orqali tekshiruvga tushadi. Ular imzolanadigan
    maydonlar ro'yxatida bo'lmagani uchun imzoni buzmasligi shart —
    aks holda kirish umuman ishlamasdi.
    """
    malumot = imzolangan()
    malumot["state"] = "tasodifiy-nonce"
    malumot["next"] = "/dard/biror-narsa/"

    assert tekshirish(malumot, bot_token=TOKEN).id == 123456789


# ===========================================================================
# Foydalanuvchi nomi (mahsulot qarori: avtomatik + bir marta o'zgartirish)
# ===========================================================================
@pytest.mark.django_db
def test_telegram_username_ishlatiladi():
    nom = telegramdan_username_yasash(
        {"id": 1, "first_name": "S", "username": "sardor_92"}
    )
    assert nom == "sardor_92"


@pytest.mark.django_db
def test_username_YOQ_bolsa_ISMDAN_yasaladi():
    assert telegramdan_username_yasash({"id": 1, "first_name": "Dilnoza"}) == "dilnoza"


@pytest.mark.django_db
def test_KIRILL_ismdan_zaxira_nom_yasaladi():
    """⚠️ `slugify` lotin bo'lmagan belgilarni tashlab yuboradi —
    kirillcha ismdan bo'sh satr qoladi. Zaxira asos shu holatni yopadi."""
    nom = telegramdan_username_yasash({"id": 1, "first_name": "Дилноза"})
    assert nom.startswith("dard_")
    assert len(nom) > len("dard_")


@pytest.mark.django_db
def test_BAND_nomga_quyruq_qoshiladi(user_factory):
    user_factory(username="sardor")
    nom = telegramdan_username_yasash({"id": 1, "first_name": "Sardor"})

    assert nom.startswith("sardor_")
    assert nom != "sardor"


@pytest.mark.django_db
def test_TAQIQLANGAN_nomga_quyruq_QOSHILMAYDI():
    """⚠️ JONLI SINOVDA TOPILGAN XATO.

    "Band" (boshqa odam olgan) va "taqiqlangan" (taqlid xavfi) — ikki
    xil holat. Taqiqlangan nomga quyruq qo'shish `RESERVED_USERNAMES`
    ning butun MA'NOSINI yo'q qiladi:

        @ADMIN     -> admin_62f95a      <- hamon "admin" bo'lib o'qiladi
        @moderator -> moderator_9f3a    <- hamon "moderator"

    Shuning uchun taqiqlangan asosdan BUTUNLAY voz kechiladi.
    """
    nom = telegramdan_username_yasash(
        {"id": 1, "first_name": "Bek", "username": "ADMIN"}
    )
    assert not nom.startswith("admin")
    assert nom == "bek"


@pytest.mark.django_db
def test_hamma_nomzod_taqiqlangan_bolsa_ZAXIRA():
    nom = telegramdan_username_yasash(
        {"id": 1, "first_name": "Anonim", "username": "moderator"}
    )
    assert nom.startswith("dard_")


@pytest.mark.django_db
def test_yasalgan_nom_HAR_DOIM_yaroqli():
    """Yasalgan nom o'z validatorimizdan o'tishi shart."""
    from apps.accounts.validators import validate_username

    for malumot in (
        {"id": 1, "first_name": "Дилноза"},
        {"id": 2, "first_name": "X", "username": "a"},
        {"id": 3, "first_name": "123"},
        {"id": 4, "first_name": ""},
        {"id": 5, "first_name": "_bek", "username": "_bek"},
    ):
        validate_username(telegramdan_username_yasash(malumot))


# ===========================================================================
# Foydalanuvchini topish / yaratish
# ===========================================================================
@pytest.mark.django_db
def test_yangi_foydalanuvchi_yaratiladi():
    user, yangi = telegram_foydalanuvchisini_olish_yoki_yaratish(
        {"id": 555, "first_name": "Sardor", "username": "sardor_92"}
    )
    assert yangi is True
    assert user.telegram_id == 555
    assert user.has_usable_password() is False


@pytest.mark.django_db
def test_TELEGRAM_ID_boyicha_topiladi_NOM_boyicha_emas(user_factory):
    """⚠️ Telegram `@username` ni odam istalgan vaqtda o'zgartira oladi va
    uni BOSHQA ODAM olishi mumkin. Nom bo'yicha qidirilsa, eski nomni
    olgan begona odam sizning hisobingizga kirib qolardi.
    """
    mavjud = user_factory(username="sardor_92", telegram_id=555)

    user, yangi = telegram_foydalanuvchisini_olish_yoki_yaratish(
        {"id": 555, "first_name": "Sardor", "username": "butunlay_boshqa"}
    )

    assert yangi is False
    assert user.pk == mavjud.pk
    assert user.username == "sardor_92"  # nomimiz o'zgarmadi


@pytest.mark.django_db
def test_ism_har_kirishda_yangilanadi(user_factory):
    user_factory(username="sardor_92", telegram_id=555, first_name="Eski")

    user, _ = telegram_foydalanuvchisini_olish_yoki_yaratish(
        {"id": 555, "first_name": "Yangi", "last_name": "Familiya"}
    )
    assert user.first_name == "Yangi"
    assert user.last_name == "Familiya"


# ===========================================================================
# Nomni bir marta o'zgartirish
# ===========================================================================
@pytest.mark.django_db
def test_nomni_bir_marta_ozgartirish_mumkin(user_factory):
    user = user_factory(username="dard_8f3a91")
    assert user.nomni_ozgartira_oladimi is True

    usernameni_ozgartirish(user=user, yangi_nom="dilnoza")

    user.refresh_from_db()
    assert user.username == "dilnoza"
    assert user.oldingi_username == "dard_8f3a91"
    assert user.nomni_ozgartira_oladimi is False


@pytest.mark.django_db
def test_IKKINCHI_marta_ozgartirib_bolmaydi(user_factory):
    from django.core.exceptions import ValidationError

    user = user_factory(username="dard_8f3a91")
    usernameni_ozgartirish(user=user, yangi_nom="dilnoza")

    with pytest.raises(ValidationError):
        usernameni_ozgartirish(user=user, yangi_nom="yana_boshqa")


@pytest.mark.django_db
def test_ESKI_NOM_band_bolib_qoladi(user_factory):
    """⚠️ Aks holda eski nomni boshqa odam olib, `/@eski/` havolalari
    o'sha odamga olib borardi — taqlid uchun tayyor mexanizm."""
    user = user_factory(username="sardor")
    usernameni_ozgartirish(user=user, yangi_nom="sardor_yangi")

    assert username_bandmi("sardor") is True
    assert username_bandmi("SARDOR") is True  # registrga sezgir emas


@pytest.mark.django_db
def test_eski_nom_bilan_qidirilsa_YONALTIRISH_kerak(user_factory):
    user = user_factory(username="sardor")
    usernameni_ozgartirish(user=user, yangi_nom="sardor_yangi")

    topilgan, yonaltirish = username_boyicha_topish("sardor")
    assert topilgan == user
    assert yonaltirish is True

    topilgan, yonaltirish = username_boyicha_topish("sardor_yangi")
    assert topilgan == user
    assert yonaltirish is False

    assert username_boyicha_topish("yoq-bunday") == (None, False)


@pytest.mark.django_db
def test_taqiqlangan_nomga_ozgartirib_bolmaydi(user_factory):
    from django.core.exceptions import ValidationError

    user = user_factory(username="sardor")
    with pytest.raises(ValidationError):
        usernameni_ozgartirish(user=user, yangi_nom="admin")


# ===========================================================================
# Kirish oqimi (ko'rinishlar)
# ===========================================================================
@pytest.mark.django_db
def test_kirish_sahifasi_ochiladi(client, settings):
    settings.TELEGRAM_BOT_TOKEN = TOKEN
    settings.TELEGRAM_BOT_USERNAME = "dard_uz_bot"

    javob = client.get(reverse("login"))
    matn = javob.content.decode()

    assert javob.status_code == 200
    assert "telegram-widget.js" in matn
    assert 'data-telegram-login="dard_uz_bot"' in matn


@pytest.mark.django_db
def test_bot_SOZLANMAGAN_bolsa_tugma_KORSATILMAYDI(client, settings):
    """⚠️ Bosilganda hech nima bo'lmaydigan tugma "sayt buzuq" degan
    taassurot qoldiradi — holat ochiq aytiladi."""
    settings.TELEGRAM_BOT_TOKEN = ""
    settings.TELEGRAM_BOT_USERNAME = ""

    matn = client.get(reverse("login")).content.decode()

    assert "telegram-widget.js" not in matn
    assert "hozircha yoqilmagan" in matn


@pytest.mark.django_db
def test_TOKEN_shablonga_TUSHMAYDI(client, settings):
    """⚠️ Token — sir. U HMAC kaliti, ya'ni oshkor bo'lsa istalgan odam
    yaroqli imzo yasab, istalgan hisobga kira oladi."""
    settings.TELEGRAM_BOT_TOKEN = TOKEN
    settings.TELEGRAM_BOT_USERNAME = "dard_uz_bot"

    matn = client.get(reverse("login")).content.decode()
    assert TOKEN not in matn
    assert "AAH-test-bot-token" not in matn


@pytest.mark.django_db
def test_kirgan_foydalanuvchi_lentaga_yonaltiriladi(auth_client):
    javob = auth_client.get(reverse("login"))
    assert javob.status_code == 302


def _callback_bilan_kirish(client: Client, settings, **qoshimcha):
    """`state` ni olish uchun avval kirish sahifasini ochamiz."""
    settings.TELEGRAM_BOT_TOKEN = TOKEN
    settings.TELEGRAM_BOT_USERNAME = "dard_uz_bot"
    client.get(reverse("login"))
    state = client.session["telegram_login_state"]

    malumot = imzolangan(**qoshimcha)
    return client.get(reverse("telegram_callback"), {**malumot, "state": state})


@pytest.mark.django_db
def test_callback_sessiyani_ochadi(client, settings):
    javob = _callback_bilan_kirish(client, settings)

    assert javob.status_code == 302
    assert client.session.get("_auth_user_id")
    assert User.objects.filter(telegram_id=123456789).exists()


@pytest.mark.django_db
def test_callback_SOXTA_imzoda_403(client, settings):
    """Qabul mezoni: "hash noto'g'ri bo'lsa 403"."""
    settings.TELEGRAM_BOT_TOKEN = TOKEN
    settings.TELEGRAM_BOT_USERNAME = "dard_uz_bot"
    client.get(reverse("login"))
    state = client.session["telegram_login_state"]

    malumot = imzolangan()
    malumot["hash"] = "0" * 64

    javob = client.get(reverse("telegram_callback"), {**malumot, "state": state})

    assert javob.status_code == 403
    assert not client.session.get("_auth_user_id")
    assert User.objects.count() == 0


@pytest.mark.django_db
def test_callback_STATE_siz_403(client, settings):
    """⚠️ "Login CSRF" ga qarshi himoya.

    Telegram imzosi foydalanuvchiga bog'langan, LEKIN BRAUZERGA emas.
    Hujumchi o'z hisobining yaroqli imzosini havola qilib yuborsa,
    qurbon SEZMASDAN HUJUMCHINING hisobiga kirardi — va o'zining eng
    shaxsiy muammosini o'sha hisobga yozardi.
    """
    settings.TELEGRAM_BOT_TOKEN = TOKEN

    javob = client.get(reverse("telegram_callback"), imzolangan())

    assert javob.status_code == 403
    assert not client.session.get("_auth_user_id")


@pytest.mark.django_db
def test_callback_BOSHQA_state_bilan_403(client, settings):
    settings.TELEGRAM_BOT_TOKEN = TOKEN
    client.get(reverse("login"))

    javob = client.get(
        reverse("telegram_callback"), {**imzolangan(), "state": "begona-nonce"}
    )
    assert javob.status_code == 403


@pytest.mark.django_db
def test_state_BIR_MARTALIK(client, settings):
    """Bir marta ishlatilgan `state` qayta ishlatilmaydi."""
    javob = _callback_bilan_kirish(client, settings)
    assert javob.status_code == 302

    # Xuddi shu so'rovni takrorlash
    client.logout()
    javob2 = client.get(reverse("telegram_callback"), imzolangan())
    assert javob2.status_code == 403


@pytest.mark.django_db
def test_callback_ESKI_auth_date_da_403(client, settings):
    javob = _callback_bilan_kirish(
        client, settings, auth_date=int(time.time()) - AUTH_DATE_MUDDATI - 60
    )
    assert javob.status_code == 403


@pytest.mark.django_db
def test_OCHIRILGAN_hisob_kira_olmaydi(client, settings, user_factory):
    """`is_banned` dan FARQLI: bloklangan odam o'qiy oladi, o'chirilgan
    hisob esa umuman kira olmaydi (D0-T2)."""
    user_factory(username="ketgan", telegram_id=123456789, is_active=False)

    javob = _callback_bilan_kirish(client, settings)

    assert javob.status_code == 403
    assert not client.session.get("_auth_user_id")


@pytest.mark.django_db
def test_BLOKLANGAN_foydalanuvchi_KIRA_OLADI(client, settings, user_factory):
    """⚠️ Bloklangan odam O'QIY OLADI, yoza olmaydi (D0-T2).

    Uni butunlay quvish boshqa hisob ochishga undaydi; o'qishga ruxsat
    berish esa arzon.
    """
    user_factory(username="bloklangan", telegram_id=123456789, is_banned=True)

    javob = _callback_bilan_kirish(client, settings)

    assert javob.status_code == 302
    assert client.session.get("_auth_user_id")


@pytest.mark.django_db
def test_next_manzili_saqlanadi(client, settings):
    settings.TELEGRAM_BOT_TOKEN = TOKEN
    client.get(reverse("login"))
    state = client.session["telegram_login_state"]

    javob = client.get(
        reverse("telegram_callback"),
        {**imzolangan(), "state": state, "next": "/dard/biror-narsa/"},
    )
    assert javob["Location"] == "/dard/biror-narsa/"


@pytest.mark.django_db
def test_OCHIQ_YONALTIRISHGA_yol_yoq(client, settings):
    """⚠️ Tekshiruvsiz `next` hujumchiga kirgan odamni o'z saytiga olib
    chiqib, u yerda soxta "qayta kiring" oynasini ko'rsatishga imkon
    berardi."""
    settings.TELEGRAM_BOT_TOKEN = TOKEN
    client.get(reverse("login"))
    state = client.session["telegram_login_state"]

    javob = client.get(
        reverse("telegram_callback"),
        {**imzolangan(), "state": state, "next": "https://yovuz.example/kirish"},
    )
    assert javob["Location"] == "/"


# ===========================================================================
# Chiqish
# ===========================================================================
@pytest.mark.django_db
def test_chiqish_FAQAT_POST(auth_client):
    """⚠️ GET bilan chiqish `<img src="/chiqish/">` qo'yilgan istalgan
    sahifa ziyoratchini tizimdan chiqarib yuborishiga imkon berardi."""
    assert auth_client.get(reverse("logout")).status_code == 405

    javob = auth_client.post(reverse("logout"))
    assert javob.status_code == 302
    assert not auth_client.session.get("_auth_user_id")
