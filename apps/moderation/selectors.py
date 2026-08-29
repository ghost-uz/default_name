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

from django.db.models import Count
from django.utils import timezone

from .models import ModerationAction, Report, ReportReason

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

    # ⚠️ Muallifning OLDINGI qoidabuzarliklari soni (D2-T11).
    #    Bu maydon `navbat()` da OMMAVIY hisoblanadi, xossa EMAS:
    #    xossa bo'lsa har holat uchun bitta so'rov ketardi va 50
    #    holatli navbat 50 ta qo'shimcha so'rov qilardi — D2-T2
    #    hal qilgan "har holatda 5 ta sahifa" muammosining
    #    so'rovlardagi ko'rinishi.
    #
    # ⚠️ Zaxira `0`: mavjud testlar `Holat(...)` ni to'g'ridan-to'g'ri
    #    quradi va ular yangi maydon uchun o'zgarishi shart emas.
    qoidabuzarliklar: int = 0

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
    def takroriymi(self) -> bool:
        """Muallifda avval ham chora ko'rilganmi (D2-T11).

        ⚠️ Moderator uchun bu KONTEKST, jazo emas. "Birinchi marta
           xato qilgan odam" va "beshinchi marta bir xil narsani
           qilayotgan odam" bir xil ko'rinsa, moderator ikkalasiga
           ham bir xil muomala qiladi — va bu ikkalasiga ham noto'g'ri.
        """
        return self.qoidabuzarliklar > 0

    @property
    def keyingisi_cheklaydimi(self) -> str:
        """Keyingi chora avtomatik cheklovni ishga tushiradimi.

        `""` | `"vaqtinchalik"` | `"doimiy"`.

        ⚠️⚠️ MODERATOR OQIBATNI BOSISHDAN OLDIN KO'RSIN.
           `eskalatsiyani_tekshirish()` chora ko'rilgandan keyin
           avtomatik ishlaydi — bu to'g'ri (sanash mashinaning ishi),
           lekin ogohlantirish tugmasini bosgan moderator odamni
           bloklab qo'yganini KEYIN bilishi noto'g'ri. Bu yerda u
           tugmadagi yozuvni o'zgartiradi.

        ⚠️ Sanoq shu holatning O'ZIDAGI chorani ham qo'shib hisoblaydi
           (`+ 1`): avtomatika ham aynan shunday sanaydi (chora
           yozilgandan KEYIN chaqiriladi).
        """
        from django.conf import settings

        if self.muallif is None or self.cheklanganmi:
            return ""

        keyin = self.qoidabuzarliklar + 1
        if keyin >= settings.DOIMIY_BLOK_CHEGARASI:
            return "doimiy"
        if keyin >= settings.CHEKLOV_CHEGARASI:
            return "vaqtinchalik"
        return ""

    @property
    def cheklanganmi(self) -> bool:
        """Muallif AYNI PAYTDA cheklanganmi.

        ⚠️ `is_currently_banned` — muddat tekshiruvi bilan. `is_banned`
           bayrog'i muddat o'tgach ham `True` turadi (uni tozalaydigan
           fon vazifasi yo'q), ya'ni bayroqqa qarasak navbat allaqachon
           tugagan cheklovni "amal qilmoqda" deb ko'rsatardi va
           moderator ikkinchi marta cheklamasdi.
        """
        muallif = self.muallif
        return muallif is not None and muallif.is_currently_banned

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

    maqsadlar = {kalit: guruh[0].target for kalit, guruh in guruhlar.items()}
    sonlar = _qoidabuzarlik_sonlari(
        {t.author_id for t in maqsadlar.values() if t.author_id}
    )

    holatlar = [
        Holat(
            turi=turi,
            target=maqsadlar[(turi, pk)],
            shikoyatlar=guruh,
            # `order_by("created_at")` tufayli birinchisi eng eskisi.
            birinchi_shikoyat=guruh[0].created_at,
            qoidabuzarliklar=sonlar.get(maqsadlar[(turi, pk)].author_id, 0),
        )
        for (turi, pk), guruh in guruhlar.items()
    ]
    holatlar.sort(key=_tartib_kaliti)
    return holatlar


def _qoidabuzarlik_sonlari(mualliflar: set[int]) -> dict[int, int]:
    """`{muallif_id: qoidabuzarliklar_soni}` — BITTA so'rovda (D2-T11).

    ⚠️⚠️ `.order_by()` ATAYLAB va U MAJBURIY.

       `ModerationAction.Meta.ordering = ("-created_at",)`. Django
       `values(...).annotate(...)` da modelning standart tartibini
       GROUP BY ga QO'SHIB YUBORADI — ya'ni guruhlash
       `(muallif, created_at)` bo'yicha ketardi va har chora o'ziga
       alohida guruh bo'lardi. Natijada HAMMA sanoq `1` chiqardi.

       Bu xato hech qanday belgi bermaydi: so'rov bajariladi, ma'lumot
       qaytadi, faqat raqamlar yolg'on bo'ladi. `.order_by()` tartibni
       tozalaydi va GROUP BY faqat muallif bo'yicha qoladi.

    ⚠️ Sanoq mantiqi `services.qoidabuzarliklar_soni()` bilan BIR XIL
       bo'lishi shart (bekor qilingani sanalmaydi) — aks holda navbat
       "2-chi qoidabuzarlik" deb yozib turgan paytda avtomatika
       boshqa raqam bo'yicha qaror qabul qilardi. Ikkalasi ham
       `QOIDABUZARLIK_CHORALARI` ga tayanadi va buni
       `tests_bloklash.py` qo'riqlaydi.
    """
    if not mualliflar:
        return {}

    from .services import QOIDABUZARLIK_CHORALARI

    juftlar = (
        ModerationAction.objects.filter(
            target_author_id__in=mualliflar, action__in=QOIDABUZARLIK_CHORALARI
        )
        .filter(bekor_qilishlar__isnull=True)
        .order_by()  # ⚠️ Meta.ordering'ni tozalaydi — yuqoriga qarang
        .values_list("target_author_id")
        .annotate(soni=Count("pk"))
    )
    return dict(juftlar)


def holat_topish(*, turi: str, pk: int) -> Holat | None:
    """Bitta holat — HTMX bilan kartani qayta chizish uchun."""
    for holat in navbat():
        if holat.turi == turi and holat.target.pk == pk:
            return holat
    return None
