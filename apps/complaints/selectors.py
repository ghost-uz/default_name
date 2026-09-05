"""Muammolar — o'qish so'rovlari (D1-T7).

`services.py` YOZADI, `selectors.py` O'QIYDI. Ajratishning sababi amaliy:
lenta so'rovi keyinchalik qidiruvda (D4-T3), kategoriya sahifasida va
Telegram avto-postida (D5-T3) qayta ishlatiladi. Agar u `views.py` ichida
qolsa, har joyda qaytadan yoziladi — va ko'rinish invariantlaridan biri
(moderatsiya, yumshoq o'chirish) bir joyda unutiladi.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from django.conf import settings
from django.contrib.postgres.search import (
    SearchQuery,
    SearchRank,
    TrigramWordSimilarity,
)
from django.db import models

from apps.common.matn import qidiruv_uchun

from .models import (
    Category,
    Complaint,
    ComplaintStatus,
    Generation,
    SavedComplaint,
)

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

# Qidiruv sahifasidagi holat filtri uchun yorliqlar (D4-T3).
# ⚠️ `ComplaintStatus.choices` dan foydalanilmadi: u "Ochiq / Yechilgan /
#    Yopilgan" beradi, filtr chipida esa "Ochiq savollar" tushunarliroq —
#    chip yolg'iz turadi va nimaning holati ekani kontekstdan ko'rinmaydi.
HOLAT_FILTRI: dict[str, str] = {
    ComplaintStatus.OPEN: "Ochiq savollar",
    ComplaintStatus.SOLVED: "Yechilgan",
    ComplaintStatus.CLOSED: "Yopilgan",
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
    # ⚠️ D4-T3 da QO'SHILDI va lentaga ham tegadi (`?status=solved`).
    #    Bu ataylab: filtr URL'da bo'lgani uchun uni faqat qidiruvga
    #    cheklash sun'iy bo'lardi — lentada ham ishlagani zarar qilmaydi.
    #
    #    ⚠️ `sort="solved"` bilan CHALKASHTIRMANG: u maketdan kelgan tab
    #       va o'zi ham holat filtri qo'shadi (`FILTRLI_SARALASH`).
    #       Ikkalasi birga berilsa IKKALASI ham qo'llanadi — ya'ni
    #       `?sort=solved&status=open` bo'sh natija beradi. Bu to'g'ri
    #       xulq: foydalanuvchi bir-biriga zid ikki shart so'radi.
    status: str = ""

    @property
    def faolmi(self) -> bool:
        """Biror filtr qo'llanganmi (bo'sh holatda matnni tanlash uchun)."""
        return bool(self.category or self.generation or self.status)


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

    # ⚠️ Holat `generation` bilan bir xil ishlanadi (noma'lum qiymat
    #    TASHLANADI), `category` bilan emas: kategoriya slug'i erkin
    #    matn va uni tekshirib bo'lmaydi, holat esa yopiq ro'yxat.
    status = GET.get("status") or ""
    if status not in ComplaintStatus.values:
        status = ""

    return LentaFiltri(
        sort=sort,
        category=(GET.get("category") or "").strip(),
        generation=generation,
        status=status,
    )


def lenta_queryset(
    filtr: LentaFiltri, *, bloklanganlar: Sequence[int] = ()
) -> models.QuerySet[Complaint]:
    """Lentaning asosiy so'rovi.

    ⚠️ `visible()` — D2-T3 dagi "yagona kirish nuqtasi" qoidasi.
       `Complaint.objects` yumshoq o'chirilganlarni allaqachon filtrlaydi,
       lekin moderatsiya ATAYLAB standart emas (muallif o'z yashirilgan
       postini ko'rishi kerak) — shuning uchun bu yerda OCHIQ yoziladi.

    ⚠️ `select_related` — D1-T14. Usiz har karta uchun muallif va
       kategoriya alohida so'raladi: 20 karta = 40 qo'shimcha so'rov.
    """
    qs = Complaint.objects.visible().select_related("author", "category")

    # ⚠️ BLOKLANGAN MUALLIFLAR LENTADAN CHIQADI (D2-T11).
    #    Bu foydalanuvchining O'Z qarori — moderator bloki emas.
    #    Bloklangan odam bundan xabardor emas va hech qanday cheklov
    #    olmaydi (`apps/accounts/models.py::UserBlock`).
    #
    # ⚠️ Ro'yxat ALOHIDA PARAMETR, `LentaFiltri` ichida EMAS:
    #    `LentaFiltri` — URL'dan o'qilgan holat (D1-T7), blok esa
    #    foydalanuvchining holati. Ularni aralashtirish "filtr URL'da"
    #    qoidasini buzardi va bloklangan odamlar ro'yxati manzilga
    #    tushib qolishi mumkin bo'lardi.
    #
    # ⚠️ Ro'yxat BIR MARTA olinadi (`accounts.services.bloklangan_idlar`)
    #    va so'rovga QIYMAT sifatida tushadi: ichma-ich `QuerySet` bo'lsa
    #    PostgreSQL uni har safar qayta bajarardi.
    if bloklanganlar:
        qs = qs.exclude(author_id__in=bloklanganlar)

    if filtr.category:
        qs = qs.filter(category__slug=filtr.category)
    if filtr.generation:
        qs = qs.filter(generation_tag=filtr.generation)
    if filtr.status:
        qs = qs.filter(status=filtr.status)

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


# ===========================================================================
# Kursor bo'yicha sahifalash (D1-T12)
# ===========================================================================
def kursor_filtri(*, sort: str, oxirgi: Complaint) -> models.Q:
    """ "Shu elementdan KEYIN kelganlar" shartini quradi.

    ⚠️ NEGA OFFSET EMAS
       `LIMIT 20 OFFSET 400` bazadan 420 ta qatorni O'QIB, birinchi 400
       tasini TASHLAB YUBORISHNI talab qiladi — sahifa raqami o'sgan sari
       so'rov sekinlashadi. Kursor esa indeksdagi aniq nuqtadan boshlaydi:
       20-sahifa ham 1-sahifa kabi tez (D1-T12 qabul mezoni).

       Ikkinchi sabab muhimroq: OFFSET paytida yangi post qo'shilsa,
       hamma narsa bir pozitsiyaga suriladi va foydalanuvchi ALLAQACHON
       KO'RGAN postni yana ko'radi (yoki bittasi butunlay tushib qoladi).
       Kursor qiymatga bog'langani uchun bunday bo'lmaydi.

    ⚠️ TENGLIKNI UZISH ZANJIRI
       Saralash maydonlari teng bo'lishi mumkin (masalan ikki postda
       `hot_score` bir xil), shuning uchun shart bosqichma-bosqich
       quriladi:

           hot_score < H
           YOKI (hot_score = H VA created_at < C)
           YOKI (hot_score = H VA created_at = C VA id < I)

       `SARALASH` da har bir tartib `-id` bilan tugagani uchun oxirgi
       bosqich har doim NOYOB — ya'ni element ikki marta ham chiqmaydi,
       tushib ham qolmaydi.

    ⚠️ Barcha saralashlar KAMAYISH tartibida (`-` bilan), shuning uchun
       taqqoslash bir xilda `__lt`. Aralash yo'nalish qo'shilsa bu
       funksiya ham o'zgarishi kerak — pastdagi tekshiruv shuni eslatadi.
    """
    maydonlar = SARALASH[sort]
    if not all(m.startswith("-") for m in maydonlar):
        raise ValueError(
            f"`{sort}` saralashida o'sish tartibidagi maydon bor; "
            "kursor mantiqi faqat kamayish uchun yozilgan."
        )

    shart = models.Q()
    tenglik: dict[str, object] = {}
    for maydon in (m.lstrip("-") for m in maydonlar):
        qiymat = getattr(oxirgi, maydon)
        shart |= models.Q(**tenglik, **{f"{maydon}__lt": qiymat})
        tenglik[maydon] = qiymat
    return shart


def lenta_sahifasi(
    filtr: LentaFiltri,
    *,
    after_pk: int | None = None,
    bloklanganlar: Sequence[int] = (),
) -> tuple[list[Complaint], int | None]:
    """Bir sahifa muammo + keyingi kursor (`None` bo'lsa oxiri).

    ⚠️ KURSOR — POST'NING `pk` I, KODLANGAN QIYMATLAR EMAS
       Saralash qiymatlarini (`hot_score`, `created_at`, `id`) URL'ga
       kodlash mumkin edi, lekin u holda: (1) ularni tahlil qilish va
       tekshirish kerak, (2) buzilgan kursor 500 beradi, (3) foydalanuvchi
       qiymatlarni o'zgartirib so'rovni buzishi mumkin.

       `pk` esa bitta indeksli qidiruvga tushadi va qolgan hamma narsa
       bazadan olinadi. Narxi — sahifaga bitta arzon so'rov.

    ⚠️ `SAHIFA_HAJMI + 1` OLINADI, `COUNT(*)` QILINMAYDI
       "Yana bormi?" savoliga javob uchun butun natijani sanash shart
       emas — bitta ortiqcha qator yetarli. `COUNT(*)` katta jadvalda
       sahifaning o'zidan qimmatroq tushadi.

    ⚠️ CHEGARA HOLATI: `hot_score` har 10 daqiqada qayta hisoblanadi
       (D1-T11). Foydalanuvchi sahifalar orasida turganda ballar
       o'zgarsa, ba'zi postlar takrorlanishi yoki tushib qolishi mumkin.
       Bu O'ZGARUVCHAN reyting bo'yicha sahifalashning tabiati (Reddit'da
       ham shunday); "Yangi" saralashida bunday bo'lmaydi, chunki
       `created_at` o'zgarmaydi.
    """
    qs = lenta_queryset(filtr, bloklanganlar=bloklanganlar)

    if after_pk is not None:
        # ⚠️ Kursor posti o'chirilgan/yashirilgan bo'lishi mumkin — o'shanda
        #    `all_objects`: uning saralash qiymatlari hamon to'g'ri chegara
        #    beradi. Umuman topilmasa kursor e'tiborsiz qoldiriladi
        #    (birinchi sahifa) — 404 dan ko'ra tushunarli xulq.
        # korinish-istisno: kursor posti KO'RSATILMAYDI, undan faqat
        # saralash qiymatlari olinadi. Yashirilgan post ham to'g'ri
        # chegara beradi; usiz sahifalash o'sha nuqtada uzilardi.
        oxirgi = Complaint.all_objects.filter(pk=after_pk).first()
        if oxirgi is not None:
            qs = qs.filter(kursor_filtri(sort=filtr.sort, oxirgi=oxirgi))

    natijalar = list(qs[: SAHIFA_HAJMI + 1])
    yana_bor = len(natijalar) > SAHIFA_HAJMI
    natijalar = natijalar[:SAHIFA_HAJMI]
    keyingi = natijalar[-1].pk if (yana_bor and natijalar) else None
    return natijalar, keyingi


def kursorni_oqish(GET) -> int | None:  # noqa: N803 — Django uslubi
    """`?after=123` -> `123`. Noto'g'ri qiymat 500 BERMAYDI.

    Bunday havolalar botlardan va qo'lda tahrirlangan URL'lardan doim
    keladi; ular birinchi sahifani ko'rsatishi kerak.
    """
    xom = (GET.get("after") or "").strip()
    if not xom.isdigit():
        return None
    return int(xom)


# ===========================================================================
# Saqlanganlar (D1-T13)
# ===========================================================================
def saqlangan_idlari(*, user, targets: Sequence[Complaint]) -> set[int]:
    """`{muammo_id, ...}` — lentadagi barcha kartalar uchun BITTA so'rovda.

    ⚠️ `user_votes_for` bilan bir xil sabab (D1-T14): har karta uchun
       "saqlaganmanmi?" deb alohida so'rash 20 ta kartada 20 ta
       qo'shimcha so'rov degani.

    Kirmagan foydalanuvchi uchun bo'sh to'plam — so'rov umuman ketmaydi.
    """
    if not targets or not getattr(user, "is_authenticated", False):
        return set()

    return set(
        SavedComplaint.objects.filter(user=user, complaint__in=targets).values_list(
            "complaint_id", flat=True
        )
    )


def saqlanganlar_queryset(*, user) -> models.QuerySet[Complaint]:
    """Foydalanuvchi saqlagan muammolar — eng yangi saqlangani birinchi.

    ⚠️ `SavedComplaint` orqali emas, `Complaint` orqali qaytariladi:
       shablon `_complaint_card.html` ni qayta ishlatadi va u
       `Complaint` kutadi.

    ⚠️ `visible()` BU YERDA HAM: moderator yashirgan post saqlanganlar
       ro'yxatida qolib ketmasin — u lentada yo'q, demak bu yerda ham
       bo'lmasligi kerak (D2-T3).
    """
    return (
        Complaint.objects.visible()
        .filter(saved_by__user=user)
        .select_related("author", "category")
        .order_by("-saved_by__created_at", "-id")
    )


# ===========================================================================
# Qidiruv (D4-T1)
# ===========================================================================
def qidiruv_queryset(
    xom: str,
    *,
    filtr: LentaFiltri | None = None,
    bloklanganlar: Sequence[int] = (),
) -> models.QuerySet[Complaint]:
    """To'liq matnli qidiruv — dolzarblik bo'yicha saralangan.

    ⚠️ ASOSDA `lenta_queryset` TURADI, `Complaint.objects` EMAS.
       Bu ataylab: ko'rinish invarianti (`visible()`), bloklangan
       mualliflar va kategoriya/avlod filtrlari BITTA joyda yozilgan
       (D2-T3). Qidiruv o'z so'rovini noldan qursa, bir kuni ulardan
       biri bu yerda unutilardi — va aynan qidiruv Google'dan kelgan
       begona odam ko'radigan sahifa.

    ⚠️ `config="simple"` INDEKS BILAN BIR XIL BO'LISHI SHART.
       `Complaint.search_vector` GENERATED ustuni `'simple'` bilan
       qurilgan. Bu yerda boshqa konfiguratsiya berilsa so'rov xato
       BERMAYDI — u shunchaki hech narsa topmaydi va sabab ko'rinmaydi.

    ⚠️ SO'ROV HAM `qidiruv_uchun()` DAN O'TADI — indeks bilan bir xil
       normal shakl. Bittasi unutilsa qidiruv jimgina buziladi.

    ⚠️ `websearch` TURI TANLANDI (`plain` emas):
       u ham bo'sh so'rovda ham, `((` kabi buzuq kiritmada ham xato
       bermaydi (`raw` beradi), lekin qo'shimcha ravishda qo'shtirnoq
       ichidagi ibora va `-so'z` bilan istisnoni tushunadi. Ya'ni
       `plain` ning ustiga faqat qo'shadi, hech narsa olib tashlamaydi.

    ⚠️ TENGLIKNI UZISH: `-created_at`, `-id`. `ts_rank` ko'p yozuvda
       bir xil chiqadi (ayniqsa qisqa so'rovda) va usiz tartib har
       so'rovda o'zgarardi — foydalanuvchi uchun natijalar "sakraydi".
    """
    qs = lenta_queryset(filtr or LentaFiltri(), bloklanganlar=bloklanganlar)

    normal = qidiruv_uchun(xom)
    if not normal:
        # Bo'sh so'rov — bo'sh natija. "Hammasini ko'rsatish" bo'lardi
        # yolg'on: foydalanuvchi hech narsa so'ramagan.
        return qs.none()

    sorov = SearchQuery(normal, config="simple", search_type="websearch")

    return (
        qs.filter(search_vector=sorov)
        .annotate(dolzarblik=SearchRank(models.F("search_vector"), sorov))
        .order_by("-dolzarblik", "-created_at", "-id")
    )


def taxminiy_natijalar(
    xom: str,
    *,
    bloklanganlar: Sequence[int] = (),
    soni: int | None = None,
) -> models.QuerySet[Complaint]:
    """Xato yozilgan so'rov uchun eng yaqin sarlavhalar (trigram).

    ⚠️ NEGA KERAK: tsvector ANIQ lexemaga tayanadi. "ipotaka" deb
       yozilgan so'rov "ipoteka" ni HECH QACHON topmaydi va foydalanuvchi
       "saytda bunday narsa yo'q" degan xulosaga keladi. Bitta harf.

    ⚠️ `word_similarity`, oddiy `similarity` EMAS — o'lchangan farq:

           similarity('ipotaka', 'ipoteka olish qiyinmi')       = 0.20
           word_similarity('ipotaka', 'ipoteka olish qiyinmi')  = 0.50

       `similarity` butun satrlarni taqqoslaydi, ya'ni uzun sarlavha
       qisqa so'rovga hech qachon "o'xshamaydi". `word_similarity` esa
       eng mos KELGAN bo'lakni oladi — bizga aynan shu kerak.

    ⚠️ NEGA `<%` OPERATORI (indeksli) EMAS, OSHKORA TAQQOSLASH
       `<%` chegarani `pg_trgm.word_similarity_threshold` GUC'idan
       oladi va uning standarti 0.6 — yuqoridagi 0.50 ni O'TKAZIB
       YUBORADI. Uni o'zgartirish esa ULANISH holatiga yozish degani:
       `CONN_MAX_AGE=60` bilan ulanishlar qayta ishlatiladi, ya'ni
       `SET` so'rovlar orasida oqib ketardi va buni test ushlamasdi.

       Oshkora taqqoslash indeksdan foydalanmaydi (ketma-ket skanerlash),
       lekin: (1) chegara SOZLAMADA — ko'rinadigan va sinaladigan
       mahsulot parametri, (2) o'lchangan narxi 10 041 postda **43 ms**,
       (3) bu yo'l FAQAT asosiy qidiruv bo'sh qaytganda ishlaydi.

    ⚠️ FAQAT SARLAVHA BO'YICHA — trigram indeksi ham shunday (modeldagi
       izohga qarang). Tavsif bo'yicha o'xshashlik uzun matnda ma'nosiz
       shovqin beradi.
    """
    qs = lenta_queryset(LentaFiltri(), bloklanganlar=bloklanganlar)

    normal = qidiruv_uchun(xom)
    if not normal:
        return qs.none()

    chegara = settings.QIDIRUV_OXSHASHLIK_CHEGARASI
    limit = settings.QIDIRUV_TAKLIF_SONI if soni is None else soni

    return (
        qs.annotate(oxshashlik=TrigramWordSimilarity(normal, "qidiruv_sarlavha"))
        .filter(oxshashlik__gte=chegara)
        .order_by("-oxshashlik", "-id")[:limit]
    )
