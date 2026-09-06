"""To'lovlar — fon vazifalari (D6-T1)."""

from __future__ import annotations

import logging

from celery import shared_task

from .services import muddati_otganlarni_belgilash

log = logging.getLogger(__name__)


@shared_task(
    name="apps.payments.tasks.obunalarni_tekshirish",
    # ⚠️ Qayta urinish YO'Q: vazifa IDEMPOTENT va kuniga bir marta
    #    ishlaydi — o'tkazib yuborilgan ish ertaga baribir bajariladi.
    max_retries=0,
)
def obunalarni_tekshirish() -> str:
    """⚠️ D6-T1 QABUL MEZONI: «muddati tugashi Celery bilan tekshiriladi».

    ⚠️⚠️ LEKIN BU YAGONA HIMOYA EMAS. `Subscription.faolmi` muddatni
       har chaqiruvda o'zi tekshiradi, ya'ni worker o'chib qolsa ham
       muddati tugagan obuna ishlab QOLMAYDI. Vazifa faqat holatni
       tozalaydi.

       Teskari tartib (vazifa — yagona himoya) aynan task `nega`
       bo'limidagi xatoni berardi: «muddati tugagan obuna qayerdadir
       ishlab qolaveradi».
    """
    soni = muddati_otganlarni_belgilash()
    if soni:
        log.info("obuna: %s ta muddati tugagan deb belgilandi", soni)
    return f"{soni} ta"
