"""Tezlik cheklovi (D2-T4)."""

from __future__ import annotations

import pytest
from django.core.cache import cache
from django.test import Client, RequestFactory, override_settings
from django.urls import reverse

from apps.common import ratelimit
from apps.common.ratelimit import (
    Cheklov,
    chegarani_oqish,
    cheklovlarni_olish,
    mijoz_ip,
    tezlik_cheklovi,
)
from apps.complaints.factories import ComplaintFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def soat(monkeypatch):
    """Boshqariladigan vaqt — oyna almashishini sinash uchun.

    ⚠️ `time.sleep()` bilan yozilsa test sekin VA nomukammal bo'lardi:
       oyna chegarasi qayerda ekanini bilmaymiz, ya'ni ba'zan tasodifan
       o'tib ketardi.
    """
    holat = {"t": 1_800_000_000.0}
    monkeypatch.setattr(ratelimit.time, "time", lambda: holat["t"])
    return holat


def sorov(usul: str = "POST", **meta):
    """Dekorator uchun oddiy so'rov (autentifikatsiyasiz)."""
    from django.contrib.auth.models import AnonymousUser

    r = getattr(RequestFactory(), usul.lower())("/", **meta)
    r.user = AnonymousUser()
    return r


# ===========================================================================
# Chegarani o'qish — sozlamadagi xato JIM O'TMASIN
# ===========================================================================
@pytest.mark.parametrize(
    ("matn", "soni", "oyna"),
    [
        ("30/m", 30, 60),
        ("5/h", 5, 3600),
        ("100/2h", 100, 7200),
        ("10/s", 10, 1),
        ("3/d", 3, 86400),
        ("  7/m  ", 7, 60),
    ],
)
def test_chegara_oqiladi(matn, soni, oyna):
    assert chegarani_oqish(matn) == Cheklov(soni=soni, oyna=oyna)


@pytest.mark.parametrize("matn", ["30/min", "30", "abc", "", "m/30", "30/0x"])
def test_NOTOGRI_chegara_XATO_beradi(matn):
    """⚠️ Sozlamadagi xato ("30/min") jim o'tsa, cheklov BUTUNLAY
    o'chib qolardi va buni hech kim payqamasdi."""
    with pytest.raises(ValueError, match="Chegara noto'g'ri"):
        chegarani_oqish(matn)


def test_nomalum_cheklov_nomi_XATO_beradi():
    with pytest.raises(ValueError, match="TEZLIK_CHEKLOVLARI"):
        cheklovlarni_olish("bunday_cheklov_yoq")


def test_tavsif_odam_oqiydigan_shaklda():
    assert chegarani_oqish("30/m").tavsif == "30 marta / daqiqa"
    assert chegarani_oqish("5/h").tavsif == "5 marta / soat"
    assert chegarani_oqish("100/2h").tavsif == "100 marta / 2 soat"


# ===========================================================================
# Mijoz IP'si — ikkita teskari xato, ikkalasi ham jim
# ===========================================================================
@override_settings(ISHONCHLI_PROKSILAR_SONI=0)
def test_proksisiz_XFF_UMUMAN_inobatga_olinmaydi():
    """⚠️ `X-Forwarded-For` ni MIJOZ o'zi yozadi.

    Proksi yo'q bo'lsa unga ishonish cheklovni butunlay ma'nosiz
    qilardi: har so'rovda boshqa qiymat yuborgan skript hech qachon
    chegaraga urilmasdi.
    """
    r = sorov(REMOTE_ADDR="10.0.0.7", HTTP_X_FORWARDED_FOR="1.2.3.4, 5.6.7.8")

    assert mijoz_ip(r) == "10.0.0.7"


@override_settings(ISHONCHLI_PROKSILAR_SONI=1)
def test_bitta_proksida_OXIRGI_element_olinadi():
    """Nginx `$proxy_add_x_forwarded_for` ro'yxat OXIRIGA o'ziga
    ulangan manzilni qo'shadi — ya'ni mijoz IP'si oxirgi."""
    r = sorov(REMOTE_ADDR="172.18.0.2", HTTP_X_FORWARDED_FOR="1.2.3.4, 95.85.1.9")

    assert mijoz_ip(r) == "95.85.1.9"


@override_settings(ISHONCHLI_PROKSILAR_SONI=2)
def test_ikki_proksida_oxirgidan_IKKINCHISI():
    r = sorov(HTTP_X_FORWARDED_FOR="1.1.1.1, 95.85.1.9, 172.18.0.2")

    assert mijoz_ip(r) == "95.85.1.9"


@override_settings(ISHONCHLI_PROKSILAR_SONI=2)
def test_XFF_KUTILGANIDAN_QISQA_bolsa_REMOTE_ADDR():
    """Proksi sozlamasi noto'g'ri — ochiq qoldirgandan ko'ra
    `REMOTE_ADDR` ga qaytamiz (va ogohlantirish yoziladi)."""
    r = sorov(REMOTE_ADDR="10.0.0.7", HTTP_X_FORWARDED_FOR="1.2.3.4")

    assert mijoz_ip(r) == "10.0.0.7"


def test_IP_umuman_bolmasa_ham_yiqilmaydi():
    r = sorov()
    r.META.pop("REMOTE_ADDR", None)

    assert mijoz_ip(r) == "nomalum"


# ===========================================================================
# Sanash
# ===========================================================================
@override_settings(TEZLIK_CHEKLOVLARI={"sinov": {"ip": "3/m"}})
def test_chegaragacha_OTADI_undan_keyin_429():
    @tezlik_cheklovi("sinov")
    def korinish(request):
        from django.http import HttpResponse

        return HttpResponse("ok")

    javoblar = [korinish(sorov()).status_code for _ in range(4)]

    assert javoblar == [200, 200, 200, 429]


@override_settings(TEZLIK_CHEKLOVLARI={"sinov": {"ip": "1/m"}})
def test_429_javobida_RETRY_AFTER_va_TUSHUNARLI_xabar():
    """⚠️ Qabul mezoni: "chegara oshsa 429 va tushunarli xabar"."""

    @tezlik_cheklovi("sinov")
    def korinish(request):
        from django.http import HttpResponse

        return HttpResponse("ok")

    korinish(sorov())
    javob = korinish(sorov())
    matn = javob.content.decode()

    assert javob.status_code == 429
    assert 0 < int(javob["Retry-After"]) <= 60
    assert "1 marta / daqiqa" in matn
    assert "Juda tez" in matn


@override_settings(TEZLIK_CHEKLOVLARI={"sinov": {"ip": "1/m"}})
def test_HAR_IP_ozining_hisobiga_ega():
    @tezlik_cheklovi("sinov")
    def korinish(request):
        from django.http import HttpResponse

        return HttpResponse("ok")

    assert korinish(sorov(REMOTE_ADDR="1.1.1.1")).status_code == 200
    assert korinish(sorov(REMOTE_ADDR="1.1.1.1")).status_code == 429
    assert korinish(sorov(REMOTE_ADDR="2.2.2.2")).status_code == 200


@override_settings(TEZLIK_CHEKLOVLARI={"sinov": {"ip": "2/m"}})
def test_OYNA_almashsa_hisob_NOLDAN_boshlanadi(soat):
    @tezlik_cheklovi("sinov")
    def korinish(request):
        from django.http import HttpResponse

        return HttpResponse("ok")

    assert korinish(sorov()).status_code == 200
    assert korinish(sorov()).status_code == 200
    assert korinish(sorov()).status_code == 429

    soat["t"] += 61  # keyingi oyna

    assert korinish(sorov()).status_code == 200


@override_settings(TEZLIK_CHEKLOVLARI={"sinov": {"ip": "1/m"}})
@pytest.mark.parametrize("usul", ["get", "head", "options"])
def test_OQISH_sorovlari_SANALMAYDI(usul):
    """⚠️ Aks holda "soatiga 5 ta post" chegarasi formani 6 marta
    OCHGAN odamni bloklardi — va sabab butunlay ko'rinmasdi."""

    @tezlik_cheklovi("sinov")
    def korinish(request):
        from django.http import HttpResponse

        return HttpResponse("ok")

    javoblar = [korinish(sorov(usul)).status_code for _ in range(5)]

    assert javoblar == [200] * 5


@override_settings(TEZLIK_CHEKLOVLARI={"sinov": {"ip": "1/m"}})
def test_KESH_ISHLAMASA_sorov_OTADI(monkeypatch, caplog):
    """⚠️ Fail open — ATAYLAB.

    Redis o'chsa cheklov ishlamaydi, lekin sayt ishlashda davom etadi.
    Teskarisi (fail closed) Redis nosozligini butun saytni "yozib
    bo'lmaydigan" holatga aylantirardi — tezlik cheklovi esa yumshatish
    chorasi, xavfsizlik chegarasi emas.
    """

    def buzuq(*a, **kw):
        raise ConnectionError("Redis yiqildi")

    monkeypatch.setattr(cache, "add", buzuq)

    @tezlik_cheklovi("sinov")
    def korinish(request):
        from django.http import HttpResponse

        return HttpResponse("ok")

    javoblar = [korinish(sorov()).status_code for _ in range(3)]

    assert javoblar == [200, 200, 200]
    assert "keshi ishlamadi" in caplog.text


# ===========================================================================
# Foydalanuvchi va IP — ikki doira birdan
# ===========================================================================
@override_settings(
    TEZLIK_CHEKLOVLARI={"sinov": {"foydalanuvchi": "1/m", "ip": "100/m"}}
)
def test_FOYDALANUVCHI_chegarasi_alohida(user, other_user):
    @tezlik_cheklovi("sinov")
    def korinish(request):
        from django.http import HttpResponse

        return HttpResponse("ok")

    def s(u):
        r = sorov()
        r.user = u
        return korinish(r).status_code

    assert s(user) == 200
    assert s(user) == 429
    assert s(other_user) == 200, "boshqa foydalanuvchi ta'sirlanmasligi kerak"


@override_settings(TEZLIK_CHEKLOVLARI={"sinov": {"foydalanuvchi": "5/m", "ip": "2/m"}})
def test_BITTA_IP_ortidagi_ikki_foydalanuvchi_IP_hisobini_BOLISHADI(
    user, other_user, user_factory
):
    """⚠️ CGNAT holati — IP chegarasi shu sababdan BO'SH.

    O'zbekistonda mobil operatorlar bitta tashqi IP ortida minglab
    abonentni saqlaydi. Tor IP chegarasi butun mahallani bloklardi va
    sabab tashqaridan umuman ko'rinmasdi ("menda ishlamayapti,
    do'stimda ishlayapti").
    """

    @tezlik_cheklovi("sinov")
    def korinish(request):
        from django.http import HttpResponse

        return HttpResponse("ok")

    def s(u):
        r = sorov(REMOTE_ADDR="95.85.1.9")
        r.user = u
        return korinish(r).status_code

    assert s(user) == 200
    assert s(other_user) == 200
    # Uchinchi odam IP chegarasiga uriladi — o'z hisobida hech nima
    # yozmagan bo'lsa ham.
    assert s(user_factory()) == 429


@override_settings(TEZLIK_CHEKLOVLARI={"sinov": {"foydalanuvchi": "1/m"}})
def test_ANONIM_foydalanuvchida_FOYDALANUVCHI_chegarasi_QOLLANMAYDI():
    """Kirmagan odamda `pk` yo'q — hammasi bitta kalitga tushib,
    butun anonim trafikni birdan bloklardi."""

    @tezlik_cheklovi("sinov")
    def korinish(request):
        from django.http import HttpResponse

        return HttpResponse("ok")

    javoblar = [korinish(sorov()).status_code for _ in range(5)]

    assert javoblar == [200] * 5


# ===========================================================================
# Ko'rinishlarga ulanishi (qabul mezonlari)
# ===========================================================================
@override_settings(TEZLIK_CHEKLOVLARI={"ovoz": {"foydalanuvchi": "2/m", "ip": "50/m"}})
def test_OVOZ_endpointi_cheklanadi(auth_client):
    """⚠️ Task tavsifi: ovoz — eng arzon va eng ko'p suiiste'mol
    qilinadigan nuqta."""
    muammo = ComplaintFactory()
    yol = reverse("dard_ovoz", args=[muammo.pk])

    kodlar = [auth_client.post(yol, {"qiymat": "1"}).status_code for _ in range(3)]

    assert kodlar[:2] != [429, 429]
    assert kodlar[-1] == 429


@override_settings(TEZLIK_CHEKLOVLARI={"ovoz": {"foydalanuvchi": "1/m"}})
def test_HTMX_429_MATN_oladi_HTML_sahifa_EMAS(auth_client):
    """⚠️ HTMX 2xx bo'lmagan javobni DOM'ga qo'ymaydi — shuning uchun
    javob qisqa matn va uni `app.js` toast qilib ko'rsatadi.
    To'liq HTML sahifa yuborilsa u foydasiz yuk bo'lardi."""
    muammo = ComplaintFactory()
    yol = reverse("dard_ovoz", args=[muammo.pk])
    sarlavhalar = {"hx-request": "true"}

    auth_client.post(yol, {"qiymat": "1"}, headers=sarlavhalar)
    javob = auth_client.post(yol, {"qiymat": "-1"}, headers=sarlavhalar)

    assert javob.status_code == 429
    assert javob["Content-Type"].startswith("text/plain")
    assert "<html" not in javob.content.decode()
    assert "Juda tez" in javob.content.decode()


@override_settings(TEZLIK_CHEKLOVLARI={"ovoz": {"foydalanuvchi": "1/m"}})
def test_HTMXSIZ_429_TUSHUNARLI_sahifa_beradi(auth_client):
    """JavaScript'siz brauzer to'liq sahifa ko'radi."""
    muammo = ComplaintFactory()
    yol = reverse("dard_ovoz", args=[muammo.pk])

    auth_client.post(yol, {"qiymat": "1"})
    javob = auth_client.post(yol, {"qiymat": "-1"})
    matn = javob.content.decode()

    assert javob.status_code == 429
    assert "Biroz kuting" in matn
    assert "Lentaga qaytish" in matn
    # ⚠️ Ohang ayblovchi bo'lmasin: chegaraga urilganlarning aksariyati
    #    hujumchi emas.
    assert "bloklandingiz" not in matn.lower()


@override_settings(
    TEZLIK_CHEKLOVLARI={"dard_yozish": {"foydalanuvchi": "1/h", "ip": "5/h"}}
)
def test_FORMANI_OCHISH_chegarani_yemaydi(auth_client):
    """⭐ Eng oson qilinadigan xato: GET ham sanalsa, "soatiga 1 ta
    post" chegarasi formani ikkinchi marta OCHGAN odamni bloklardi."""
    yol = reverse("complaint_create")

    kodlar = [auth_client.get(yol).status_code for _ in range(4)]

    assert kodlar == [200] * 4


@override_settings(TEZLIK_CHEKLOVLARI={"shikoyat": {"foydalanuvchi": "1/h"}})
def test_SHIKOYAT_endpointi_cheklanadi(auth_client):
    muammo = ComplaintFactory()
    yol = reverse("dard_shikoyat", args=[muammo.pk])

    assert auth_client.get(yol).status_code == 200  # forma ochiladi
    auth_client.post(yol, {"reason": "spam"})
    javob = auth_client.post(yol, {"reason": "spam"})

    assert javob.status_code == 429


def test_STAFF_uchun_ISTISNO_YOQ(staff):
    """⚠️ "Moderatorga cheklov qo'llanmaydi" degan yashirin qoida hisob
    buzib kirilganda aynan eng kuchli hisobni cheklovsiz qoldirardi."""
    c = Client()
    c.force_login(staff)
    muammo = ComplaintFactory()
    yol = reverse("dard_ovoz", args=[muammo.pk])

    with override_settings(TEZLIK_CHEKLOVLARI={"ovoz": {"foydalanuvchi": "1/m"}}):
        c.post(yol, {"qiymat": "1"})
        javob = c.post(yol, {"qiymat": "-1"})

    assert javob.status_code == 429


# ===========================================================================
# Qabul mezoni: "cheklovlar sozlamada, kodda emas"
# ===========================================================================
def test_chegaralar_SOZLAMADA_kodda_EMAS():
    """⭐ Qabul mezoni to'g'ridan-to'g'ri tekshiriladi.

    Sozlamani o'zgartirish xulqni o'zgartiradi — ya'ni chegarani
    sozlash uchun kod tegish shart emas. Yuqoridagi barcha testlar ham
    aynan shu mexanizmga (`@override_settings`) tayanadi.
    """
    from django.conf import settings

    # Ishlab chiqarish qiymatlari o'qiladi va to'g'ri shaklda.
    for nom in settings.TEZLIK_CHEKLOVLARI:
        cheklovlar = cheklovlarni_olish(nom)
        assert cheklovlar, nom
        for cheklov in cheklovlar.values():
            assert cheklov.soni > 0
            assert cheklov.oyna > 0

    # Task tavsifidagi to'rt nuqta qamrab olingan.
    assert {"dard_yozish", "yechim_yozish", "ovoz", "shikoyat"} <= set(
        settings.TEZLIK_CHEKLOVLARI
    )


def test_IP_chegarasi_foydalanuvchi_chegarasidan_BOSHROQ():
    """⚠️ CGNAT: IP chegarasi tor bo'lsa butun mahalla bloklanadi.

    Bu test qiymatlarni emas, MUNOSABATNI qotiradi — kelajakda chegara
    o'zgartirilsa ham qoida saqlanib qolsin.
    """
    from django.conf import settings

    for nom, doiralar in settings.TEZLIK_CHEKLOVLARI.items():
        if "ip" not in doiralar or "foydalanuvchi" not in doiralar:
            continue
        ip = chegarani_oqish(doiralar["ip"])
        fd = chegarani_oqish(doiralar["foydalanuvchi"])
        assert ip.oyna == fd.oyna, f"{nom}: oynalar bir xil bo'lsin"
        assert ip.soni > fd.soni, (
            f"{nom}: IP chegarasi ({ip.soni}) foydalanuvchi chegarasidan "
            f"({fd.soni}) BO'SHROQ bo'lishi kerak — CGNAT sababi"
        )
