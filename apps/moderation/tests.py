"""Shikoyat modeli va oqimi (D2-T1)."""

from __future__ import annotations

import pytest
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.urls import reverse

from apps.common.models import ModerationStatus
from apps.complaints.factories import ComplaintFactory
from apps.moderation.models import (
    ESKALATSIYA_CHEGARASI,
    Report,
    ReportReason,
    ReportStatus,
)
from apps.moderation.services import (
    AllaqachonShikoyatQilingan,
    eskalatsiya_qilinganmi,
    shikoyat_yuborish,
    shikoyatni_yopish,
)
from apps.solutions.factories import SolutionFactory

pytestmark = pytest.mark.django_db


def dard_url(muammo) -> str:
    return reverse("dard_shikoyat", args=[muammo.pk])


# ===========================================================================
# Model — baza darajasidagi kafolatlar
# ===========================================================================
def test_bir_foydalanuvchi_bir_marta_shikoyat_qiladi(user):
    """Qabul mezoni: "bir foydalanuvchi bitta obyektga bir marta".

    ⚠️ Kodda tekshirish yetarli emas: ikki bir vaqtli so'rov ikkalasi
       ham "yo'q ekan" deb ko'radi.
    """
    muammo = ComplaintFactory()
    Report.objects.create(reporter=user, complaint=muammo, reason=ReportReason.SPAM)

    with pytest.raises(IntegrityError), transaction.atomic():
        Report.objects.create(
            reporter=user, complaint=muammo, reason=ReportReason.HAQORAT
        )


def test_bir_foydalanuvchi_IKKI_XIL_obyektga_shikoyat_qila_oladi(user):
    muammo = ComplaintFactory()
    yechim = SolutionFactory()

    Report.objects.create(reporter=user, complaint=muammo, reason=ReportReason.SPAM)
    Report.objects.create(reporter=user, solution=yechim, reason=ReportReason.SPAM)

    assert Report.objects.count() == 2


def test_MAQSADSIZ_shikoyat_YOZILMAYDI(user):
    """⚠️ Ikkalasi ham `NULL` bo'lsa — "hech kimga tegishli bo'lmagan"
    shikoyat paydo bo'lardi va navbat uni qayerga qo'yishni bilmasdi."""
    with pytest.raises(IntegrityError), transaction.atomic():
        Report.objects.create(reporter=user, reason=ReportReason.SPAM)


def test_IKKI_maqsadli_shikoyat_YOZILMAYDI(user):
    with pytest.raises(IntegrityError), transaction.atomic():
        Report.objects.create(
            reporter=user,
            complaint=ComplaintFactory(),
            solution=SolutionFactory(),
            reason=ReportReason.SPAM,
        )


def test_shikoyatchi_ochirilsa_shikoyat_QOLADI(user):
    """⚠️ `SET_NULL`: shikoyat moderator qarorining asosi va D2-T7
    auditining bir qismi — hisob o'chgani bilan yo'qolmasligi kerak."""
    muammo = ComplaintFactory()
    Report.objects.create(reporter=user, complaint=muammo, reason=ReportReason.SPAM)

    user.delete()

    hisobot = Report.objects.get()
    assert hisobot.reporter is None
    assert hisobot.complaint == muammo


def test_XAVF_sababi_SHOSHILINCH_deb_belgilanadi(user):
    """⚠️ Odam hayoti haqidagi signal spam bilan bir navbatda turmasin
    (D2-T6 shu signalga ulanadi)."""
    oddiy = Report(reason=ReportReason.SPAM)
    xavfli = Report(reason=ReportReason.XAVF)

    assert oddiy.shoshilinchmi is False
    assert xavfli.shoshilinchmi is True


# ===========================================================================
# Xizmat
# ===========================================================================
def test_shikoyat_yoziladi(user):
    muammo = ComplaintFactory()

    hisobot, eskalatsiya = shikoyat_yuborish(
        reporter=user, complaint=muammo, reason=ReportReason.SPAM, comment="  reklama  "
    )

    assert hisobot.reporter == user
    assert hisobot.complaint == muammo
    assert hisobot.comment == "reklama"  # bo'sh joylar kesiladi
    assert hisobot.status == ReportStatus.OCHIQ
    assert eskalatsiya is False


def test_OZ_kontentiga_shikoyat_qilib_bolmaydi(user):
    """⚠️ O'z postini "shikoyat" qilib navbatni to'ldirish ma'nosiz —
    uni o'chirish kerak."""
    ozimniki = ComplaintFactory(author=user)

    with pytest.raises(PermissionDenied):
        shikoyat_yuborish(reporter=user, complaint=ozimniki, reason=ReportReason.SPAM)

    assert Report.objects.count() == 0


def test_takroriy_shikoyat_TUSHUNARLI_xato_beradi(user):
    """⚠️ `IntegrityError` (500) emas, ma'noli xabar."""
    muammo = ComplaintFactory()
    shikoyat_yuborish(reporter=user, complaint=muammo, reason=ReportReason.SPAM)

    with pytest.raises(AllaqachonShikoyatQilingan, match="allaqachon"):
        shikoyat_yuborish(reporter=user, complaint=muammo, reason=ReportReason.HAQORAT)


def test_maqsadsiz_chaqiruv_XATO(user):
    with pytest.raises(ValueError, match="Aynan bitta"):
        shikoyat_yuborish(reporter=user, reason=ReportReason.SPAM)


# ===========================================================================
# Eskalatsiya (qabul mezoni)
# ===========================================================================
def test_N_ta_shikoyat_NAVBATGA_kotaradi(user_factory):
    """Qabul mezoni: "N ta shikoyat avtomatik navbatga ko'taradi"."""
    muammo = ComplaintFactory()

    for i in range(ESKALATSIYA_CHEGARASI):
        _, eskalatsiya = shikoyat_yuborish(
            reporter=user_factory(), complaint=muammo, reason=ReportReason.SPAM
        )
        kutilgan = i + 1 >= ESKALATSIYA_CHEGARASI
        assert eskalatsiya is kutilgan

    assert eskalatsiya_qilinganmi(complaint=muammo) is True
    assert Report.objects.eskalatsiya_qilinganlar().count() == ESKALATSIYA_CHEGARASI


def test_chegaradan_KAM_shikoyat_kotarmaydi(user_factory):
    muammo = ComplaintFactory()
    for _ in range(ESKALATSIYA_CHEGARASI - 1):
        shikoyat_yuborish(
            reporter=user_factory(), complaint=muammo, reason=ReportReason.SPAM
        )

    assert eskalatsiya_qilinganmi(complaint=muammo) is False
    assert Report.objects.eskalatsiya_qilinganlar().count() == 0


def test_ESKALATSIYA_kontentni_YASHIRMAYDI(user_factory):
    """⚠️⚠️ MAHSULOT QARORI — eng muhim testlardan biri.

    Dard.uz'da odamlar eng og'ir shaxsiy holatlarini yozadi. Uchta
    kelishib olgan odam istalgan postni o'chirib tashlay olsa, bu
    qurolga aylanadi — va zarba aynan eng himoyasiz foydalanuvchiga
    tegadi.

    Shuning uchun shikoyat NAVBATDAGI o'rinni o'zgartiradi, KO'RINISHNI
    emas. Shoshilinch olib tashlash moderator qo'lida qoladi (D2-T2).
    """
    muammo = ComplaintFactory()
    for _ in range(ESKALATSIYA_CHEGARASI + 2):
        shikoyat_yuborish(
            reporter=user_factory(), complaint=muammo, reason=ReportReason.HAQORAT
        )

    muammo.refresh_from_db()
    assert muammo.moderation_status == ModerationStatus.VISIBLE
    assert muammo in list(type(muammo).objects.visible())


def test_YOPILGAN_shikoyatlar_eskalatsiyaga_qoshilmaydi(user_factory, staff):
    """Moderator ko'rib chiqqan shikoyat navbatni band qilib turmasin."""
    muammo = ComplaintFactory()
    hisobotlar = [
        shikoyat_yuborish(
            reporter=user_factory(), complaint=muammo, reason=ReportReason.SPAM
        )[0]
        for _ in range(ESKALATSIYA_CHEGARASI)
    ]
    assert eskalatsiya_qilinganmi(complaint=muammo) is True

    shikoyatni_yopish(report=hisobotlar[0], moderator=staff, qabul_qilindi=False)

    assert eskalatsiya_qilinganmi(complaint=muammo) is False


# ===========================================================================
# Moderator qarori
# ===========================================================================
def test_shikoyatni_yopish(user, staff):
    muammo = ComplaintFactory()
    hisobot, _ = shikoyat_yuborish(
        reporter=user, complaint=muammo, reason=ReportReason.SPAM
    )

    shikoyatni_yopish(
        report=hisobot, moderator=staff, qabul_qilindi=True, izoh="Reklama, o'chirildi"
    )

    hisobot.refresh_from_db()
    assert hisobot.status == ReportStatus.HAL_QILINDI
    assert hisobot.resolved_by == staff
    assert hisobot.resolved_at is not None
    assert hisobot.resolution_note == "Reklama, o'chirildi"


def test_ODDIY_foydalanuvchi_shikoyatni_yopa_olmaydi(user, other_user):
    muammo = ComplaintFactory()
    hisobot, _ = shikoyat_yuborish(
        reporter=user, complaint=muammo, reason=ReportReason.SPAM
    )

    with pytest.raises(PermissionDenied):
        shikoyatni_yopish(report=hisobot, moderator=other_user, qabul_qilindi=True)


def test_shikoyat_ADMINDA_ochirilmaydi():
    """⚠️ Shikoyat audit zanjirining bir qismi (D2-T7).

    Noto'g'ri shikoyat "rad etildi" deb yopiladi, yo'q qilinmaydi: nizo
    chiqsa "kim, qachon, nima uchun shikoyat qilgan" savoliga javob
    qolishi kerak.
    """
    from django.contrib import admin

    from apps.moderation.admin import ReportAdmin

    admin_obj = ReportAdmin(Report, admin.site)
    assert admin_obj.has_delete_permission(None) is False


# ===========================================================================
# Ko'rinishlar
# ===========================================================================
def test_shikoyat_sahifasi_kirish_talab_qiladi(client):
    muammo = ComplaintFactory()
    javob = client.get(dard_url(muammo))

    assert javob.status_code == 302
    assert reverse("login") in javob["Location"]


def test_shikoyat_sahifasi_ochiladi(auth_client):
    muammo = ComplaintFactory(title="Shikoyat qilinadigan post")
    matn = auth_client.get(dard_url(muammo)).content.decode()

    assert "Shikoyat yuborish" in matn
    assert "Shikoyat qilinadigan post" in matn
    # ⚠️ Django shablonda `'` ni `&#x27;` ga aylantiradi — yorliqlarni
    #    xom holda qidirish yolg'on xato beradi.
    from django.utils.html import escape

    for _, yorliq in ReportReason.choices:
        assert escape(yorliq) in matn


def test_shikoyat_yuboriladi(auth_client, user):
    muammo = ComplaintFactory()

    javob = auth_client.post(
        dard_url(muammo), {"reason": ReportReason.HAQORAT, "comment": "haqorat bor"}
    )

    assert javob.status_code == 302
    hisobot = Report.objects.get()
    assert hisobot.reporter == user
    assert hisobot.reason == ReportReason.HAQORAT


def test_SABABSIZ_forma_rad_etiladi(auth_client):
    muammo = ComplaintFactory()
    javob = auth_client.post(dard_url(muammo), {"comment": "izoh"})

    assert javob.status_code == 200  # qayta render
    assert Report.objects.count() == 0


def test_takroriy_shikoyat_formada_XATO_korsatadi(auth_client, user):
    muammo = ComplaintFactory()
    auth_client.post(dard_url(muammo), {"reason": ReportReason.SPAM})

    javob = auth_client.post(dard_url(muammo), {"reason": ReportReason.SPAM})

    assert javob.status_code == 200
    assert "allaqachon" in javob.content.decode()
    assert Report.objects.count() == 1


def test_OZ_postiga_shikoyat_403(auth_client, user):
    ozimniki = ComplaintFactory(author=user)
    javob = auth_client.post(dard_url(ozimniki), {"reason": ReportReason.SPAM})

    assert javob.status_code == 403
    assert Report.objects.count() == 0


def test_YASHIRILGAN_postga_shikoyat_qilib_bolmaydi(auth_client):
    """⚠️ U allaqachon navbatda yoki olib tashlangan."""
    muammo = ComplaintFactory(moderation_status=ModerationStatus.HIDDEN)
    assert auth_client.get(dard_url(muammo)).status_code == 404


def test_yechimga_shikoyat_ishlaydi(auth_client, user):
    yechim = SolutionFactory()

    javob = auth_client.post(
        reverse("yechim_shikoyat", args=[yechim.pk]), {"reason": ReportReason.SPAM}
    )

    assert javob.status_code == 302
    assert Report.objects.get().solution == yechim


def test_OCHIQ_YONALTIRISHGA_yol_yoq(auth_client):
    muammo = ComplaintFactory()
    javob = auth_client.post(
        dard_url(muammo),
        {"reason": ReportReason.SPAM, "next": "https://yovuz.example/"},
    )

    assert javob["Location"] == muammo.get_absolute_url()


def test_ESKALATSIYA_foydalanuvchiga_AYTILMAYDI(auth_client, user_factory):
    """⚠️ "Yana 2 ta shikoyat kerak" degan xabar odamlarni kelishib
    shikoyat qilishga undardi — tizimni o'yinga aylantirardi."""
    muammo = ComplaintFactory()
    for _ in range(ESKALATSIYA_CHEGARASI - 1):
        shikoyat_yuborish(
            reporter=user_factory(), complaint=muammo, reason=ReportReason.SPAM
        )

    javob = auth_client.post(
        dard_url(muammo), {"reason": ReportReason.SPAM}, follow=True
    )

    # ⚠️ Xabarning O'Z MATNI tekshiriladi, sahifa HTML'i emas: birinchi
    #    versiyada "3 soni javobda yo'q" deb qaralgan edi va u CSS sinf
    #    nomlaridagi (`gap-3`, `mb-3`) raqamlarga urilib yiqilardi.
    xabarlar = [str(m) for m in javob.context["messages"]]

    assert xabarlar == ["Shikoyatingiz yuborildi. Moderatorlar ko'rib chiqadi."]
    # ⚠️ HTML darajasida ham: kontekstda bo'lishi sahifada ko'rinishini
    #    ANGLATMAYDI — D2-T1 gacha aynan shu halqa uzilgan edi.
    assert "Shikoyatingiz yuborildi" in javob.content.decode()
    assert not any(belgi.isdigit() for x in xabarlar for belgi in x), (
        "Xabarda raqam bor — eskalatsiya chegarasi oshkor bo'lmasin"
    )


# ===========================================================================
# Shablon
# ===========================================================================
def test_batafsil_sahifada_shikoyat_HAVOLASI_bor(auth_client):
    muammo = ComplaintFactory()
    SolutionFactory(complaint=muammo)

    matn = auth_client.get(muammo.get_absolute_url()).content.decode()

    assert f"/shikoyat/dard/{muammo.pk}/" in matn
    assert "/shikoyat/yechim/" in matn


def test_OZ_postida_shikoyat_havolasi_YOQ(auth_client, user):
    ozimniki = ComplaintFactory(author=user)
    matn = auth_client.get(ozimniki.get_absolute_url()).content.decode()

    assert f"/shikoyat/dard/{ozimniki.pk}/" not in matn


def test_MEHMONGA_shikoyat_havolasi_YOQ(client):
    muammo = ComplaintFactory()
    matn = client.get(muammo.get_absolute_url()).content.decode()

    assert "/shikoyat/" not in matn


def test_SOXTA_toast_qolmagan():
    """⚠️ GUARD: maketda `data-toast="Shikoyat yuborildi"` tugmasi bor edi —
    modal ochib, serverga hech nima yubormasdan "yuborildi" deb yozardi.
    """
    import re
    from pathlib import Path

    from django.conf import settings

    IZOH = re.compile(r"{%\s*comment\s*%}.*?{%\s*endcomment\s*%}", re.DOTALL)
    for yol in (Path(settings.BASE_DIR) / "templates").rglob("*.html"):
        matn = IZOH.sub("", yol.read_text(encoding="utf-8"))
        assert 'data-toast="Shikoyat yuborildi"' not in matn, (
            f"{yol.name} da maketning soxta shikoyat tugmasi qolgan"
        )
