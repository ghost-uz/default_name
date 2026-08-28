"""Muammo yaratish va tahrirlash formasi (D1-T9)."""

from __future__ import annotations

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.complaints.factories import CategoryFactory, ComplaintFactory
from apps.complaints.forms import SARLAVHA_MIN, TAVSIF_MIN, ComplaintForm
from apps.complaints.models import TAHRIRLASH_OYNASI, Complaint, Generation
from apps.solutions.factories import SolutionFactory

pytestmark = pytest.mark.django_db

YOZISH = "/yozish/"


def togri_malumot(kategoriya, **ozgarish) -> dict:
    malumot = {
        "title": "Ipoteka olmoqchiman, lekin bank rad etdi",
        "description": (
            "Ikki bankka murojaat qildim va ikkalasi ham rad etdi. "
            "Kredit tarixim toza, daromadim rasmiy. Nima qilish kerak?"
        ),
        "category": kategoriya.pk,
        "generation_tag": Generation.MILLENNIAL,
    }
    malumot.update(ozgarish)
    return malumot


# ===========================================================================
# Server tomonda validatsiya (qabul mezoni)
# ===========================================================================
def test_qisqa_sarlavha_SERVER_tomonda_rad_etiladi():
    """Qabul mezoni: "min uzunlik server tomonda tekshiriladi".

    ⚠️ Maketdagi `data-minlen` faqat brauzerda ishlaydi va uni o'chirish
       uchun DevTools'da bitta atributni olib tashlash yetarli. Mijoz
       tomonidagi tekshiruv — QULAYLIK, himoya emas.
    """
    kategoriya = CategoryFactory()
    form = ComplaintForm(data=togri_malumot(kategoriya, title="Qisqa"))

    assert not form.is_valid()
    assert "title" in form.errors


def test_qisqa_tavsif_rad_etiladi():
    kategoriya = CategoryFactory()
    form = ComplaintForm(data=togri_malumot(kategoriya, description="Juda qisqa."))

    assert not form.is_valid()
    assert "description" in form.errors


def test_FAQAT_BOSH_JOYDAN_iborat_matn_otmaydi():
    """⚠️ `clean_<field>` validatorlardan KEYIN ishlaydi.

    Ya'ni 50 ta bo'sh joy `MinLengthValidator` dan O'TIB KETARDI, keyin
    `strip()` uni bo'sh satrga aylantirardi va bazaga shunday tushardi.
    Bu jim ma'lumot buzilishi — sahifa 302 qaytaradi, post esa bo'sh.
    """
    kategoriya = CategoryFactory()
    form = ComplaintForm(
        data=togri_malumot(
            kategoriya,
            title=" " * (SARLAVHA_MIN + 5),
            description=" " * (TAVSIF_MIN + 5),
        )
    )

    assert not form.is_valid()
    assert "title" in form.errors
    assert "description" in form.errors


def test_faolsiz_kategoriyani_TANLAB_BOLMAYDI():
    """`is_active=False` tanlov ro'yxatidan chiqib ketishi kerak."""
    faolsiz = CategoryFactory(is_active=False)
    form = ComplaintForm(data=togri_malumot(faolsiz))

    assert not form.is_valid()
    assert "category" in form.errors


def test_avlod_oldindan_TANLANMAGAN():
    """⚠️ Maketda "Gen Z" `checked` edi — bu hammani Gen Z deb taxmin
    qilish va ma'lumotni buzish degani."""
    form = ComplaintForm()
    assert form["generation_tag"].value() in (None, "")


def test_avlodsiz_forma_rad_etiladi():
    kategoriya = CategoryFactory()
    malumot = togri_malumot(kategoriya)
    del malumot["generation_tag"]

    form = ComplaintForm(data=malumot)
    assert not form.is_valid()
    assert "generation_tag" in form.errors


# ===========================================================================
# Yaratish oqimi
# ===========================================================================
def test_kirmagan_foydalanuvchi_login_sahifasiga(client):
    javob = client.get(YOZISH)
    assert javob.status_code == 302
    assert reverse("login") in javob["Location"]


def test_bloklangan_foydalanuvchi_YOZA_OLMAYDI(banned_user):
    from django.test import Client

    c = Client()
    c.force_login(banned_user)
    assert c.get(YOZISH).status_code == 403


def test_post_yaratiladi_va_muallif_QOYILADI(auth_client, user):
    kategoriya = CategoryFactory()

    javob = auth_client.post(YOZISH, togri_malumot(kategoriya))

    assert javob.status_code == 302
    muammo = Complaint.objects.get()
    assert muammo.author == user
    assert muammo.slug
    assert javob["Location"] == muammo.get_absolute_url()


def test_xato_bolganda_MATN_YOQOLMAYDI(auth_client):
    """⚠️ Uzun tavsifni qaytadan yozish — odamni ketkazadigan tajriba."""
    kategoriya = CategoryFactory()
    uzun = "Bu juda uzun va batafsil tavsif. " * 5

    javob = auth_client.post(
        YOZISH, togri_malumot(kategoriya, title="Qisqa", description=uzun)
    )

    assert javob.status_code == 200
    assert uzun.strip() in javob.content.decode()


def test_anonim_post_yaratiladi(auth_client):
    kategoriya = CategoryFactory()
    auth_client.post(YOZISH, togri_malumot(kategoriya, is_anonymous="on"))

    muammo = Complaint.objects.get()
    assert muammo.is_anonymous is True
    assert muammo.public_author is None


# ===========================================================================
# Tahrirlash oynasi (qabul mezoni)
# ===========================================================================
def test_muallif_30_daqiqa_ICHIDA_tahrirlay_oladi(user):
    muammo = ComplaintFactory(author=user)
    assert muammo.tahrirlay_oladimi(user) is True


def test_30_daqiqadan_KEYIN_tahrirlab_bolmaydi(user):
    """Qabul mezoni: "tahrirlash oynasi cheklangan (masalan 30 daqiqa)"."""
    muammo = ComplaintFactory(
        author=user,
        created_at=timezone.now() - TAHRIRLASH_OYNASI - timezone.timedelta(seconds=1),
    )
    assert muammo.tahrirlay_oladimi(user) is False


def test_YECHIM_KELGANDAN_KEYIN_tahrirlab_bolmaydi(user):
    """⚠️ Vaqt chegarasidan MUSTAQIL va undan muhimroq shart.

    Aks holda: zararsiz savol yoziladi, javoblar yig'iladi, keyin savol
    matni almashtiriladi — va o'nlab odamning javobi butunlay boshqa
    savolga "javob berayotgandek" ko'rinadi. Ularning nomidan
    aytilmagan gap aytilgan bo'lib qoladi.
    """
    muammo = ComplaintFactory(author=user)
    SolutionFactory(complaint=muammo)
    muammo.refresh_from_db()
    muammo.solutions_count = 1  # `yechim_yozish()` shuni qiladi

    assert muammo.tahrirlay_oladimi(user) is False


def test_begona_odam_tahrirlay_OLMAYDI(user, other_user):
    muammo = ComplaintFactory(author=user)
    assert muammo.tahrirlay_oladimi(other_user) is False


def test_mehmon_tahrirlay_OLMAYDI(user):
    from django.contrib.auth.models import AnonymousUser

    muammo = ComplaintFactory(author=user)
    assert muammo.tahrirlay_oladimi(AnonymousUser()) is False


def test_tahrirlash_sahifasi_ochiladi(auth_client, user):
    muammo = ComplaintFactory(author=user)
    javob = auth_client.get(reverse("complaint_edit", args=[muammo.slug]))

    assert javob.status_code == 200
    assert muammo.title in javob.content.decode()


def test_oyna_yopilganda_403(auth_client, user):
    """403, 404 EMAS: post bor va foydalanuvchi uni ko'ra oladi —
    faqat tahrirlash oynasi yopilgan."""
    muammo = ComplaintFactory(
        author=user, created_at=timezone.now() - TAHRIRLASH_OYNASI * 2
    )
    javob = auth_client.get(reverse("complaint_edit", args=[muammo.slug]))
    assert javob.status_code == 403


def test_tahrirlash_saqlanadi(auth_client, user):
    muammo = ComplaintFactory(author=user)
    kategoriya = muammo.category

    auth_client.post(
        reverse("complaint_edit", args=[muammo.slug]),
        togri_malumot(kategoriya, title="Butunlay yangi sarlavha bo'ldi"),
    )

    muammo.refresh_from_db()
    assert muammo.title == "Butunlay yangi sarlavha bo'ldi"


def test_ANONIMLIKNI_tahrirlashda_ozgartirib_bolmaydi(auth_client, user):
    """⚠️ Post allaqachon ko'rilgan va ulashilgan bo'lishi mumkin.
    "Anonim" dan "ismli" ga o'tish odamning o'zini fosh qilishi bo'lardi
    — va u buni tugmani bosgan lahzada anglamasligi mumkin.
    """
    muammo = ComplaintFactory(author=user, is_anonymous=True)
    kategoriya = muammo.category

    # Formada maydon umuman yo'q
    form = ComplaintForm(instance=muammo, tahrirlash=True)
    assert "is_anonymous" not in form.fields

    # POST bilan majburlashga urinish ham natija bermaydi
    auth_client.post(
        reverse("complaint_edit", args=[muammo.slug]),
        togri_malumot(kategoriya, is_anonymous=""),
    )
    muammo.refresh_from_db()
    assert muammo.is_anonymous is True


def test_tahrirlash_slugni_OZGARTIRMAYDI(auth_client, user):
    """Ulashilgan havolalar va Google indeksi o'lik bo'lib qolmasin."""
    muammo = ComplaintFactory(author=user)
    eski_slug = muammo.slug

    auth_client.post(
        reverse("complaint_edit", args=[muammo.slug]),
        togri_malumot(muammo.category, title="Mutlaqo boshqacha sarlavha"),
    )

    muammo.refresh_from_db()
    assert muammo.slug == eski_slug
