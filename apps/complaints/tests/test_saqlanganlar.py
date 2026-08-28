"""Saqlanganlar / xatcho'p (D1-T13)."""

from __future__ import annotations

import pytest
from django.db import IntegrityError, transaction
from django.urls import reverse

from apps.common.models import ModerationStatus
from apps.complaints.factories import ComplaintFactory
from apps.complaints.models import SavedComplaint
from apps.complaints.selectors import saqlangan_idlari, saqlanganlar_queryset

pytestmark = pytest.mark.django_db
HTMX = {"HTTP_HX_REQUEST": "true"}


def saqlash_url(muammo) -> str:
    return reverse("dard_saqlash", args=[muammo.pk])


# ===========================================================================
# Model
# ===========================================================================
def test_IKKI_MARTA_saqlab_bolmaydi(user):
    """Qabul mezoni: `unique_together(user, target)`.

    ⚠️ Kodda `get_or_create` yetarli emas: ikki bir vaqtli so'rov
       ikkalasi ham "yo'q ekan" deb ko'radi. Faqat DB cheklovi yopadi.
    """
    muammo = ComplaintFactory()
    SavedComplaint.objects.create(user=user, complaint=muammo)

    with pytest.raises(IntegrityError), transaction.atomic():
        SavedComplaint.objects.create(user=user, complaint=muammo)


def test_ikki_xil_foydalanuvchi_bir_postni_saqlay_oladi(user, other_user):
    muammo = ComplaintFactory()
    SavedComplaint.objects.create(user=user, complaint=muammo)
    SavedComplaint.objects.create(user=other_user, complaint=muammo)

    assert SavedComplaint.objects.filter(complaint=muammo).count() == 2


def test_post_ochirilsa_xatchop_ham_KETADI(user):
    """`CASCADE` — yetim xatcho'p qolmasin."""
    muammo = ComplaintFactory()
    SavedComplaint.objects.create(user=user, complaint=muammo)

    muammo.hard_delete()

    assert SavedComplaint.objects.count() == 0


# ===========================================================================
# Saqlash / olib tashlash
# ===========================================================================
def test_saqlash_va_OLIB_TASHLASH_bitta_tugma(auth_client, user):
    muammo = ComplaintFactory()

    auth_client.post(saqlash_url(muammo), **HTMX)
    assert SavedComplaint.objects.filter(user=user, complaint=muammo).exists()

    auth_client.post(saqlash_url(muammo), **HTMX)
    assert not SavedComplaint.objects.filter(user=user, complaint=muammo).exists()


def test_javob_FAQAT_TUGMANI_qaytaradi(auth_client):
    muammo = ComplaintFactory()
    javob = auth_client.post(saqlash_url(muammo), **HTMX)

    assert javob.status_code == 200
    assert javob.templates[0].name == "components/_save_button.html"
    assert "<!doctype html>" not in javob.content.decode().lower()


def test_saqlangandan_keyin_tugma_HOLATI_ozgaradi(auth_client):
    muammo = ComplaintFactory()
    matn = auth_client.post(saqlash_url(muammo), **HTMX).content.decode()

    assert 'aria-pressed="true"' in matn
    assert "Saqlanganlardan olib tashlash" in matn


def test_kirmagan_foydalanuvchi_saqlay_OLMAYDI(client):
    muammo = ComplaintFactory()
    javob = client.post(saqlash_url(muammo), **HTMX)

    assert javob.status_code == 401
    assert SavedComplaint.objects.count() == 0


def test_GET_bilan_saqlab_bolmaydi(auth_client):
    """⚠️ GET ishlaganda `<img src="/saqlash/dard/1/">` qo'yilgan sahifa
    ziyoratchilarning ro'yxatiga post qo'shib qo'yardi."""
    muammo = ComplaintFactory()
    assert auth_client.get(saqlash_url(muammo)).status_code == 405


def test_yashirilgan_postni_saqlab_bolmaydi(auth_client):
    muammo = ComplaintFactory(moderation_status=ModerationStatus.HIDDEN)
    assert auth_client.post(saqlash_url(muammo), **HTMX).status_code == 404


def test_JS_siz_POST_qayta_yonaltiradi(auth_client, user):
    muammo = ComplaintFactory()
    javob = auth_client.post(saqlash_url(muammo))  # HX-Request yo'q

    assert javob.status_code == 302
    assert SavedComplaint.objects.filter(user=user).count() == 1


def test_takroriy_sorov_XATO_bermaydi(auth_client, user):
    """⚠️ HTMX qayta urinishi yoki ikki marta bosish `IntegrityError`
    bermasin — `get_or_create` shuning uchun."""
    muammo = ComplaintFactory()
    SavedComplaint.objects.create(user=user, complaint=muammo)

    # Endi "olib tashlash" bo'ladi, keyin yana qo'shish
    assert auth_client.post(saqlash_url(muammo), **HTMX).status_code == 200
    assert auth_client.post(saqlash_url(muammo), **HTMX).status_code == 200


# ===========================================================================
# Ro'yxat sahifasi
# ===========================================================================
def test_saqlanganlar_sahifasi_kirish_talab_qiladi(client):
    javob = client.get(reverse("saqlanganlar"))
    assert javob.status_code == 302
    assert reverse("login") in javob["Location"]


def test_saqlanganlar_sahifasi_FAQAT_OZINIKINI_korsatadi(auth_client, user, other_user):
    """⚠️ Xatcho'p — SHAXSIY ro'yxat. Boshqa odamnikini ko'rsatish
    maxfiylik buzilishi bo'lardi."""
    meniki = ComplaintFactory(title="Men saqladim")
    boshqaniki = ComplaintFactory(title="Boshqa odam saqladi")
    SavedComplaint.objects.create(user=user, complaint=meniki)
    SavedComplaint.objects.create(user=other_user, complaint=boshqaniki)

    javob = auth_client.get(reverse("saqlanganlar"))

    assert [m.pk for m in javob.context["complaints"]] == [meniki.pk]


def test_YASHIRILGAN_post_royxatda_KORINMAYDI(auth_client, user):
    """⚠️ Moderator yashirgan post lentada yo'q — saqlanganlarda ham
    bo'lmasligi kerak (D2-T3)."""
    korinadigan = ComplaintFactory()
    yashirilgan = ComplaintFactory(moderation_status=ModerationStatus.HIDDEN)
    SavedComplaint.objects.create(user=user, complaint=korinadigan)
    SavedComplaint.objects.create(user=user, complaint=yashirilgan)

    javob = auth_client.get(reverse("saqlanganlar"))
    assert [m.pk for m in javob.context["complaints"]] == [korinadigan.pk]


def test_royxat_ENG_YANGI_saqlangani_birinchi(auth_client, user):
    birinchi = ComplaintFactory(title="Avval saqlangan")
    ikkinchi = ComplaintFactory(title="Keyin saqlangan")
    SavedComplaint.objects.create(user=user, complaint=birinchi)
    SavedComplaint.objects.create(user=user, complaint=ikkinchi)

    natija = list(saqlanganlar_queryset(user=user))
    assert [m.pk for m in natija] == [ikkinchi.pk, birinchi.pk]


def test_bosh_royxatda_KEYINGI_QADAM_korsatiladi(auth_client):
    """⚠️ Bo'sh ekran — xato emas, LEKIN foydalanuvchi uni xato deb
    o'ylaydi. Har doim: nima yo'qligi + keyingi qadam."""
    matn = auth_client.get(reverse("saqlanganlar")).content.decode()

    assert "Hozircha bo'sh" in matn
    assert "xatcho'p belgisini bosing" in matn


# ===========================================================================
# Lentadagi holat
# ===========================================================================
def test_saqlangan_idlari_BITTA_sorovda(user, django_assert_num_queries):
    """⚠️ Har karta uchun alohida so'rash 20 ta kartada 20 ta so'rov."""
    muammolar = [ComplaintFactory() for _ in range(5)]
    SavedComplaint.objects.create(user=user, complaint=muammolar[0])
    SavedComplaint.objects.create(user=user, complaint=muammolar[3])

    with django_assert_num_queries(1):
        natija = saqlangan_idlari(user=user, targets=muammolar)

    assert natija == {muammolar[0].pk, muammolar[3].pk}


def test_kirmagan_foydalanuvchida_SOROV_KETMAYDI(django_assert_num_queries):
    from django.contrib.auth.models import AnonymousUser

    muammolar = [ComplaintFactory()]
    with django_assert_num_queries(0):
        assert saqlangan_idlari(user=AnonymousUser(), targets=muammolar) == set()


def test_lentada_saqlangan_holati_KORINADI(auth_client, user):
    muammo = ComplaintFactory()
    SavedComplaint.objects.create(user=user, complaint=muammo)

    javob = auth_client.get("/")
    assert javob.context["complaints"][0].saqlangan is True
    assert "Saqlanganlardan olib tashlash" in javob.content.decode()


def test_mehmonda_hx_post_QOYILMAYDI(client):
    """Mehmonda app.js login taklifini ko'rsatadi (ovoz berish bilan bir xil)."""
    ComplaintFactory()
    matn = client.get("/").content.decode()

    assert "saqlash/dard/" in matn  # forma bor (JS'siz ishlaydi)
    assert "hx-post" not in matn  # lekin HTMX yo'q


def test_SOXTA_toast_qolmagan():
    """⚠️ GUARD: maketda `data-toast="Saqlanganlarga qo'shildi"` tugmasi
    bor edi — u serverga hech nima yubormasdan "saqlandi" deb yozardi.

    Bunday soxta muvaffaqiyat xabari eng yomon xato turi: foydalanuvchi
    ishonadi, keyin ro'yxatni ochib hech nima topmaydi.
    """
    import re
    from pathlib import Path

    from django.conf import settings

    # ⚠️ `{% comment %}` bloklari OLIB TASHLANADI: bu qoidani TUSHUNTIRADIGAN
    #    izohlarning o'zi qidirilayotgan satrni o'z ichiga oladi. Birinchi
    #    versiyada test aynan shu sababdan yiqilgan edi — yolg'on
    #    ogohlantirish. (`test_anonimlik.py` dagi guard ham shu naqshda.)
    IZOH = re.compile(r"{%\s*comment\s*%}.*?{%\s*endcomment\s*%}", re.DOTALL)

    for yol in (Path(settings.BASE_DIR) / "templates").rglob("*.html"):
        matn = IZOH.sub("", yol.read_text(encoding="utf-8"))
        assert 'data-toast="Saqlanganlarga qo\'shildi"' not in matn, (
            f"{yol.name} da maketning soxta saqlash tugmasi qolgan"
        )
