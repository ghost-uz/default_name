"""Profil sahifasi va tablar (D3-T4) + karma tarixi (D3-T1)."""

from __future__ import annotations

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.selectors import TABLAR
from apps.complaints.factories import ComplaintFactory
from apps.complaints.models import SavedComplaint
from apps.gamification.models import KarmaReason
from apps.gamification.services import karma_yoz
from apps.solutions.factories import SolutionFactory

pytestmark = pytest.mark.django_db


def profil_url(user, tab: str = "") -> str:
    yol = reverse("profile", args=[user.username])
    return f"{yol}?tab={tab}" if tab else yol


def matn(client: Client, user, tab: str = "") -> str:
    return client.get(profil_url(user, tab)).content.decode()


# ===========================================================================
# ⭐ QABUL MEZONI: begona profilda anonim postlar YO'Q
# ===========================================================================
def test_QABUL_MEZONI_BEGONA_profilda_anonim_DARD_yoq(anonymous_client, user):
    """⭐ Task tavsifi: "anonim postni ommaviy profilda ko'rsatish —
    anonimlikni buzishning eng oson yo'li"."""
    ComplaintFactory(author=user, is_anonymous=True, title="Yashirin dard")
    ComplaintFactory(author=user, is_anonymous=False, title="Ochiq dard")

    sahifa = matn(anonymous_client, user)

    assert "Ochiq dard" in sahifa
    assert "Yashirin dard" not in sahifa


def test_QABUL_MEZONI_BEGONA_profilda_anonim_YECHIM_yoq(auth_client, user_factory):
    egasi = user_factory()
    SolutionFactory(author=egasi, is_anonymous=True, content="Yashirin javob matni")
    SolutionFactory(author=egasi, is_anonymous=False, content="Ochiq javob matni")

    sahifa = matn(auth_client, egasi, "yechimlar")

    assert "Ochiq javob matni" in sahifa
    assert "Yashirin javob matni" not in sahifa


def test_EGASI_oz_anonim_postlarini_KORADI(auth_client, user):
    """⚠️ Aks holda odam o'z yozganini topa olmasdi va "post yo'qoldi"
    deb o'ylardi. Ular "anonim" nishoni bilan belgilanadi — odam
    boshqalar nimani ko'rishini bilishi kerak."""
    ComplaintFactory(author=user, is_anonymous=True, title="Yashirin dard")

    sahifa = matn(auth_client, user)

    assert "Yashirin dard" in sahifa


# ===========================================================================
# ⭐⭐ Raqamlar ham anonimlikni oshkor qilmaydi
# ===========================================================================
def test_BEGONAGA_sanoqlar_anonimni_HISOBLAMAYDI(anonymous_client, user):
    """⭐⭐ Agar profil "3 dard" desa-yu ro'yxatda 1 tasi ko'rinsa,
    kuzatuvchi 2 ta ANONIM post borligini hisoblab chiqaradi — ya'ni bu
    odam anonim yozishini fosh qiladi.

    Ko'rsatilgan raqam ko'rsatilgan ro'yxatga TENG bo'lishi shart.
    """
    from apps.accounts.selectors import profil_statistikasi

    ComplaintFactory(author=user, is_anonymous=False)
    for _ in range(2):
        ComplaintFactory(author=user, is_anonymous=True)

    stat = profil_statistikasi(profil=user, ozimi=False)

    assert stat.dardlar == 1, "anonimlar sanoqqa kirib ketdi — bu oshkor qiladi"


def test_EGASIGA_sanoqlar_HAMMASINI_hisoblaydi(user):
    from apps.accounts.selectors import profil_statistikasi

    ComplaintFactory(author=user, is_anonymous=False)
    for _ in range(2):
        ComplaintFactory(author=user, is_anonymous=True)

    stat = profil_statistikasi(profil=user, ozimi=True)

    assert stat.dardlar == 3
    assert stat.anonim_dardlar == 2


def test_EGASIGA_anonim_izohi_KORSATILADI(auth_client, user):
    ComplaintFactory(author=user, is_anonymous=True)

    sahifa = matn(auth_client, user)

    assert "anonim" in sahifa
    assert "faqat sizga ko'rinadi" in sahifa


def test_BEGONAGA_anonim_izohi_KORSATILMAYDI(anonymous_client, user):
    ComplaintFactory(author=user, is_anonymous=True)

    sahifa = matn(anonymous_client, user)

    assert "faqat sizga ko'rinadi" not in sahifa


# ===========================================================================
# ⭐ Karma tarixi (D3-T1 qabul mezoni)
# ===========================================================================
def test_QABUL_MEZONI_profilda_KARMA_TARIXI_korinadi(auth_client, user, user_factory):
    """⭐ D3-T1: "profilda karma tarixi ko'rinadi".

    D3-T1 `nega` bo'limi: "nima uchun 1340 ball?" savoliga javob bo'lishi
    kerak — shuning uchun har qatorda sabab, ball va qaysi yechim ekani
    turadi.
    """
    yechim = SolutionFactory(author=user)
    karma_yoz(user=user, reason=KarmaReason.SOLUTION_ACCEPTED, solution=yechim)

    sahifa = matn(auth_client, user, "karma")

    assert "Yechim qabul qilindi" in sahifa
    assert "+15" in sahifa


def test_KARMA_TARIXI_OMMAVIY_EMAS(auth_client, user_factory):
    """⚠️⚠️ `KarmaEvent` yechimga FK bilan bog'langan. Tarixni ommaviy
    ko'rsatish "shu ANONIM yechim shu odamniki" degan xaritani ochiq
    berardi — karma tarixi anonimlikni buzadigan asbobga aylanardi."""
    egasi = user_factory()
    yechim = SolutionFactory(author=egasi, is_anonymous=True)
    karma_yoz(user=egasi, reason=KarmaReason.SOLUTION_ACCEPTED, solution=yechim)

    sahifa = matn(auth_client, egasi, "karma")

    assert "Yechim qabul qilindi" not in sahifa


# ===========================================================================
# Tablar
# ===========================================================================
def test_TABLAR_MANZILDA_ishlaydi(auth_client, user):
    """⚠️ Maketda tablar JavaScript bilan almashardi. Bu yerda ular
    havola: JS'siz ishlaydi, ulashsa bo'ladi va ochilmagan tabning
    so'rovi umuman ketmaydi."""
    ComplaintFactory(author=user, title="Dard sarlavhasi")
    SolutionFactory(author=user, content="Yechim matni bu yerda")

    dardlar = matn(auth_client, user, "dardlar")
    yechimlar = matn(auth_client, user, "yechimlar")

    assert "Dard sarlavhasi" in dardlar
    assert "Yechim matni bu yerda" not in dardlar
    assert "Yechim matni bu yerda" in yechimlar


def test_NOMALUM_tab_birinchisiga_tushadi(auth_client, user):
    ComplaintFactory(author=user, title="Dard sarlavhasi")

    sahifa = matn(auth_client, user, "yoq-bunday-tab")

    assert "Dard sarlavhasi" in sahifa


def test_SHAXSIY_tab_begonaga_XATO_BERMAYDI_jimgina_tushadi(auth_client, user_factory):
    """⚠️ 403 "bu yerda yashiradigan narsa bor" degan signal bo'lardi."""
    egasi = user_factory()
    ComplaintFactory(author=egasi, title="Dard sarlavhasi")

    javob = auth_client.get(profil_url(egasi, "saqlanganlar"))

    assert javob.status_code == 200
    assert "Dard sarlavhasi" in javob.content.decode()


def test_SHAXSIY_tablar_BEGONAGA_KORSATILMAYDI(auth_client, user_factory):
    """⚠️ "Qulflangan" holda ham ko'rsatilmaydi: qulf "bu yerda nimadir
    bor" degan signalning o'zi."""
    egasi = user_factory()

    sahifa = matn(auth_client, egasi)

    assert "Saqlanganlar" not in sahifa
    assert "Karma tarixi" not in sahifa


def test_SHAXSIY_tablar_EGASIGA_korsatiladi(auth_client, user):
    sahifa = matn(auth_client, user)

    assert "Saqlanganlar" in sahifa
    assert "Karma tarixi" in sahifa


def test_SAQLANGANLAR_tabi_ishlaydi(auth_client, user):
    muammo = ComplaintFactory(title="Saqlangan dard")
    SavedComplaint.objects.create(user=user, complaint=muammo)

    sahifa = matn(auth_client, user, "saqlanganlar")

    assert "Saqlangan dard" in sahifa


# ===========================================================================
# Ko'rinish va kirish
# ===========================================================================
def test_YASHIRILGAN_post_profilda_YOQ(anonymous_client, user):
    """⚠️ `visible()` qatlami (D2-T3) — moderator yashirgan post
    profilda ham chiqmasligi kerak."""
    from apps.common.models import ModerationStatus

    muammo = ComplaintFactory(author=user, title="Yashirilgan dard")
    type(muammo).all_objects.filter(pk=muammo.pk).update(
        moderation_status=ModerationStatus.HIDDEN
    )

    assert "Yashirilgan dard" not in matn(anonymous_client, user)


def test_OCHIRILGAN_hisob_profili_404(anonymous_client, user):
    """⚠️ Anonimlashtirilgan hisobning (D2-T8) profili "bo'sh odam"
    bo'lib turishi kerak emas: kontent qoladi, shaxs qolmaydi."""
    from django.utils import timezone

    user.ochirilgan_at = timezone.now()
    user.save(update_fields=["ochirilgan_at"])

    assert anonymous_client.get(profil_url(user)).status_code == 404


def test_MEHMON_profilni_KORA_OLADI(anonymous_client, user):
    """Profil ommaviy sahifa (SEO, D4-T4)."""
    assert anonymous_client.get(profil_url(user)).status_code == 200


def test_profilda_BLOKLASH_tugmasi_bor(auth_client, user_factory):
    """D2-T11: odam profilga kelib qaraydi va aynan o'sha payt qaror
    qabul qiladi."""
    begona = user_factory(username="begonaprofil")

    sahifa = matn(auth_client, begona)

    assert reverse("foydalanuvchini_bloklash", args=[begona.username]) in sahifa


def test_OZ_profilida_bloklash_tugmasi_YOQ(auth_client, user):
    sahifa = matn(auth_client, user)

    assert reverse("foydalanuvchini_bloklash", args=[user.username]) not in sahifa


# ===========================================================================
# N+1
# ===========================================================================
def test_profil_sorov_soni_ELEMENT_soniga_BOGLIQ_EMAS(user, django_assert_num_queries):
    """⚠️ D1-T14 qoidasi: 2 va 10 element AYNAN bir xil so'rov berishi
    kerak."""
    c = Client()
    c.force_login(user)

    for _ in range(2):
        ComplaintFactory(author=user)
    c.get(profil_url(user))  # sessiyani ilitamiz

    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    with CaptureQueriesContext(connection) as kam:
        c.get(profil_url(user))

    for _ in range(8):
        ComplaintFactory(author=user)

    with CaptureQueriesContext(connection) as kop:
        c.get(profil_url(user))

    assert len(kam) == len(kop), (
        f"So'rov soni element soniga bog'liq: {len(kam)} -> {len(kop)}"
    )


def test_TABLAR_royxati_MANZIL_API_si(user):
    """⚠️ Tab nomlari manzilga tushadi — ular interfeys matni emas, API.
    O'zgartirilsa eski havolalar buziladi."""
    assert TABLAR == ("dardlar", "yechimlar", "saqlanganlar", "karma")
