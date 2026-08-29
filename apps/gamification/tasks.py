"""Gamifikatsiya — fon vazifalari (D3-T2)."""

from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.contrib.auth import get_user_model
from django.utils import timezone

from .models import KarmaEvent
from .services import nishonlarni_tekshirish

log = logging.getLogger(__name__)

# ⚠️ 25 soat, 24 EMAS. Vazifa sutkada bir marta ishlaydi va oynani aynan
#    24 soat qilsak, ikki ishga tushish orasidagi kichik siljish (beat
#    kechikishi, qayta joylash) tufayli bir necha daqiqalik "ko'r nuqta"
#    paydo bo'lardi va o'sha oraliqdagi faollik NAVBATDAGI ishga ham
#    tushmasdi. Ustma-ust tushish esa zararsiz: `nishonlarni_tekshirish`
#    idempotent.
OYNA = timedelta(hours=25)


@shared_task(name="apps.gamification.tasks.nishonlarni_yangilash")
def nishonlarni_yangilash() -> int:
    """Yaqinda karma olgan foydalanuvchilarning nishonlarini tekshiradi.

    ⚠️ NEGA KERAK: nishon berish `accept_solution()` da ochiq
       chaqiriladi, lekin OVOZ yo'lida chaqirilmaydi — u juda tez-tez
       bo'ladi va har ovozda ikkita qo'shimcha so'rov D1-T14 da
       qotirilgan byudjetni yeb qo'yardi. Ovozdan kelib chiqadigan
       nishonlar (karma, olingan ovoz) shu yerda beriladi.

    ⚠️ HAMMA FOYDALANUVCHI EMAS, faqat oynada FAOLLARI: baza o'sganda
       "hammasini aylanish" sutkalik vazifani soatlab cho'zardi.
       Faollik belgisi — karma hodisasi: nishon metrikalarining
       hammasi karma bilan birga o'zgaradi.
    """
    chegara = timezone.now() - OYNA
    idlar = (
        KarmaEvent.objects.filter(created_at__gte=chegara)
        .values_list("user_id", flat=True)
        .distinct()
    )

    berilgan = 0
    # ⚠️ `iterator()` — faol foydalanuvchilar ro'yxati katta bo'lishi
    #    mumkin va uni butunlay xotiraga olish shart emas.
    for user in get_user_model().objects.filter(pk__in=idlar).iterator():
        berilgan += len(nishonlarni_tekshirish(user=user))

    log.info(
        "Nishon tekshiruvi: %s foydalanuvchi, %s yangi nishon", len(idlar), berilgan
    )
    return berilgan
