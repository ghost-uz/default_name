"""Trending (`hot_score`) qayta hisoblash — D1-T11.

Vazifa Celery beat orqali har 10 daqiqada ishlaydi (config/settings/base.py:
`CELERY_BEAT_SCHEDULE`).
"""

from __future__ import annotations

import hashlib
import logging
import math
from datetime import UTC, datetime, timedelta

from celery import shared_task
from django.core.files.base import ContentFile
from django.utils import timezone

from apps.common.og import og_rasm_yasash

from .models import Complaint

log = logging.getLogger(__name__)

# ⚠️ BOSHLANG'ICH NUQTA — o'zgartirilmaydi.
#    Barcha ballar shu nuqtaga nisbatan hisoblanadi. Uni ko'chirish
#    BARCHA postlarning ballarini bir vaqtda siljitadi; lenta bir marta
#    to'liq qayta tartiblanadi. Kichik son bo'lishi uchun loyiha
#    boshlangan yil olindi (Reddit 2005-yilni ishlatadi).
HOT_BOSHLANGICH = datetime(2026, 1, 1, tzinfo=UTC)

# ⚠️ 45000 sekund ≈ 12.5 soat — vaqt hadining "og'irligi".
#    Ma'nosi: post 12.5 soat yangiroq bo'lsa, u taxminan 10 barobar
#    ko'proq ovoz olgan postga teng keladi (`log10` shkalasi).
#    Kichraytirilsa lenta tezroq yangilanadi, kattalashtirilsa
#    ovozlar ustunroq bo'ladi.
HOT_VAQT_OGIRLIGI = 45000

# Faqat oxirgi 7 kunlik postlar qayta hisoblanadi (D1-T11 tavsifi).
HOT_OYNA_KUNLARI = 7

# Bir `bulk_update` ga nechta qator. 500 — xotira va so'rov hajmi
# o'rtasidagi muvozanat; 10 000 ta post 20 ta so'rovda yangilanadi.
HOT_BOLAK = 500


def hot_score_hisobla(*, score: int, created_at: datetime) -> float:
    """«Qaynoqlik» balli: ovozlar logarifmi + yangilik bonusi.

    ⚠️⚠️ TAVSIFDAGI FORMULA TUZATILDI — ikki joyda.

    Taskda shunday yozilgan edi:

        log10(max(|ovoz|,1)) + sign(ovoz) * (yosh_sekundlarda / 45000)

    1. **`yosh` (age) NOTO'G'RI.** Yosh vaqt o'tishi bilan O'SADI, ya'ni
       eski postlar KATTAROQ ball olardi va «Qaynoq» lenta teskariga
       aylanardi — eng eski postlar tepada turardi. Kerakli narsa
       teskarisi: post qancha KEYIN yozilgan bo'lsa, shuncha yuqori.
       Shuning uchun `created_at - BOSHLANG'ICH` ishlatiladi (Reddit
       algoritmidagi kabi).

    2. **`sign` VAQT HADIDA emas, TARTIB hadida.** Tavsifdagi joylashuvda
       manfiy ballli post uchun vaqt hadi ham manfiy bo'lardi va eski
       minusli post yangi minusli postdan YUQORI turardi. Reddit
       varianti: `sign * tartib + vaqt`. Unda vaqt hamma uchun bir xil
       yo'nalishda ishlaydi, ovoz esa faqat "ko'tarish/tushirish"
       vazifasini bajaradi.

    Natija: ovozsiz yangi post ovozsiz eski postdan doim yuqori; 10 ta
    ovozli post 1 ta ovozlidan bir pog'ona yuqori (`log10` shkalasi).
    """
    tartib = math.log10(max(abs(score), 1))
    ishora = 1 if score > 0 else (-1 if score < 0 else 0)
    sekundlar = (created_at - HOT_BOSHLANGICH).total_seconds()
    return round(ishora * tartib + sekundlar / HOT_VAQT_OGIRLIGI, 7)


@shared_task(ignore_result=True)
def hot_scorelarni_yangilash(kunlar: int = HOT_OYNA_KUNLARI) -> int:
    """Oxirgi `kunlar` kunlik postlarning `hot_score` ini qayta hisoblaydi.

    Yangilangan qatorlar sonini qaytaradi.

    ⚠️ NEGA FAQAT OYNA, BUTUN BAZA EMAS
       Ball vaqtga bog'liq, ya'ni u har daqiqada "eskiradi". Lekin 7
       kundan eski postning balli allaqachon shu qadar past-ki, uni
       qayta hisoblash lentaga TA'SIR QILMAYDI. Butun bazani aylanish
       esa 10 ming postdan keyin vazifani sekinlashtiradi va u har 10
       daqiqada takrorlanadi — server doimiy yuk ostida qoladi.

    ⚠️ `bulk_update` + BO'LAKLAB (D1-T11 qabul mezoni)
       Har qatorni alohida `save()` qilish 10 ming post uchun 10 ming
       so'rov degani. `bulk_update` bitta so'rovda 500 tasini yangilaydi.

    ⚠️ FAQAT O'ZGARGANLARI YOZILADI
       Ball o'zgarmagan post `UPDATE` ga qo'shilmaydi. Amalda bu kam
       yordam beradi (vaqt hadi doim o'zgaradi), lekin ovozsiz eski
       postlarda foydali va yozish yukini kamaytiradi.

    ⚠️ `objects` (tirik) — yumshoq o'chirilganlar hisoblanmaydi: ular
       lentada baribir ko'rinmaydi. Tiklansa keyingi ishga tushishda
       (10 daqiqa ichida) o'z ballini oladi.
    """
    chegara = timezone.now() - timedelta(days=kunlar)
    # korinish-istisno: yashirilgan post ham hisoblanadi — u tiklansa
    # balli TAYYOR bo'lishi kerak, aks holda lentaning eng pastida
    # paydo bo'lardi. Bu yerda hech nima KO'RSATILMAYDI.
    qs = (
        Complaint.objects.filter(created_at__gte=chegara)
        # ⚠️⚠️ `score_cached` SHU YERDA BO'LISHI SHART (vaqt yedi).
        #    U GENERATED ustun bo'lsa-da, BAZADA HAQIQIY ustun. `.only()`
        #    ro'yxatida bo'lmasa Django uni KECHIKTIRADI va sikldagi har
        #    `muammo.score_cached` ALOHIDA `SELECT` ishga tushiradi:
        #    60 post = 60 qo'shimcha so'rov.
        #
        #    Ya'ni `.only()` optimizatsiya sifatida qo'yiladi va aynan
        #    teskarisiga aylanadi. Xato jim: natija to'g'ri, vazifa
        #    shunchaki sekin. Uni faqat so'rov sanog'i fosh qildi
        #    (test_vazifa_BULK_UPDATE_ishlatadi).
        .only("id", "created_at", "score_cached", "hot_score")
        # ⚠️ Barqaror tartib: `iterator()` server kursorini ishlatadi va
        #    tartibsiz so'rovda qatorlar takrorlanishi mumkin.
        .order_by("id")
    )

    yangilangan = 0
    bolak: list[Complaint] = []

    def bolakni_yozish() -> None:
        nonlocal yangilangan
        if bolak:
            # korinish-istisno: yozish amali, ko'rsatish emas.
            Complaint.objects.bulk_update(bolak, ["hot_score"])
            yangilangan += len(bolak)
            bolak.clear()

    for muammo in qs.iterator(chunk_size=HOT_BOLAK):
        yangi = hot_score_hisobla(
            score=muammo.score_cached, created_at=muammo.created_at
        )
        if muammo.hot_score != yangi:
            muammo.hot_score = yangi
            bolak.append(muammo)
        if len(bolak) >= HOT_BOLAK:
            bolakni_yozish()

    bolakni_yozish()

    log.info("hot_score yangilandi: %s ta post (oyna: %s kun)", yangilangan, kunlar)
    return yangilangan


# ===========================================================================
# Open Graph rasmi (D4-T4)
# ===========================================================================
@shared_task(
    name="apps.complaints.tasks.og_rasmni_yangilash",
    # ⚠️ Rasm — KOSMETIKA. Yasalmasa post baribir ishlaydi va shablon
    #    standart rasmga qaytadi. Shuning uchun cheksiz qayta urinish
    #    ma'nosiz: navbatni band qiladi va hech narsani tuzatmaydi.
    max_retries=2,
    default_retry_delay=60,
)
def og_rasmni_yangilash(complaint_id: int) -> str:
    """Muammo uchun OG kartasini yasaydi va saqlaydi.

    ⚠️ `all_objects`: yashirilgan yoki yumshoq o'chirilgan post uchun ham
       yasaladi. Sabab — tiklangandan keyin rasm DARHOL kerak bo'ladi va
       uni qayta yasashni hech kim eslamaydi. Rasmning o'zi hech qayerda
       ko'rsatilmaydi: uni faqat `og:image` metasi beradi, u esa
       yashirilgan postda umuman render bo'lmaydi.

    ⚠️ FAYL NOMIDA MAZMUN HASHI BOR — bu ATAYLAB:

       Ijtimoiy tarmoqlar `og:image` ni MANZIL bo'yicha keshlaydi va
       uzoq vaqt yangilamaydi. Nom o'zgarmasa (`og/12.png`), sarlavha
       tahrirlangandan keyin ham Telegram ESKI rasmni ko'rsatishda davom
       etardi. Hash esa mazmun o'zgarganda manzilni ham o'zgartiradi.

       Teskari tomoni ham muhim: mazmun O'ZGARMAGAN bo'lsa nom ham
       o'zgarmaydi, ya'ni har saqlashda yangi fayl to'planmaydi.
    """
    # korinish-istisno: rasm yasash — kontent KO'RSATILMAYDI. `og:image`
    # metasi yashirilgan postda render bo'lmaydi (ko'rinish tekshiruvi
    # `complaint_detail` da), bu yerda esa tiklanish holati qamraladi.
    muammo = (
        Complaint.all_objects.select_related("category").filter(pk=complaint_id).first()
    )

    if muammo is None:
        log.warning("og_rasmni_yangilash: muammo topilmadi (id=%s)", complaint_id)
        return "topilmadi"

    baytlar = og_rasm_yasash(
        sarlavha=muammo.title,
        kategoriya=muammo.category.name if muammo.category_id else "",
    )
    nom = f"{muammo.pk}-{hashlib.sha256(baytlar).hexdigest()[:8]}.png"

    if muammo.og_rasm and muammo.og_rasm.name.endswith(nom):
        return "o'zgarmadi"

    # ⚠️ Eskisi O'CHIRILADI: aks holda har tahrirdan keyin `media/og/` da
    #    yetim fayl qolardi va katalog cheksiz o'sardi.
    if muammo.og_rasm:
        muammo.og_rasm.delete(save=False)

    muammo.og_rasm.save(nom, ContentFile(baytlar), save=False)
    # ⚠️ `update_fields` — boshqa maydonlarga tegilmaydi. Vazifa fonda
    #    ishlaydi va shu orada post tahrirlangan bo'lishi mumkin.
    muammo.save(update_fields=["og_rasm"])
    return nom


# ===========================================================================
# O'xshash muammolar (D4-T7)
# ===========================================================================
def oxshash_kesh_kaliti(complaint_id: int) -> str:
    return f"oxshash:{complaint_id}"


def oxshash_ish_kaliti(complaint_id: int) -> str:
    return f"oxshash:ish:{complaint_id}"


@shared_task(
    name="apps.complaints.tasks.oxshash_muammolarni_hisoblash",
    # ⚠️ Yon paneldagi ro'yxat — KOSMETIKA. Hisoblanmasa sahifa baribir
    #    ishlaydi va blok umuman chizilmaydi. Cheksiz qayta urinish
    #    navbatni band qiladi va hech narsani tuzatmaydi.
    max_retries=1,
    default_retry_delay=120,
)
def oxshash_muammolarni_hisoblash(complaint_id: int) -> int:
    """Muammoga o'xshash postlarni topib, KESHGA yozadi.

    ⚠️⚠️ D4-T7 QABUL MEZONI: "hisoblash fon vazifasida, so'rov paytida
       emas". Trigram/FTS bo'yicha butun jadvalni skanerlash detal
       sahifasining har ochilishida bo'lmasligi kerak — sahifa esa
       lentadan keyin eng ko'p ochiladigan sahifa.

    ⚠️ KESHDA `pk` LAR SAQLANADI, KO'RSATISH MA'LUMOTI EMAS.
       Sarlavhani keshda saqlash bitta so'rovni tejardi, lekin post
       keshlangandan KEYIN yashirilsa yoki o'chirilsa, yon panel unga
       havola berishda davom etardi — ya'ni ko'rinish invarianti (D2-T3)
       kesh muddati davomida buzilardi. `pk` lar esa har so'rovda
       `visible()` dan qayta o'tadi.

    ⚠️ TRIGRAM O'RNIGA FTS. Task tavsifida "trigram o'xshashligi" deb
       yozilgan va u birinchi bo'lib sinaldi, lekin jonli ma'lumotda
       ishlamadi: butun sarlavhalar bo'yicha `similarity()` mavzuviy
       yaqinlikni emas, HARFLAR ustma-ustligini o'lchaydi.

           similarity: to'g'ri natija 0.140, begona 0.118  (farq yo'q)
           FTS + to'xtash so'zlar: to'g'ri 0.152, begona 0.008

       Trigram D4-T1 da o'z joyini topgan (xato yozilgan SO'ROV uchun) —
       u yerda qisqa so'rov solishtiriladi va aynan shunda ishlaydi.
    """
    from django.conf import settings
    from django.contrib.postgres.search import SearchQuery, SearchRank
    from django.core.cache import cache
    from django.db.models import F

    from apps.common.matn import mavzuli_sozlar

    # korinish-istisno: manba postning O'ZI ko'rsatilmaydi — undan faqat
    # sarlavha olinadi. Yashirilgan post tiklanganda ro'yxati tayyor
    # turishi kerak; NATIJALAR esa quyida `visible()` dan o'tadi.
    muammo = Complaint.all_objects.filter(pk=complaint_id).first()
    if muammo is None:
        log.warning("oxshash: muammo topilmadi (id=%s)", complaint_id)
        return 0

    sozlar = mavzuli_sozlar(muammo.title)
    if not sozlar:
        # ⚠️ Bo'sh ro'yxat ham KESHLANADI: aks holda mavzuli so'zi yo'q
        #    sarlavha (masalan "Nima qilay?") har ochilishida yangi
        #    vazifa yaratardi.
        cache.set(oxshash_kesh_kaliti(complaint_id), [], settings.OXSHASH_KESH_MUDDATI)
        return 0

    sorov = SearchQuery(" OR ".join(sozlar), config="simple", search_type="websearch")

    natija = list(
        Complaint.objects.visible()
        .exclude(pk=complaint_id)
        .filter(search_vector=sorov)
        # ⚠️ Vaznlar [D, C, B, A]: sarlavhadagi moslik tavsifdagidan
        #    ancha muhimroq — biz MAVZU yaqinligini qidiryapmiz, matn
        #    ichida tasodifan uchragan so'zni emas.
        .annotate(
            oxshashlik=SearchRank(
                F("search_vector"), sorov, weights=[0.0, 0.0, 0.05, 1.0]
            )
        )
        .filter(oxshashlik__gte=settings.OXSHASH_CHEGARASI)
        .order_by("-oxshashlik", "-id")
        .values_list("pk", flat=True)[: settings.OXSHASH_SONI]
    )

    cache.set(oxshash_kesh_kaliti(complaint_id), natija, settings.OXSHASH_KESH_MUDDATI)
    return len(natija)
