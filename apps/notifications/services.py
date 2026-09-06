"""Bildirishnomalar — yozish va o'qish (D5-T1).

⚠️ `services.py` YOZADI, sanoq esa KESHDAN o'qiladi. Ikkalasi shu
   faylda, chunki ular BIR XIL keshni boshqaradi: yozuvchi tomon
   keshni tozalashni unutsa, sanoq soatlab noto'g'ri turardi.
"""

from __future__ import annotations

from django.conf import settings
from django.core.cache import cache
from django.db import models
from django.utils import timezone

from .models import BildirishnomaTuri, Notification


def kesh_kaliti(user_id: int) -> str:
    return f"bildirishnoma:oqilmagan:{user_id}"


def _keshni_tozalash(user_id: int) -> None:
    cache.delete(kesh_kaliti(user_id))


# ===========================================================================
# Yozish
# ===========================================================================
def bildirishnoma_yaratish(
    *,
    recipient,
    turi: str,
    actor=None,
    complaint=None,
    solution=None,
    kontakt_sorovi=None,
) -> Notification | None:
    """Bildirishnoma yozadi. O'ZINGIZGA yozilmaydi.

    ⚠️ O'ZIGA BILDIRISHNOMA YOZILMAYDI — bu eng ko'p uchraydigan
       bezovtalik: o'z muammosiga o'zi javob yozgan odam "sizga yechim
       keldi" degan xabar olardi. Tekshiruv chaqiruvchida emas, SHU
       YERDA: aks holda uni har yangi chaqiruv joyida takrorlash kerak
       bo'lardi va biri albatta unutilardi.

    ⚠️ `recipient` bo'sh bo'lishi MUMKIN: muallif hisobini o'chirgan
       bo'lsa `complaint.author` `None` (D2-T8). O'shanda hech narsa
       yozilmaydi.

    ⚠️⚠️ ANONIMLIK CHAQIRUVCHIDA HAL QILINADI: anonim manbada `actor`
       BERILMAYDI (model docstring'iga qarang). Bu yerda qo'shimcha
       tekshiruv yo'q, chunki bu funksiya manbaning anonimligini
       bilmaydi — u faqat unga berilgan narsani yozadi.
    """
    if recipient is None:
        return None
    if actor is not None and actor.pk == recipient.pk:
        return None

    bildirishnoma = Notification.objects.create(
        recipient=recipient,
        actor=actor,
        turi=turi,
        complaint=complaint,
        solution=solution,
        kontakt_sorovi=kontakt_sorovi,
    )
    _keshni_tozalash(recipient.pk)

    # ⚠️⚠️ `on_commit` — VAZIFANI TO'G'RIDAN-TO'G'RI `delay()` QILMANG.
    #
    #    Bu funksiya tranzaksiya ICHIDA chaqiriladi (`yechim_yozish`,
    #    `accept_solution` — ikkalasi ham `@transaction.atomic`). Vazifa
    #    darhol navbatga tushsa, worker uni tranzaksiya COMMIT
    #    bo'lgunicha olishi mumkin va o'shanda bildirishnoma bazada
    #    HALI YO'Q — vazifa "topilmadi" deb tugaydi.
    #
    #    Xato TASODIFIY bo'lardi: sekin bazada o'tib ketardi, yuk
    #    ostida esa qaytalanardi. `on_commit` uni butunlay yo'q qiladi.
    #
    # ⚠️ Import funksiya ichida: `tasks` -> `telegram` -> `settings`
    #    zanjiri modul yuklanishida kerak emas.
    from django.db import transaction

    from .tasks import telegram_yuborish

    transaction.on_commit(lambda: telegram_yuborish.delay(bildirishnoma.pk))

    return bildirishnoma


def dayjest_bildirishnomasi(*, ekspert, savollar) -> Notification | None:
    """Ekspertga haftalik dayjest yozuvi (D5-T5).

    ⚠️ `actor=None`: dayjestni ODAM yubormaydi, tizim yuboradi. Aktyor
       qo'yish "kimdir sizga yozdi" degan yolg'on taassurot berardi.

    ⚠️ `complaint` — ro'yxatning BIRINCHI savoli. U yagona savolni
       bildirmaydi: `matn` va `manzil` undan faqat KATEGORIYANI oladi
       (model docstring'i). Yon ta'siri foydali — savol haqiqiy
       o'chirilsa (D2-T8) dayjest yozuvi ham CASCADE bilan ketadi va
       yetim havola qolmaydi.
    """
    if not savollar:
        return None

    return bildirishnoma_yaratish(
        recipient=ekspert.user,
        turi=BildirishnomaTuri.DAYJEST,
        complaint=savollar[0],
    )


def kontakt_sorovi_bildirishnomasi(*, sorov) -> Notification | None:
    """«Sizga shaxsiy suhbat taklif qilindi» (D6-T5).

    ⚠️⚠️ `actor` BERILMAYDI. So'ragan odam anonim yozgan bo'lishi
       mumkin va `actor` bildirishnoma matnida uning ismini
       chiqarardi — anonimlik invariantining SUHBATDAGI ko'rinishi.
       Matn ismsiz ham to'liq ma'noli.
    """
    from apps.accounts.models import User

    oluvchi = User.objects.filter(pk=sorov.qarshi_tomon_id).first()
    return bildirishnoma_yaratish(
        recipient=oluvchi,
        turi=BildirishnomaTuri.KONTAKT_SOROVI,
        kontakt_sorovi=sorov,
    )


def kontakt_javobi_bildirishnomasi(*, sorov) -> Notification | None:
    """So'rov yuborgan odamga javob (qabul yoki rad).

    ⚠️ RAD ETILGANDA HAM yuboriladi: javobsiz qolgan so'rov odamni
       kutishda qoldirardi va u qayta-qayta tekshirib yurardi.
    """
    return bildirishnoma_yaratish(
        recipient=sorov.soragan,
        turi=BildirishnomaTuri.KONTAKT_JAVOBI,
        kontakt_sorovi=sorov,
    )


def yangi_xabar_bildirishnomasi(*, xabar) -> Notification | None:
    """Suhbatdagi yangi xabar haqida.

    ⚠️⚠️ O'QILMAGAN BILDIRISHNOMA TURGANDA YANGISI YARATILMAYDI.
       Aks holda faol suhbat o'nlab bildirishnoma va o'nlab Telegram
       xabari berardi — aynan D5-T4 ogohlantirgan «ortiqcha
       bildirishnoma botdan chiqib ketishga olib keladi» holati.

       Ya'ni bir suhbat bir «o'qilmagan» to'lqinda BITTA bildirishnoma
       beradi. Foydalanuvchi markazni ochib o'qigach, keyingi xabar
       yana xabar beradi.

    ⚠️ `actor` BERILMAYDI — sabab `kontakt_sorovi_bildirishnomasi` da.
    """
    from apps.accounts.models import User

    suhbat = xabar.suhbat
    oluvchi_id = next(
        (pk for pk in suhbat.ishtirokchi_idlari() if pk != xabar.author_id), None
    )
    if oluvchi_id is None:
        return None

    sorov = suhbat.sorov
    kutayotgan = Notification.objects.filter(
        recipient_id=oluvchi_id,
        turi=BildirishnomaTuri.YANGI_XABAR,
        kontakt_sorovi=sorov,
        okilgan_at__isnull=True,
    ).exists()
    if kutayotgan:
        return None

    return bildirishnoma_yaratish(
        recipient=User.objects.filter(pk=oluvchi_id).first(),
        turi=BildirishnomaTuri.YANGI_XABAR,
        kontakt_sorovi=sorov,
    )


def yangi_yechim_bildirishnomasi(*, solution) -> Notification | None:
    """Muammo egasiga "yechim keldi" deb xabar beradi (D1-T10 ulanishi).

    ⚠️⚠️ ANONIM YECHIMDA `actor` YOZILMAYDI. `public_author` — D1-T6
       dagi yagona ommaviy kirish nuqtasi va u anonim yechimda `None`
       qaytaradi. `solution.author` ni to'g'ridan-to'g'ri ishlatish
       anonimlikni JIM ravishda buzardi va buni faqat bildirishnoma
       ro'yxatini ochgan odam ko'rardi.
    """
    return bildirishnoma_yaratish(
        recipient=solution.complaint.author,
        turi=BildirishnomaTuri.YANGI_YECHIM,
        actor=solution.public_author,
        complaint=solution.complaint,
        solution=solution,
    )


def yechim_qabul_bildirishnomasi(*, solution) -> Notification | None:
    """Yechim muallifiga "javobingiz qabul qilindi" deb xabar beradi.

    ⚠️ Bu yerda `actor` — MUAMMO egasi (qabul qilgan odam). Muammo
       anonim bo'lsa u ham ko'rsatilmaydi.
    """
    return bildirishnoma_yaratish(
        recipient=solution.author,
        turi=BildirishnomaTuri.YECHIM_QABUL,
        actor=solution.complaint.public_author,
        complaint=solution.complaint,
        solution=solution,
    )


# ===========================================================================
# O'qish
# ===========================================================================
def oqilmagan_soni(user) -> int:
    """Sarlavhadagi belgi uchun o'qilmaganlar soni — KESHDAN.

    ⚠️⚠️ BU SANOQ HAR SAHIFADA KERAK. Keshsiz u har ko'rishda bitta
       qo'shimcha `COUNT(*)` degani bo'lardi — D1-T14 da qotirilgan
       so'rov byudjetiga to'g'ridan-to'g'ri qo'shilardi.

    ⚠️ D3-T3 dagi reytingdan FARQI: bu yerda kesh bo'sh bo'lsa sanoq
       HISOBLANADI. Sabab — narx boshqacha: reyting butun baza bo'ylab
       ikkita agregat so'rov edi, bu esa BITTA indeksli `COUNT` va u
       faqat bitta foydalanuvchiga tegishli (thundering herd yo'q).

    ⚠️ TTL — ZAXIRA. Sanoq o'zgarganda kesh OCHIQ tozalanadi
       (`_keshni_tozalash`); TTL esa tozalash unutilgan holat uchun
       xavfsizlik to'ri, aks holda noto'g'ri son mangu qolardi.
    """
    if not getattr(user, "is_authenticated", False):
        return 0

    kalit = kesh_kaliti(user.pk)
    soni = cache.get(kalit)
    if soni is None:
        soni = Notification.objects.filter(
            recipient=user, okilgan_at__isnull=True
        ).count()
        cache.set(kalit, soni, settings.BILDIRISHNOMA_KESH_MUDDATI)
    return soni


def hammasini_oqilgan_deb_belgilash(*, user) -> int:
    """Ro'yxat ochilganda hammasi o'qilgan deb belgilanadi (qabul mezoni).

    ⚠️ HAR BIRINI ALOHIDA BELGILASH TALAB QILINMAYDI: bildirishnoma —
       signal, vazifa ro'yxati emas. Ro'yxatni ochgan odam ularni
       ko'rgan hisoblanadi; aks holda belgi sahifadan chiqib ketgandan
       keyin ham osilib turardi va foydalanuvchi uni "buzuq" deb
       hisoblardi.

    ⚠️ `QuerySet.update()` — `save()` va signal chaqirilmaydi, lekin bu
       yerda kerak emas: kesh ochiq tozalanadi.
    """
    soni = Notification.objects.filter(recipient=user, okilgan_at__isnull=True).update(
        okilgan_at=timezone.now(), updated_at=timezone.now()
    )
    _keshni_tozalash(user.pk)
    return soni


def bildirishnomalar_royxati(*, user) -> models.QuerySet[Notification]:
    """Foydalanuvchining bildirishnomalari — yangisidan eskisiga.

    ⚠️ `select_related` — ro'yxatda har qator aktyor nomini va muammo
       sarlavhasini ko'rsatadi. Usiz 20 qator = 40 qo'shimcha so'rov
       (D1-T14 dagi bir xil sabab).

    ⚠️ `complaint__category` — dayjest qatorining matni va manzili
       kategoriyaga tayanadi (D5-T5). Usiz har dayjest qatori bitta
       qo'shimcha so'rov qilardi.
    """
    return (
        Notification.objects.filter(recipient=user)
        .select_related(
            "actor",
            "complaint",
            "complaint__category",
            # ⚠️ D6-T5: suhbat qatorining matni va manzili so'rovga
            #    tayanadi (`sorov.holat`, `sorov.suhbat`).
            "kontakt_sorovi",
            "kontakt_sorovi__suhbat",
        )
        .order_by("-created_at", "-id")
    )
