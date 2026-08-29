"""Profil sahifasi — o'qish so'rovlari (D3-T4).

⚠️⚠️ BU MODULNING BUTUN MAZMUNI — ANONIMLIK.

   Task tavsifi buni ochiq aytadi: "anonim postni ommaviy profilda
   ko'rsatish — anonimlikni buzishning eng oson yo'li". Shuning uchun
   har bir so'rov ikki xil javob beradi: EGASIGA va BOSHQALARGA.

   Anonimlik qoidasi bitta joyda (`_anonimsiz()`), chunki uni har
   so'rovda qayta yozish — bir kuni bittasini unutish demakdir.
   `visible()` esa ATAYLAB har chaqiruvda ochiq turadi (D2-T3 guard'i
   uni manba kodida ko'rishi kerak).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db import models

from apps.complaints.models import Complaint
from apps.complaints.selectors import saqlanganlar_queryset
from apps.gamification.models import KarmaEvent
from apps.solutions.models import Solution

# ⚠️ Tab nomlari MANZILGA tushadi (`?tab=yechimlar`) — ular interfeys
#    matni emas, API. O'zgartirilsa eski havolalar buziladi.
TABLAR = ("dardlar", "yechimlar", "saqlanganlar", "karma")

# ⚠️ FAQAT EGASIGA ko'rinadigan tablar.
#    · saqlanganlar — bu foydalanuvchining XATCHO'PLARI, ya'ni u nimani
#      o'qimoqchi ekani. Boshqaga ko'rsatish maxfiylikni buzardi.
#    · karma — pastdagi `profil_karma_tarixi()` izohiga qarang: u anonim
#      yechimlarni egasiga bog'lab qo'yardi.
SHAXSIY_TABLAR = frozenset({"saqlanganlar", "karma"})

# ⚠️ Yorliqlar NEYTRAL ("Dardlar", "Dardlari"/"Dardlarim" emas): bitta
#    shablon ham o'z profilini, ham begonasini chizadi va egalik
#    qo'shimchasi ikki xil matn talab qilardi.
TAB_YORLIQLARI: dict[str, str] = {
    "dardlar": "Dardlar",
    "yechimlar": "Yechimlar",
    "saqlanganlar": "Saqlanganlar",
    "karma": "Karma tarixi",
}

SAHIFA_HAJMI = 10


def korinadigan_tablar(*, ozimi: bool) -> list[tuple[str, str]]:
    """Shu ko'ruvchiga ko'rsatiladigan tablar.

    ⚠️ Shaxsiy tab begonaga UMUMAN ko'rsatilmaydi — "qulflangan" holda
       ham emas. Qulf "bu yerda nimadir bor" degan signal bo'lardi va
       aynan shu signal maxfiylikni buzardi.
    """
    return [
        (kalit, TAB_YORLIQLARI[kalit])
        for kalit in TABLAR
        if ozimi or kalit not in SHAXSIY_TABLAR
    ]


def tabni_oqish(GET, *, ozimi: bool) -> str:  # noqa: N803 — Django uslubi
    """Manzildan tabni oladi. Noma'lum yoki ruxsatsiz bo'lsa — birinchisi.

    ⚠️ Ruxsatsiz tab XATO BERMAYDI, jimgina birinchisiga tushadi.
       `?tab=saqlanganlar` bilan begona profilga kirgan odam 403 olsa,
       bu "bu yerda yashiradigan narsa bor" degan signal bo'lardi.
    """
    tab = GET.get("tab", "")
    if tab not in TABLAR:
        return TABLAR[0]
    if tab in SHAXSIY_TABLAR and not ozimi:
        return TABLAR[0]
    return tab


def _anonimsiz(qs, *, ozimi: bool):
    """⚠️⚠️ QABUL MEZONI (D3-T4): "boshqa odam profilida anonim postlar YO'Q".

    ⚠️ BU FUNKSIYA `visible()` NI CHAQIRMAYDI — ataylab.
       Ko'rinish invarianti guard'i (D2-T3) `visible()` MANBA KODIDA
       ko'rinishini talab qiladi. Uni shu yerga yashirsak, guard
       chaqiruv joylarini "buzuq" deb belgilardi va yagona chiqish yo'li
       `# korinish-istisno:` izohi bo'lardi — ya'ni HAQIQIY istisno
       bo'lmagan joyga istisno belgisi qo'yilardi va belgi o'z ma'nosini
       yo'qotardi.

       Shuning uchun bu funksiya FAQAT anonimlik qatlamini qo'shadi,
       `visible()` esa har chaqiruvda ochiq turadi.

    ⚠️ Egasi o'z anonim postlarini KO'RADI: aks holda u o'z yozganini
       topa olmasdi va "post yo'qoldi" deb o'ylardi. Shablon ularni
       "anonim" nishoni bilan belgilaydi — odam boshqalar nimani
       ko'rishini bilishi kerak.
    """
    if ozimi:
        return qs
    return qs.filter(is_anonymous=False)


@dataclass(frozen=True)
class ProfilStatistikasi:
    """Sarlavhadagi to'rtta raqam.

    ⚠️⚠️ RAQAMLAR HAM ANONIMLIKNI OSHKOR QILISHI MUMKIN.
       Agar ommaviy profil "18 dard" desa-yu ro'yxatda 12 tasi
       ko'rinsa, kuzatuvchi 6 ta ANONIM post borligini hisoblab
       chiqaradi — ya'ni bu odam anonim yozishini va qanchalik tez-tez
       yozishini fosh qiladi.

       Shuning uchun raqamlar KO'RSATILGAN RO'YXAT bo'yicha hisoblanadi:
       begona uchun anonimlarsiz, egasi uchun hammasi. Ko'rsatilgan
       raqam ko'rsatilgan ro'yxatga TENG bo'lishi shart.
    """

    dardlar: int
    yechimlar: int
    qabul_qilingan: int
    olingan_ovoz: int
    anonim_dardlar: int  # faqat egasiga ko'rsatiladi
    anonim_yechimlar: int


def profil_statistikasi(*, profil, ozimi: bool) -> ProfilStatistikasi:
    """Sarlavha raqamlari — IKKI so'rovda (har biri bitta agregat)."""
    dard_qs = _anonimsiz(Complaint.objects.visible().filter(author=profil), ozimi=ozimi)
    yechim_qs = _anonimsiz(
        Solution.objects.visible().filter(author=profil), ozimi=ozimi
    )

    dardlar = dard_qs.aggregate(
        soni=models.Count("pk"),
        anonim=models.Count("pk", filter=models.Q(is_anonymous=True)),
    )
    yechimlar = yechim_qs.aggregate(
        soni=models.Count("pk"),
        anonim=models.Count("pk", filter=models.Q(is_anonymous=True)),
        qabul=models.Count("pk", filter=models.Q(is_accepted=True)),
        ovoz=models.Sum("upvotes_cached", default=0),
    )

    return ProfilStatistikasi(
        dardlar=dardlar["soni"],
        yechimlar=yechimlar["soni"],
        qabul_qilingan=yechimlar["qabul"],
        olingan_ovoz=yechimlar["ovoz"],
        anonim_dardlar=dardlar["anonim"],
        anonim_yechimlar=yechimlar["anonim"],
    )


def profil_dardlari(*, profil, ozimi: bool) -> models.QuerySet[Complaint]:
    return (
        _anonimsiz(Complaint.objects.visible().filter(author=profil), ozimi=ozimi)
        # ⚠️ `author` KERAK, garchi u HAR DOIM profil egasi bo'lsa ham.
        #    `_complaint_card.html` muallifni `public_author` orqali
        #    o'qiydi va u `self.author` ga cho'ziladi — ya'ni Django
        #    har karta uchun BIR MARTA bazaga boradi. Bu N+1 aynan
        #    shu testda ushlandi (12 -> 20 so'rov), chunki ko'z bilan
        #    "muallif allaqachon ma'lum-ku" deb o'ylash oson.
        .select_related("author", "category")
        .order_by("-created_at")
    )


def profil_yechimlari(*, profil, ozimi: bool) -> models.QuerySet[Solution]:
    return (
        _anonimsiz(Solution.objects.visible().filter(author=profil), ozimi=ozimi)
        # ⚠️ `complaint` KERAK: har yechim ostida "javob berilgan: <muammo>"
        #    havolasi bor. Usiz 10 ta kartada 10 ta qo'shimcha so'rov
        #    bo'lardi (D1-T14 qoidasi).
        .select_related("complaint")
        .order_by("-created_at")
    )


def profil_saqlanganlari(*, profil) -> models.QuerySet[Complaint]:
    """⚠️ FAQAT EGASIGA — `tabni_oqish()` buni majburlaydi.

    Xatcho'p — odam NIMANI o'qimoqchi ekani. Boshqaga ko'rsatish
    maxfiylikni buzardi va bu "profil ochiq" degani bilan aloqasi yo'q.

    ⚠️ MAVJUD SELEKTOR QAYTA ISHLATILADI, yangisi yozilmaydi.
       `complaints/views.py::saqlanganlar` allaqachon shuni aytgan edi:
       "D3-T4 uni profilga ko'chirishi mumkin — o'shanda faqat shablon
       o'zgaradi, `selectors` qoladi". Ikkinchi so'rov yozilsa,
       `visible()` qoidasi ikki joyda bo'lardi va bir kuni faqat
       bittasi tuzatilardi.

    ⚠️ Saqlangan post BOSHQANIKI, ya'ni bu yerda anonimlik filtri
       ISHLAMAYDI: muallif `public_author` orqali chiqadi (shablon
       shuni ishlatadi).
    """
    return saqlanganlar_queryset(user=profil)


def profil_karma_tarixi(*, profil) -> models.QuerySet[KarmaEvent]:
    """⚠️⚠️ FAQAT EGASIGA — va bu ANONIMLIK sababli, maxfiylik emas.

    `KarmaEvent` yechimga FK bilan bog'langan. Tarixni ommaviy
    ko'rsatish "shu ANONIM yechim shu odamniki" degan xaritani ochiq
    berardi — ya'ni karma tarixi anonimlikni buzadigan asbobga
    aylanardi.

    Egasiga esa ko'rsatiladi: D3-T1 qabul mezoni ("profilda karma
    tarixi ko'rinadi") va uning `nega` bo'limi — "nima uchun 1340
    ball?" savoliga javob bo'lishi kerak.
    """
    return (
        KarmaEvent.objects.filter(user=profil)
        .select_related("solution", "solution__complaint")
        .order_by("-created_at")
    )


def tab_royxati(*, tab: str, profil, ozimi: bool) -> Any:
    """Tanlangan tabning ro'yxati — ko'rinishda `if` zanjiri bo'lmasin."""
    if tab == "yechimlar":
        return profil_yechimlari(profil=profil, ozimi=ozimi)
    if tab == "saqlanganlar":
        return profil_saqlanganlari(profil=profil)
    if tab == "karma":
        return profil_karma_tarixi(profil=profil)
    return profil_dardlari(profil=profil, ozimi=ozimi)
