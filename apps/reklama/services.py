"""Reklama hisoblari (D6-T6) — ko'rsatish va bosish.

⚠️⚠️ KO'RSATISH BAZAGA HAR RENDERDA YOZILMAYDI.
   Batafsil sahifa ko'p ochiladi; har ochilishda `UPDATE` qilish o'qish
   sahifasini YOZISH sahifasiga aylantirardi (har ko'rish — bitta qator
   qulfi). Sanoq keshda yig'iladi, Celery beat esa uni davriy ravishda
   bazaga ko'chiradi.

⚠️⚠️ KESH KALITIDA VAQT OYNASI BOR — tezlik cheklovidagi (D2-T4) naqsh.
   Yig'uvchi vazifa FAQAT O'TGAN oynalarni o'qiydi, ya'ni «o'qidim ->
   o'chirdim» orasiga tushib yo'qoladigan ko'rsatish bo'lmaydi. Oynasiz
   sanoq bilan bu poyga jimgina hisobni kamaytirardi.

⚠️ KESH YO'QOLSA (Redis qayta ishga tushsa) o'sha oynadagi ko'rsatishlar
   yo'qoladi. Bu ONGLI qaror: reklama statistikasi — TAXMINIY o'lchov,
   pul harakati emas (pul `payments.Tolov` da va u bazada).

⚠️ BOSISH esa bazaga darhol yoziladi: u kam uchraydi va aynan shu son
   reklama beruvchi bilan hisob-kitobda ishlatiladi.
"""

from __future__ import annotations

import logging
import time

from django.core.cache import cache
from django.db import models

from .models import AdSlot

log = logging.getLogger(__name__)

# Kesh oynasi (soniya). Yig'uvchi vazifa shundan uzunroq oraliqda
# ishlashi kerak emas — u O'TGAN oynalarni o'qiydi.
OYNA = 300

# Yig'ishda nechta o'tgan oyna ko'riladi. Uchtasi = 15 daqiqa: vazifa
# bir-ikki marta o'tkazib yuborilsa ham sanoq yo'qolmaydi.
YIGISH_OYNALARI = 3


def korsatish_kaliti(reklama_pk: int, oyna: int) -> str:
    return f"reklama:korsatish:{reklama_pk}:{oyna}"


def joriy_oyna(hozir: float | None = None) -> int:
    return int((time.time() if hozir is None else hozir) // OYNA)


def korsatishni_qayd_etish(reklama_pk: int) -> None:
    """Ko'rsatishni KESHDA sanaydi (bazaga tegmaydi).

    ⚠️ FAIL OPEN: kesh ishlamasa sahifa baribir ochilishi kerak. Reklama
       sanog'i yo'qolgani sahifani yiqitadigan sabab emas (D2-T4 dagi
       tezlik cheklovi bilan bir xil qaror).
    """
    kalit = korsatish_kaliti(reklama_pk, joriy_oyna())
    try:
        cache.add(kalit, 0, timeout=OYNA * (YIGISH_OYNALARI + 2))
        cache.incr(kalit)
    except Exception:  # kesh nosozligi sahifani yiqitmasin
        log.exception("Reklama ko'rsatishini sanab bo'lmadi (pk=%s)", reklama_pk)


def bosishni_qayd_etish(reklama_pk: int) -> None:
    """Bosishni BAZAGA darhol yozadi (`F()` bilan, poygasiz)."""
    AdSlot.objects.filter(pk=reklama_pk).update(
        bosishlar=models.F("bosishlar") + 1,
    )


def korsatishlarni_yigish(*, oynalar: int = YIGISH_OYNALARI) -> int:
    """Keshdagi O'TGAN oynalarni bazaga ko'chiradi. Qaytaradi: jami son.

    ⚠️ JORIY OYNA TEGILMAYDI — u hali to'lib turibdi. Shu sababli
       «o'qidim va o'chirdim» orasida yangi ko'rsatish yo'qolmaydi.

    ⚠️ Barcha reklamalar aylanadi (ular kam) — kesh kalitlarini
       SKANERLASH kerak emas. `keys()` naqshi Redis'da sekin va Django
       kesh API'sida umuman yo'q.
    """
    joriy = joriy_oyna()
    jami = 0
    for reklama_pk in AdSlot.objects.values_list("pk", flat=True):
        for siljish in range(1, oynalar + 1):
            kalit = korsatish_kaliti(reklama_pk, joriy - siljish)
            soni = cache.get(kalit)
            if not soni:
                continue
            AdSlot.objects.filter(pk=reklama_pk).update(
                korsatishlar=models.F("korsatishlar") + soni,
            )
            cache.delete(kalit)
            jami += int(soni)

    if jami:
        log.info("Reklama ko'rsatishlari yig'ildi: %s", jami)
    return jami
