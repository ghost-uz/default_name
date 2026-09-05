"""Barcha muammolar uchun OG rasmlarini qayta yasaydi (D4-T4).

⚠️ QACHON KERAK
   · brend, palitra yoki maket o'zgarganda — eski kartalar eski
     ko'rinishda qolib ketadi va ular ijtimoiy tarmoqda YILLAB
     aylanib yuradi;
   · sovuq start (D7-T7) — ommaviy kiritilgan postlarda rasm yo'q,
     chunki `bulk_create` ko'rinishdan o'tmaydi;
   · fon vazifasi biror sababga ko'ra bajarilmay qolganda.

⚠️ VAZIFA SINXRON CHAQIRILADI (`.delay()` EMAS).
   Buyruq odatda qo'lda, deploy paytida ishlatiladi va uning natijasi
   DARHOL ko'rinishi kerak. `.delay()` bo'lsa buyruq "tayyor" deb
   yozardi-yu, aslida ish navbatda turardi — va Redis o'chiq bo'lsa
   umuman bajarilmasdi.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.complaints.models import Complaint
from apps.complaints.tasks import og_rasmni_yangilash


class Command(BaseCommand):
    help = "Barcha muammolar uchun Open Graph rasmini qayta yasaydi."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--faqat-yoqlar",
            action="store_true",
            help="Faqat rasmi YO'Q muammolar (mavjudlariga tegilmaydi).",
        )

    def handle(self, *args, **sozlamalar) -> None:
        # korinish-istisno: rasm yasash — kontent KO'RSATILMAYDI.
        # Yashirilgan post tiklanganda rasmi tayyor turishi kerak
        # (sabab `tasks.og_rasmni_yangilash` da).
        queryset = Complaint.all_objects.order_by("pk")
        if sozlamalar["faqat_yoqlar"]:
            queryset = queryset.filter(og_rasm="")

        jami = 0
        yangilandi = 0

        for pk in queryset.values_list("pk", flat=True).iterator():
            jami += 1
            if og_rasmni_yangilash(pk) not in ("o'zgarmadi", "topilmadi"):
                yangilandi += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Ko'rildi: {jami} ta muammo, {yangilandi} tasida rasm yangilandi."
            )
        )
