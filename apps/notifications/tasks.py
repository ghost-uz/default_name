"""Telegram orqali bildirishnoma yuborish (D5-T2).

⚠️⚠️ NEGA BU RETENTION'NING ASOSIY DVIGATELI
   Muammo egasiga yechim kelganini bildirmaslik — qaytib kelish siklini
   BUTUNLAY yo'qotadi: odam savolini yozadi, ketadi va javob kelganini
   hech qachon bilmaydi. Sayt esa "hech kim javob bermaydi" degan
   taassurot qoldiradi, holbuki javob bor.
"""

from __future__ import annotations

import logging

from celery import shared_task
from django.conf import settings

from .models import Notification
from .telegram import (
    TelegramBloklandi,
    TelegramVaqtinchalik,
    TelegramXatosi,
    html_qochirish,
    xabar_yuborish,
)

log = logging.getLogger(__name__)

# ⚠️ Qayta urinishlar oralig'i o'sib boradi: 1, 2, 4, 8 daqiqa.
#    Doimiy oraliq Telegram tomonidagi vaqtinchalik nosozlikda navbatni
#    bir xil ritmda urib turardi va tiklanishga xalaqit berardi.
QAYTA_URINISH_BOSHLANGICH = 60
QAYTA_URINISH_SONI = 4


def _xabar_matni(bildirishnoma: Notification) -> str:
    """Telegram xabari — ikki qator, ortiqchasiz.

    ⚠️ Matn QISQA: Telegram lentasida bildirishnoma bir qarashda
       o'qilishi kerak. Batafsili saytda va unga tugma olib boradi.

    ⚠️⚠️ ANONIMLIK: matn `Notification.matn` dan olinadi va u anonim
       manbada "Kimdir..." deydi (D5-T1). Bu yerda `actor` ga
       TO'G'RIDAN-TO'G'RI murojaat qilinmaydi — aks holda anonimlik
       Telegram xabarida buzilardi va uni qaytarib bo'lmasdi
       (xabar allaqachon yuborilgan).
    """
    qatorlar = [f"<b>{html_qochirish(bildirishnoma.matn)}</b>"]
    if bildirishnoma.complaint is not None:
        qatorlar.append(html_qochirish(bildirishnoma.complaint.title))
    return "\n".join(qatorlar)


@shared_task(
    bind=True,
    name="apps.notifications.tasks.telegram_yuborish",
    max_retries=QAYTA_URINISH_SONI,
)
def telegram_yuborish(self, notification_id: int) -> str:
    """Bildirishnomani Telegram'ga uzatadi.

    ⚠️ D5-T2 QABUL MEZONI 1: "yuborish sinxron EMAS". Bu vazifa
       `transaction.on_commit()` orqali navbatga qo'yiladi
       (`services.bildirishnoma_yaratish`), ya'ni foydalanuvchi javobni
       Telegram serveridan kutmaydi.

    ⚠️ D5-T2 QABUL MEZONI 2: 403 da foydalanuvchi BELGILANADI va qayta
       urinilmaydi. Aks holda navbat bitta odam uchun cheksiz aylanardi
       va har yangi bildirishnoma yana bir necha urinish qo'shardi.

    ⚠️ VAZIFA HECH QACHON ISTISNO BILAN TUGAMAYDI (qayta urinishdan
       tashqari): u qaytaradigan satr — jurnal uchun. Fon vazifasidagi
       istisno hech kimga ko'rinmaydi, lekin Celery uni xato deb
       sanaydi va monitoring shovqinini oshiradi.
    """
    bildirishnoma = (
        Notification.objects.select_related("recipient", "complaint")
        .filter(pk=notification_id)
        .first()
    )
    if bildirishnoma is None:
        # Bildirishnoma vazifa navbatda turganda o'chirilgan bo'lishi
        # mumkin (kontent o'chirilsa CASCADE ketadi).
        return "topilmadi"

    oluvchi = bildirishnoma.recipient
    if not oluvchi.telegram_id:
        # Telegram'siz hisob (masalan staff) — ichki markaz yetarli.
        return "telegram yo'q"
    if oluvchi.telegram_bloklandi:
        return "bloklangan"

    try:
        xabar_yuborish(
            chat_id=oluvchi.telegram_id,
            matn=_xabar_matni(bildirishnoma),
            tugma_manzili=f"{settings.SAYT_MANZILI}{bildirishnoma.manzil}",
        )
    except TelegramBloklandi:
        # ⚠️ `update()` — `save()` boshqa maydonlarni ham yozardi va
        #    vazifa fonda ishlagani uchun ular eskirgan bo'lishi mumkin.
        type(oluvchi).objects.filter(pk=oluvchi.pk).update(telegram_bloklandi=True)
        log.info("telegram: bot bloklangan (user=%s)", oluvchi.pk)
        return "bloklandi"
    except TelegramVaqtinchalik as xato:
        # ⚠️ Telegram 429 da `retry_after` beradi — uni HURMAT QILISH
        #    shart, aks holda keyingi urinish ham rad etiladi va
        #    cheklov yanada uzayadi.
        kechikish = xato.keyin or QAYTA_URINISH_BOSHLANGICH * (2**self.request.retries)
        raise self.retry(exc=xato, countdown=kechikish) from xato
    except TelegramXatosi as xato:
        # 400 va boshqalar — qayta urinish tuzatmaydi.
        log.warning("telegram: yuborilmadi (id=%s): %s", notification_id, xato)
        return "xato"

    return "yuborildi"
