"""To'lovlar — yozish amallari (D6-T1).

⚠️ OBUNA FAQAT SHU YERDA O'ZGARADI. D6-T2/T3 (Click/Payme) webhook'lari
   ham shu funksiyalarni chaqiradi — provayderga xos kod obuna
   mantiqini TAKRORLAMASIN, aks holda ikkita to'lov yo'li ikki xil
   qoida bo'yicha ishlardi va farqni faqat mijoz sezardi.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import ObunaHolati, ObunaRejasi, Subscription

log = logging.getLogger(__name__)


def _keshni_yangilash(user, obuna: Subscription) -> None:
    """Chaqiruvchi ushlab turgan `user` obyektidagi obunani yangilaydi.

    ⚠️⚠️ NEGA BU KERAK — JIM ESKIRISH.
       Bu funksiyalar obunani `select_for_update()` bilan QAYTA oladi,
       ya'ni ular chaqiruvchidagi `user.obuna` dan BOSHQA nusxani
       o'zgartiradi. Django teskari OneToOne ni obyektda keshlaydi
       (mavjud emasligini HAM keshlaydi), shuning uchun uzaytirishdan
       keyin O'SHA SO'ROV ichida `user.has_pro` hamon ESKI javobni
       berardi.

       Bu D6-T2/T3 da haqiqiy xatoga aylanardi: to'lov webhook'i
       obunani uzaytiradi, keyin o'sha so'rovda javob sahifasi
       "PRO faol emas" deb ko'rsatardi. Xato tasodifiy ko'rinardi —
       yangi so'rovda hammasi to'g'ri bo'lardi.

       Testlar buni ushladi (`test_MUDDATI_OTGAN_obuna_HOZIRDAN_boshlanadi`).
    """
    user.obuna = obuna


@transaction.atomic
def obunani_uzaytirish(
    *,
    user,
    kunlar: int | None = None,
    plan: str = ObunaRejasi.PRO,
) -> Subscription:
    """Obunani yaratadi yoki uzaytiradi.

    ⚠️⚠️ UZAYTIRISH QOLGAN MUDDAT USTIGA QO'SHILADI, `now` DAN EMAS.
       Muddati tugamagan obunani yangilagan odam qolgan kunlarini
       YO'QOTMASLIGI kerak — `now + 30` shakli aynan shuni qilardi va
       erta to'lagan mijozni jazolardi.

       Muddati ALLAQACHON o'tgan bo'lsa esa `now` dan boshlanadi:
       teskarisida uzoq tanaffusdan keyin qaytgan odam o'tmishga
       to'lagan bo'lardi.

    ⚠️ `select_for_update` — ikkita webhook bir vaqtda kelsa (D6-T2/T3
       da qayta urinish ODATIY hol) ikkalasi ham bir xil `expires_at`
       ni o'qib, bittasining uzaytirishi yo'qolardi.
    """
    kunlar = kunlar if kunlar is not None else settings.OBUNA_MUDDATI_KUN
    hozir = timezone.now()

    obuna = Subscription.objects.select_for_update().filter(user=user).first()
    if obuna is None:
        obuna = Subscription.objects.create(
            user=user,
            plan=plan,
            status=ObunaHolati.FAOL,
            started_at=hozir,
            expires_at=hozir + timedelta(days=kunlar),
        )
        log.info("obuna: yaratildi (user=%s, kun=%s)", user.pk, kunlar)
        _keshni_yangilash(user, obuna)
        return obuna

    asos = obuna.expires_at if obuna.expires_at > hozir else hozir
    obuna.expires_at = asos + timedelta(days=kunlar)
    obuna.plan = plan
    obuna.status = ObunaHolati.FAOL
    if asos == hozir:
        # Tanaffusdan keyin qaytdi — yangi davr boshlandi.
        obuna.started_at = hozir
    obuna.save(
        update_fields=["expires_at", "plan", "status", "started_at", "updated_at"]
    )
    log.info("obuna: uzaytirildi (user=%s, kun=%s)", user.pk, kunlar)
    _keshni_yangilash(user, obuna)
    return obuna


def avto_yangilashni_ozgartirish(*, user, yoqilsin: bool) -> Subscription | None:
    """«Bekor qilish» — avtomatik yangilashni o'chirish.

    ⚠️⚠️ OBUNA DARHOL TO'XTAMAYDI. Odam to'lagan muddati uchun xizmatni
       oladi; holati `FAOL` bo'lib qolaveradi va muddat tugagach
       vazifa uni `TUGAGAN` ga o'tkazadi.

       Darhol to'xtatish «bekor qilish» tugmasini JAZOGA aylantirardi:
       oyning boshida bekor qilgan odam yigirma to'qqiz kunini
       yo'qotardi va bu pulni qaytarish talabini keltirib chiqarardi.
    """
    obuna = Subscription.objects.filter(user=user).first()
    if obuna is None:
        return None

    obuna.auto_renew = yoqilsin
    obuna.save(update_fields=["auto_renew", "updated_at"])
    _keshni_yangilash(user, obuna)
    return obuna


def muddati_otganlarni_belgilash() -> int:
    """Muddati o'tgan FAOL obunalarni `TUGAGAN` deb belgilaydi.

    ⚠️⚠️ BU TOZALASH, HAQIQAT MANBAI EMAS. `Subscription.faolmi`
       muddatni HAR DOIM o'zi tekshiradi, ya'ni bu vazifa umuman
       ishlamasa ham hech kim bepul PRO olmaydi. Vazifaning ishi —
       hisobotlar va so'rovlar uchun holatni haqiqatga yaqin tutish.

    ⚠️ `update()` — `save()` har qator uchun so'rov qilardi va bu yerda
       hech qanday model mantiqi kerak emas.
    """
    return Subscription.objects.filter(
        status=ObunaHolati.FAOL, expires_at__lte=timezone.now()
    ).update(status=ObunaHolati.TUGAGAN, updated_at=timezone.now())
