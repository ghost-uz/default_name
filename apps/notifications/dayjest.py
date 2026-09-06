"""Ekspertlarga «javobsiz savollar» dayjesti (D5-T5).

⚠️ NEGA BU SOVUQ START DAVRIDA ENG FOYDALI VAZIFA
   Task `nega` bo'limi ikki muammoni bir vaqtda ko'rsatadi: javobsiz
   savollar kamayadi VA ekspert qaytib keladi. Yangi platformaning eng
   katta xavfi — savol yozgan odam javob olmasligi: u qaytmaydi va
   boshqalarga ham aytmaydi. Ekspert esa ro'yxatdan o'tib, keyin nima
   qilishni bilmay yo'qoladi. Dayjest ikkalasini bir-biriga ulaydi.

⚠️⚠️ QABUL MEZONI: FAQAT EKSPERT SOHASIGA MOS SAVOLLAR.
   `ExpertProfile.specialty` — `Category` ga FK (D3-T5), ya'ni "shu
   kategoriyadagi javobsiz savollar" so'rovi to'g'ridan-to'g'ri
   ifodalanadi. D3-T5 docstring'i aynan shu taskni ko'zlab shunday
   yozilgan: ikkinchi taksonomiya («Huquq» bu yerda, «huquq» u yerda)
   bir kuni ajralib ketardi va dayjest noto'g'ri odamga borardi.

⚠️⚠️ INQIROZ BELGISI BOR POST DAYJESTGA KIRMAYDI — LEKIN D5-T3 DAN
   BOSHQA SABABGA KO'RA.
   Kanalda (D5-T3) sabab KUCHAYTIRISH edi: minglab odamga tarqatish.
   Bu yerda esa auditoriya bitta malakali odam, ya'ni u dalil ishlamaydi.

   Haqiqiy sabab — ASBOB NOTO'G'RI: dayjest HAFTALIK va u "ish navbati"
   shaklida keladi. Shoshilinch yordamga muhtoj odamning yozuvini olti
   kun kutadigan navbatga qo'yish ikki marta xato: yordam kechikadi, va
   biz uni "bajariladigan ish" qatoriga tushirib qo'yamiz. Inqirozga
   javob D2-T6 dagi darhol ko'rsatiladigan telefonlar, dayjest emas.

⚠️ ANONIMLIK: dayjestda MUALLIF KO'RSATILMAYDI (kanal bilan bir xil).
   Ekspert SAVOLGA javob beradi, odamga emas — va matnda muallif
   bo'lmasa, uni oshkor qilish ehtimoli ham yo'q.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.accounts.models import ExpertProfile, TasdiqHolati
from apps.complaints.models import Complaint, ComplaintStatus
from apps.solutions.models import Solution

log = logging.getLogger(__name__)


def _bloklanmagan() -> models.Q:
    """Bloki HOZIR kuchda bo'lmagan foydalanuvchilar.

    ⚠️ `is_banned=False` YETARLI EMAS: vaqtinchalik blok muddati o'tgan
       bo'lsa bayroq hali `True` turishi mumkin (uni fon vazifasi
       tozalaydi). Bu — `User.is_currently_banned` xossasining SQL
       shakli; xossaning o'zi bu yerda ishlatib bo'lmaydi, chunki
       filtr bazada bajarilishi kerak.
    """
    return models.Q(user__is_banned=False) | models.Q(
        user__banned_until__lt=timezone.now()
    )


def ekspertlar() -> models.QuerySet[ExpertProfile]:
    """Dayjest oladigan ekspertlar.

    ⚠️ `pro_faolmi` TEKSHIRILMAYDI — ATAYLAB. PRO to'lov bilan bog'liq
       (D3-T5), dayjest esa yo'naltirish vositasi. Faqat to'lovchilarga
       yuborish taskning maqsadini — javobsiz savollarni kamaytirishni —
       buzardi: eng ko'p javob yozadigan odam eng ko'p to'lovchi emas.

    ⚠️ BLOKLANGAN ODAMGA YUBORILMAYDI: u yoza olmaydi (D2-T11), ya'ni
       dayjest uni bajarib bo'lmaydigan ishga chaqirardi.

    ⚠️ `telegram_bloklandi` — D5-T2 dagi belgi. Botni bloklagan odamga
       urinish navbatni bekorga aylantiradi.
    """
    return (
        ExpertProfile.objects.filter(
            _bloklanmagan(),
            verification_status=TasdiqHolati.TASDIQLANGAN,
            user__is_active=True,
            user__telegram_id__isnull=False,
            user__telegram_bloklandi=False,
        )
        .select_related("user", "specialty")
        .order_by("pk")
    )


def javobsiz_savollar(*, kategoriya_idlari: list[int]) -> models.QuerySet[Complaint]:
    """Berilgan kategoriyalardagi javobsiz savollar — eng uzoq kutgani birinchi.

    ⚠️ `visible()` — D2-T3 dagi yagona kirish nuqtasi. Yashirilgan post
       dayjestga tushsa, moderatsiyaning ma'nosi qolmaydi.

    ⚠️ "JAVOBSIZ" = KO'RINADIGAN yechimi yo'q. Yashirilgan yoki
       o'chirilgan yechim JAVOB EMAS: savol egasi uchun ham, ekspert
       uchun ham u mavjud emas. `Solution.objects` — "tirik" menejer,
       ya'ni yumshoq o'chirilgan yechim ham hisobga olinmaydi.

    ⚠️ `status=OPEN`: muallif savolini YOPGAN bo'lsa (o'zi hal qildi
       yoki dolzarbligini yo'qotdi), unga javob kutilmaydi. Bu
       "javobsiz" bo'lsa ham, ekspert vaqtini yeydi.

    ⚠️ TARTIB — ENG ESKISI BIRINCHI, eng yangisi emas.
       Maqsad "bu haftada nima bo'ldi" emas, JAVOBSIZ SAVOLLARNI
       KAMAYTIRISH. Yangisidan boshlansa, band kategoriyada eski
       savollar HECH QACHON ro'yxatga tushmasdi: har hafta yangi beshta
       kelardi va eskilari ostida ko'milib qolardi.

       Takror ATAYLAB: javob berilmagan savol keyingi haftada yana
       chiqadi. Dayjest — yangiliklar lentasi emas, ISH NAVBATI.
       Oyna (`DAYJEST_OYNA_KUNLARI`) uni cheklaydi: umidsiz eski savol
       o'zi tushib qoladi.
    """
    if not kategoriya_idlari:
        # korinish-istisno: bo'sh natija — hech qanday qator qaytmaydi,
        # ya'ni ko'rinish filtri qo'llaydigan narsa yo'q.
        return Complaint.objects.none()

    chegara = timezone.now() - timedelta(days=settings.DAYJEST_OYNA_KUNLARI)

    # ⚠️ `Solution.objects.visible()` ota-postning holatini ham
    #    tekshiradi (D2-T1 da tuzatilgan xato) — bu yerda ortiqcha,
    #    lekin zararsiz va `visible()` invariantini buzmaydi.
    javobli = Solution.objects.visible().values("complaint_id")

    return (
        Complaint.objects.visible()
        .filter(
            category_id__in=kategoriya_idlari,
            status=ComplaintStatus.OPEN,
            created_at__gte=chegara,
            # ⚠️ Modul docstring'idagi sabab — asbob noto'g'ri, kuchaytirish emas.
            inqiroz_aniqlandi=False,
        )
        .exclude(pk__in=javobli)
        .select_related("category")
        .order_by("created_at", "id")
    )


def savollar_uchun(ekspert: ExpertProfile) -> list[Complaint]:
    """Bitta ekspert uchun ro'yxat.

    ⚠️ Bu YOLG'IZ chaqiruv yo'li: `dayjestlar()` hamma ekspert uchun
       BITTA so'rov qiladi. Bu funksiya xabar yuborish paytida qayta
       hisoblash uchun (`tasks._dayjest_matni`), ya'ni kamdan-kam.
    """
    return list(
        javobsiz_savollar(kategoriya_idlari=[ekspert.specialty_id])[
            : settings.DAYJEST_SAVOL_SONI
        ]
    )


def dayjestlar() -> list[tuple[ExpertProfile, list[Complaint]]]:
    """Hamma ekspert uchun ro'yxatlar — IKKI so'rovda.

    ⚠️ EKSPERT BOSHIGA SO'ROV QILINMAYDI (D1-T14 dagi N+1 qoidasi).
       Har ekspert uchun alohida so'rov 100 ta ekspertda 100 ta so'rov
       degani; guruhlash Python'da qilinadi. So'rov soni ekspertlar
       soniga BOG'LIQ EMAS.

    ⚠️ BO'SH RO'YXAT QAYTARILMAYDI. "Bu hafta sohangizda javobsiz savol
       yo'q" degan xabar — aynan botdan chiqib ketishga olib keladigan
       shovqin (D5-T4). Jim turish yaxshiroq.
    """
    ekspert_royxati = list(ekspertlar())
    if not ekspert_royxati:
        return []

    kategoriyalar = {e.specialty_id for e in ekspert_royxati}
    hammasi = list(javobsiz_savollar(kategoriya_idlari=sorted(kategoriyalar)))

    guruh: dict[int, list[Complaint]] = {kid: [] for kid in kategoriyalar}
    for muammo in hammasi:
        guruh[muammo.category_id].append(muammo)

    chegara = settings.DAYJEST_SAVOL_SONI
    natija = []
    for ekspert in ekspert_royxati:
        savollar = guruh[ekspert.specialty_id][:chegara]
        if savollar:
            natija.append((ekspert, savollar))
    return natija


def xabar_matni(*, ekspert: ExpertProfile, savollar: list[Complaint]) -> str:
    """Telegram xabari — sarlavhalar va to'g'ridan-to'g'ri havolalar.

    ⚠️⚠️ MUALLIF YO'Q — na ismi, na `public_author` (kanal bilan bir
       xil qoida, D5-T3). Ekspert savolga javob beradi, odamga emas.

    ⚠️ HAVOLA HAR SAVOLDA: dayjestning butun qiymati — bir bosishda
       javob yozish sahifasiga tushish. "Saytga kiring va qidiring"
       degan xabar hech kimni qaytarmaydi.
    """
    from .telegram import html_qochirish

    sayt = settings.SAYT_MANZILI
    qatorlar = [
        f"<b>{html_qochirish(ekspert.specialty.name)}</b> sohasida javobsiz savollar:",
        "",
    ]
    for muammo in savollar:
        manzil = f"{sayt}{muammo.get_absolute_url()}"
        qatorlar.append(f'• <a href="{manzil}">{html_qochirish(muammo.title)}</a>')

    return "\n".join(qatorlar)
