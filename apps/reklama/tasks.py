"""Reklama fon vazifalari (D6-T6)."""

from __future__ import annotations

from celery import shared_task

from .services import korsatishlarni_yigish


@shared_task(
    name="apps.reklama.tasks.korsatishlarni_yigish",
    # ⚠️ Qayta urinish YO'Q: vazifa har 5 daqiqada ishlaydi va o'tkazib
    #    yuborilgan yurish keyingisida yopiladi — kesh kalitlari uchta
    #    oyna davomida saqlanadi (`services.YIGISH_OYNALARI`).
    max_retries=0,
    ignore_result=True,
)
def korsatishlarni_yigish_vazifasi() -> int:
    """Keshdagi ko'rsatish sanog'ini bazaga ko'chiradi."""
    return korsatishlarni_yigish()
