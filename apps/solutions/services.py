"""Yechim oqimi — xizmat funksiyalari (D1-T4, D1-T10, D3-T1).

Ko'rinishlar shu funksiyalarni chaqiradi. Mantiq bu yerda, `views.py` da
emas: qabul qilish uchta jadvalga tegadi va uni bir necha joyda
(veb-forma, Telegram bot, admin) takrorlash mumkin emas.
"""

from __future__ import annotations

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models, transaction
from django.utils import timezone

from apps.common.voting import VoteResult, cast_vote
from apps.complaints.models import Complaint, ComplaintStatus
from apps.gamification.services import (
    ovoz_karmasi,
    yechim_qabul_karmasi,
    yechim_qabuli_bekor_karmasi,
)

from .models import Solution, SolutionVote


@transaction.atomic
def yechim_yozish(
    *, complaint: Complaint, author, content: str, is_anonymous: bool = False
) -> Solution:
    """Yangi yechim qo'shadi va muammoning sanoqchilarini yangilaydi.

    ⚠️ SANOQCHILAR SHU YERDA YANGILANADI, signalda EMAS.
       Signal (`post_save`) jozibali ko'rinadi, lekin u `bulk_create`,
       `loaddata` va ommaviy import'da ISHLAMAYDI — sanoqchi jimgina
       haqiqatdan uziladi. Bitta ochiq kirish nuqtasi esa ko'rinib turadi.

    ⚠️ `has_expert_answer` — keshlangan bayroq (lentadagi "Ekspert javob
       berdi" nishoni). Uni har kartada JOIN bilan hisoblash 20 karta
       uchun 20 ta qo'shimcha so'rov degani (D1-T14).
    """
    if not getattr(author, "can_write", False):
        raise PermissionDenied("Hisobingiz cheklangan.")
    if complaint.is_deleted or not complaint.is_publicly_visible:
        raise ValidationError("Bu muammoga yechim yozib bo'lmaydi.")

    # korinish-istisno: YARATISH. Muammoning ko'rinishi yuqorida
    # `is_publicly_visible` bilan allaqachon tekshirilgan.
    yechim = Solution.objects.create(
        complaint=complaint,
        author=author,
        content=content,
        is_anonymous=is_anonymous,
    )

    yangilanish: dict[str, object] = {
        "solutions_count": models.F("solutions_count") + 1,
        # ⚠️ `auto_now` `QuerySet.update()` da ISHLAMAYDI — qo'lda beriladi
        #    (apps/common/models.py, TimeStampedModel dagi ogohlantirish).
        "updated_at": timezone.now(),
    }
    if yechim.is_by_expert:
        yangilanish["has_expert_answer"] = True

    # korinish-istisno: sanoqchilarni yangilash, ko'rsatish emas.
    Complaint.all_objects.filter(pk=complaint.pk).update(**yangilanish)
    return yechim


@transaction.atomic
def accept_solution(*, solution: Solution, by_user) -> Solution:
    """Muammo muallifi yechimni "to'g'ri javob" deb belgilaydi.

    ⚠️ AMALLAR TARTIBI — E'TIBORSIZ QOLDIRIB BO'LMAYDI
       Avval ESKI qabul qilingan yechim bekor qilinadi, KEYIN yangisi
       belgilanadi. Teskari tartibda `solution_one_accepted_per_complaint`
       noyoblik indeksi darhol buziladi: PostgreSQL noyoblikni har
       `UPDATE` dan keyin tekshiradi, tranzaksiya oxirida emas (indeks
       `DEFERRABLE` emas).

    ⚠️ MUAMMO QATORI QULFLANADI
       `select_for_update()` — muallif ikki oynada ikki xil yechimni
       deyarli bir vaqtda qabul qilsa, ikkinchisi birinchisini kutadi.

    ⚠️ IDEMPOTENT: allaqachon qabul qilingan yechim uchun karma QAYTA
       BERILMAYDI. Usiz tugmani ikki marta bosish (yoki HTMX'ning takroriy
       so'rovi) ballarni ikkilantirardi.
    """
    # korinish-istisno: qatorni QULFLASH (yozish). Ruxsat quyida
    # tekshiriladi va yechimning ko'rinishi ham alohida.
    complaint = Complaint.objects.select_for_update().get(pk=solution.complaint_id)

    if complaint.author_id != getattr(by_user, "pk", None):
        # ⚠️ Ruxsat tekshiruvi XIZMATDA, faqat ko'rinishda emas: bu funksiya
        #    keyinchalik bot va admin buyruqlaridan ham chaqiriladi.
        raise PermissionDenied("Yechimni faqat muammo muallifi qabul qila oladi.")

    if solution.is_deleted or not solution.is_publicly_visible:
        raise ValidationError(
            "O'chirilgan yoki yashirilgan yechimni qabul qilib bo'lmaydi."
        )

    if solution.is_accepted:
        return solution  # allaqachon qabul qilingan — hech nima o'zgarmaydi

    # 1) Eskisini bekor qilamiz (bor bo'lsa) — karma teskari yozuvi bilan.
    # korinish-istisno: eski qabulni bekor qilish (yozish amali).
    eskilar = list(
        Solution.objects.filter(complaint=complaint, is_accepted=True).exclude(
            pk=solution.pk
        )
    )
    if eskilar:
        # korinish-istisno: yozish amali.
        Solution.objects.filter(pk__in=[s.pk for s in eskilar]).update(
            is_accepted=False, accepted_at=None, updated_at=timezone.now()
        )
        for eski in eskilar:
            yechim_qabuli_bekor_karmasi(solution=eski)

    # 2) Yangisini belgilaymiz.
    solution.is_accepted = True
    solution.accepted_at = timezone.now()
    solution.save(update_fields=["is_accepted", "accepted_at", "updated_at"])

    # 3) Muammo holatini yangilaymiz.
    complaint.accepted_solution = solution
    complaint.status = ComplaintStatus.SOLVED
    complaint.save(update_fields=["accepted_solution", "status", "updated_at"])

    # 4) Karma — D1-T10 qabul mezoni.
    yechim_qabul_karmasi(solution=solution)

    return solution


@transaction.atomic
def unaccept_solution(*, solution: Solution, by_user) -> Solution:
    """Qabul qilishni bekor qiladi — muammo yana "ochiq" bo'ladi.

    Nega kerak: muallif shoshib tanlashi mumkin, yoki keyinroq yechim
    ishlamagani ma'lum bo'ladi. Qaytarib bo'lmaydigan tugma foydalanuvchini
    umuman bosmaslikka undaydi.
    """
    # korinish-istisno: qatorni QULFLASH (yozish), ruxsat quyida.
    complaint = Complaint.objects.select_for_update().get(pk=solution.complaint_id)

    if complaint.author_id != getattr(by_user, "pk", None):
        raise PermissionDenied("Buni faqat muammo muallifi qila oladi.")

    if not solution.is_accepted:
        return solution  # idempotent

    solution.is_accepted = False
    solution.accepted_at = None
    solution.save(update_fields=["is_accepted", "accepted_at", "updated_at"])

    complaint.accepted_solution = None
    complaint.status = ComplaintStatus.OPEN
    complaint.save(update_fields=["accepted_solution", "status", "updated_at"])

    yechim_qabuli_bekor_karmasi(solution=solution)
    return solution


def yechimga_ovoz(*, solution: Solution, user, qiymat: int) -> VoteResult:
    """Yechimga ovoz beradi VA muallif karmasini yangilaydi (D3-T1).

    ⚠️ YAGONA KIRISH NUQTASI — ko'rinish `cast_vote()` ni to'g'ridan-to'g'ri
       chaqirmasligi kerak. Aks holda karma "ovoz ko'rinishida" turardi va
       kelajakda qo'shiladigan ikkinchi yo'l (masalan API yoki ommaviy
       import) uni jimgina o'tkazib yuborardi — bu D1-T10 dagi
       "signal emas, bitta ochiq kirish nuqtasi" qarorining o'zi.

    ⚠️ DARDGA OVOZDA bunday o'ram YO'Q va bo'lmasligi ham kerak: dard
       karma bermaydi (`KARMA_QIYMATLARI` izohi). `complaints` ko'rinishi
       `cast_vote()` ni to'g'ridan-to'g'ri chaqiraveradi.
    """
    natija = cast_vote(
        target=solution,
        vote_model=SolutionVote,
        target_field="solution",
        user=user,
        value=qiymat,
    )
    ovoz_karmasi(solution=solution, natija=natija, qiymat=qiymat, ovoz_beruvchi=user)
    return natija
