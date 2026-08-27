"""HTMX ovoz berish endpoint'i (D1-T8)."""

from __future__ import annotations

import pytest
from django.test import Client
from django.urls import reverse

from apps.common.models import ModerationStatus
from apps.complaints.factories import ComplaintFactory
from apps.complaints.models import Complaint, ComplaintVote
from apps.solutions.factories import SolutionFactory

pytestmark = pytest.mark.django_db

HTMX = {"HTTP_HX_REQUEST": "true"}


def ovoz_url(muammo) -> str:
    return reverse("dard_ovoz", args=[muammo.pk])


# ===========================================================================
# Ruxsat
# ===========================================================================
def test_kirmagan_foydalanuvchida_ovoz_OZGARMAYDI(client):
    """Qabul mezoni: "kirmagan foydalanuvchida ovoz o'zgarmaydi".

    ⚠️ Bu server tomonidagi ikkinchi qatlam. Birinchi qatlam — brauzerda
       login taklifi (app.js). Ammo brauzerni chetlab o'tib so'rov
       yuborish oson, shuning uchun haqiqiy himoya faqat shu yerda.
    """
    muammo = ComplaintFactory()

    javob = client.post(ovoz_url(muammo), {"qiymat": "1"}, **HTMX)

    assert javob.status_code == 401
    muammo.refresh_from_db()
    assert muammo.score_cached == 0
    assert ComplaintVote.objects.count() == 0


def test_kirmagan_foydalanuvchi_JS_SIZ_login_sahifasiga_ketadi(client):
    """⚠️ `@login_required` ISHLATILMAGANINING sababi shu yerda ko'rinadi:
    u HTMX so'roviga ham 302 qaytarardi va HTMX yo'naltirishni kuzatib,
    BUTUN LOGIN SAHIFASINI ovoz blokining o'rniga qo'yardi.
    """
    muammo = ComplaintFactory()

    javob = client.post(ovoz_url(muammo), {"qiymat": "1"})  # HX-Request YO'Q

    assert javob.status_code == 302
    assert javob["Location"].startswith(reverse("login"))


def test_bloklangan_foydalanuvchi_ovoz_BERA_OLMAYDI(banned_user):
    """D0-T2: `is_banned` — o'qiy oladi, yoza olmaydi."""
    c = Client()
    c.force_login(banned_user)
    muammo = ComplaintFactory()

    javob = c.post(ovoz_url(muammo), {"qiymat": "1"}, **HTMX)

    assert javob.status_code == 403
    assert ComplaintVote.objects.count() == 0


def test_GET_bilan_ovoz_berib_BOLMAYDI(auth_client):
    """⚠️ Agar GET ishlaganda: `<img src="/ovoz/dard/1/">` qo'yilgan
    istalgan sahifa ziyoratchilarning ovozini o'g'irlardi."""
    muammo = ComplaintFactory()
    assert auth_client.get(ovoz_url(muammo)).status_code == 405


def test_CSRF_himoyalangan(user):
    """Qabul mezoni: CSRF himoyalangan."""
    c = Client(enforce_csrf_checks=True)
    c.force_login(user)
    muammo = ComplaintFactory()

    javob = c.post(ovoz_url(muammo), {"qiymat": "1"}, **HTMX)

    assert javob.status_code == 403
    assert ComplaintVote.objects.count() == 0


# ===========================================================================
# Ovoz berish
# ===========================================================================
def test_ovoz_hisoblanadi(auth_client):
    muammo = ComplaintFactory()

    javob = auth_client.post(ovoz_url(muammo), {"qiymat": "1"}, **HTMX)

    assert javob.status_code == 200
    muammo.refresh_from_db()
    assert muammo.score_cached == 1


def test_takroriy_bosish_ovozni_BEKOR_qiladi(auth_client):
    muammo = ComplaintFactory()
    auth_client.post(ovoz_url(muammo), {"qiymat": "1"}, **HTMX)
    auth_client.post(ovoz_url(muammo), {"qiymat": "1"}, **HTMX)

    muammo.refresh_from_db()
    assert muammo.score_cached == 0
    assert ComplaintVote.objects.count() == 0


def test_javob_FAQAT_KARTANI_qaytaradi(auth_client):
    """Qabul mezoni: javob butun sahifani emas, kartani qaytaradi.

    ⚠️ Karta tanlangani ataylab: ovoz bloki kartada IKKI marta turadi
       (desktop ustuni + mobil qator, CSS bilan almashadi). Faqat
       bittasini almashtirsak, ikkinchisi eski sanoq bilan qolardi va
       telefonni burganda "ovozim yo'qoldi" holati chiqardi.
    """
    muammo = ComplaintFactory()
    javob = auth_client.post(ovoz_url(muammo), {"qiymat": "1"}, **HTMX)
    matn = javob.content.decode()

    assert javob.templates[0].name == "components/_complaint_card.html"
    assert "<!doctype html>" not in matn.lower()
    assert "<article" in matn
    assert muammo.title in matn


def test_javobda_ovoz_holati_BOSILGAN_deb_keladi(auth_client):
    """Maketdagi `aria-pressed` — ekran o'quvchi holatni shundan biladi."""
    muammo = ComplaintFactory()
    matn = auth_client.post(ovoz_url(muammo), {"qiymat": "1"}, **HTMX).content.decode()

    assert 'data-vote="up"' in matn
    assert 'aria-pressed="true"' in matn


def test_JS_siz_POST_qayta_yonaltiradi(auth_client):
    """POST/Redirect/GET — "orqaga" tugmasi qayta yuborishni so'ramasin."""
    muammo = ComplaintFactory()

    javob = auth_client.post(ovoz_url(muammo), {"qiymat": "1"})  # HX-Request yo'q

    assert javob.status_code == 302
    muammo.refresh_from_db()
    assert muammo.score_cached == 1


def test_ochiq_yonaltirishga_yol_YOQ(auth_client):
    """⚠️ `HTTP_REFERER` foydalanuvchi boshqaradigan sarlavha. Tekshiruvsiz
    ishlatilsa hujumchi qurbonni o'z saytiga olib chiqib, u yerda soxta
    login ko'rsatishi mumkin edi."""
    muammo = ComplaintFactory()

    javob = auth_client.post(
        ovoz_url(muammo), {"qiymat": "1"}, HTTP_REFERER="https://yovuz.example/login"
    )

    assert javob.status_code == 302
    assert javob["Location"] == muammo.get_absolute_url()


# ===========================================================================
# Noto'g'ri kirish
# ===========================================================================
@pytest.mark.parametrize("xom", ["0", "5", "-2", "up", "", "1.5"])
def test_notogri_qiymat_400_beradi(auth_client, xom):
    muammo = ComplaintFactory()
    javob = auth_client.post(ovoz_url(muammo), {"qiymat": xom}, **HTMX)

    assert javob.status_code == 400
    assert ComplaintVote.objects.count() == 0


def test_yashirilgan_postga_ovoz_BERIB_BOLMAYDI(auth_client):
    """⚠️ Usiz: moderator yashirgan post lentadan yo'qolardi, lekin
    havolasi bor odam unga ovoz berishda davom etardi."""
    muammo = ComplaintFactory(moderation_status=ModerationStatus.HIDDEN)

    javob = auth_client.post(ovoz_url(muammo), {"qiymat": "1"}, **HTMX)

    assert javob.status_code == 404
    assert ComplaintVote.objects.count() == 0


def test_ochirilgan_postga_ovoz_BERIB_BOLMAYDI(auth_client):
    muammo = ComplaintFactory()
    muammo.delete()

    javob = auth_client.post(ovoz_url(muammo), {"qiymat": "1"}, **HTMX)
    assert javob.status_code == 404


def test_mavjud_bolmagan_post(auth_client):
    assert (
        auth_client.post(
            reverse("dard_ovoz", args=[999999]), {"qiymat": "1"}, **HTMX
        ).status_code
        == 404
    )


# ===========================================================================
# Yechim ovozi
# ===========================================================================
def test_yechimga_ovoz_berish_ISHLAYDI(auth_client):
    yechim = SolutionFactory()

    javob = auth_client.post(
        reverse("yechim_ovoz", args=[yechim.pk]), {"qiymat": "1"}, **HTMX
    )

    assert javob.status_code == 200
    assert javob.templates[0].name == "components/_vote.html"
    yechim.refresh_from_db()
    assert yechim.score_cached == 1


def test_yechim_javobi_SORALGAN_layoutni_qaytaradi(auth_client):
    """⚠️ Usiz mobil variant desktop varianti bilan almashib qolardi:
    HTMX qaytgan HTML'ni o'z joyiga qo'yadi, lekin klasslari boshqa
    breakpoint uchun bo'lardi va blok KO'RINMAY qolardi."""
    yechim = SolutionFactory()

    matn = auth_client.post(
        reverse("yechim_ovoz", args=[yechim.pk]),
        {"qiymat": "1", "layout": "row"},
        **HTMX,
    ).content.decode()

    assert "sm:hidden" in matn  # mobil variant


# ===========================================================================
# Lenta va ovoz birga
# ===========================================================================
def test_ovozdan_keyin_lentada_holat_KORINADI(auth_client):
    muammo = ComplaintFactory()
    auth_client.post(ovoz_url(muammo), {"qiymat": "1"}, **HTMX)

    javob = auth_client.get("/")
    kelgan = javob.context["complaints"][0]

    assert kelgan.user_vote == 1
    assert 'aria-pressed="true"' in javob.content.decode()


def test_kirmagan_foydalanuvchida_hx_post_QOYILMAYDI(client):
    """Mehmonda HTMX so'rovi umuman ketmasin — app.js login taklifini
    ko'rsatadi (hal qilingan C varianti)."""
    ComplaintFactory()
    matn = client.get("/").content.decode()

    assert "hx-post" not in matn
    assert 'data-guest="true"' in matn


def test_kirgan_foydalanuvchida_hx_post_BOR(auth_client):
    muammo = ComplaintFactory()
    matn = auth_client.get("/").content.decode()

    assert f'hx-post="{ovoz_url(muammo)}"' in matn
    assert 'data-guest="false"' in matn


def test_ovoz_formasi_JS_SIZ_ham_yuboriladi(auth_client):
    """⚠️ Forma bo'lgani uchun HTMX yuklanmasa ham ovoz berish ishlaydi.

    Bu progressiv yaxshilanishning butun ma'nosi: JS qatlami yo'qolsa
    funksiya SEKINLASHADI, YO'QOLMAYDI.
    """
    ComplaintFactory()
    matn = auth_client.get("/").content.decode()

    assert "<form" in matn
    assert 'name="qiymat"' in matn
    assert 'value="1"' in matn
    assert 'value="-1"' in matn
    assert "csrfmiddlewaretoken" in matn


def test_ovoz_bloki_score_cached_ni_korsatadi(auth_client, user_factory):
    """⚠️ `upvotes_cached` EMAS: u faqat ijobiy ovozlarni sanaydi va
    "−3" holatini ko'rsata olmaydi."""
    from apps.common.models import VoteValue
    from apps.common.voting import cast_vote

    muammo = ComplaintFactory()
    for _ in range(3):
        cast_vote(
            target=muammo,
            vote_model=ComplaintVote,
            target_field="complaint",
            user=user_factory(),
            value=VoteValue.DOWN,
        )

    matn = auth_client.get("/").content.decode()
    assert Complaint.objects.get(pk=muammo.pk).score_cached == -3
    assert ">\n    -3\n  </span>" in matn or "-3" in matn
