"""Bildirishnoma sozlamalari (D5-T4).

⚠️⚠️ SOZLAMA YETKAZISHNI BOSHQARADI, YOZUVNI EMAS.
   O'chirilgan tur uchun ham `Notification` yozuvi YARATILADI — faqat
   Telegram xabari yuborilmaydi.

   Sabab: ichki markaz (D5-T1) — ZAXIRA kanal. Foydalanuvchi "Telegram'da
   bezovta qilmang" degan bo'lsa, bu "menga umuman aytmang" degani emas:
   u saytga kirganda nima bo'lganini ko'rishi kerak. Yozuvni ham
   to'xtatish esa tarixni yo'q qilardi va uni qaytarib bo'lmasdi.

⚠️ NEGA "ORTIQCHA BILDIRISHNOMA" JIDDIY MUAMMO
   Task `nega` bo'limi: ortiqcha bildirishnoma botdan chiqib ketishga
   olib keladi — VA U QAYTMAYDI. Ya'ni bitta keraksiz xabar butun
   kanalni yo'qotishi mumkin. Shuning uchun standart sozlama ehtiyotkor.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

from django.conf import settings
from django.utils import timezone

from .models import BildirishnomaTuri

# ⚠️⚠️ D5-T4 QABUL MEZONI: "standart holatda faqat MUHIM bildirishnomalar
#    yoqiq".
#
#    Ro'yxat ATAYLAB qisqa va yopiq: yangi tur qo'shilganda u standart
#    holatda O'CHIQ bo'ladi. Bu tanlov ehtiyotkor tomonga xato qiladi —
#    yangi tur qo'shgan dasturchi uni ochiq deb belgilashni ONGLI
#    ravishda qilishi kerak, unutib qo'yish esa hech kimni bezovta
#    qilmaydi.
MUHIM_TURLAR = frozenset(
    {
        # Muammo egasiga javob kelgani — retention'ning butun sababi.
        BildirishnomaTuri.YANGI_YECHIM,
        # Javob qabul qilingani — kam uchraydigan va kuchli ijobiy signal.
        BildirishnomaTuri.YECHIM_QABUL,
        # ⚠️⚠️ DAYJEST (D5-T5) — bu ro'yxatga ONGLI ravishda qo'shildi.
        #
        #    Yuqoridagi ehtiyotkorlik qoidasi HAJMGA qarshi edi: ko'p
        #    xabar botdan chiqib ketishga olib keladi. Dayjest esa
        #    HAFTADA BIR MARTA va faqat tasdiqlangan ekspertga boradi —
        #    ya'ni u dalil bu yerda ishlamaydi.
        #
        #    Teskarisi rost: ekspert ariza topshirib, tasdiqlanib, keyin
        #    hech narsa olmasa — u qaytmaydi. Standart holatda o'chiq
        #    dayjest sozlamalar sahifasini ochgan bir necha odamga
        #    yetardi, ya'ni taskning maqsadi bajarilmasdi.
        BildirishnomaTuri.DAYJEST,
        # ⚠️⚠️ SUHBAT TURLARI (D6-T5) — uchalasi ham ONGLI ravishda.
        #
        #    So'rov va javob KAM UCHRAYDI (faqat qabul qilingan
        #    yechimdan keyin, yechimga bitta) va ular JAVOB TALAB
        #    QILADI — o'chiq bo'lsa odam so'rovni ko'rmay qolardi va
        #    qarshi tomon «javob bermadi» deb o'ylardi.
        #
        #    `YANGI_XABAR` esa hajm bo'yicha xavfli ko'rinadi, lekin
        #    `services.yangi_xabar_bildirishnomasi` uni CHEKLAYDI:
        #    o'qilmagan bildirishnoma turganda YANGISI YARATILMAYDI.
        #    Ya'ni bir suhbat bir «o'qilmagan» to'lqinda BITTA
        #    bildirishnoma beradi, yuzta emas.
        BildirishnomaTuri.KONTAKT_SOROVI,
        BildirishnomaTuri.KONTAKT_JAVOBI,
        BildirishnomaTuri.YANGI_XABAR,
    }
)


def standart_yoqilganmi(turi: str) -> bool:
    """Sozlama berilmagan turda standart holat."""
    return turi in MUHIM_TURLAR


def jim_vaqtmi(*, hozir: datetime | None = None) -> bool:
    """Hozir "jim soatlar" oynasidami.

    ⚠️ MAHALLIY VAQT bo'yicha: baza UTC'da ishlaydi, foydalanuvchi esa
       Toshkentda uxlaydi (`TIME_ZONE = "Asia/Tashkent"`). UTC bilan
       solishtirish oynani besh soatga siljitardi va xabar aynan tunda
       kelardi.

    ⚠️ OYNA YARIM TUNDAN O'TADI (22:00 -> 08:00), ya'ni oddiy
       `boshlanish <= hozir < tugash` taqqoslash ISHLAMAYDI — u har
       doim `False` berardi.
    """
    hozir = timezone.localtime(hozir)
    boshlanish: time = settings.JIM_SOATLAR_BOSHI
    tugash: time = settings.JIM_SOATLAR_OXIRI
    vaqt = hozir.time()

    if boshlanish <= tugash:
        return boshlanish <= vaqt < tugash
    return vaqt >= boshlanish or vaqt < tugash


def jim_oyna_tugashigacha(*, hozir: datetime | None = None) -> int:
    """Jim oyna tugashigacha necha sekund qolgani.

    ⚠️ XABAR TASHLANMAYDI, KECHIKTIRILADI. "Jim soatlarda yubormaslik"
       ni "umuman yubormaslik" deb tushunish oson va noto'g'ri:
       foydalanuvchi tunda bezovta qilinmaslikni so'radi, xabardan voz
       kechishni emas. Kechiktirish ikkalasini ham beradi.
    """
    hozir = timezone.localtime(hozir)
    tugash: time = settings.JIM_SOATLAR_OXIRI

    nishon = hozir.replace(
        hour=tugash.hour, minute=tugash.minute, second=0, microsecond=0
    )
    if nishon <= hozir:
        nishon += timedelta(days=1)

    return int((nishon - hozir).total_seconds())
