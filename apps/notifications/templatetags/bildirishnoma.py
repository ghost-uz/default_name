"""Sarlavhadagi o'qilmaganlar belgisi (D5-T1).

⚠️ NEGA SHABLON TEGI, KONTEKST-PROTSESSOR EMAS
   Kontekst-protsessor qiymatni HAR renderga qo'shadi — jumladan HTMX
   qismlariga (ovoz kartasi, "yana yuklash"), ular esa sarlavhani
   umuman chizmaydi. Bu D1-T14 da qotirilgan so'rov byudjetiga
   bekorga qo'shilardi.

   `apps/common/templatetags/seo.py` da ham xuddi shu sabab yozilgan.
"""

from __future__ import annotations

from django import template
from django.conf import settings

from apps.notifications.services import oqilmagan_soni

register = template.Library()


@register.simple_tag(takes_context=True)
def oqilmagan_bildirishnomalar(context: dict) -> str:
    """Belgidagi son: `""`, `"3"` yoki `"99+"`.

    ⚠️ Bo'sh satr qaytaradi (nol emas): shablon `{% if %}` bilan
       belgini umuman chizmasligi uchun. "0" chizilgan belgi
       foydalanuvchiga "yangi narsa bor" degan yolg'on signal berardi.
    """
    request = context.get("request")
    user = getattr(request, "user", None)

    soni = oqilmagan_soni(user)
    if not soni:
        return ""

    chegara = settings.BILDIRISHNOMA_BELGI_CHEGARASI
    return f"{chegara}+" if soni > chegara else str(soni)
