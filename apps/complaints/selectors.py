"""Muammolar — o'qish so'rovlari (D1-T7).

`services.py` YOZADI, `selectors.py` O'QIYDI. Ajratishning sababi amaliy:
lenta so'rovi keyinchalik qidiruvda (D4-T3), kategoriya sahifasida va
Telegram avto-postida (D5-T3) qayta ishlatiladi. Agar u `views.py` ichida
qolsa, har joyda qaytadan yoziladi — va ko'rinish invariantlaridan biri
(moderatsiya, yumshoq o'chirish) bir joyda unutiladi.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.db import models

from .models import Category, Complaint, ComplaintStatus, Generation

# ⚠️ Kalitlar MAKETDAGI havolalar bilan bir xil: `?sort=hot|new|top|solved`
#    (templates/complaints/feed.html). O'zgartirilsa ulashilgan havolalar
#    o'lik bo'lib qoladi.
#
# ⚠️ Har bir saralash `-id` bilan tugaydi — TENGLIKNI UZISH uchun.
#    Usiz teng `hot_score` li ikki qator har so'rovda boshqa tartibda
#    kelishi mumkin. Bu lentada sezilmaydi, LEKIN kursor bo'yicha
#    sahifalash (D1-T12) buziladi: element ikki marta ko'rinadi yoki
#    umuman tushib qoladi.
SARALASH: dict[str, tuple[str, ...]] = {
    "hot": ("-hot_score", "-created_at", "-id"),
    "new": ("-created_at", "-id"),
    "top": ("-score_cached", "-created_at", "-id"),
    "solved": ("-created_at", "-id"),
}
STANDART_SARALASH = "hot"

# Tab yorlig'i va sahifa sarlavhasi. Shablonda `{% if %}` zanjiri
# yozilmasin: to'rt tab to'rt marta takrorlanadigan markup degani va
# beshinchisi qo'shilganda biri albatta unutiladi.
SARALASH_TABI: dict[str, str] = {
    "hot": "Qaynoq",
    "new": "Yangi",
    "top": "Eng yaxshi",
    "solved": "Yechilgan",
}
SARALASH_SARLAVHASI: dict[str, str] = {
    "hot": "Qaynoq dardlar",
    "new": "Yangi dardlar",
    "top": "Eng yaxshi dardlar",
    "solved": "Yechilgan dardlar",
}

# ⚠️ "Yechilgan" — maketda saralash tabi, amalda esa FILTR.
#    Shuning uchun u alohida ro'yxatda: tab bosilganda `status=solved`
#    ham qo'shiladi.
FILTRLI_SARALASH = {"solved": ComplaintStatus.SOLVED}

SAHIFA_HAJMI = 20


@dataclass(frozen=True)
class LentaFiltri:
    """URL'dan o'qilgan holat.

    ⚠️ HOLAT URL'DA (D1-T7 ning butun ma'nosi). Sessiyada yoki
       cookie'da saqlansa: foydalanuvchi filtrlangan lentani ulasha
       olmaydi, "orqaga" tugmasi filtrni yo'qotadi va ikki tabda ikki
       xil filtr ishlatib bo'lmaydi.
    """

    sort: str = STANDART_SARALASH
    category: str = ""
    generation: str = ""

    @property
    def faolmi(self) -> bool:
        """Biror filtr qo'llanganmi (bo'sh holatda matnni tanlash uchun)."""
        return bool(self.category or self.generation)


def filtrni_oqish(GET) -> LentaFiltri:  # noqa: N803 — Django uslubi
    """`request.GET` -> `LentaFiltri`, noto'g'ri qiymatlar tashlanadi.

    ⚠️ NOMA'LUM QIYMAT XATO BERMAYDI, STANDARTGA QAYTADI.
       `?sort=<script>` yoki `?generation=xyz` bilan kelgan so'rov 500
       bermasligi kerak: bunday havolalar botlardan, eski xatcho'plardan
       va qo'lda tahrirlangan URL'lardan doim keladi.

       Istisno — `category`: u ATAYLAB tekshirilmaydi. Mavjud bo'lmagan
       slug so'rovni BO'SH qiladi va foydalanuvchi "topilmadi" ni ko'radi.
       Uni jimgina tashlab yuborish "hammasini ko'rsatish" degani bo'lardi,
       ya'ni foydalanuvchiga YOLG'ON aytilardi.
    """
    sort = GET.get("sort") or STANDART_SARALASH
    if sort not in SARALASH:
        sort = STANDART_SARALASH

    generation = GET.get("generation") or ""
    if generation not in Generation.values:
        generation = ""

    return LentaFiltri(
        sort=sort,
        category=(GET.get("category") or "").strip(),
        generation=generation,
    )


def lenta_queryset(filtr: LentaFiltri) -> models.QuerySet[Complaint]:
    """Lentaning asosiy so'rovi.

    ⚠️ `visible()` — D2-T3 dagi "yagona kirish nuqtasi" qoidasi.
       `Complaint.objects` yumshoq o'chirilganlarni allaqachon filtrlaydi,
       lekin moderatsiya ATAYLAB standart emas (muallif o'z yashirilgan
       postini ko'rishi kerak) — shuning uchun bu yerda OCHIQ yoziladi.

    ⚠️ `select_related` — D1-T14. Usiz har karta uchun muallif va
       kategoriya alohida so'raladi: 20 karta = 40 qo'shimcha so'rov.
    """
    qs = Complaint.objects.visible().select_related("author", "category")

    if filtr.category:
        qs = qs.filter(category__slug=filtr.category)
    if filtr.generation:
        qs = qs.filter(generation_tag=filtr.generation)

    holat = FILTRLI_SARALASH.get(filtr.sort)
    if holat:
        qs = qs.filter(status=holat)

    return qs.order_by(*SARALASH[filtr.sort])


def yon_panel_kategoriyalari() -> models.QuerySet[Category]:
    """Chap ustundagi kategoriyalar + har biridagi ko'rinadigan post soni.

    ⚠️ Sanoq FILTRLANGAN `Count` bilan olinadi, oddiy `Count("complaints")`
       bilan emas: aks holda o'chirilgan va yashirilgan postlar ham
       sanalardi va sonlar lentadagi haqiqatga mos kelmasdi
       ("Moliya 12" deydi, ochsangiz 9 ta chiqadi).

    Bu bitta so'rov. Trafik o'sganda keshlash kerak bo'ladi (D1-T14 /
    D2 kesh qatlami) — hozircha jadval kichik.
    """
    from apps.common.models import ModerationStatus

    return (
        Category.objects.filter(is_active=True)
        .annotate(
            postlar_soni=models.Count(
                "complaints",
                filter=models.Q(
                    complaints__deleted_at__isnull=True,
                    complaints__moderation_status=ModerationStatus.VISIBLE,
                ),
            )
        )
        # ⚠️⚠️ `order_by()` SHART — `Meta.ordering` bu yerda ISHLAMAYDI.
        #    Django 3.1 dan beri `annotate()` GROUP BY hosil qilganda
        #    `Meta.ordering` JIMGINA tashlab yuboriladi (ilgari u
        #    GROUP BY ga tushib, guruhlashni noto'g'ri bo'lardi).
        #    Ogohlantirish YO'Q: so'rovda ORDER BY umuman bo'lmaydi va
        #    PostgreSQL qatorlarni o'zi qulay tartibda qaytaradi.
        #
        #    Oqibati jonli sahifada ko'rindi: yon paneldagi kategoriyalar
        #    tasodifiy tartibda turardi ("Boshqa" o'rtada, "Karyera"
        #    beshinchi). Birlik testlar buni ushlamadi — ular SANOQNI
        #    tekshirardi, TARTIBNI emas.
        .order_by("order", "name")
    )
