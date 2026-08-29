"""Nishonlar tizimi (D3-T2)."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest
from django.conf import settings
from django.core.management import call_command
from django.db.utils import IntegrityError
from django.urls import reverse
from django.utils import timezone

from apps.complaints.factories import ComplaintFactory
from apps.gamification.models import (
    Badge,
    KarmaEvent,
    KarmaReason,
    NishonIkonka,
    NishonMetrikasi,
    UserBadge,
)
from apps.gamification.services import (
    NISHON_METRIKALARI,
    karma_yoz,
    nishon_holati,
    nishonlarni_tekshirish,
)
from apps.solutions.factories import SolutionFactory

pytestmark = pytest.mark.django_db

FIXTURE = Path(settings.BASE_DIR) / "apps/gamification/fixtures/nishonlar.json"
IKONKA_SHABLONI = Path(settings.BASE_DIR) / "templates/components/_nishon_ikonka.html"


def nishon(**kw) -> Badge:
    kw.setdefault("slug", f"sinov-{Badge.objects.count() + 1}")
    kw.setdefault("nom", "Sinov nishoni")
    kw.setdefault("tavsif", "Sinov uchun.")
    kw.setdefault("metrika", NishonMetrikasi.YECHIMLAR)
    kw.setdefault("chegara", 1)
    return Badge.objects.create(**kw)


# ===========================================================================
# ⭐⭐ QABUL MEZONI: nishon shartlari MA'LUMOTLARDA, kodda emas
# ===========================================================================
def test_QABUL_MEZONI_yangi_nishon_KODSIZ_qoshiladi(user):
    """⭐⭐ Qabul mezoni: "nishon shartlari ma'lumotlarda, kodda emas".

    Bu test KOD YOZMASDAN yangi nishon qo'shadi — faqat baza qatori —
    va u ishlashini talab qiladi. Agar shart kodda bo'lsa (masalan
    `if` zanjiri yoki qattiq yozilgan ro'yxat), bu test yiqiladi.
    """
    SolutionFactory(author=user)
    SolutionFactory(author=user)

    # Faqat MA'LUMOT: hech qanday kod o'zgarmadi.
    yangi = Badge.objects.create(
        slug="ikki-yechim",
        nom="Ikki yechim",
        tavsif="2 ta yechim yozsangiz ochiladi.",
        metrika=NishonMetrikasi.YECHIMLAR,
        chegara=2,
    )

    berilgan = nishonlarni_tekshirish(user=user)

    assert [b.badge_id for b in berilgan] == [yangi.pk]


def test_CHEGARA_ham_MALUMOTDA(user):
    """Chegarani o'zgartirish uchun ham kod tegilmaydi."""
    SolutionFactory(author=user)
    baland = nishon(slug="baland", chegara=5)

    assert nishonlarni_tekshirish(user=user) == []

    baland.chegara = 1
    baland.save(update_fields=["chegara"])

    assert len(nishonlarni_tekshirish(user=user)) == 1


def test_SHART_IFODA_SATRI_EMAS():
    """⚠️⚠️ "Shart ma'lumotda" degani "bazada ifoda saqlaymiz" DEGANI
    EMAS.

    Bajariladigan mantiqni bazaga solish — admin panelga kirgan odam
    yozgan matn serverda ishga tushishi degani. Loyiha bu qarorni
    `CategoryIcon` da allaqachon qabul qilgan (u yerda SVG, bu yerda
    ifoda — bir xil teshikning ikki shakli).

    Guard: modelda ifoda uchun matn maydoni PAYDO BO'LMASIN.
    """
    maydonlar = {f.name for f in Badge._meta.get_fields()}

    for shubhali in ("shart", "ifoda", "expression", "formula", "kod"):
        assert shubhali not in maydonlar, (
            f"`{shubhali}` maydoni qo'shilgan — bazada bajariladigan mantiq "
            "saqlanmoqdami? `NishonMetrikasi` docstring'iga qarang."
        )


def test_GUARD_metrikalar_hisoblanadi():
    """⚠️ `NishonMetrikasi` ga qiymat qo'shilib, `_metrikalar()` da
    hisoblash unutilsa — nishon HECH QACHON berilmasdi va hech qanday
    xato chiqmasdi."""
    assert set(NishonMetrikasi.values) == set(NISHON_METRIKALARI)


def test_GUARD_har_bir_metrika_HAQIQATAN_hisoblanadi(user):
    """⚠️ Yuqoridagi guard faqat NOMLARNI solishtiradi. Bu esa
    `_metrikalar()` HAR BIR kalitni qaytarishini talab qiladi."""
    from apps.gamification.services import _metrikalar

    olchovlar = _metrikalar(user=user)

    for qiymat in NishonMetrikasi.values:
        assert qiymat in olchovlar, f"`{qiymat}` hisoblanmaydi"


def test_GUARD_har_bir_ikonka_shablonda_bor():
    """⚠️ `NishonIkonka` ga kalit qo'shilib, shablonga unutilsa, nishon
    ikonkasiz (bo'sh kvadrat) chiqadi va sahifa baribir 200 qaytaradi.
    `CategoryIcon` dagi bir xil guard."""
    matn = IKONKA_SHABLONI.read_text(encoding="utf-8")

    for qiymat in NishonIkonka.values:
        assert f'== "{qiymat}"' in matn, f"`{qiymat}` shablonda yo'q"


# ===========================================================================
# Fixture
# ===========================================================================
def test_FIXTURE_yuklanadi_va_TAKRORIY_yuklash_xato_bermaydi():
    call_command("loaddata", "nishonlar", verbosity=0)
    soni = Badge.objects.count()
    call_command("loaddata", "nishonlar", verbosity=0)

    assert Badge.objects.count() == soni > 0


def test_FIXTURE_ichidagi_kalitlar_haqiqiy():
    """⚠️ Noto'g'ri `ikonka` yoki `metrika` kaliti xato BERMAYDI
    (`choices` faqat forma darajasida tekshiriladi) — nishon shunchaki
    hech qachon berilmaydi yoki ikonkasiz chiqadi."""
    yozuvlar = json.loads(FIXTURE.read_text(encoding="utf-8"))
    ikonkalar = set(NishonIkonka.values)
    metrikalar = set(NishonMetrikasi.values)

    sluglar = [y["fields"]["slug"] for y in yozuvlar]
    assert len(set(sluglar)) == len(sluglar), "Fixture ichida takroriy slug"

    for y in yozuvlar:
        f = y["fields"]
        assert f["ikonka"] in ikonkalar, f"Noma'lum ikonka: {f['ikonka']}"
        assert f["metrika"] in metrikalar, f"Noma'lum metrika: {f['metrika']}"
        assert f["chegara"] > 0
        assert f["tavsif"].endswith("."), "Tavsif gap bo'lsin — u qulfda ko'rinadi"


# ===========================================================================
# Berish mantiqi
# ===========================================================================
def test_CHEGARAGA_yetmasa_berilmaydi(user):
    nishon(chegara=3)
    SolutionFactory(author=user)

    assert nishonlarni_tekshirish(user=user) == []


def test_TAKRORIY_tekshiruv_ikkinchi_marta_BERMAYDI(user):
    nishon(chegara=1)
    SolutionFactory(author=user)

    nishonlarni_tekshirish(user=user)
    nishonlarni_tekshirish(user=user)

    assert UserBadge.objects.filter(user=user).count() == 1


def test_NISHON_QAYTIB_OLINMAYDI(user):
    """⚠️⚠️ Karma tushib ketsa ham (kompensatsiya, D3-T1) nishon
    QOLADI: "sizda bor edi, endi yo'q" odamni jazolagandek bo'lardi va
    u nimani noto'g'ri qilganini tushunmasdi. Yutuq — TARIX."""
    b = nishon(metrika=NishonMetrikasi.KARMA, chegara=15)
    karma_yoz(user=user, reason=KarmaReason.SOLUTION_ACCEPTED)
    nishonlarni_tekshirish(user=user)
    assert UserBadge.objects.filter(user=user, badge=b).exists()

    karma_yoz(user=user, reason=KarmaReason.SOLUTION_UNACCEPTED)
    nishonlarni_tekshirish(user=user)

    user.refresh_from_db()
    assert user.karma_cached == 0
    assert UserBadge.objects.filter(user=user, badge=b).exists(), "nishon qaytib olindi"


def test_ANONIM_ish_ham_HISOBLANADI(user):
    """⚠️⚠️ Foydalanuvchi qarori: anonim javob berish JAZOLANMAYDI —
    D3-T1 dagi karma qarori bilan aynan bir xil sabab. Eng og'ir
    mavzudagi javoblar ko'pincha anonim yoziladi."""
    nishon(chegara=2)
    SolutionFactory(author=user, is_anonymous=True)
    SolutionFactory(author=user, is_anonymous=True)

    assert len(nishonlarni_tekshirish(user=user)) == 1


def test_OLIB_TASHLANGAN_kontent_HISOBLANMAYDI(staff, user):
    """⚠️ D3-T1 da uning karmasi ham qaytariladi — ikkala tizim bir xil
    narsani "yo'q" deb bilishi kerak."""
    from apps.moderation.models import ModerationActionType, Report, ReportReason
    from apps.moderation.services import qaror_qabul_qilish

    nishon(chegara=1)
    yechim = SolutionFactory(author=user)
    Report.objects.create(solution=yechim, reason=ReportReason.SPAM)
    qaror_qabul_qilish(
        moderator=staff, target=yechim, action=ModerationActionType.OLIB_TASHLASH
    )

    assert nishonlarni_tekshirish(user=user) == []


def test_NOFAOL_nishon_berilmaydi(user):
    nishon(chegara=1, is_active=False)
    SolutionFactory(author=user)

    assert nishonlarni_tekshirish(user=user) == []


def test_NOL_chegara_BAZA_darajasida_taqiqlangan():
    """⚠️ Nol chegarali nishon HAMMAGA darhol berilardi va "yutuq"
    so'zi ma'nosini yo'qotardi."""
    with pytest.raises(IntegrityError):
        Badge.objects.create(
            slug="nol", nom="Nol", tavsif="x.", metrika=NishonMetrikasi.KARMA, chegara=0
        )


def test_MUALLIFSIZ_foydalanuvchida_yiqilmaydi():
    assert nishonlarni_tekshirish(user=None) == []


# ===========================================================================
# Qabul qilish oqimiga ulanish
# ===========================================================================
def test_YECHIM_QABUL_QILINGANDA_nishon_beriladi(user, other_user):
    """⚠️ Qabul qilish — kam uchraydigan va kuchli signal, ya'ni nishonni
    darhol berish uchun eng ma'noli payt."""
    from apps.solutions.services import accept_solution

    b = nishon(metrika=NishonMetrikasi.QABUL_QILINGAN, chegara=1)
    muammo = ComplaintFactory(author=other_user)
    yechim = SolutionFactory(complaint=muammo, author=user)

    accept_solution(solution=yechim, by_user=other_user)

    assert UserBadge.objects.filter(user=user, badge=b).exists()


# ===========================================================================
# Celery vazifasi
# ===========================================================================
def test_VAZIFA_ovozdan_kelgan_nishonni_beradi(user):
    """⚠️ Ovoz yo'lida nishon tekshirilmaydi (D1-T14 so'rov byudjeti) —
    shuning uchun bu vazifa kerak."""
    from apps.gamification.tasks import nishonlarni_yangilash

    b = nishon(metrika=NishonMetrikasi.KARMA, chegara=2)
    karma_yoz(user=user, reason=KarmaReason.SOLUTION_UPVOTED)

    assert nishonlarni_yangilash() == 1
    assert UserBadge.objects.filter(user=user, badge=b).exists()


def test_VAZIFA_faqat_YAQINDAGI_faollarni_tekshiradi(user, other_user):
    """⚠️ Baza o'sganda "hammasini aylanish" sutkalik vazifani soatlab
    cho'zardi."""
    from apps.gamification.tasks import nishonlarni_yangilash

    nishon(metrika=NishonMetrikasi.KARMA, chegara=2)
    karma_yoz(user=user, reason=KarmaReason.SOLUTION_UPVOTED)

    eski = karma_yoz(user=other_user, reason=KarmaReason.SOLUTION_UPVOTED)
    KarmaEvent.objects.filter(pk=eski.pk).update(
        created_at=timezone.now() - timedelta(days=10)
    )

    nishonlarni_yangilash()

    assert UserBadge.objects.filter(user=user).exists()
    assert not UserBadge.objects.filter(user=other_user).exists()


# ===========================================================================
# ⭐⭐ Ko'rsatish: qulf va progress FAQAT EGASIGA
# ===========================================================================
def test_BEGONAGA_faqat_OLINGAN_nishonlar(user):
    """⭐⭐ Foydalanuvchi qarori. Progress ommaviy bo'lsa, ommaviy sanoq
    (anonimsiz, D3-T4) bilan ayirma anonim ishlarning ANIQ sonini
    berardi."""
    olingan = nishon(slug="olingan", chegara=1)
    nishon(slug="qulflangan", chegara=99)
    SolutionFactory(author=user)
    nishonlarni_tekshirish(user=user)

    holat = nishon_holati(profil=user, ozimi=False)

    assert [h["badge"].pk for h in holat] == [olingan.pk]
    assert all(h["progress"] is None for h in holat)


def test_EGASIGA_QULFLANGAN_ham_PROGRESS_bilan(user):
    nishon(slug="olingan", chegara=1)
    nishon(slug="qulflangan", chegara=10)
    SolutionFactory(author=user)
    SolutionFactory(author=user)
    nishonlarni_tekshirish(user=user)

    holat = {h["badge"].slug: h for h in nishon_holati(profil=user, ozimi=True)}

    assert holat["olingan"]["olingan"] is True
    assert holat["qulflangan"]["olingan"] is False
    assert holat["qulflangan"]["progress"] == 2


def test_PROGRESS_chegaradan_OSHMAYDI(user):
    """⚠️ "12/10" chalkash ko'rinardi va progress chizig'i buzilardi."""
    b = nishon(chegara=2)
    for _ in range(5):
        SolutionFactory(author=user)

    holat = nishon_holati(profil=user, ozimi=True)

    assert holat[0]["progress"] == b.chegara


def test_QULFLANGAN_nishon_SABABI_bilan_KORINADI(auth_client, user):
    """⭐ Task `nega`: "maketda 'Ishonchli maslahatchi' qulflangan holati
    bor va u ochilish shartini AYTADI — bu shunchaki bezak emas, xulqni
    yo'naltiradi"."""
    nishon(
        slug="ishonchli",
        nom="Ishonchli maslahatchi",
        tavsif="10 ta yechimingiz qabul qilinsa ochiladi.",
        metrika=NishonMetrikasi.QABUL_QILINGAN,
        chegara=10,
    )

    matn = auth_client.get(reverse("profile", args=[user.username])).content.decode()

    assert "Ishonchli maslahatchi" in matn
    assert "qabul qilinsa ochiladi" in matn


def test_BEGONA_profilida_QULF_va_progress_YOQ(anonymous_client, user):
    nishon(slug="qulflangan", nom="Qulflangan nishon", chegara=99)

    matn = anonymous_client.get(
        reverse("profile", args=[user.username])
    ).content.decode()

    assert "Qulflangan nishon" not in matn


def test_profil_SOROV_soni_nishonlardan_OSMAYDI(user, django_assert_num_queries):
    """⚠️ Nishonlar bloki HAR NISHON uchun so'rov qilmasligi kerak
    (D1-T14 qoidasi)."""
    from django.db import connection
    from django.test import Client
    from django.test.utils import CaptureQueriesContext

    c = Client()
    c.force_login(user)
    yol = reverse("profile", args=[user.username])

    nishon(slug="bir", chegara=1)
    SolutionFactory(author=user)
    c.get(yol)
    with CaptureQueriesContext(connection) as kam:
        c.get(yol)

    for i in range(8):
        nishon(slug=f"kop-{i}", chegara=i + 2)

    with CaptureQueriesContext(connection) as kop:
        c.get(yol)

    assert len(kam) == len(kop), (
        f"So'rov soni nishonlar soniga bog'liq: {len(kam)} -> {len(kop)}"
    )
