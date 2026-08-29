"""Moderatsiya — xizmat funksiyalari (D2-T1, D2-T2, D2-T5, D2-T6, D2-T7)."""

from __future__ import annotations

import logging

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction

from .audit import audit
from .models import (
    CHORA_HOLATI,
    ESKALATSIYA_CHEGARASI,
    AuditAction,
    ModerationAction,
    ModerationActionType,
    Report,
    ReportReason,
    ReportStatus,
)

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

    # ⚠️ Bu amal MODEL YARATMAYDI, ya'ni `ModerationAction`
    #    signali uni ushlamaydi — jurnalga OCHIQ yoziladi.
    audit(
        action=AuditAction.SHIKOYAT_YOPILDI,
        obyekt=f"shikoyat #{report.pk}",
        actor=moderator,
        izoh=report.resolution_note,
        qabul_qilindi=qabul_qilindi,
        maqsad=report.target_nomi,
    )
    return report


# ===========================================================================
# Moderator qarori (D2-T2)
# ===========================================================================
class BekorQilibBolmaydi(ValidationError):
    """Bu qarorni bekor qilib bo'lmaydi."""


def _maqsad_kwargs(target) -> dict:
    """`Complaint` yoki `Solution` ni FK nomiga aylantiradi."""
    from apps.complaints.models import Complaint

    return (
        {"complaint": target, "solution": None}
        if isinstance(target, Complaint)
        else {"complaint": None, "solution": target}
    )


def _moderatorni_tekshirish(moderator) -> None:
    if not getattr(moderator, "is_staff", False):
        raise PermissionDenied("Faqat moderator chora ko'ra oladi.")


@transaction.atomic
def qaror_qabul_qilish(
    *, moderator, target, action: str, izoh: str = ""
) -> ModerationAction:
    """Kontent ustidan chora ko'radi va uning BARCHA ochiq shikoyatlarini yopadi.

    ⚠️ BITTA QAROR — BARCHA SHIKOYATLAR. Bu D2-T2 ning "bitta ekranda
       qaror qabul qilinadi" qabul mezonining asosi.

       Django admin shikoyatlarni BIRMA-BIR ko'rsatadi: bitta postga 5 ta
       shikoyat kelsa, moderator bir xil kontentni 5 marta o'qib, 5 marta
       bir xil qaror qabul qiladi. Aslida qaror KONTENT haqida, shikoyat
       haqida emas — shuning uchun navbat obyekt bo'yicha guruhlanadi va
       qaror hammasini birdan yopadi.

    ⚠️ `RAD_ETISH` shikoyatlarni `RAD_ETILDI` qiladi, qolganlari
       `HAL_QILINDI`. Farq muhim: "shikoyat asossiz edi" va "shikoyat
       o'rinli edi, chora ko'rildi" — bu ikki xil ma'lumot va D2-T5
       (spam evristikasi) shikoyatchining aniqligini shu farqdan
       o'lchaydi.
    """
    from django.utils import timezone

    _moderatorni_tekshirish(moderator)

    if action == ModerationActionType.BEKOR_QILISH:
        raise ValueError("Bekor qilish uchun `qarorni_bekor_qilish()` ishlatiladi.")
    if action not in CHORA_HOLATI:
        raise ValueError(f"Noma'lum chora: {action}")

    kwargs = _maqsad_kwargs(target)
    izoh = izoh.strip()[:300]

    chora = ModerationAction.objects.create(
        moderator=moderator,
        action=action,
        target_author_id=target.author_id,
        note=izoh,
        oldingi_holat=target.moderation_status,
        **kwargs,
    )

    yangi_holat = CHORA_HOLATI[action]
    if yangi_holat is not None:
        target.moderation_status = yangi_holat
        # ⚠️ Izoh kontentga ham yoziladi: muallif "nega ko'rinmayapti?"
        #    degan savol bilan qolmasligi kerak (D1-T10 sahifasi buni
        #    ko'rsatadi).
        target.moderation_note = izoh
        target.save(
            update_fields=["moderation_status", "moderation_note", "updated_at"]
        )

    yopildi = (
        Report.objects.ochiq()
        .filter(**kwargs)
        .update(
            status=(
                ReportStatus.RAD_ETILDI
                if action == ModerationActionType.RAD_ETISH
                else ReportStatus.HAL_QILINDI
            ),
            resolved_by=moderator,
            resolved_at=timezone.now(),
            resolution_note=izoh,
            yopgan_chora=chora,
            updated_at=timezone.now(),
        )
    )

    log.info(
        "Chora: %s %s izoh=%r yopilgan_shikoyat=%s",
        action,
        chora.target_nomi,
        izoh[:60],
        yopildi,
    )
    return chora


@transaction.atomic
def qarorni_bekor_qilish(*, moderator, chora: ModerationAction) -> ModerationAction:
    """Qarorni ORQAGA QAYTARADI — yozuvni o'chirmasdan.

    ⚠️ NEGA O'CHIRMAYMIZ: jurnal tahrirlansa dalil bo'lishdan to'xtaydi.
       `KarmaEvent` da ham xuddi shu naqsh — kompensatsiya yozuvi.
       Qo'shimcha foydasi bor: "qaror qildi, keyin qaytarib oldi" ning
       o'zi ma'lumot. Agar bu tez-tez uchrasa, qoidalar tushunarsiz.

    ⚠️ Kontent `oldingi_holat` ga qaytariladi, `VISIBLE` ga EMAS:
       post yashirilishidan oldin allaqachon `PENDING` da turgan bo'lishi
       mumkin va uni jimgina ko'rinadigan qilib yuborish xato bo'lardi.

    Shu chora yopgan shikoyatlar ham navbatga QAYTADI — ular aslida
    ko'rib chiqilmagan.
    """
    _moderatorni_tekshirish(moderator)

    if not chora.qaytarilishi_mumkinmi:
        raise BekorQilibBolmaydi("Bekor qilishning o'zini bekor qilib bo'lmaydi.")
    if chora.bekor_qilinganmi:
        raise BekorQilibBolmaydi("Bu qaror allaqachon bekor qilingan.")

    target = chora.target
    kwargs = _maqsad_kwargs(target)

    qaytarish = ModerationAction.objects.create(
        moderator=moderator,
        action=ModerationActionType.BEKOR_QILISH,
        target_author_id=target.author_id,
        note=f"Bekor qilindi: {chora.get_action_display()}",
        oldingi_holat=target.moderation_status,
        bekor_qiladi=chora,
        **kwargs,
    )

    if chora.oldingi_holat and target.moderation_status != chora.oldingi_holat:
        target.moderation_status = chora.oldingi_holat
        target.moderation_note = ""
        target.save(
            update_fields=["moderation_status", "moderation_note", "updated_at"]
        )

    chora.yopilgan_shikoyatlar.update(
        status=ReportStatus.OCHIQ,
        resolved_by=None,
        resolved_at=None,
        resolution_note="",
        yopgan_chora=None,
    )

    log.info("Chora bekor qilindi: #%s %s", chora.pk, chora.target_nomi)
    return qaytarish


# ===========================================================================
# Avtomatik filtr (D2-T5)
# ===========================================================================
def avtomatik_belgilash(*, target, baho) -> Report | None:
    """Evristika shubhali topgan kontentni NAVBATGA qo'yadi.

    ⚠️⚠️ KONTENT YASHIRILMAYDI — mahsulot qarori (foydalanuvchi tanlagan).
       Shubhali post e'lon qilinadi va odamlar uni ko'radi; faqat
       moderator navbatiga qo'shimcha holat tushadi. Sabab
       `apps/common/spam.py` docstring'ida: yolg'on ijobiy holatning
       narxi bu yerda spamnikidan yuqori.

    ⚠️ NEGA ALOHIDA "SpamSignal" MODELI EMAS
       Navbat allaqachon `Report` ustiga qurilgan (D2-T2): guruhlash,
       tartiblash, choralar, bekor qilish — hammasi tayyor. Tizim
       shikoyati shu quvurga `reporter=None` bilan tushadi va butun
       mexanizmni bepul oladi. Ikkinchi model ikkinchi navbat, ikkinchi
       tartib mantig'i va ikkinchi unutiladigan joy degani bo'lardi.

    `reporter=None` — "shikoyatchi" o'chirilgan hisob EMAS, TIZIM.
    Navbat buni ajratib ko'rsatadi (`Holat.avtomatikmi`).
    """
    if not baho.shubhalimi:
        return None

    kwargs = _maqsad_kwargs(target)

    # Bitta obyektga bitta OCHIQ tizim shikoyati yetarli: tahrirlash
    # har safar yangi qator yaratsa, navbat bir xil holat bilan
    # to'lib ketardi.
    # ⚠️ `reason` ham filtrga kiradi: inqiroz shikoyati (D2-T6) ham
    #    `reporter=None` bilan yoziladi. Sababsiz qidirsak, spam
    #    izohi inqiroz izohining ustiga yozilardi va navbatdagi
    #    eng muhim signal yo'qolardi.
    mavjud = (
        Report.objects.ochiq()
        .filter(reporter__isnull=True, reason=ReportReason.SPAM, **kwargs)
        .first()
    )
    if mavjud is not None:
        mavjud.comment = baho.izoh[:2000]
        mavjud.save(update_fields=["comment", "updated_at"])
        return mavjud

    hisobot = Report.objects.create(
        reporter=None,
        reason=ReportReason.SPAM,
        comment=baho.izoh[:2000],
        **kwargs,
    )
    # ⚠️ `actor=None` — bu TIZIM harakati, odam emas. Jurnalda
    #    u "tizim" deb ko'rinadi va moderator qarorlaridan
    #    ajralib turadi.
    audit(
        action=AuditAction.AVTOMATIK_BELGI,
        obyekt=hisobot.target_nomi,
        izoh=baho.izoh,
        ball=baho.ball,
        sabablar=baho.sabablar,
    )
    return hisobot


# ===========================================================================
# Inqirozli kontent (D2-T6)
# ===========================================================================
@transaction.atomic
def inqirozni_belgilash(*, target, matnlar: list[str]) -> Report | None:
    """Inqiroz belgisi topilsa kontentni navbat TEPASIGA chiqaradi.

    ⚠️⚠️ KONTENT O'CHIRILMAYDI, YASHIRILMAYDI VA MUALLIF HECH QANDAY
       OGOHLANTIRISH OLMAYDI. Task tavsifi buni ochiq aytadi: "jim
       o'chirish eng yomon variant — u odamni yakkalaydi".

       Bu funksiya faqat ikki narsa qiladi:
         1. `inqiroz_aniqlandi` bayrog'ini qo'yadi (sahifada yordam
            ma'lumoti chiqishi uchun);
         2. `XAVF` sababli TIZIM shikoyatini yozadi — D2-T2 navbati
            `XAVF` ni HAR DOIM eng tepaga qo'yadi, ya'ni "15 daqiqa
            ichida moderatorga ko'rinadi" qabul mezoni bajariladi
            (amalda darhol).

    ⚠️ Aniqlash TASHXIS EMAS. Yolg'on ijobiy ataylab ko'p (ro'yxat keng
       — `apps/common/inqiroz.py`), chunki o'tkazib yuborishning narxi
       beqiyos yuqori. Qaror moderatorda: `/moderatsiya/qollanma/`.
    """
    from apps.common.inqiroz import topilgan_belgilar

    belgilar = topilgan_belgilar(*matnlar)
    if not belgilar:
        return None

    if not target.inqiroz_aniqlandi:
        target.inqiroz_aniqlandi = True
        target.save(update_fields=["inqiroz_aniqlandi", "updated_at"])

    kwargs = _maqsad_kwargs(target)
    izoh = "Inqiroz belgisi: " + "; ".join(belgilar[:5])

    mavjud = (
        Report.objects.ochiq()
        .filter(reporter__isnull=True, reason=ReportReason.XAVF, **kwargs)
        .first()
    )
    if mavjud is not None:
        return mavjud

    hisobot = Report.objects.create(
        reporter=None,
        reason=ReportReason.XAVF,
        comment=izoh[:2000],
        **kwargs,
    )
    audit(
        action=AuditAction.INQIROZ_ANIQLANDI,
        obyekt=hisobot.target_nomi,
        izoh=izoh,
        belgilar=belgilar,
    )
    log.warning("INQIROZ BELGISI: %s (%s)", hisobot.target_nomi, len(belgilar))
    return hisobot
