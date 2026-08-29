"""Ma'lumot eksporti — fon vazifalari (D2-T8)."""

from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

log = logging.getLogger(__name__)

# Eksport shu muddatdan keyin o'chiriladi. Ichida shaxsiy ma'lumot bor
# va u bazada cheksiz turishi kerak emas.
EKSPORT_MUDDATI = timedelta(days=7)


def eksport_malumoti(user) -> dict:
    """Foydalanuvchining O'ZI yaratgan ma'lumotlari.

    ⚠️⚠️ BOSHQA ODAMLARNING MA'LUMOTI EKSPORTGA TUSHMAYDI.

       Vasvasa katta: "menga tegishli hamma narsa" deb postga kelgan
       shikoyatlarni, kim ovoz berganini va kim javob yozganini ham
       qo'shib yuborish oson. Lekin bu boshqa odamlarning ma'lumoti
       bo'lardi — va eksport ularning roziligisiz shaxsiy ma'lumot
       tarqatadigan quvurga aylanardi.

       Aynan shu sabab shikoyatlarda `reporter` YOZILMAYDI (kim
       shikoyat qilgani muallifga oshkor bo'lmasligi kerak — D2-T1) va
       ovozlar faqat SON sifatida chiqadi.

    ⚠️ Anonim postlar ham kiradi: ular MUALLIF UCHUN anonim emas.
    """
    from apps.complaints.models import Complaint, ComplaintVote, SavedComplaint
    from apps.gamification.models import KarmaEvent
    from apps.solutions.models import Solution, SolutionVote

    def vaqt(qiymat):
        return qiymat.isoformat() if qiymat else None

    return {
        "eksport_sanasi": timezone.now().isoformat(),
        "profil": {
            "username": user.username,
            "ism": user.first_name,
            "bio": user.bio,
            "qoshilgan": vaqt(user.date_joined),
            "karma": user.karma_cached,
            "ekspert": user.is_expert,
        },
        "dardlar": [
            {
                "sarlavha": d.title,
                "matn": d.description,
                "kategoriya": d.category.name if d.category_id else None,
                "holat": d.status,
                "anonim": d.is_anonymous,
                "yozilgan": vaqt(d.created_at),
                "ball": d.score_cached,
                "korishlar": d.views_count,
            }
            # korinish-istisno: foydalanuvchining O'Z ma'lumoti. Yashirilgan
            # yoki o'chirilgan posti ham unga tegishli va eksportga kirishi
            # kerak — bu ommaviy ko'rinish emas.
            for d in Complaint.all_objects.filter(author=user).select_related(
                "category"
            )
        ],
        "yechimlar": [
            {
                "matn": y.content,
                "anonim": y.is_anonymous,
                "qabul_qilingan": y.is_accepted,
                "yozilgan": vaqt(y.created_at),
                "ball": y.score_cached,
            }
            # korinish-istisno: yuqoridagi bilan bir xil sabab.
            for y in Solution.all_objects.filter(author=user)
        ],
        "saqlanganlar": [
            {"sarlavha": s.complaint.title, "saqlangan": vaqt(s.created_at)}
            for s in SavedComplaint.objects.filter(user=user).select_related(
                "complaint"
            )
        ],
        "karma_tarixi": [
            {"sabab": k.reason, "ball": k.points, "vaqt": vaqt(k.created_at)}
            for k in KarmaEvent.objects.filter(user=user)
        ],
        # ⚠️ Faqat SON: kimga ovoz berilgani ham, kim ovoz bergani ham
        #    boshqa odamlar bilan bog'liq ma'lumot.
        "ovozlar_soni": {
            "dardlarga": ComplaintVote.objects.filter(user=user).count(),
            "yechimlarga": SolutionVote.objects.filter(user=user).count(),
        },
    }


@shared_task
def eksportni_tayyorlash(eksport_id: int) -> str:
    """Eksportni yig'adi va saqlaydi.

    ⚠️ Xato bo'lsa ham yozuv `XATO` holatida QOLADI: foydalanuvchi
       "so'rovim yo'qoldimi?" degan holatda qolmasin. Jim o'chirish
       eng yomon variant.
    """
    from .models import EksportHolati, MalumotEksporti

    eksport = MalumotEksporti.objects.select_related("user").get(pk=eksport_id)
    try:
        eksport.malumot = eksport_malumoti(eksport.user)
        eksport.holat = EksportHolati.TAYYOR
        eksport.tayyor_at = timezone.now()
        eksport.xato = ""
    except Exception as exc:
        log.exception("Eksport tayyorlanmadi: %s", eksport_id)
        eksport.holat = EksportHolati.XATO
        eksport.xato = str(exc)[:500]

    eksport.save(update_fields=["malumot", "holat", "tayyor_at", "xato"])
    return eksport.holat


@shared_task
def eskirgan_eksportlarni_ochirish() -> int:
    """Muddati o'tgan eksportlarni o'chiradi (`CELERY_BEAT_SCHEDULE`).

    ⚠️ Eksport ichida shaxsiy ma'lumot bor. "Bir marta so'ralgan, keyin
       unutilgan" fayl bazada yillab turishi — ma'lumot sizishining
       eng oddiy yo'li.
    """
    from .models import MalumotEksporti

    soni, _ = MalumotEksporti.objects.filter(muddat__lt=timezone.now()).delete()
    if soni:
        log.info("Eskirgan eksportlar o'chirildi: %s", soni)
    return soni
