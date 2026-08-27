"""Yechim oqimi — xizmat funksiyalari (D1-T4).

Ko'rinishlar (D1-T10) shu funksiyalarni chaqiradi. Mantiq bu yerda,
`views.py` da emas: qabul qilish uchta jadvalga tegadi va uni bir necha
joyda (veb-forma, Telegram bot, admin) takrorlash mumkin emas.
"""

from __future__ import annotations

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.complaints.models import Complaint, ComplaintStatus

from .models import Solution


@transaction.atomic
def accept_solution(*, solution: Solution, by_user) -> Solution:
    """Muammo muallifi yechimni "to'g'ri javob" deb belgilaydi.

    ⚠️ AMALLAR TARTIBI — E'TIBORSIZ QOLDIRIB BO'LMAYDI
       Avval ESKI qabul qilingan yechim bekor qilinadi, KEYIN yangisi
       belgilanadi. Teskari tartibda `solution_one_accepted_per_complaint`
       noyoblik indeksi darhol buziladi: PostgreSQL noyoblikni har
       `UPDATE` dan keyin tekshiradi, tranzaksiya oxirida emas (indeks
       `DEFERRABLE` emas). Ya'ni bir lahza ikkita qabul qilingan yechim
       bo'lishi mumkin emas — hatto tranzaksiya ichida ham.

    ⚠️ MUAMMO QATORI QULFLANADI
       `select_for_update()` — muallif ikki oynada ikki xil yechimni
       deyarli bir vaqtda qabul qilsa, ikkinchisi birinchisini kutadi.
       Usiz ikkalasi ham "eski qabul qilingani yo'q" deb ko'rardi.
    """
    complaint = Complaint.objects.select_for_update().get(pk=solution.complaint_id)

    if complaint.author_id != getattr(by_user, "pk", None):
        # ⚠️ Ruxsat tekshiruvi XIZMATDA, faqat ko'rinishda emas: bu funksiya
        #    keyinchalik bot va admin buyruqlaridan ham chaqiriladi.
        raise PermissionDenied("Yechimni faqat muammo muallifi qabul qila oladi.")

    if solution.is_deleted or not solution.is_publicly_visible:
        raise ValidationError(
            "O'chirilgan yoki yashirilgan yechimni qabul qilib bo'lmaydi."
        )

    # 1) Eskisini bekor qilamiz (bor bo'lsa).
    Solution.objects.filter(complaint=complaint, is_accepted=True).exclude(
        pk=solution.pk
    ).update(is_accepted=False, accepted_at=None, updated_at=timezone.now())

    # 2) Yangisini belgilaymiz.
    solution.is_accepted = True
    solution.accepted_at = timezone.now()
    solution.save(update_fields=["is_accepted", "accepted_at", "updated_at"])

    # 3) Muammo holatini yangilaymiz.
    complaint.accepted_solution = solution
    complaint.status = ComplaintStatus.SOLVED
    complaint.save(update_fields=["accepted_solution", "status", "updated_at"])

    return solution


@transaction.atomic
def unaccept_solution(*, solution: Solution, by_user) -> Solution:
    """Qabul qilishni bekor qiladi — muammo yana "ochiq" bo'ladi.

    Nega kerak: muallif shoshib tanlashi mumkin, yoki keyinroq yechim
    ishlamagani ma'lum bo'ladi. Qaytarib bo'lmaydigan tugma foydalanuvchini
    umuman bosmaslikka undaydi.
    """
    complaint = Complaint.objects.select_for_update().get(pk=solution.complaint_id)

    if complaint.author_id != getattr(by_user, "pk", None):
        raise PermissionDenied("Buni faqat muammo muallifi qila oladi.")

    solution.is_accepted = False
    solution.accepted_at = None
    solution.save(update_fields=["is_accepted", "accepted_at", "updated_at"])

    complaint.accepted_solution = None
    complaint.status = ComplaintStatus.OPEN
    complaint.save(update_fields=["accepted_solution", "status", "updated_at"])

    return solution
