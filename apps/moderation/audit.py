"""Audit jurnaliga yozish (D2-T7).

⚠️ YOZISH IKKI YO'L BILAN BO'LADI VA BU ATAYLAB:

  1. **Signal** — `ModerationAction` yaratilganda jurnal AVTOMATIK
     to'ldiriladi. Kontent ustidagi chora eng muhim yozuv va uni
     qo'lda chaqirishga qoldirish — bir kuni unutish demak.

  2. **`audit()` chaqiruvi** — modelsiz amallar uchun (shikoyat
     yopish, kelajakda bloklash). Ular hech qanday qator yaratmaydi,
     ya'ni ilinadigan signal yo'q.

   Faqat signalga tayanish mumkin emas: staff amallarining hammasi
   ham model yaratmaydi. Faqat qo'lda chaqirishga tayanish ham
   mumkin emas: eng muhim yo'l unutilishi mumkin.
"""

from __future__ import annotations

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import AuditAction, AuditLog, ModerationAction, ModerationActionType

log = logging.getLogger(__name__)


def audit(
    *,
    action: str,
    obyekt: str,
    actor=None,
    izoh: str = "",
    **malumot,
) -> AuditLog:
    """Jurnalga bitta yozuv qo'shadi.

    ⚠️ `actor_nomi` YOZUV PAYTIDA nusxalanadi: hisob keyinchalik
       o'chirilsa `actor` `None` bo'ladi, lekin "kim qildi?" savoliga
       javob qolishi kerak — javobsiz jurnal dalil emas.
    """
    yozuv = AuditLog.objects.create(
        actor=actor if getattr(actor, "pk", None) else None,
        actor_nomi=getattr(actor, "username", "") or "",
        action=action,
        obyekt=obyekt[:100],
        izoh=izoh,
        malumot=malumot,
    )
    log.info("Audit: %s %s (%s)", action, obyekt, yozuv.kim)
    return yozuv


@receiver(post_save, sender=ModerationAction, dispatch_uid="audit_moderation_action")
def _choradan_jurnalga(sender, instance: ModerationAction, created: bool, **kwargs):
    """`ModerationAction` yaratilishi jurnalga AVTOMATIK tushadi.

    ⚠️ `created` tekshiruvi: jurnal faqat QO'SHILADI, ya'ni mavjud
       chorani saqlash yangi audit yozuvini bermaydi.
    """
    if not created:
        return

    bekormi = instance.action == ModerationActionType.BEKOR_QILISH
    audit(
        action=AuditAction.CHORA_BEKOR if bekormi else AuditAction.KONTENT_CHORA,
        obyekt=instance.target_nomi,
        actor=instance.moderator,
        izoh=instance.note,
        chora=instance.action,
        chora_id=instance.pk,
        oldingi_holat=instance.oldingi_holat,
        bekor_qiladi=instance.bekor_qiladi_id,
    )
