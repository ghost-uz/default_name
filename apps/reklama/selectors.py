"""Reklama tanlash (D6-T6) — o'qish so'rovlari."""

from __future__ import annotations

from django.db import models

from .models import AdSlot


def sahifa_reklamasi(*, kategoriya_id: int | None, inqiroz: bool) -> AdSlot | None:
    """Sahifaga mos reklama yoki `None`.

    ⚠️⚠️ INQIROZLI SAHIFADA REKLAMA YO'Q — D6-T6 qabul mezoni. Tekshiruv
       SHU YERDA, ko'rinishda EMAS: reklama ikkinchi joyga qo'shilganda
       (masalan kategoriya sahifasi) qoida o'zi bilan keladi. Ko'rinishga
       yozilsa, u yerda bir kuni unutilardi — va aynan o'sha sahifada
       o'zini zarar yetkazish haqida yozgan odam reklama ko'rardi.

       Bu D5-T3 tamoyilining davomi: kontentni CHEKLAMAYMIZ, lekin
       uning yonida pul ishlamaymiz ham.

    ⚠️ MAQSADLI REKLAMA UMUMIYDAN USTUN: shu kategoriyaga yozilgani
       birinchi, umumiylari keyin. Tenglar orasida TASODIFIY — bir nechta
       reklama bo'lsa ko'rsatishlar ular orasida teng bo'linadi
       (D6-T4 dagi boost navbati bilan bir xil mulohaza).

    ⚠️ BITTA blok qaytariladi: yon panelda ikkita reklama ketma-ket
       tursa sahifa reklama lentasiga o'xshab qolardi.
    """
    if inqiroz:
        return None

    qs = AdSlot.objects.faol()
    if kategoriya_id is None:
        # Kategoriyasi noma'lum sahifa — faqat umumiy reklamalar.
        return qs.filter(kategoriya__isnull=True).order_by("?").first()

    return (
        qs.filter(
            models.Q(kategoriya__isnull=True) | models.Q(kategoriya_id=kategoriya_id)
        )
        .annotate(
            maqsadli=models.Case(
                models.When(kategoriya_id=kategoriya_id, then=models.Value(1)),
                default=models.Value(0),
                output_field=models.IntegerField(),
            )
        )
        .order_by("-maqsadli", "?")
        .first()
    )
