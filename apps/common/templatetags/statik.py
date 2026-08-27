"""Kesh buzuvchi statik teg (D1-T8 da topilgan tuzoq)."""

from __future__ import annotations

from pathlib import Path

from django import template
from django.conf import settings
from django.contrib.staticfiles import finders
from django.templatetags.static import static

register = template.Library()


@register.simple_tag
def static_v(yol: str) -> str:
    """`{% static %}` + DEV'da fayl o'zgarish vaqti (`?v=<mtime>`).

    ⚠️ NIMANI HAL QILADI (vaqt yedi, jonli brauzerda topildi)
       `runserver` ning statik ishlovchisi `Last-Modified` yuboradi, lekin
       `Cache-Control` YUBORMAYDI. Sarlavhasiz brauzer RFC 9111 bo'yicha
       EVRISTIK YANGILIK qo'llaydi: faylni qayta so'ramasdan keshdan
       oladi. Ya'ni `app.js` ni tahrirlaysiz, sahifani yangilaysiz — va
       ESKI kod ishlaydi.

       Xato ko'rinishi butunlay chalg'ituvchi: kodda siz yozgan narsa
       turibdi, brauzerda esa boshqacha xulq. Bir marta aynan shu sababdan
       mavjud bo'lmagan "mehmon xatosi" qidirildi; uni faqat
       `performance.getEntriesByType('resource')` dagi `transferSize: 0`
       fosh qildi.

    ⚠️ NEGA MIDDLEWARE EMAS
       Birinchi urinish `Cache-Control: no-store` qo'yadigan middleware
       edi va u ISHLAMADI: `runserver` statik fayllarni
       `StaticFilesHandler` orqali beradi, u esa middleware zanjirini
       BUTUNLAY CHETLAB O'TADI (so'rov Django'ning odatiy siklga
       umuman kirmaydi). Shuning uchun yechim so'rovda emas, MANZILDA.

    ⚠️ PRODDA HECH NIMA QO'SHILMAYDI
       U yerda fayllar hash bilan nomlanadi (`ManifestStaticFilesStorage`)
       va nginx ularni `immutable, max-age=31536000` bilan beradi —
       qo'shimcha parametr faqat keshni buzardi.
    """
    manzil = static(yol)
    if not settings.DEBUG:
        return manzil

    topilgan = finders.find(yol)
    if not topilgan:
        return manzil
    if isinstance(topilgan, list):  # bir nechta topilsa — birinchisi
        topilgan = topilgan[0]

    try:
        mtime = int(Path(topilgan).stat().st_mtime)
    except OSError:
        return manzil

    ajratgich = "&" if "?" in manzil else "?"
    return f"{manzil}{ajratgich}v={mtime}"
