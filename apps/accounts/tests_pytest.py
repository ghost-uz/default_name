"""Fabrikalar va fixture'lar (D0-T7).

⚠️ USLUB QOIDASI: yangi testlar SHU uslubda yoziladi — oddiy funksiya +
   fixture. Mavjud `tests.py` dagi `TestCase` sinflari ham pytest ostida
   ishlaydi, shuning uchun ular qayta yozilmadi (o'zgarish qiymat
   keltirmaydi, xavf esa bor).
"""

import pytest

from apps.accounts.factories import ExpertFactory, TelegramUserFactory, UserFactory
from apps.accounts.services import username_bandmi


# ===========================================================================
# Fabrikalar
# ===========================================================================
@pytest.mark.django_db
def test_fabrika_noyob_username_beradi():
    """Sequence ishlatiladi — tasodifiy ism to'qnashishi mumkin edi va
    test vaqti-vaqti bilan yiqiladigan bo'lib qolardi."""
    nomlar = {UserFactory().username for _ in range(20)}
    assert len(nomlar) == 20


@pytest.mark.django_db
def test_fabrika_standart_bolib_parolsiz_yaratadi():
    """Haqiqiy foydalanuvchilar Telegram orqali kiradi — parolga ega emas.

    Fabrika shu holatni takrorlaydi, aks holda testlar hayotda
    bo'lmaydigan holatni sinab ko'rardi.
    """
    u = UserFactory()
    assert not u.has_usable_password()


@pytest.mark.django_db
def test_fabrikaga_parol_berish_mumkin():
    u = UserFactory(password="sirsuz")
    assert u.check_password("sirsuz")


@pytest.mark.django_db
def test_telegram_fabrikasi_id_beradi():
    a, b = TelegramUserFactory(), TelegramUserFactory()
    assert a.telegram_id != b.telegram_id
    assert a.telegram_id > 32_767  # BigInteger kerakligini eslatadi


@pytest.mark.django_db
def test_ekspert_fabrikasi():
    e = ExpertFactory()
    assert e.is_expert
    assert e.karma_cached >= 1000


# ===========================================================================
# Fixture'lar
# ===========================================================================
def test_user_fixture(user):
    assert user.telegram_id is not None
    assert user.can_write


def test_ikki_foydalanuvchi_farqli(user, other_user):
    """Ruxsat testlari uchun: "boshqa odamning postini tahrirlay olmaydi"."""
    assert user.pk != other_user.pk


def test_banned_user_oqiy_oladi_yoza_olmaydi(banned_user):
    assert banned_user.is_active  # kira oladi
    assert banned_user.is_currently_banned
    assert not banned_user.can_write


def test_auth_client_kirgan(auth_client, user):
    javob = auth_client.get("/")
    assert javob.wsgi_request.user == user
    assert javob.wsgi_request.user.is_authenticated


@pytest.mark.django_db
def test_anonymous_client_kirmagan(anonymous_client):
    # ⚠️ `django_db` D1-T7 dan keyin kerak bo'ldi: `/` endi maketning
    #    statik sahifasi emas, bazadan o'qiydigan haqiqiy lenta.
    javob = anonymous_client.get("/")
    assert not javob.wsgi_request.user.is_authenticated


def test_staff_client(staff_client, staff):
    assert staff.is_staff
    javob = staff_client.get("/")
    assert javob.wsgi_request.user.is_staff


# ===========================================================================
# services.username_bandmi
# ===========================================================================
@pytest.mark.django_db
def test_band_username_aniqlanadi(user):
    assert username_bandmi(user.username)


@pytest.mark.django_db
def test_registrga_sezgir_emas(user):
    """⚠️ D0-T2 dagi taqlidga qarshi qoida bilan mos bo'lishi shart:
    DB registrga sezgir bo'lmagan noyoblikni talab qiladi, shuning uchun
    tekshiruv ham shunday bo'lishi kerak."""
    assert username_bandmi(user.username.upper())
    assert username_bandmi(user.username.capitalize())


@pytest.mark.django_db
def test_band_nomlar_royxati():
    for nom in ("admin", "anonim", "kirish", "ekspertlar"):
        assert username_bandmi(nom), nom


@pytest.mark.django_db
def test_yaroqsiz_shakl_band_deb_hisoblanadi():
    """Yasash funksiyasi (D1-T1) shu tekshiruvga tayanadi — yaroqsiz
    nomni "bo'sh" deb qaytarish uni cheksiz siklga tushirardi."""
    for nom in ("ab", "1sardor", "sardor-92", "x" * 31):
        assert username_bandmi(nom), nom


@pytest.mark.django_db
def test_bosh_nom_bosh_deb_qaytadi():
    assert not username_bandmi("yangi_foydalanuvchi")


# ===========================================================================
# Infratuzilma
# ===========================================================================
def test_health_endpoint(anonymous_client):
    javob = anonymous_client.get("/health/")
    assert javob.status_code == 200
    assert javob.content == b"ok"


@pytest.mark.django_db
def test_tashqi_tarmoq_taqiqlangan():
    """conftest fixture'i tashqi chaqiruvni ushlaydi.

    Telegram (D1-T1, D5-T2) va to'lov (D6-T2/T3) integratsiyalari
    tasodifan haqiqiy so'rov yubormasin.
    """
    import socket

    # ⚠️ `with` SHART: yopilmagan soket ResourceWarning beradi, u esa
    #    `filterwarnings = ["error"]` sababli testni yiqitadi. Xato
    #    xabari ("PytestUnraisableExceptionWarning") sababni ko'rsatmaydi.
    with socket.socket() as s:
        with pytest.raises(RuntimeError, match="tashqi tarmoqqa"):
            s.connect(("api.telegram.org", 443))
