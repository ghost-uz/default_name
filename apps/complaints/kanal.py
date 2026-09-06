"""Telegram kanaliga avto-post (D5-T3).

⚠️ NEGA BU O'SISH KANALI
   Rejadagi strategiya: kanal obunachilari har kuni bir nechta qaynoq
   savolni ko'radi va ularning bir qismi javob yozish uchun saytga
   qaytadi. Bu SEO'dan farqli o'laroq darhol ishlaydi va sovuq start
   davrida yagona jonli trafik manbai bo'lishi mumkin.

⚠️⚠️ ANONIMLIK BU YERDA ENG XAVFLI
   Kanal posti QAYTARIB OLINMAYDI: u yuz minglab odamga bir zumda
   ko'rinadi va Telegram'da o'chirilgan xabar ham allaqachon o'qilgan
   bo'ladi. Ya'ni bu yerdagi xato — invariantning eng qimmat buzilishi.

   Shuning uchun matn `public_author` ga ham murojaat QILMAYDI: kanalda
   MUALLIF UMUMAN KO'RSATILMAYDI, na anonimda, na ochiqda. Kanal posti
   savolni ko'rsatadi, odamni emas.

⚠️⚠️ INQIROZ BELGISI BO'LGAN POST KANALGA CHIQMAYDI
   D2-T6 siyosati: aniqlangan post o'chirilmaydi va yashirilmaydi — u
   saytda odatdagidek turadi. Lekin uni MINGLAB odamga o'zimiz tarqatish
   butunlay boshqa narsa: bu odamning eng og'ir daqiqasini ommaviy
   tomoshaga aylantirardi.

   Farq nozik va muhim: biz kontentni CHEKLAMAYMIZ, lekin uni
   KUCHAYTIRMAYMIZ ham.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from .models import Complaint

log = logging.getLogger(__name__)


def nomzodlar() -> models.QuerySet[Complaint]:
    """Kanalga chiqishi mumkin bo'lgan postlar — eng qaynog'idan.

    ⚠️ `visible()` — yashirilgan yoki tekshiruvdagi post kanalga
       chiqsa, moderatsiyaning ma'nosi qolmaydi (D2-T3).

    ⚠️ FAQAT YANGI POSTLAR: `hot_score` eski postda ham yuqori bo'lishi
       mumkin (ko'p ovoz yig'gan). Kanal esa "bugun nima bo'lyapti"
       degan lenta — bir oylik post u yerda g'alati ko'rinadi va
       obunachiga yangi narsa bermaydi.
    """
    chegara = timezone.now() - timedelta(days=settings.KANAL_OYNA_KUNLARI)

    return (
        Complaint.objects.visible()
        .filter(
            created_at__gte=chegara,
            kanalga_yuborilgan_at__isnull=True,
            # ⚠️ Inqiroz belgisi — modul docstring'idagi sabab.
            inqiroz_aniqlandi=False,
        )
        .select_related("category")
        .order_by("-hot_score", "-created_at", "-id")
    )


def post_matni(muammo: Complaint) -> str:
    """Kanal posti — sarlavha, kategoriya va qisqa parcha.

    ⚠️⚠️ MUALLIF YO'Q — na ismi, na `public_author`. Modul
       docstring'idagi sabab: kanal posti savolni ko'rsatadi, odamni
       emas, va xatoni qaytarib bo'lmaydi.

    ⚠️ Parcha QISQA: Telegram uzun xabarni yig'ib qo'yadi va
       "ko'proq" tugmasi ostida qolgan matn o'qilmaydi. Maqsad —
       qiziqtirish, to'liq javob berish emas.
    """
    from apps.notifications.telegram import html_qochirish

    tavsif = muammo.description.strip()
    if len(tavsif) > settings.KANAL_PARCHA_UZUNLIGI:
        tavsif = tavsif[: settings.KANAL_PARCHA_UZUNLIGI].rstrip() + "…"

    qatorlar = [
        f"<b>{html_qochirish(muammo.title)}</b>",
        "",
        html_qochirish(tavsif),
    ]
    if muammo.category_id:
        qatorlar += ["", f"#{html_qochirish(muammo.category.name).replace(' ', '_')}"]

    return "\n".join(qatorlar)


def belgilash(muammo: Complaint) -> None:
    """Postni "kanalga chiqdi" deb belgilaydi.

    ⚠️ `QuerySet.update()` — `save()` `updated_at` ni yangilardi va post
       lentada "hozirgina tahrirlangan" bo'lib ko'rinardi. Kanalga
       chiqish kontentga tegmaydi.

    ⚠️ `all_objects`: belgilash — hisobot yozuvi, ko'rsatish emas.
    """
    # korinish-istisno: belgi qo'yish, kontent ko'rsatish emas. Post
    # `nomzodlar()` da allaqachon `visible()` dan o'tgan.
    Complaint.all_objects.filter(pk=muammo.pk).update(
        kanalga_yuborilgan_at=timezone.now()
    )
