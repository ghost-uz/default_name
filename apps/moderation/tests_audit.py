"""O'zgarmas audit jurnali (D2-T7)."""

from __future__ import annotations

import ast
import pathlib

import pytest
from django.contrib.admin.sites import site as admin_site
from django.urls import reverse

from apps.complaints.factories import ComplaintFactory
from apps.moderation.audit import audit
from apps.moderation.models import (
    AuditAction,
    AuditLog,
    JurnalOzgarmas,
    ModerationActionType,
    Report,
    ReportReason,
)
from apps.moderation.services import (
    avtomatik_belgilash,
    qaror_qabul_qilish,
    qarorni_bekor_qilish,
    shikoyatni_yopish,
)

pytestmark = pytest.mark.django_db

JURNAL_URL = reverse("moderatsiya_jurnal")


def shikoyat(*, target, reporter):
    return Report.objects.create(
        reporter=reporter, complaint=target, reason=ReportReason.SPAM
    )


# ===========================================================================
# O'ZGARMASLIK — jurnalning butun ma'nosi shunda
# ===========================================================================
def test_yozuv_TAHRIRLANMAYDI():
    """⚠️ Tahrirlanadigan jurnal dalil emas: nizo chiqqanda "kim, nima,
    qachon" javobi keyinchalik o'zgartirilgan bo'lishi mumkin bo'lardi."""
    yozuv = audit(action=AuditAction.SHIKOYAT_YOPILDI, obyekt="shikoyat #1")

    yozuv.izoh = "boshqacha"
    with pytest.raises(JurnalOzgarmas, match="tahrirlanmaydi"):
        yozuv.save()

    yozuv.refresh_from_db()
    assert yozuv.izoh == ""


def test_yozuv_OCHIRILMAYDI():
    yozuv = audit(action=AuditAction.SHIKOYAT_YOPILDI, obyekt="shikoyat #1")

    with pytest.raises(JurnalOzgarmas, match="o'chirilmaydi"):
        yozuv.delete()

    assert AuditLog.objects.count() == 1


def test_OMMAVIY_ozgartirish_ham_YOPIQ():
    """⭐ Eng oson unutiladigan teshik.

    `AuditLog.objects.filter(...).update(izoh="")` HECH QANDAY model
    metodini chaqirmaydi — ya'ni `save()` dagi himoya uni ushlamaydi.
    Jurnal uchun bu teshik ochiq qolsa, qolgan himoyaning ma'nosi yo'q.
    """
    audit(action=AuditAction.SHIKOYAT_YOPILDI, obyekt="shikoyat #1")

    with pytest.raises(JurnalOzgarmas):
        AuditLog.objects.all().update(izoh="o'zgartirildi")

    with pytest.raises(JurnalOzgarmas):
        AuditLog.objects.all().delete()

    assert AuditLog.objects.get().izoh == ""


def test_yangi_yozuv_QOSHILADI():
    """O'zgarmaslik "yozib bo'lmaydi" degani emas."""
    audit(action=AuditAction.SHIKOYAT_YOPILDI, obyekt="shikoyat #1")
    audit(action=AuditAction.KONTENT_CHORA, obyekt="muammo #1")

    assert AuditLog.objects.count() == 2


def test_QABUL_MEZONI_adminda_qoshish_tahrirlash_ochirish_YOPIQ(rf, staff):
    """⭐ Qabul mezoni: "admin'da o'chirish/tahrirlash o'chirilgan"."""
    admin = admin_site._registry[AuditLog]
    sorov = rf.get("/")
    sorov.user = staff

    assert admin.has_add_permission(sorov) is False
    assert admin.has_change_permission(sorov) is False
    assert admin.has_delete_permission(sorov) is False


# ===========================================================================
# Kim qildi — hisob o'chsa ham qolishi kerak
# ===========================================================================
def test_ACTOR_NOMI_yozuv_paytida_NUSXALANADI(staff):
    """⚠️ `actor` FK `SET_NULL` — hisob o'chirilsa `None` bo'ladi.

    "Kim qildi?" savoliga javobsiz jurnal dalil emas, shuning uchun ism
    yozuv paytida nusxalanadi.
    """
    audit(action=AuditAction.SHIKOYAT_YOPILDI, obyekt="shikoyat #1", actor=staff)
    nomi = staff.username

    staff.delete()

    yozuv = AuditLog.objects.get()
    assert yozuv.actor is None
    assert yozuv.actor_nomi == nomi
    assert yozuv.kim == nomi


def test_ACTORSIZ_yozuv_TIZIM_deb_korinadi():
    yozuv = audit(action=AuditAction.AVTOMATIK_BELGI, obyekt="muammo #1")

    assert yozuv.actor is None
    assert yozuv.kim == "tizim"


# ===========================================================================
# Xizmatlar jurnalga yozadimi
# ===========================================================================
def test_KONTENT_chorasi_AVTOMATIK_jurnalga_tushadi(staff, user_factory):
    """⚠️ Signal orqali — qo'lda chaqirishga qoldirilsa bir kuni
    unutilardi, va aynan eng muhim yozuv yo'qolardi."""
    muammo = ComplaintFactory()
    shikoyat(target=muammo, reporter=user_factory())

    qaror_qabul_qilish(
        moderator=staff,
        target=muammo,
        action=ModerationActionType.YASHIRISH,
        izoh="Reklama",
    )

    yozuv = AuditLog.objects.get(action=AuditAction.KONTENT_CHORA)
    assert yozuv.obyekt == f"muammo #{muammo.pk}"
    assert yozuv.kim == staff.username
    assert yozuv.izoh == "Reklama"
    assert yozuv.malumot["chora"] == ModerationActionType.YASHIRISH
    assert yozuv.malumot["oldingi_holat"] == "visible"


def test_BEKOR_QILISH_alohida_harakat_sifatida_yoziladi(staff, user_factory):
    muammo = ComplaintFactory()
    shikoyat(target=muammo, reporter=user_factory())
    chora = qaror_qabul_qilish(
        moderator=staff, target=muammo, action=ModerationActionType.YASHIRISH
    )

    qarorni_bekor_qilish(moderator=staff, chora=chora)

    assert AuditLog.objects.filter(action=AuditAction.KONTENT_CHORA).count() == 1
    bekor = AuditLog.objects.get(action=AuditAction.CHORA_BEKOR)
    assert bekor.malumot["bekor_qiladi"] == chora.pk


def test_SHIKOYAT_YOPISH_jurnalga_tushadi(staff, user_factory):
    """⚠️ Bu amal MODEL YARATMAYDI, ya'ni signal uni ushlamaydi —
    `audit()` ochiq chaqiriladi."""
    muammo = ComplaintFactory()
    hisobot = shikoyat(target=muammo, reporter=user_factory())

    shikoyatni_yopish(
        report=hisobot, moderator=staff, qabul_qilindi=False, izoh="Asossiz"
    )

    yozuv = AuditLog.objects.get(action=AuditAction.SHIKOYAT_YOPILDI)
    assert yozuv.obyekt == f"shikoyat #{hisobot.pk}"
    assert yozuv.malumot["qabul_qilindi"] is False
    assert yozuv.kim == staff.username


def test_AVTOMATIK_filtr_TIZIM_nomidan_yoziladi():
    from apps.common.spam import bahola

    muammo = ComplaintFactory()
    baho = bahola(honeypot="", vaqt="", matn="matn")

    avtomatik_belgilash(target=muammo, baho=baho)

    yozuv = AuditLog.objects.get(action=AuditAction.AVTOMATIK_BELGI)
    assert yozuv.kim == "tizim"
    assert yozuv.malumot["ball"] == baho.ball
    assert yozuv.malumot["sabablar"] == baho.sabablar


def test_chora_SAQLANSA_ikkinchi_yozuv_QOSHILMAYDI(staff, user_factory):
    """Signal `created` ni tekshiradi: jurnal faqat QO'SHILADI."""
    muammo = ComplaintFactory()
    shikoyat(target=muammo, reporter=user_factory())
    chora = qaror_qabul_qilish(
        moderator=staff, target=muammo, action=ModerationActionType.OGOHLANTIRISH
    )

    chora.note = "yangilandi"
    chora.save(update_fields=["note"])

    assert AuditLog.objects.filter(action=AuditAction.KONTENT_CHORA).count() == 1


# ===========================================================================
# Guard — yangi staff xizmati jurnalsiz qolmasin
# ===========================================================================
# ⚠️ Bu ro'yxat QO'LDA yuritiladi va bu ATAYLAB: pastdagi guard yangi
#    staff xizmati paydo bo'lganda YIQILADI va uni bu yerga qo'shishga
#    (ya'ni jurnal yozilishini tekshirishga) majbur qiladi.
JURNALGA_YOZADIGAN_XIZMATLAR = {
    "shikoyatni_yopish",
    "qaror_qabul_qilish",
    "qarorni_bekor_qilish",
}


def test_HAR_BIR_staff_xizmati_test_bilan_QOPLANGAN():
    """⚠️ Jurnalga yozishni unutish JIM xato: xizmat ishlaydi, faqat
    iz qolmaydi. Va bu aynan nizo chiqqanda ma'lum bo'ladi — ya'ni
    eng kech va eng qimmat paytda.

    Guard `services.py` dagi staff-himoyali funksiyalarni AST bilan
    topadi va har biri yuqoridagi ro'yxatda borligini talab qiladi.
    """
    manba = pathlib.Path("apps/moderation/services.py").read_text(encoding="utf-8")
    daraxt = ast.parse(manba)

    def staff_tekshiruvi_bormi(tugun: ast.FunctionDef) -> bool:
        for ichki in ast.walk(tugun):
            if (
                isinstance(ichki, ast.Call)
                and isinstance(ichki.func, ast.Name)
                and ichki.func.id == "_moderatorni_tekshirish"
            ):
                return True
            if isinstance(ichki, ast.Constant) and ichki.value == "is_staff":
                return True
        return False

    topilgan = {
        t.name
        for t in daraxt.body
        if isinstance(t, ast.FunctionDef)
        and not t.name.startswith("_")
        and staff_tekshiruvi_bormi(t)
    }

    assert topilgan == JURNALGA_YOZADIGAN_XIZMATLAR, (
        "Staff xizmatlari ro'yxati o'zgardi.\n"
        f"  Kodda: {sorted(topilgan)}\n"
        f"  Testda: {sorted(JURNALGA_YOZADIGAN_XIZMATLAR)}\n"
        "Yangi xizmat qo'shilgan bo'lsa: u AuditLog ga yozishini "
        "tekshiradigan test yozing va ro'yxatga qo'shing."
    )


# ===========================================================================
# Staff sahifasi
# ===========================================================================
def test_jurnal_ODDIY_foydalanuvchiga_404(auth_client, anonymous_client):
    assert anonymous_client.get(JURNAL_URL).status_code == 404
    assert auth_client.get(JURNAL_URL).status_code == 404


def test_jurnal_STAFF_ga_korinadi(staff_client, staff):
    audit(action=AuditAction.SHIKOYAT_YOPILDI, obyekt="shikoyat #7", actor=staff)

    matn = staff_client.get(JURNAL_URL).content.decode()

    assert "Audit jurnali" in matn
    assert "shikoyat #7" in matn
    assert staff.username in matn


def test_jurnal_HARAKAT_boyicha_filtrlanadi(staff_client):
    audit(action=AuditAction.SHIKOYAT_YOPILDI, obyekt="shikoyat #7")
    audit(action=AuditAction.AVTOMATIK_BELGI, obyekt="muammo #9")

    matn = staff_client.get(
        JURNAL_URL, {"harakat": AuditAction.AVTOMATIK_BELGI}
    ).content.decode()

    assert "muammo #9" in matn
    assert "shikoyat #7" not in matn


def test_NOMALUM_filtr_hammasini_korsatadi(staff_client):
    """Qo'lda yozilgan manzil sahifani buzmasin."""
    audit(action=AuditAction.SHIKOYAT_YOPILDI, obyekt="shikoyat #7")

    javob = staff_client.get(JURNAL_URL, {"harakat": "bunday-yoq"})

    assert javob.status_code == 200
    assert "shikoyat #7" in javob.content.decode()


def test_jurnal_SAHIFALANADI(staff_client):
    from apps.moderation.views import JURNAL_SAHIFA

    for i in range(JURNAL_SAHIFA + 5):
        audit(action=AuditAction.SHIKOYAT_YOPILDI, obyekt=f"shikoyat #{i}")

    birinchi = staff_client.get(JURNAL_URL)
    ikkinchi = staff_client.get(JURNAL_URL, {"sahifa": 2})

    assert len(birinchi.context["sahifa"].object_list) == JURNAL_SAHIFA
    assert len(ikkinchi.context["sahifa"].object_list) == 5


def test_jurnal_YANGISIDAN_ESKISIGA(staff_client):
    audit(action=AuditAction.SHIKOYAT_YOPILDI, obyekt="birinchi")
    audit(action=AuditAction.SHIKOYAT_YOPILDI, obyekt="ikkinchi")

    yozuvlar = list(staff_client.get(JURNAL_URL).context["sahifa"])

    assert [y.obyekt for y in yozuvlar] == ["ikkinchi", "birinchi"]


def test_jurnalda_TAHRIRLASH_tugmasi_YOQ(staff_client):
    """⚠️ Bor tugmani bir kuni ishlatib qo'yishadi — interfeysda
    o'zgartirish yo'li umuman bo'lmasligi kerak."""
    audit(action=AuditAction.SHIKOYAT_YOPILDI, obyekt="shikoyat #7")

    matn = staff_client.get(JURNAL_URL).content.decode()

    assert "<form" not in matn.split('id="main"')[1]
    for soz in ("O'chirish", "Tahrirlash", "Bekor qilish"):
        assert soz not in matn.split('id="main"')[1]


def test_jurnal_sorovlari_YOZUVLAR_soniga_BOGLIQ_EMAS(staff_client):
    """D1-T14 tartibi: bog'liqlik tekshiriladi, qat'iy son emas."""
    from django.db import connection, reset_queries
    from django.test.utils import CaptureQueriesContext

    def sorovlar() -> int:
        staff_client.get(JURNAL_URL)
        reset_queries()
        with CaptureQueriesContext(connection) as ctx:
            assert staff_client.get(JURNAL_URL).status_code == 200
        return len(ctx)

    for i in range(3):
        audit(action=AuditAction.SHIKOYAT_YOPILDI, obyekt=f"a{i}")
    kam = sorovlar()

    for i in range(30):
        audit(action=AuditAction.KONTENT_CHORA, obyekt=f"b{i}")
    kop = sorovlar()

    assert kam == kop, f"3 yozuvda {kam}, 33 yozuvda {kop} so'rov — N+1"
