"""Moderatsiya — xizmat funksiyalari (D2-T1, D2-T2, D2-T5, D2-T6, D2-T7)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.gamification.services import (
    kontent_karmasini_qaytarish,
    kontent_karmasini_tiklash,
)

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


def _karmani_moslash(target) -> None:
    """Kontent ko'rinishi o'zgargach yechim karmasini moslaydi (D3-T1).

    ⚠️ QABUL MEZONI (D3-T1): "kontent o'chirilsa teskari hodisa yoziladi".
       Bugungi kunda kontent ko'rinmay qolishining YAGONA yo'li —
       moderatsiya chorasi (muallif uchun o'chirish ko'rinishi hali
       yozilmagan). O'sha ko'rinish qo'shilganda U HAM shu funksiyani
       chaqirishi kerak — signal qo'yilmagan, chunki `bulk_create` va
       `QuerySet.update()` da signal ishlamaydi (D1-T10 dagi bir xil
       qaror).

    ⚠️ FAQAT YECHIM: dard karma bermaydi (`KARMA_QIYMATLARI` izohi),
       ya'ni qaytariladigan narsa ham yo'q.

    ⚠️ IKKALA YO'L HAM IDEMPOTENT, shuning uchun bu funksiyani HAR
       qarordan keyin so'zsiz chaqirish mumkin: "ogohlantirish" yoki
       "rad etish" ko'rinishni o'zgartirmaydi va tiklash hech nima
       yozmaydi (kompensatsiya yig'indisi allaqachon nol).
    """
    from apps.solutions.models import Solution

    if not isinstance(target, Solution):
        return

    korinadimi = target.is_publicly_visible and not target.is_deleted
    if korinadimi:
        kontent_karmasini_tiklash(solution=target)
    else:
        kontent_karmasini_qaytarish(solution=target)


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

    # ⚠️ KARMA (D3-T1): kontent ko'rinmay qolsa, u bergan ball
    #    QAYTARILADI — aks holda olib tashlangan yechim muallifga ball
    #    berib turaverardi va "suiisteʼmolni orqaga qaytarib bo'lmaydi"
    #    muammosi saqlanib qolardi (D3-T1 `nega` bo'limi).
    _karmani_moslash(target)

    # ⚠️ UCH OGOHLANTIRISH (D2-T11) — moderator sanab o'tirmasin.
    #    Chora yozilgandan KEYIN chaqiriladi: sanoq shu chorani ham
    #    hisobga olishi kerak.
    eskalatsiyani_tekshirish(moderator=moderator, user=target.author)

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

    # ⚠️ KARMA QAYTARIB BERILADI (D3-T1). Moderatorning xatosi
    #    foydalanuvchining ballida abadiy qolmasligi kerak — bu D2-T11
    #    dagi "bekor qilingan chora qoidabuzarlik sanalmaydi"
    #    qoidasining karmadagi ko'rinishi.
    #
    # ⚠️ Kontent `oldingi_holat` ga qaytadi va u KO'RINADIGAN bo'lmasligi
    #    ham mumkin (masalan `PENDING`) — shuning uchun bu yerda
    #    "so'zsiz tiklash" emas, `_karmani_moslash()` chaqiriladi:
    #    u JORIY holatga qaraydi.
    _karmani_moslash(target)

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


# ===========================================================================
# Foydalanuvchini cheklash — uch ogohlantirish (D2-T11)
# ===========================================================================
# ⚠️ QOIDABUZARLIK choralari: shular sanaladi.
#    `RAD_ETISH` yo'q — u "qoidabuzarlik yo'q" degani.
#    `BEKOR_QILISH` ham yo'q — u chora emas, chorani qaytarish.
QOIDABUZARLIK_CHORALARI = (
    ModerationActionType.OGOHLANTIRISH,
    ModerationActionType.YASHIRISH,
    ModerationActionType.OLIB_TASHLASH,
)


def qoidabuzarliklar_soni(*, user) -> int:
    """Foydalanuvchiga nisbatan ko'rilgan choralar soni.

    ⚠️ BEKOR QILINGAN chora SANALMAYDI. Moderator xato qilib, keyin
       qaytarib olgan bo'lsa, u odamni jazolashda hisobga olinmasligi
       kerak — aks holda moderatorning xatosi foydalanuvchining
       "jinoyat tarixiga" aylanardi.
    """
    return (
        ModerationAction.objects.filter(
            target_author=user, action__in=QOIDABUZARLIK_CHORALARI
        )
        .filter(bekor_qilishlar__isnull=True)
        .count()
    )


def yangi_muddat(*, user, kun: int) -> datetime:
    """Cheklov muddati: mavjud cheklov USTIGA yangisi qo'yilganda nima bo'ladi.

    ⚠️⚠️ BU FUNKSIYA MAVJUDLIGINING SABABI — JIM YUMSHATISH XAVFI.

       Sodda yozuv `timezone.now() + kun` bo'lardi va u KAMAYTIRISHI
       mumkin: moderator odamni 30 kunga cheklagan bo'lsa-yu, ikki
       kundan keyin unga standart 7 kunlik cheklov tushsa, muddat
       28 kunga QISQARARDI. Ya'ni YANGI JAZO jazoni yengillashtirardi.

       Kod boshqa joyda bu xavfdan allaqachon himoyalangan:
       `eskalatsiyani_tekshirish()` doimiy blokni vaqtinchalikka
       TUSHIRMAYDI. Bu yerda esa o'sha qoidaning vaqtinchalik
       cheklovlar orasidagi ko'rinishi.

    Kirish:
      `user` — cheklanayotgan foydalanuvchi. `user.banned_until`
               `None` (cheklov yo'q yoki doimiy) yoki `datetime`
               bo'lishi mumkin, va u O'TIB KETGAN ham bo'lishi
               mumkin (muddati tugagan cheklov bayrog'i tozalanmaydi).
      `kun`   — so'ralayotgan yangi cheklov uzunligi, kunlarda.

    Qaytaradi: yangi `banned_until` (aware `datetime`).
    """
    hozir = timezone.now()
    soralgan = hozir + timedelta(days=kun)
    mavjud = user.banned_until

    # ⚠️ MUDDAT HECH QACHON QISQARMAYDI, lekin QO'SHILMAYDI ham.
    #
    #    Uch yo'l bor edi va uchalasi ham asosli:
    #      1. `max(mavjud, soralgan)` — TANLANGAN.
    #      2. Qolgan vaqt USTIGA qo'shish: muddatlar tez o'sib
    #         ketardi (30 + 7 + 7 + 7) va amalda doimiy blokka
    #         aylanardi — lekin "doimiy" deb ATALMAGAN holda.
    #         Yashirin doimiy blok esa apellyatsiyani ham,
    #         tushuntirishni ham imkonsiz qiladi.
    #      3. Doimiyga ko'tarish: eng qattiq va `CHEKLOV_MUDDATI_KUN`
    #         sozlamasini ma'nosiz qilardi.
    #
    #    `max` eng kam ajablantiradi: muddat FAQAT uzayadi, va
    #    "doimiy" degan qaror ochiq qabul qilinadi (`doimiy=True`),
    #    jimgina yig'ilib qolmaydi.
    #
    # ⚠️ O'TIB KETGAN muddat `max` da o'z-o'zidan chetlab o'tiladi:
    #    u `hozir` dan kichik, `soralgan` esa doim kattaroq.
    #    Alohida shart yozish shart emas — lekin bu tasodif emas,
    #    testda qotirilgan (`test_MUDDATI_TUGAGAN_cheklov_...`).
    if mavjud is None:
        return soralgan
    return max(mavjud, soralgan)


@transaction.atomic
def foydalanuvchini_cheklash(
    *, moderator, user, sabab: str, doimiy: bool = False, kun: int | None = None
):
    """Foydalanuvchini vaqtinchalik yoki doimiy cheklaydi.

    ⚠️⚠️ QABUL MEZONI: "bloklangan foydalanuvchi YOZA OLMAYDI, lekin
       O'QIY OLADI". Shuning uchun `is_active` TEGILMAYDI — u kirishni
       butunlay yopadi (D0-T2 dagi farq). Faqat `is_banned` qo'yiladi.

    ⚠️ Cheklangan odam saytni o'qiy olishi ataylab: u o'ziga kelgan
       javoblarni ko'rishi va nima uchun cheklanganini tushunishi
       kerak. Eshikni butunlay yopish odamni tushuntirishsiz
       qoldiradi.
    """
    _moderatorni_tekshirish(moderator)

    user.is_banned = True
    user.banned_until = (
        None
        if doimiy
        else yangi_muddat(user=user, kun=kun or settings.CHEKLOV_MUDDATI_KUN)
    )
    user.ban_reason = sabab[:200]
    user.save(update_fields=["is_banned", "banned_until", "ban_reason"])

    audit(
        action=AuditAction.FOYDALANUVCHI_CHEKLANDI,
        obyekt=f"foydalanuvchi #{user.pk}",
        actor=moderator,
        izoh=sabab,
        doimiy=doimiy,
        muddat=user.banned_until.isoformat() if user.banned_until else None,
    )
    log.warning(
        "Foydalanuvchi cheklandi: #%s doimiy=%s sabab=%r", user.pk, doimiy, sabab[:60]
    )
    return user


@transaction.atomic
def cheklovni_yechish(*, moderator, user, sabab: str = ""):
    """Cheklovni olib tashlaydi (moderator xato qilgan bo'lsa)."""
    _moderatorni_tekshirish(moderator)

    user.is_banned = False
    user.banned_until = None
    user.ban_reason = ""
    user.save(update_fields=["is_banned", "banned_until", "ban_reason"])

    audit(
        action=AuditAction.CHEKLOV_YECHILDI,
        obyekt=f"foydalanuvchi #{user.pk}",
        actor=moderator,
        izoh=sabab,
    )
    return user


def eskalatsiyani_tekshirish(*, moderator, user):
    """Chora ko'rilgandan keyin avtomatik bosqichni qo'llaydi.

    ⚠️ AVTOMATIK, LEKIN MODERATOR NOMIDAN. Chora qo'lda ko'rilgan
       bo'lsa-yu, uchinchi marta bo'lsa — cheklov o'z-o'zidan qo'yiladi.
       Moderator har safar "nechanchi marta edi?" deb sanab
       o'tirmasligi kerak; sanash mashinaning ishi.

    ⚠️ Mavjud DOIMIY blok QAYTA YOZILMAYDI: doimiy blokdan
       vaqtinchalikka "tushirish" jim yumshatish bo'lardi.
    """
    if user is None or (user.is_banned and user.banned_until is None):
        return None

    soni = qoidabuzarliklar_soni(user=user)

    if soni >= settings.DOIMIY_BLOK_CHEGARASI:
        return foydalanuvchini_cheklash(
            moderator=moderator,
            user=user,
            sabab=f"Avtomatik: {soni} ta qoidabuzarlik (doimiy).",
            doimiy=True,
        )
    if soni >= settings.CHEKLOV_CHEGARASI:
        return foydalanuvchini_cheklash(
            moderator=moderator,
            user=user,
            sabab=f"Avtomatik: {soni} ta qoidabuzarlik.",
        )
    return None
