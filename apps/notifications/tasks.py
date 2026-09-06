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

from . import dayjest
from .models import BildirishnomaTuri, Notification
from .sozlama import jim_oyna_tugashigacha, jim_vaqtmi
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


def _dayjest_matni(bildirishnoma: Notification) -> str:
    """Dayjest xabari — YUBORISH PAYTIDA qayta hisoblanadi (D5-T5).

    ⚠️⚠️ RO'YXAT SAQLANMAYDI, QAYTA HISOBLANADI. Yozuv yaratilgan
       vaqt bilan yuborilgan vaqt orasida farq bo'lishi mumkin — jim
       soatlar (D5-T4) xabarni ertalabgacha kechiktiradi. Saqlangan
       ro'yxat o'shanda allaqachon javob olgan savollarni ko'rsatardi
       va ekspertni bekorga yugurtirardi.

    ⚠️ Ro'yxat BO'SHAB QOLSA bo'sh satr qaytadi va chaqiruvchi
       yubormaydi: "javobsiz savol yo'q" degan xabar aynan botdan
       chiqib ketishga olib keladigan shovqin.
    """
    from . import dayjest

    ekspert = getattr(bildirishnoma.recipient, "ekspert_profili", None)
    if ekspert is None:
        # Ekspertlik dayjest yaratilgandan keyin bekor qilingan.
        return ""

    savollar = dayjest.savollar_uchun(ekspert)
    if not savollar:
        return ""

    return dayjest.xabar_matni(ekspert=ekspert, savollar=savollar)


@shared_task(
    bind=True,
    name="apps.notifications.tasks.telegram_yuborish",
    max_retries=QAYTA_URINISH_SONI,
)
def telegram_yuborish(
    self, notification_id: int, *, kechiktirilgan: bool = False
) -> str:
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
        Notification.objects.select_related(
            "recipient", "complaint", "recipient__bildirishnoma_sozlamasi"
        )
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

    # ⚠️ SOZLAMA (D5-T4). Yozuv ALLAQACHON yaratilgan — bu yerda faqat
    #    YETKAZISH to'xtatiladi. Ichki markaz zaxira kanal bo'lib
    #    qolaveradi (sabab `sozlama.py` docstring'ida).
    sozlama = getattr(oluvchi, "bildirishnoma_sozlamasi", None)
    if sozlama is not None and not sozlama.yoqilganmi(bildirishnoma.turi):
        return "o'chirilgan"

    # ⚠️ JIM SOATLAR: xabar TASHLANMAYDI, ertalabgacha KECHIKTIRILADI.
    #    `countdown` bilan qayta navbatga qo'yiladi — `retry` EMAS,
    #    chunki bu xato emas va `max_retries` ni yeb qo'ymasligi kerak.
    #
    # ⚠️⚠️ KECHIKTIRISH BIR MARTALIK (`kechiktirilgan` bayrog'i).
    #    Ikki sabab, ikkalasi ham jonli topilgan:
    #
    #    1. EAGER rejimda (`CELERY_TASK_ALWAYS_EAGER`, ya'ni TESTLARDA)
    #       `apply_async` `countdown` ni E'TIBORSIZ qoldiradi va vazifani
    #       DARHOL qayta ishga tushiradi. Bayroqsiz u yana jim soatga
    #       tushib, yana o'zini chaqirardi — `RecursionError`. Bu 2026-09-06
    #       da soat 22:00 dan o'tganda 14 ta ALOQASIZ testni yiqitdi va
    #       to'plamni 87s dan 331s ga cho'zdi. Xato KUNDUZI ko'rinmasdi.
    #
    #    2. Ishlab chiqarishda ham himoya: `jim_vaqtmi()` yoki oyna
    #       sozlamasi buzuq bo'lsa (masalan boshi = oxiri) xabar CHEKSIZ
    #       kechikardi va hech qachon yetib bormasdi. Endi eng yomon
    #       holatda u bir marta kechikadi va YUBORILADI.
    if not kechiktirilgan and (sozlama is None or sozlama.jim_soatlar) and jim_vaqtmi():
        telegram_yuborish.apply_async(
            args=[notification_id],
            kwargs={"kechiktirilgan": True},
            countdown=jim_oyna_tugashigacha(),
        )
        return "jim soat"

    if bildirishnoma.turi == BildirishnomaTuri.DAYJEST:
        matn = _dayjest_matni(bildirishnoma)
        if not matn:
            return "bo'shab qoldi"
    else:
        matn = _xabar_matni(bildirishnoma)

    try:
        xabar_yuborish(
            chat_id=oluvchi.telegram_id,
            matn=matn,
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


@shared_task(
    name="apps.notifications.tasks.dayjest_yuborish",
    # ⚠️ QAYTA URINISH YO'Q: vazifa haftada bir marta ishlaydi va u
    #    yozuvlar YARATADI. Qayta urinish bir ekspertga ikkita dayjest
    #    yuborardi — aynan ortiqcha bildirishnoma muammosi (D5-T4).
    #    Har ekspertning Telegram xabari esa O'Z vazifasida qayta
    #    urinadi (`telegram_yuborish`), ya'ni yo'qotish yo'q.
    max_retries=0,
)
def dayjest_yuborish() -> str:
    """Ekspertlarga haftalik «javobsiz savollar» dayjesti (D5-T5).

    ⚠️ Yozuv HAR EKSPERT uchun alohida yaratiladi va Telegram xabari
       `bildirishnoma_yaratish` ichidagi `on_commit` orqali O'Z
       vazifasiga tushadi. Ya'ni bitta ekspertdagi nosozlik
       qolganlarni to'xtatmaydi.

    ⚠️ BEAT `crontab()` EMAS, oddiy interval (sozlama moduli celery'ni
       import qilmasin — `base.py` dagi qoida). Bu vazifa haftaning
       istalgan soatida ishga tushishi mumkin, LEKIN tunda kelgan
       xabarni jim soatlar (D5-T4) ertalabgacha kechiktiradi. Ya'ni
       aniq soat kerak emas — himoya allaqachon bor.
    """
    from .services import dayjest_bildirishnomasi

    yuborildi = 0
    for ekspert, savollar in dayjest.dayjestlar():
        if dayjest_bildirishnomasi(ekspert=ekspert, savollar=savollar) is not None:
            yuborildi += 1

    log.info("dayjest: %s ekspertga yuborildi", yuborildi)
    return f"{yuborildi} ta"
