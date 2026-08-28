"""Moderatsiya navbati — staff interfeysi (D2-T2)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.exceptions import PermissionDenied
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.common.models import ModerationStatus
from apps.complaints.factories import ComplaintFactory
from apps.moderation.models import (
    ModerationAction,
    ModerationActionType,
    Report,
    ReportReason,
    ReportStatus,
)
from apps.moderation.selectors import SLA, navbat
from apps.moderation.services import (
    BekorQilibBolmaydi,
    qaror_qabul_qilish,
    qarorni_bekor_qilish,
)
from apps.solutions.factories import SolutionFactory

pytestmark = pytest.mark.django_db

NAVBAT_URL = reverse("moderatsiya_navbat")


def shikoyat(*, target, reporter, sabab=ReportReason.SPAM, yosh=timedelta(0)) -> Report:
    """Yoshi boshqariladigan shikoyat (tartib testlari uchun).

    ⚠️ `created_at` `auto_now_add` — uni `create()` da berib bo'lmaydi,
       shuning uchun keyin `update()` bilan qo'yiladi (`update()` model
       `save()` ini chetlab o'tadi va `auto_now_add` ni qayta yozmaydi).
    """
    from apps.complaints.models import Complaint

    kwargs = (
        {"complaint": target} if isinstance(target, Complaint) else {"solution": target}
    )
    r = Report.objects.create(reporter=reporter, reason=sabab, **kwargs)
    Report.objects.filter(pk=r.pk).update(created_at=timezone.now() - yosh)
    r.refresh_from_db()
    return r


# ===========================================================================
# Ruxsat — navbat mavjudligini ham oshkor qilmaydi
# ===========================================================================
def test_MEHMONGA_404(anonymous_client):
    assert anonymous_client.get(NAVBAT_URL).status_code == 404


def test_ODDIY_foydalanuvchiga_404_403_EMAS(auth_client):
    """⚠️ 403 "bu manzil bor, lekin sizga ruxsat yo'q" degani — ya'ni
    moderatsiya interfeysining manzilini tasdiqlab beradi va qidirish
    uchun boshlang'ich nuqta bo'ladi. 404 hech narsa aytmaydi."""
    javob = auth_client.get(NAVBAT_URL)

    assert javob.status_code == 404
    assert javob.status_code != 403


def test_STAFF_koradi(staff_client):
    assert staff_client.get(NAVBAT_URL).status_code == 200


def test_ODDIY_foydalanuvchi_QAROR_qabul_qila_OLMAYDI(auth_client, user_factory):
    muammo = ComplaintFactory()
    shikoyat(target=muammo, reporter=user_factory())

    javob = auth_client.post(
        reverse("moderatsiya_qaror_muammo", args=[muammo.pk]),
        {"action": ModerationActionType.OLIB_TASHLASH},
    )

    assert javob.status_code == 404
    muammo.refresh_from_db()
    assert muammo.moderation_status == ModerationStatus.VISIBLE


def test_qaror_GET_bilan_qabul_qilinmaydi(staff_client):
    """Holatni o'zgartiradigan amal GET bilan bajarilmasin (CSRF/prefetch)."""
    muammo = ComplaintFactory()
    javob = staff_client.get(reverse("moderatsiya_qaror_muammo", args=[muammo.pk]))
    assert javob.status_code == 405


# ===========================================================================
# Guruhlash — D2-T2 ning asosiy g'oyasi
# ===========================================================================
def test_BITTA_obyektga_kelgan_shikoyatlar_BITTA_holat(user_factory):
    """⚠️ Qabul mezoni: "bitta ekranda qaror qabul qilinadi".

    Admin shikoyatlarni birma-bir ko'rsatadi: 5 ta shikoyat = 5 ta qator
    va moderator bir xil kontentni 5 marta o'qiydi. Qaror esa KONTENT
    haqida, shikoyat haqida emas.
    """
    muammo = ComplaintFactory()
    for _ in range(5):
        shikoyat(target=muammo, reporter=user_factory())

    holatlar = navbat()

    assert len(holatlar) == 1
    assert holatlar[0].soni == 5
    assert holatlar[0].target == muammo


def test_har_xil_obyekt_HAR_XIL_holat(user_factory):
    muammo = ComplaintFactory()
    yechim = SolutionFactory()
    shikoyat(target=muammo, reporter=user_factory())
    shikoyat(target=yechim, reporter=user_factory())

    holatlar = navbat()

    assert len(holatlar) == 2
    assert {h.turi for h in holatlar} == {"muammo", "yechim"}


def test_YOPILGAN_shikoyat_navbatda_YOQ(user_factory, staff):
    muammo = ComplaintFactory()
    shikoyat(target=muammo, reporter=user_factory())
    qaror_qabul_qilish(
        moderator=staff, target=muammo, action=ModerationActionType.RAD_ETISH
    )

    assert navbat() == []


def test_sabablar_YIGILADI(user_factory):
    """Naqsh ko'rinsin: bir xil sabab × 5 — ehtimol kelishilgan hujum."""
    muammo = ComplaintFactory()
    for _ in range(3):
        shikoyat(target=muammo, reporter=user_factory(), sabab=ReportReason.SPAM)
    shikoyat(target=muammo, reporter=user_factory(), sabab=ReportReason.HAQORAT)

    sabablar = dict(navbat()[0].sabablar)

    assert sabablar["Spam yoki reklama"] == 3
    assert sabablar["Haqorat yoki nafrat"] == 1


def test_MUALLIF_OCHIRGAN_kontent_navbatdan_CHIQMAYDI(user_factory):
    """⚠️ Kontent ketgan bo'lsa ham shikoyat "ko'rib chiqilmagan" bo'lib
    qolmasligi kerak — muallifga nisbatan chora hali ham ma'noli."""
    muammo = ComplaintFactory()
    shikoyat(target=muammo, reporter=user_factory())
    muammo.delete()  # yumshoq

    holatlar = navbat()

    assert len(holatlar) == 1
    assert holatlar[0].ochirilganmi is True


# ===========================================================================
# Navbat tartibi — MAHSULOT QARORI (foydalanuvchi tanlagan)
# ===========================================================================
def test_XAVF_har_doim_TEPADA(user_factory):
    """⚠️ Muhokama qilinmaydi: odam hayoti haqidagi signal spam bilan
    bir navbatda turmaydi — u eng yangi va yolg'iz bo'lsa ham."""
    eski = ComplaintFactory(title="Uch kun kutgan")
    for _ in range(5):
        shikoyat(target=eski, reporter=user_factory(), yosh=timedelta(days=3))

    xavfli = ComplaintFactory(title="Yangi, yolg'iz, lekin xavf")
    shikoyat(target=xavfli, reporter=user_factory(), sabab=ReportReason.XAVF)

    holatlar = navbat()

    assert holatlar[0].target == xavfli
    assert holatlar[0].shoshilinchmi is True


def test_KECHIKKANLAR_kechikmaganlardan_oldin(user_factory):
    kechikkan = ComplaintFactory(title="30 soat kutgan")
    shikoyat(target=kechikkan, reporter=user_factory(), yosh=timedelta(hours=30))

    yangi = ComplaintFactory(title="2 soat, 5 shikoyat")
    for _ in range(5):
        shikoyat(target=yangi, reporter=user_factory(), yosh=timedelta(hours=2))

    holatlar = navbat()

    assert holatlar[0].target == kechikkan, (
        "SLA buzilgan holat kutib qolmasligi kerak — shikoyat sahifasi "
        "'24 soat ichida' deb va'da beradi"
    )
    assert holatlar[1].target == yangi


def test_KECHIKKANLAR_orasida_ESKISI_birinchi(user_factory):
    uch_kun = ComplaintFactory(title="3 kun")
    shikoyat(target=uch_kun, reporter=user_factory(), yosh=timedelta(days=3))

    ottiz_soat = ComplaintFactory(title="30 soat")
    for _ in range(9):  # ko'p shikoyat ham eskisini bosib o'tmaydi
        shikoyat(target=ottiz_soat, reporter=user_factory(), yosh=timedelta(hours=30))

    holatlar = navbat()

    assert [h.target for h in holatlar] == [uch_kun, ottiz_soat]


def test_KECHIKMAGANLAR_orasida_KOP_SHIKOYATLI_birinchi(user_factory):
    yolgiz = ComplaintFactory(title="1 shikoyat, 6 soat")
    shikoyat(target=yolgiz, reporter=user_factory(), yosh=timedelta(hours=6))

    kop = ComplaintFactory(title="5 shikoyat, 2 soat")
    for _ in range(5):
        shikoyat(target=kop, reporter=user_factory(), yosh=timedelta(hours=2))

    holatlar = navbat()

    assert [h.target for h in holatlar] == [kop, yolgiz], (
        "Tez tarqalayotgan kontent yolg'iz shikoyatdan oldin ko'rilishi kerak"
    )


def test_TOLIQ_TARTIB_foydalanuvchi_tanlagan_ssenariy(user_factory):
    """⭐ Foydalanuvchi tanlagan variantning AYNAN o'zi (D2-T2 savoli).

    1. XAVF
    2. 3 kun kutgan     <- SLA buzilgan
    3. 30 soat kutgan   <- SLA buzilgan
    4. 5 shikoyat, 2 soat
    5. 1 shikoyat, 6 soat
    """
    xavf = ComplaintFactory(title="1-XAVF")
    shikoyat(
        target=xavf,
        reporter=user_factory(),
        sabab=ReportReason.XAVF,
        yosh=timedelta(minutes=5),
    )

    uch_kun = ComplaintFactory(title="2-uch kun")
    shikoyat(target=uch_kun, reporter=user_factory(), yosh=timedelta(days=3))

    ottiz_soat = ComplaintFactory(title="3-o'ttiz soat")
    shikoyat(target=ottiz_soat, reporter=user_factory(), yosh=timedelta(hours=30))

    besh_shikoyat = ComplaintFactory(title="4-besh shikoyat")
    for _ in range(5):
        shikoyat(target=besh_shikoyat, reporter=user_factory(), yosh=timedelta(hours=2))

    bitta = ComplaintFactory(title="5-bitta shikoyat")
    shikoyat(target=bitta, reporter=user_factory(), yosh=timedelta(hours=6))

    assert [h.target.title for h in navbat()] == [
        "1-XAVF",
        "2-uch kun",
        "3-o'ttiz soat",
        "4-besh shikoyat",
        "5-bitta shikoyat",
    ]


def test_SLA_chegarasi_24_soat(user_factory):
    """SLA shikoyat sahifasidagi va'da bilan bir xil bo'lishi shart."""
    assert SLA.total_seconds() == 24 * 3600

    hali = ComplaintFactory()
    shikoyat(target=hali, reporter=user_factory(), yosh=timedelta(hours=23))
    oshgan = ComplaintFactory()
    shikoyat(target=oshgan, reporter=user_factory(), yosh=timedelta(hours=25))

    holatlar = {h.target: h for h in navbat()}

    assert holatlar[hali].kechikkanmi is False
    assert holatlar[oshgan].kechikkanmi is True


# ===========================================================================
# Choralar
# ===========================================================================
@pytest.mark.parametrize(
    ("chora", "kutilgan_holat"),
    [
        (ModerationActionType.RAD_ETISH, ModerationStatus.VISIBLE),
        (ModerationActionType.OGOHLANTIRISH, ModerationStatus.VISIBLE),
        (ModerationActionType.YASHIRISH, ModerationStatus.HIDDEN),
        (ModerationActionType.OLIB_TASHLASH, ModerationStatus.REMOVED),
    ],
)
def test_chora_kontent_holatini_TOGRI_ozgartiradi(
    staff, user_factory, chora, kutilgan_holat
):
    muammo = ComplaintFactory()
    shikoyat(target=muammo, reporter=user_factory())

    qaror_qabul_qilish(moderator=staff, target=muammo, action=chora)

    muammo.refresh_from_db()
    assert muammo.moderation_status == kutilgan_holat


def test_BITTA_qaror_BARCHA_ochiq_shikoyatlarni_yopadi(staff, user_factory):
    """⚠️ Qabul mezoni: "bitta ekranda qaror qabul qilinadi"."""
    muammo = ComplaintFactory()
    for _ in range(4):
        shikoyat(target=muammo, reporter=user_factory())

    qaror_qabul_qilish(
        moderator=staff, target=muammo, action=ModerationActionType.YASHIRISH
    )

    assert Report.objects.ochiq().count() == 0
    assert Report.objects.filter(status=ReportStatus.HAL_QILINDI).count() == 4
    assert set(Report.objects.values_list("resolved_by", flat=True)) == {staff.pk}


def test_RAD_ETISH_shikoyatlarni_RAD_ETILDI_qiladi(staff, user_factory):
    """⚠️ "Shikoyat asossiz edi" va "chora ko'rildi" — IKKI XIL ma'lumot.

    D2-T5 (spam evristikasi) shikoyatchining aniqligini aynan shu
    farqdan o'lchaydi; ikkalasini "yopildi" deb birlashtirish signalni
    yo'q qilardi.
    """
    muammo = ComplaintFactory()
    shikoyat(target=muammo, reporter=user_factory())

    qaror_qabul_qilish(
        moderator=staff, target=muammo, action=ModerationActionType.RAD_ETISH
    )

    assert Report.objects.get().status == ReportStatus.RAD_ETILDI


def test_izoh_MUALLIFGA_yoziladi(staff, user_factory):
    muammo = ComplaintFactory()
    shikoyat(target=muammo, reporter=user_factory())

    qaror_qabul_qilish(
        moderator=staff,
        target=muammo,
        action=ModerationActionType.YASHIRISH,
        izoh="Reklama havolasi",
    )

    muammo.refresh_from_db()
    assert muammo.moderation_note == "Reklama havolasi"


def test_ODDIY_foydalanuvchi_XIZMATNI_chaqira_olmaydi(user):
    """Ko'rinishdagi tekshiruv yetarli emas — xizmat o'zi ham himoyalansin."""
    muammo = ComplaintFactory()

    with pytest.raises(PermissionDenied):
        qaror_qabul_qilish(
            moderator=user, target=muammo, action=ModerationActionType.YASHIRISH
        )


def test_NOMALUM_chora_rad_etiladi(staff):
    with pytest.raises(ValueError, match="Noma'lum chora"):
        qaror_qabul_qilish(
            moderator=staff, target=ComplaintFactory(), action="postni_yoqib_yubor"
        )


def test_BEKOR_QILISH_chora_sifatida_berilmaydi(staff):
    with pytest.raises(ValueError, match="qarorni_bekor_qilish"):
        qaror_qabul_qilish(
            moderator=staff,
            target=ComplaintFactory(),
            action=ModerationActionType.BEKOR_QILISH,
        )


def test_chora_YECHIMGA_ham_qollanadi(staff, user_factory):
    yechim = SolutionFactory()
    shikoyat(target=yechim, reporter=user_factory())

    chora = qaror_qabul_qilish(
        moderator=staff, target=yechim, action=ModerationActionType.OLIB_TASHLASH
    )

    yechim.refresh_from_db()
    assert yechim.moderation_status == ModerationStatus.REMOVED
    assert chora.solution == yechim
    assert chora.complaint is None


def test_chora_MUALLIFNI_eslab_qoladi(staff, user_factory):
    """⚠️ Denormalizatsiya: kontent bir kuni haqiqatan o'chirilishi mumkin
    (D2-T8), chora esa "kimga nisbatan" ma'lumotini yo'qotmasin —
    D2-T11 (uch ogohlantirish) aynan shuni sanaydi."""
    muallif = user_factory()
    muammo = ComplaintFactory(author=muallif)
    shikoyat(target=muammo, reporter=user_factory())

    chora = qaror_qabul_qilish(
        moderator=staff, target=muammo, action=ModerationActionType.OGOHLANTIRISH
    )

    assert chora.target_author == muallif


# ===========================================================================
# Bekor qilish — jurnal o'chirilmaydi, kompensatsiya qo'shiladi
# ===========================================================================
def test_bekor_qilish_YOZUVNI_OCHIRMAYDI(staff, user_factory):
    """⚠️ `KarmaEvent` bilan bir xil falsafa: jurnal tahrirlansa u dalil
    bo'lishdan to'xtaydi."""
    muammo = ComplaintFactory()
    shikoyat(target=muammo, reporter=user_factory())
    chora = qaror_qabul_qilish(
        moderator=staff, target=muammo, action=ModerationActionType.YASHIRISH
    )

    qarorni_bekor_qilish(moderator=staff, chora=chora)

    assert ModerationAction.objects.count() == 2
    assert ModerationAction.objects.filter(pk=chora.pk).exists()
    qaytarish = ModerationAction.objects.get(action=ModerationActionType.BEKOR_QILISH)
    assert qaytarish.bekor_qiladi == chora


def test_bekor_qilish_OLDINGI_holatga_qaytaradi_VISIBLE_ga_EMAS(staff, user_factory):
    """⭐ Oson unutiladigan holat.

    Post yashirilishidan OLDIN allaqachon `PENDING` da turgan bo'lishi
    mumkin (avtomatik filtr qo'ygan — D2-T5). "VISIBLE ga qaytar" deb
    qotirib qo'yilsa, bekor qilish uni jimgina ko'rinadigan qilib
    yuborardi — ya'ni tekshiruvni chetlab o'tardi.
    """
    muammo = ComplaintFactory(moderation_status=ModerationStatus.PENDING)
    shikoyat(target=muammo, reporter=user_factory())
    chora = qaror_qabul_qilish(
        moderator=staff, target=muammo, action=ModerationActionType.OLIB_TASHLASH
    )

    qarorni_bekor_qilish(moderator=staff, chora=chora)

    muammo.refresh_from_db()
    assert muammo.moderation_status == ModerationStatus.PENDING


def test_bekor_qilish_shikoyatlarni_NAVBATGA_qaytaradi(staff, user_factory):
    muammo = ComplaintFactory()
    for _ in range(3):
        shikoyat(target=muammo, reporter=user_factory())
    chora = qaror_qabul_qilish(
        moderator=staff, target=muammo, action=ModerationActionType.YASHIRISH
    )
    assert navbat() == []

    qarorni_bekor_qilish(moderator=staff, chora=chora)

    assert len(navbat()) == 1
    assert navbat()[0].soni == 3
    assert Report.objects.filter(resolved_by__isnull=False).count() == 0


def test_bekor_qilish_FAQAT_OZI_yopgan_shikoyatlarni_ochadi(staff, user_factory):
    """⭐ Nega `Report.yopgan_chora` FK kerak bo'ldi.

    Vaqt bo'yicha taxmin ("bir xil soniyada yopilganlar") mo'rt bo'lardi:
    bitta obyektga ketma-ket ikki marta chora ko'rilishi mumkin.
    """
    muammo = ComplaintFactory()
    birinchi = shikoyat(target=muammo, reporter=user_factory())
    ikkinchi = shikoyat(target=muammo, reporter=user_factory())
    chora1 = qaror_qabul_qilish(
        moderator=staff, target=muammo, action=ModerationActionType.YASHIRISH
    )

    uchinchi = shikoyat(target=muammo, reporter=user_factory())
    qaror_qabul_qilish(
        moderator=staff, target=muammo, action=ModerationActionType.YASHIRISH
    )

    qarorni_bekor_qilish(moderator=staff, chora=chora1)

    birinchi.refresh_from_db()
    ikkinchi.refresh_from_db()
    uchinchi.refresh_from_db()
    assert birinchi.status == ReportStatus.OCHIQ
    assert ikkinchi.status == ReportStatus.OCHIQ
    assert uchinchi.status == ReportStatus.HAL_QILINDI


def test_bekor_qilishning_OZINI_bekor_qilib_bolmaydi(staff, user_factory):
    """Aks holda interfeysda cheksiz "bekorning bekori" zanjiri paydo
    bo'lardi va jurnalni o'qib bo'lmasdi."""
    muammo = ComplaintFactory()
    shikoyat(target=muammo, reporter=user_factory())
    chora = qaror_qabul_qilish(
        moderator=staff, target=muammo, action=ModerationActionType.YASHIRISH
    )
    qaytarish = qarorni_bekor_qilish(moderator=staff, chora=chora)

    with pytest.raises(BekorQilibBolmaydi, match="o'zini"):
        qarorni_bekor_qilish(moderator=staff, chora=qaytarish)


def test_IKKI_MARTA_bekor_qilib_bolmaydi(staff, user_factory):
    muammo = ComplaintFactory()
    shikoyat(target=muammo, reporter=user_factory())
    chora = qaror_qabul_qilish(
        moderator=staff, target=muammo, action=ModerationActionType.YASHIRISH
    )
    qarorni_bekor_qilish(moderator=staff, chora=chora)

    with pytest.raises(BekorQilibBolmaydi, match="allaqachon"):
        qarorni_bekor_qilish(moderator=staff, chora=chora)


def test_ODDIY_foydalanuvchi_BEKOR_qila_olmaydi(auth_client, staff, user_factory):
    muammo = ComplaintFactory()
    shikoyat(target=muammo, reporter=user_factory())
    chora = qaror_qabul_qilish(
        moderator=staff, target=muammo, action=ModerationActionType.YASHIRISH
    )

    javob = auth_client.post(reverse("moderatsiya_bekor", args=[chora.pk]))

    assert javob.status_code == 404
    muammo.refresh_from_db()
    assert muammo.moderation_status == ModerationStatus.HIDDEN


# ===========================================================================
# Ko'rinish
# ===========================================================================
def test_navbat_YASHIRILGAN_kontentni_KORSATADI(staff_client, user_factory):
    """⚠️ Bu ko'rinish invariantining ATAYLAB qilingan istisnosi:
    moderator aynan yashirilgan kontent ustidan qaror qabul qiladi.
    Himoyasi `visible()` emas, `@moderator_kerak`."""
    muammo = ComplaintFactory(
        title="YASHIRINPOSTSARLAVHASI",
        moderation_status=ModerationStatus.HIDDEN,
    )
    shikoyat(target=muammo, reporter=user_factory())

    matn = staff_client.get(NAVBAT_URL).content.decode()

    assert "YASHIRINPOSTSARLAVHASI" in matn


def test_kontent_EKRANLANADI(staff_client, user_factory):
    """⚠️ Moderator ko'radigan matn — eng ishonchsiz matn: aynan u
    haqida shikoyat bor. `safe` bu sahifada hech qachon ishlatilmaydi."""
    muammo = ComplaintFactory(description="<script>alert(1)</script>")
    shikoyat(target=muammo, reporter=user_factory())

    matn = staff_client.get(NAVBAT_URL).content.decode()

    assert "<script>alert(1)</script>" not in matn
    assert "&lt;script&gt;" in matn


def test_navbat_BOSH_bolsa_tushunarli_xabar(staff_client):
    matn = staff_client.get(NAVBAT_URL).content.decode()
    assert "Navbat bo'sh" in matn


def test_HTMX_javobi_BEKOR_QILISH_tugmasini_beradi(staff_client, user_factory):
    """⚠️ Klaviatura bilan tez ishlash chalkashishni ham tezlashtiradi —
    bekor qilish o'sha zahoti, shu joyda bo'lishi kerak."""
    muammo = ComplaintFactory()
    shikoyat(target=muammo, reporter=user_factory())

    javob = staff_client.post(
        reverse("moderatsiya_qaror_muammo", args=[muammo.pk]),
        {"action": ModerationActionType.YASHIRISH},
        headers={"hx-request": "true"},
    )
    matn = javob.content.decode()

    chora = ModerationAction.objects.get()
    assert javob.status_code == 200
    assert "Bekor qilish" in matn
    assert reverse("moderatsiya_bekor", args=[chora.pk]) in matn
    # ⚠️ `id` — HTMX almashtirish SHARTNOMASI (`hx-target="#holat-..."`).
    #    Dastlab u `target_nomi|slugify` dan qurilgandi va tasodifan
    #    to'g'ri chiqardi; endi FK'dan quriladi va shu yerda qotirilgan.
    assert f'id="holat-muammo-{muammo.pk}"' in matn


def test_HTMXSIZ_qaror_navbatga_QAYTARADI(staff_client, user_factory):
    """JavaScript'siz ham to'liq ishlashi shart (progressive enhancement)."""
    muammo = ComplaintFactory()
    shikoyat(target=muammo, reporter=user_factory())

    javob = staff_client.post(
        reverse("moderatsiya_qaror_muammo", args=[muammo.pk]),
        {"action": ModerationActionType.YASHIRISH},
        follow=True,
    )

    assert javob.redirect_chain[-1][0] == NAVBAT_URL
    assert [str(m) for m in javob.context["messages"]] == [
        f"Yashirish — muammo #{muammo.pk}."
    ]


def test_JSSIZ_bekor_qilish_yoli_SAHIFADA_bor(staff_client, user_factory, staff):
    """⚠️ HTMX'siz kartaning o'rnidagi tugma ko'rinmaydi — shuning uchun
    "So'nggi qarorlar" bo'limi bekor qilishning ikkinchi yo'li."""
    muammo = ComplaintFactory()
    shikoyat(target=muammo, reporter=user_factory())
    chora = qaror_qabul_qilish(
        moderator=staff, target=muammo, action=ModerationActionType.YASHIRISH
    )

    matn = staff_client.get(NAVBAT_URL).content.decode()

    assert "So'nggi qarorlar" in matn
    assert reverse("moderatsiya_bekor", args=[chora.pk]) in matn


def test_STAFF_navigatsiyada_navbat_havolasi(staff_client, auth_client):
    """Havola ko'rinmasa moderator manzilni yodda saqlashi kerak bo'lardi."""
    assert NAVBAT_URL in staff_client.get("/").content.decode()
    assert NAVBAT_URL not in auth_client.get("/").content.decode()


def test_klaviatura_royxati_EKRANDA(staff_client, user_factory):
    """⚠️ Ko'rsatilmagan qisqa tugma — mavjud bo'lmagan qisqa tugma."""
    shikoyat(target=ComplaintFactory(), reporter=user_factory())

    matn = staff_client.get(NAVBAT_URL).content.decode()

    assert "Klaviatura bilan tez ishlash" in matn
    for tugma in (">j<", ">k<", ">i<", ">?<"):
        assert tugma in matn


# ===========================================================================
# So'rov soni — holatlar soniga BOG'LIQ EMAS
# ===========================================================================
def sorovlar(mijoz: Client, yol: str) -> int:
    """So'rovlar soni (sessiya keshi ilitilgandan keyin) — D1-T14 naqshi."""
    from django.db import connection, reset_queries
    from django.test.utils import CaptureQueriesContext

    mijoz.get(yol)  # iliting: sessiya va contenttypes keshi
    reset_queries()
    with CaptureQueriesContext(connection) as ctx:
        javob = mijoz.get(yol)
        assert javob.status_code == 200
    return len(ctx)


def test_navbat_sorovlari_HOLATLAR_soniga_BOGLIQ_EMAS(user_factory, staff):
    """⚠️ D1-T14 da o'rnatilgan tartib: qat'iy son emas, BOG'LIQLIK.

    Qat'iy son refaktoringda "shunchaki yangilanadi"; element soniga
    bog'liqlik esa haqiqiy N+1 ni ushlaydi. Navbatda har kartada
    muallif, kategoriya va yechim uchun ota-muammo bor — `select_related`
    unutilsa 20 holat 60+ so'rov bo'lardi.
    """
    c = Client()
    c.force_login(staff)

    for _ in range(2):
        shikoyat(target=ComplaintFactory(), reporter=user_factory())
    kam = sorovlar(c, NAVBAT_URL)

    for _ in range(10):
        shikoyat(target=ComplaintFactory(), reporter=user_factory())
        shikoyat(target=SolutionFactory(), reporter=user_factory())
    kop = sorovlar(c, NAVBAT_URL)

    assert kam == kop, (
        f"2 holatda {kam}, 22 holatda {kop} so'rov — N+1 bor "
        "(`selectors.navbat` dagi `select_related` ni tekshiring)"
    )
