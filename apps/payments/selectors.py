"""To'lovlar — o'qish so'rovlari (D6-T4).

⚠️⚠️ NEGA BOOST TANLASH `complaints` DA EMAS
   README qoidasi: ilovalar orasidagi bog'liqlik BIR TOMONLAMA
   (`payments` -> `complaints` mumkin, teskarisi yo'q). Lenta so'rovi
   `complaints.selectors` da yashaydi va to'lov haqida hech narsa
   bilmaydi; bu modul uni QAYTA ISHLATADI (`lenta_queryset`), natijani
   esa ko'rinish qatlami (`complaints.views.feed`) birlashtiradi —
   `gamification.oylik_reyting` bilan bir xil naqsh.
"""

from __future__ import annotations

from collections.abc import Sequence

from django.conf import settings

from apps.complaints.models import Complaint, ComplaintStatus
from apps.complaints.selectors import SAHIFA_HAJMI, LentaFiltri, lenta_queryset

from .models import BoostOrder

# ⚠️ Ko'tarilgan postlar FAQAT shu saralashda chiqadi. Sotib olish
#    sahifasi aynan «Qaynoq» ni va'da qiladi; «Yangi» — xronologik,
#    «Eng yaxshi» — ovoz bo'yicha, ularga pullik joy qo'yish tartibning
#    o'z ma'nosini buzardi.
BOOST_SARALASHI = "hot"


def boost_joylari_soni() -> int:
    """Birinchi sahifadagi joylar soni — sahifa hajmidan HISOBLANADI.

    ⚠️ Alohida sozlama EMAS: «20 kartaga 6 ta joy» kabi qiymat ulush
       qoidasiga (ketma-ket 5 kartada ko'pi bilan 1) zid kelib qolishi
       mumkin edi va buni hech narsa ushlamasdi.
    """
    return SAHIFA_HAJMI // settings.BOOST_ORALIQ


def boost_joyi_bormi(filtr: LentaFiltri, *, after_pk: int | None) -> bool:
    """Shu lenta sahifasida ko'tarilgan postlarga joy bormi.

    ⚠️ FAQAT BIRINCHI SAHIFA. Sotib olish sahifasi «birinchi sahifada»
       deb va'da qiladi. Ikkinchi sahifaga ham qo'yilsa, bir xil bir
       nechta post har «Yana yuklash» da qayta chiqardi — lenta
       reklamaga aylanadi (task `nega` bo'limi aynan shundan ogohlantiradi).
    """
    return filtr.sort == BOOST_SARALASHI and after_pk is None


def lenta_boostlari(
    filtr: LentaFiltri,
    *,
    organik: Sequence[Complaint],
    bloklanganlar: Sequence[int] = (),
) -> list[Complaint]:
    """Birinchi sahifadagi joylarga qo'yiladigan ko'tarilgan postlar.

    ⚠️⚠️ ASOSDA `lenta_queryset` — ko'rinish invarianti (D2-T3),
       bloklangan mualliflar (D2-T11) va URL filtrlari BITTA joyda.
       Pullik joy ularning HECH BIRINI chetlab o'tmaydi: yashirilgan post
       pul to'langan bo'lsa ham chiqmaydi, «Moliya» filtrida «Ta'lim»
       posti chiqmaydi, bloklagan odamga bloklangan muallif chiqmaydi.

    ⚠️ Qo'shimcha shartlar boost MA'NOSIDAN kelib chiqadi:
       · `OPEN` — yechilgan savol «shoshilinch» emas. Sotib olish
         sahifasi buni OLDINDAN aytadi, ya'ni bu jim qoida emas;
       · inqiroz belgisi YO'Q — D5-T3 tamoyili: kontentni CHEKLAMAYMIZ,
         lekin KUCHAYTIRMAYMIZ ham. Pullik joy — kuchaytirishning eng
         to'g'ridan-to'g'ri shakli.

    ⚠️ Birinchi sahifada ORGANIK o'rni bor post CHIQARILADI: u
       allaqachon ko'rinib turibdi, joy esa boshqa boostga qoladi.
       Aks holda bitta post ikki kartaga aylanardi.

    ⚠️⚠️ TASODIFIY TARTIB — foydalanuvchi qarori (2026-09-11): sotuv
       cheklanmaydi, faol boost joylardan ko'p bo'lsa joylar NAVBAT
       BILAN bo'linadi. `ORDER BY random()` har so'rovda boshqa
       to'plamni beradi va har boost kutilgan ko'rinishni teng oladi.
       Nomzodlar — faqat HOZIR faol boostlar, ya'ni `random()` kichik
       to'plamda ishlaydi. Faol boostlar soni sotib olish sahifasida
       OCHIQ yoziladi.
    """
    soni = boost_joylari_soni()
    if soni <= 0:
        return []

    return list(
        lenta_queryset(filtr, bloklanganlar=bloklanganlar)
        .filter(
            pk__in=BoostOrder.objects.faol().values("complaint_id"),
            status=ComplaintStatus.OPEN,
            inqiroz_aniqlandi=False,
        )
        .exclude(pk__in=[muammo.pk for muammo in organik])
        .order_by("?")[:soni]
    )


def boostlarni_joylash[T](
    organik: Sequence[T],
    boostlar: Sequence[T],
    *,
    birinchi_joy: int | None = None,
    oraliq: int | None = None,
) -> list[T]:
    """Ko'tarilgan kartalarni organik ro'yxat ICHIGA joylaydi.

    Joylar (1 dan sanaganda): `birinchi_joy`, `+oraliq`, `+2*oraliq`, …
    Standart sozlamada: 3, 8, 13, 18 — ya'ni ketma-ket istalgan `oraliq`
    ta kartada ko'pi bilan BITTA ko'tarilgan karta (D6-T4 qabul mezoni)
    va birinchi ikkitasi doim organik.

    ⚠️⚠️ ORGANIK TARTIB O'ZGARMAYDI va BIRORTA organik karta tushib
       qolmaydi — boost faqat QO'SHILADI. Lenta kursori (D1-T12) oxirgi
       ORGANIK postdan quriladi, ya'ni ikkinchi sahifa aynan birinchisi
       to'xtagan joydan davom etadi.

    ⚠️ Boost hech qachon ro'yxat OXIRIDA turmaydi: joyi ro'yxat
       uzunligiga yetgan yoki undan oshgan boost TASHLANADI. Qisqa
       filtrlangan lentada pullik karta oxiriga yopishtirilsa, u
       organik kontentsiz «reklama bilan tugaydigan» sahifa bo'lardi.
       (Amalda nomzod faqat organik sahifa TO'LA bo'lganda bor: boost
       organik birinchi sahifadan chiqarilgan postlardan tanlanadi.)
    """
    birinchi = settings.BOOST_BIRINCHI_JOY if birinchi_joy is None else birinchi_joy
    qadam = settings.BOOST_ORALIQ if oraliq is None else oraliq

    natija = list(organik)
    for tartib, boost in enumerate(boostlar):
        joy = birinchi - 1 + tartib * qadam
        if joy >= len(natija):
            break
        natija.insert(joy, boost)
    return natija
