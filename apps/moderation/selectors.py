"""Moderatsiya navbati — o'qish so'rovlari (D2-T2).

⚠️ NAVBAT SHIKOYAT BO'YICHA EMAS, OBYEKT BO'YICHA GURUHLANADI.

   Django admin shikoyatlarni birma-bir ko'rsatadi. Bitta postga 5 ta
   shikoyat kelsa, moderator bir xil kontentni 5 marta o'qib, 5 marta
   bir xil qaror qabul qiladi — task tavsifidagi "har bir holatda 5 ta
   sahifa" muammosi aynan shu.

   Aslida qaror KONTENT haqida, shikoyat haqida emas. Shuning uchun bu
   yerda "holat" (case) tushunchasi bor: bitta obyekt + unga tushgan
   barcha ochiq shikoyatlar + qaror uchun kerakli kontekst.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from django.utils import timezone

from .models import Report, ReportReason

# ⚠️ Shikoyat sahifasi foydalanuvchiga "Moderatorlar 24 soat ichida ko'rib
#    chiqadi" deb VA'DA BERADI (templates/moderation/shikoyat.html).
#    Navbat tartibi shu va'dani kafolatlashi kerak — aks holda interfeys
#    o'z va'dasini o'zi buzadi.
SLA = timedelta(hours=24)


@dataclass(frozen=True)
class Holat:
    """Bitta moderatsiya holati — obyekt + unga tushgan ochiq shikoyatlar."""

    turi: str  # "muammo" | "yechim"
    target: Any
    shikoyatlar: list[Report]
    birinchi_shikoyat: datetime

    @property
    def soni(self) -> int:
        return len(self.shikoyatlar)

    @property
    def shoshilinchmi(self) -> bool:
        """Kamida bitta `XAVF` sababi bormi — odam hayoti haqidagi signal."""
        return any(s.reason == ReportReason.XAVF for s in self.shikoyatlar)

    @property
    def kechikkanmi(self) -> bool:
        return timezone.now() - self.birinchi_shikoyat > SLA

    @property
    def kutgan_vaqt(self) -> timedelta:
        return timezone.now() - self.birinchi_shikoyat

    @property
    def ochirilganmi(self) -> bool:
        """Muallif kontentni o'zi o'chirganmi (yumshoq).

        ⚠️ Bunday holat navbatdan CHIQARILMAYDI: kontent ketgan bo'lsa
           ham muallifga nisbatan chora (ogohlantirish) hali ham
           ma'noli, va shikoyat "ko'rib chiqilmagan" bo'lib qolmasligi
           kerak.
        """
        return self.target.deleted_at is not None

    @property
    def muallif(self):
        """⚠️ HAQIQIY muallif — `public_author` EMAS, ATAYLAB.

        Anonimlik BOSHQA FOYDALANUVCHILARDAN yashirish uchun. Moderator
        esa takroriy qoidabuzarni tanishi kerak: D2-T11 (uch
        ogohlantirish) aynan shunga tayanadi va anonim post ortiga
        yashiringan odam cheksiz davom etardi.

        Bu xossa shablon `.author` ga to'g'ridan-to'g'ri cho'zilmasligi
        uchun bor: anonimlik guard'i
        (`apps/complaints/tests/test_anonimlik.py`) shablonlarda xom
        `.author` ni taqiqlaydi va bu to'g'ri — istisno qarori KODDA,
        izoh bilan turishi kerak, shablonga sochilib ketmasligi.

        ⚠️ D2-T10 (maxfiylik siyosati) buni ochiq yozishi SHART:
           "anonim post moderatorga anonim EMAS".
        """
        return self.target.author

    @property
    def sabablar(self) -> list[tuple[str, int]]:
        """`[("Spam yoki reklama", 3), ...]` — ko'pdan kamga.

        Sabablarni yig'ish moderatorga darhol naqshni ko'rsatadi: 5 ta
        turli sabab bitta postda — ehtimol haqiqiy muammo; 5 ta bir xil
        sabab bir xil vaqtda — ehtimol kelishilgan hujum.
        """
        hisob = Counter(s.get_reason_display() for s in self.shikoyatlar)
        return hisob.most_common()

    @property
    def avtomatikmi(self) -> bool:
        """Holatni AVTOMATIK FILTR ochganmi (D2-T5).

        ⚠️ Moderator uchun bu farq muhim: "uchta odam shikoyat qildi" va
           "bizning filtr shubhali dedi" — butunlay boshqa dalillar.
           Ikkalasi bir xil ko'rinsa, moderator avtomatik signalga
           odam signaliga bergan ishonchni berardi.
        """
        return any(s.reporter_id is None for s in self.shikoyatlar)

    @property
    def izohlar(self) -> list[str]:
        return [s.comment for s in self.shikoyatlar if s.comment]

    @property
    def kalit(self) -> str:
        """HTML `id` va klaviatura navigatsiyasi uchun barqaror kalit."""
        return f"{self.turi}-{self.target.pk}"


def _tartib_kaliti(holat: Holat) -> tuple[int, int, float, float]:
    """Navbat tartibi — mahsulot qarori (foydalanuvchi tanlagan).

    1. `XAVF` — HAR DOIM tepada. Bu muhokama qilinmaydi: odam hayoti
       haqidagi signal spam bilan bir navbatda turmaydi.
    2. Keyin SLA buzilganlar (24 soatdan oshgan) — eskisidan yangisiga.
       Sabab: shikoyat sahifasi "24 soat ichida" deb va'da beradi va
       navbat o'sha va'dani bajarishi kerak. Bu ayni paytda "hech narsa
       chirimaydi" kafolati ham.
    3. Qolganlari — shikoyat soni ko'pdan kamga. Tez tarqalayotgan
       kontent (5 ta shikoyat 2 soatda) yolg'iz shikoyatdan oldin
       ko'riladi.

    ⚠️ 2 va 3 ATAYLAB TESKARI mantiqda: kechikkanlar orasida "eski
       birinchi", kechikmaganlar orasida "ko'p shikoyatli birinchi".
       Faqat sonni ishlatish yolg'iz, lekin haqiqiy shikoyatni cheksiz
       kuttirardi; faqat vaqtni ishlatish esa tez tarqalayotgan zararni
       navbat oxirida qoldirardi.
    """
    vaqt = holat.birinchi_shikoyat.timestamp()
    ichki: tuple[float, float] = (
        (vaqt, -float(holat.soni)) if holat.kechikkanmi else (-float(holat.soni), vaqt)
    )
    return (
        0 if holat.shoshilinchmi else 1,
        0 if holat.kechikkanmi else 1,
        *ichki,
    )


def navbat() -> list[Holat]:
    """Ochiq shikoyatlarni holatlarga guruhlab, tartiblab qaytaradi.

    ⚠️ Guruhlash Python'da, bazada emas. Sabab: `Holat` ning tartib
       kaliti ikki bosqichli va shartli (yuqoriga qarang) — uni SQL'da
       yozish `CASE WHEN` lar ichiga ko'milgan va o'qib bo'lmaydigan
       so'rov berardi. Navbat hajmi esa yuzlab, million emas.

       Agar navbat o'sib ketsa, birinchi qadam — bu funksiyaga
       cheklov (`[:N]`) qo'yish, SQL'ga ko'chirish emas.
    """
    shikoyatlar = (
        Report.objects.ochiq()
        .select_related(
            "reporter",
            "complaint",
            "complaint__author",
            "complaint__category",
            "solution",
            "solution__author",
            "solution__complaint",
        )
        .order_by("created_at")
    )

    guruhlar: dict[tuple[str, int], list[Report]] = {}
    for shikoyat in shikoyatlar:
        kalit = (
            ("muammo", shikoyat.complaint_id)
            if shikoyat.complaint_id
            else ("yechim", shikoyat.solution_id)
        )
        guruhlar.setdefault(kalit, []).append(shikoyat)

    holatlar = [
        Holat(
            turi=turi,
            target=guruh[0].target,
            shikoyatlar=guruh,
            # `order_by("created_at")` tufayli birinchisi eng eskisi.
            birinchi_shikoyat=guruh[0].created_at,
        )
        for (turi, _pk), guruh in guruhlar.items()
    ]
    holatlar.sort(key=_tartib_kaliti)
    return holatlar


def holat_topish(*, turi: str, pk: int) -> Holat | None:
    """Bitta holat — HTMX bilan kartani qayta chizish uchun."""
    for holat in navbat():
        if holat.turi == turi and holat.target.pk == pk:
            return holat
    return None
