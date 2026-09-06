"""Kontakt so'rovi va suhbat — yozish amallari (D6-T5).

⚠️ RUXSAT TEKSHIRUVI XIZMATDA, faqat ko'rinishda emas: bu funksiyalar
   keyinchalik bot va admin buyruqlaridan ham chaqiriladi (D1-T10 dagi
   `accept_solution` bilan bir xil qaror).
"""

from __future__ import annotations

import logging

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from .models import KontaktSorovi, SorovHolati, Suhbat, Xabar

log = logging.getLogger(__name__)


def _yozish_huquqi(user) -> None:
    """⚠️ Bloklangan odam suhbatda ham YOZA OLMAYDI (D2-T11).

    Usiz blok «lentada yozolmayman, lekin shaxsiyda yozaveraman»
    degan teshikka aylanardi — va aynan shaxsiy kanal bezovtalik
    uchun eng qulay joy.
    """
    if not getattr(user, "can_write", False):
        raise PermissionDenied("Hisobingiz cheklangan — yoza olmaysiz.")


def _bloklanganmi(*, kim_id: int, kimni_id: int) -> bool:
    """⚠️ IKKI TOMONLAMA tekshiriladi — `UserBlock` o'zi bir tomonlama.

    D2-T11 da bir tomonlamalik ATAYLAB: A B ni bloklasa, B buni
    bilmasligi kerak. Lekin shaxsiy kanal OCHISH boshqa gap —
    bloklagan odamga suhbat so'rovi kelishi blokning butun ma'nosini
    yo'qotardi, bloklangan odam esa baribir hech qanday signal
    olmaydi (so'rovni u YUBORA olmaydi, xolos).
    """
    from django.db.models import Q

    from apps.accounts.models import UserBlock

    return UserBlock.objects.filter(
        Q(user_id=kim_id, blocked_id=kimni_id) | Q(user_id=kimni_id, blocked_id=kim_id)
    ).exists()


@transaction.atomic
def kontakt_sorash(*, solution, soragan) -> KontaktSorovi:
    """«Shaxsiy suhbat ochaylikmi?» so'rovini yuboradi.

    ⚠️⚠️ FAQAT QABUL QILINGAN YECHIMDA. Task: «yechim qabul
       qilingandan keyin». Bu shart bezovtalikka qarshi ham ishlaydi:
       tasodifiy odam istalgan postga shaxsiy suhbat so'rab yura
       olmaydi — avval uning javobi TANLANGAN bo'lishi kerak.

    ⚠️ BLOK IKKI TOMONLAMA TEKSHIRILADI. `UserBlock` o'zi bir
       tomonlama (D2-T11) va bu TO'G'RI — lekin shaxsiy kanal ochish
       boshqa gap: bloklagan odamga suhbat so'rovi kelishi blokning
       butun ma'nosini yo'qotardi.
    """
    _yozish_huquqi(soragan)

    if not solution.is_accepted:
        raise ValidationError(
            "Shaxsiy suhbat faqat yechim qabul qilingandan keyin ochiladi."
        )
    if solution.is_deleted or not solution.is_publicly_visible:
        raise ValidationError("Bu yechim uchun suhbat ochib bo'lmaydi.")

    ishtirokchilar = {solution.complaint.author_id, solution.author_id}
    if soragan.pk not in ishtirokchilar:
        raise PermissionDenied("Siz bu suhbatning tomoni emassiz.")
    if None in ishtirokchilar or len(ishtirokchilar) < 2:
        # Bir tomon hisobini o'chirgan (D2-T8) yoki o'ziga o'zi javob yozgan.
        raise ValidationError("Bu yechim uchun suhbat ochib bo'lmaydi.")

    qarshi_id = (
        solution.author_id
        if soragan.pk == solution.complaint.author_id
        else solution.complaint.author_id
    )
    if _bloklanganmi(kim_id=soragan.pk, kimni_id=qarshi_id):
        raise ValidationError("Bu foydalanuvchi bilan suhbat ochib bo'lmaydi.")

    mavjud = KontaktSorovi.objects.filter(solution=solution).first()
    if mavjud is not None:
        # ⚠️ RAD ETILGAN SO'ROV QAYTA YUBORILMAYDI. Aks holda «yo'q»
        #    javobi hech narsani anglatmasdi va rad etish tugmasi
        #    bezovtalikni to'xtatmasdi.
        raise ValidationError("Bu yechim uchun so'rov allaqachon yuborilgan.")

    sorov = KontaktSorovi.objects.create(solution=solution, soragan=soragan)
    log.info("suhbat: so'rov yuborildi (yechim=%s, kim=%s)", solution.pk, soragan.pk)

    from apps.notifications.services import kontakt_sorovi_bildirishnomasi

    kontakt_sorovi_bildirishnomasi(sorov=sorov)
    return sorov


@transaction.atomic
def sorovga_javob(*, sorov: KontaktSorovi, user, qabul: bool) -> KontaktSorovi:
    """⚠️ QABUL MEZONI: «rad etish imkoniyati bor».

    ⚠️ Rad etish SABABSIZ va IZOHSIZ. Sabab so'rash rad etgan odamni
       o'zini oqlashga majbur qilardi; «yo'q» yetarli javob.

    ⚠️ Javob FAQAT QARSHI TOMONDAN. So'rovni yuborgan odam uni o'zi
       qabul qila olmaydi — aks holda rozilik talabi bir bosishda
       chetlab o'tilardi.
    """
    sorov = KontaktSorovi.objects.select_for_update().get(pk=sorov.pk)

    if sorov.qarshi_tomon_id != getattr(user, "pk", None):
        raise PermissionDenied("Bu so'rovga siz javob bera olmaysiz.")
    if sorov.holat != SorovHolati.KUTILMOQDA:
        raise ValidationError("Bu so'rovga allaqachon javob berilgan.")

    sorov.holat = SorovHolati.QABUL_QILINDI if qabul else SorovHolati.RAD_ETILDI
    sorov.javob_at = timezone.now()
    sorov.save(update_fields=["holat", "javob_at", "updated_at"])

    if qabul:
        Suhbat.objects.create(sorov=sorov)
        log.info("suhbat: so'rov qabul qilindi (sorov=%s)", sorov.pk)
    else:
        log.info("suhbat: so'rov rad etildi (sorov=%s)", sorov.pk)

    from apps.notifications.services import kontakt_javobi_bildirishnomasi

    kontakt_javobi_bildirishnomasi(sorov=sorov)
    return sorov


@transaction.atomic
def xabar_yozish(*, suhbat: Suhbat, author, matn: str) -> Xabar:
    """Suhbatga xabar qo'shadi.

    ⚠️ YOPIQ SUHBATGA YOZIB BO'LMAYDI — «yopish» tugmasi haqiqiy
       to'xtatish bo'lishi kerak, aks holda u faqat ko'rinish bo'lardi.

    ⚠️ INQIROZ ANIQLASH SHU YERDA HAM ishlaydi (D2-T6). Eng og'ir gap
       aynan shaxsiy yozishmada aytiladi va u ommaviy lentada hech
       qachon ko'rinmaydi — ya'ni bu tekshiruvsiz signal butunlay
       yo'qolardi.
    """
    _yozish_huquqi(author)

    if not suhbat.ishtirokchimi(author):
        raise PermissionDenied("Siz bu suhbatning tomoni emassiz.")
    if suhbat.yopiqmi:
        raise ValidationError("Suhbat yopilgan.")

    matn = (matn or "").strip()
    if not matn:
        raise ValidationError("Xabar bo'sh bo'lishi mumkin emas.")

    # korinish-istisno: YARATISH amali — yangi xabar har doim
    # ko'rinadigan holatda tug'iladi, filtrlanadigan narsa yo'q.
    xabar = Xabar.objects.create(suhbat=suhbat, author=author, content=matn)

    # ⚠️ `updated_at` — suhbatlar ro'yxati oxirgi harakat bo'yicha
    #    tartiblanadi; usiz yangi xabar ro'yxatni qayta tartiblamasdi.
    Suhbat.objects.filter(pk=suhbat.pk).update(updated_at=timezone.now())

    from apps.moderation.services import inqirozni_belgilash

    inqirozni_belgilash(target=xabar, matnlar=[matn])

    from apps.notifications.services import yangi_xabar_bildirishnomasi

    yangi_xabar_bildirishnomasi(xabar=xabar)
    return xabar


def suhbatni_yopish(*, suhbat: Suhbat, user) -> Suhbat:
    """⚠️ HAR IKKI TOMON YOPA OLADI va yopilgan suhbat QAYTA OCHILMAYDI.

    Qayta ochish tugmasi «yopish» ni yumshoq taklifga aylantirardi:
    bezovta qilayotgan odam qayta ochishni so'rab yana yozishardi.
    Yozishma QOLADI (ikkala tomon o'qiy oladi) — o'chirish esa
    shikoyat uchun dalilni yo'q qilardi.
    """
    if not suhbat.ishtirokchimi(user):
        raise PermissionDenied("Siz bu suhbatning tomoni emassiz.")
    if suhbat.yopiqmi:
        return suhbat

    suhbat.yopilgan_at = timezone.now()
    suhbat.yopgan = user
    suhbat.save(update_fields=["yopilgan_at", "yopgan", "updated_at"])
    log.info("suhbat: yopildi (suhbat=%s, kim=%s)", suhbat.pk, user.pk)
    return suhbat


def okilgan_deb_belgilash(*, suhbat: Suhbat, user) -> int:
    """Qarshi tomonning o'qilmagan xabarlarini belgilaydi."""
    # korinish-istisno: YOZISH amali (o'qilgan belgisi). Yashirilgan
    # xabarni ham belgilash zarar qilmaydi va uni chetlab o'tish
    # o'qilmaganlar sanog'ini abadiy nolga tushmaydigan qilardi.
    return (
        Xabar.objects.filter(suhbat=suhbat, okilgan_at__isnull=True)
        .exclude(author=user)
        .update(okilgan_at=timezone.now())
    )
