"""Moderatsiya — xizmat funksiyalari (D2-T1)."""

from __future__ import annotations

import logging

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction

from .models import ESKALATSIYA_CHEGARASI, Report, ReportStatus

log = logging.getLogger(__name__)


class AllaqachonShikoyatQilingan(ValidationError):
    """Bu foydalanuvchi shu obyektga allaqachon shikoyat qilgan."""


@transaction.atomic
def shikoyat_yuborish(
    *, reporter, complaint=None, solution=None, reason: str, comment: str = ""
) -> tuple[Report, bool]:
    """Shikoyat yozadi. `(report, eskalatsiya_boldimi)` qaytaradi.

    ⚠️ O'Z KONTENTIGA SHIKOYAT QILIB BO'LMAYDI
       Foydalanuvchi o'z postini "shikoyat" qilib navbatni to'ldirishi
       ma'nosiz. O'z postini olib tashlash uchun uni O'CHIRISH kerak.

    ⚠️ TAKRORIY SHIKOYAT — 400, 500 EMAS
       Noyoblik cheklovi baza darajasida (poyga holatiga qarshi), lekin
       foydalanuvchi tushunarli xabar ko'rishi kerak. `IntegrityError`
       ushlanadi va ma'noli xatoga aylantiriladi.

    ⚠️ KONTENT AVTOMATIK YASHIRILMAYDI — sabab `Report` docstring'ida.
       Eskalatsiya faqat NAVBATDAGI o'rinni o'zgartiradi.
    """
    if (complaint is None) == (solution is None):
        raise ValueError("Aynan bitta maqsad berilishi kerak")

    maqsad = complaint or solution
    if maqsad.author_id is not None and maqsad.author_id == getattr(
        reporter, "pk", None
    ):
        raise PermissionDenied("O'z kontentingizga shikoyat qila olmaysiz.")

    try:
        with transaction.atomic():
            report = Report.objects.create(
                reporter=reporter,
                complaint=complaint,
                solution=solution,
                reason=reason,
                comment=comment.strip(),
            )
    except IntegrityError as exc:
        raise AllaqachonShikoyatQilingan(
            "Siz bu kontentga allaqachon shikoyat qilgansiz. "
            "Moderatorlar uni ko'rib chiqmoqda."
        ) from exc

    ochiq_soni = (
        Report.objects.ochiq().filter(complaint=complaint, solution=solution).count()
    )
    eskalatsiya = ochiq_soni >= ESKALATSIYA_CHEGARASI

    log.info(
        "Shikoyat: %s sabab=%s ochiq=%s eskalatsiya=%s",
        report.target_nomi,
        reason,
        ochiq_soni,
        eskalatsiya,
    )
    return report, eskalatsiya


def eskalatsiya_qilinganmi(*, complaint=None, solution=None) -> bool:
    """Obyekt navbatda yuqoriga ko'tarilganmi (D2-T1 qabul mezoni)."""
    return (
        Report.objects.ochiq().filter(complaint=complaint, solution=solution).count()
        >= ESKALATSIYA_CHEGARASI
    )


@transaction.atomic
def shikoyatni_yopish(
    *, report: Report, moderator, qabul_qilindi: bool, izoh: str = ""
) -> Report:
    """Moderator qarorini yozadi.

    ⚠️ D2-T2 (navbat interfeysi) shu funksiyani chaqiradi. U hozir
       yozildi, chunki `Report` holatini ko'rinishlar to'g'ridan-to'g'ri
       o'zgartirsa, "kim yopdi?" ma'lumoti bir joyda unutilardi.

    ⚠️ Kontent ustidagi CHORA (yashirish, o'chirish) bu yerda EMAS: u
       alohida qaror va D2-T2/D2-T7 da audit jurnaliga tushadi.
       Shikoyatni yopish faqat "ko'rib chiqildi" degani.
    """
    from django.utils import timezone

    if not getattr(moderator, "is_staff", False):
        raise PermissionDenied("Faqat moderator shikoyatni yopa oladi.")

    report.status = (
        ReportStatus.HAL_QILINDI if qabul_qilindi else ReportStatus.RAD_ETILDI
    )
    report.resolved_by = moderator
    report.resolved_at = timezone.now()
    report.resolution_note = izoh.strip()[:300]
    report.save(
        update_fields=[
            "status",
            "resolved_by",
            "resolved_at",
            "resolution_note",
            "updated_at",
        ]
    )
    return report
