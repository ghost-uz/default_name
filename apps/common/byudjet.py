"""Ish faoliyati byudjeti (D7-T4).

⚠️⚠️ NEGA BYUDJET BITTA JOYDA
   Task `nega` bo'limi: «sekinlashuv asta-sekin va sezilmasdan keladi;
   o'lchov CI'da bo'lmasa hech kim payqamaydi».

   Sonlar testlar bo'ylab sochilib yotgan bo'lsa (D1-T14 dan keyin
   shunday edi), hech kim BUTUN manzarani ko'rmaydi: har test o'z
   sahifasini biladi, «sayt umuman qanchalik og'ir?» degan savolga esa
   javob beradigan joy yo'q. Jadval shu savolga javob beradi va
   o'zgarishi `git diff` da KO'RINADI.

⚠️⚠️ ENG MUHIM QAROR: QAYSI O'LCHAM YIQITADI, QAYSI BIRI OGOHLANTIRADI

   | O'lcham | Xulq | Sabab |
   |---|---|---|
   | so'rov soni | **YIQITADI** | to'liq deterministik |
   | javob hajmi (bayt) | **YIQITADI** | to'liq deterministik |
   | render vaqti | ogohlantiradi | runner yuki tasodifiy |
   | Lighthouse | ogohlantiradi | ballar ±5 tebranadi |

   Qabul mezoni aynan shunday yozilgan: «byudjet oshsa CI
   OGOHLANTIRADI». Vaqtni qat'iy chegara qilish CI'ni haftada bir
   necha marta yolg'on yiqitardi — va uchinchi yolg'on ogohlantirishdan
   keyin hech kim unga qaramaydi. Deterministik o'lchamlar esa
   YOLG'ON YIQITMAYDI, ya'ni ularni qattiq ushlash mumkin va kerak.

⚠️ HAJM BYUDJETI LIGHTHOUSE'NING KATTA QISMINI DETERMINISTIK QOPLAYDI.
   Lighthouse'ning «Performance» balli asosan BAYT va so'rovlar
   funksiyasi. Ya'ni CSS to'satdan ikki barobar o'ssa yoki kimdir
   sahifaga ulkan inline SVG qo'ysa — buni brauzersiz, tebranishsiz
   ushlaymiz.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass

from django.conf import settings

# ⚠️ Render vaqti CHEGARASI — faqat OGOHLANTIRISH uchun (yuqoriga qarang).
#    Task tavsifidagi «TTFB <300ms» ning server tomonidagi qismi: tarmoq
#    va TLS bizning nazoratimizda emas, shablon render'i esa nazoratda.
RENDER_MS = 300

# ⚠️ Lighthouse chegarasi — CI'da alohida, OGOHLANTIRUVCHI ishda.
LIGHTHOUSE_BALL = 90


@dataclass(frozen=True)
class Sahifa:
    """Bitta sahifaning byudjeti.

    ⚠️ `sorovlar` — YUQORI CHEGARA, aniq son emas: aniq sonni ushlash
       har begona o'zgarishda (masalan yangi context-processor) testni
       yiqitardi va odam uni «shunchaki yangilab» qo'yardi. Chegara esa
       ONGLI qaror talab qiladi.
    """

    nom: str
    yol: str
    sorovlar: int
    bayt: int
    kirgan: bool = False

    def manzil(self, *, slug: str) -> str:
        """`{slug}` o'rniga haqiqiy postni qo'yadi.

        ⚠️ Byudjet MAKET sahifasida emas, HAQIQIY ko'rinishda
           o'lchanadi. Birinchi urinishda ro'yxatga `/kategoriyalar/`
           tushib qolgandi — u `apps/common/maket.py` dagi statik
           namuna va **0 ta so'rov** qiladi, ya'ni byudjet u yerda
           hech qachon hech narsani ushlamasdi.
        """
        return self.yol.format(slug=slug)


# ⚠️⚠️ BU JADVALNI O'ZGARTIRISH — ONGLI QAROR.
#    Sonni oshirish oson va shuning uchun xavfli: har reliz bittadan
#    so'rov qo'shilsa, bir yildan keyin lenta ikki barobar sekin bo'ladi
#    va hech kim buni payqamaydi. `git blame` bu qatorlarda kim, qachon
#    va NEGA oshirganini ko'rsatishi kerak.
#
# ⚠️ O'LCHANGAN HOLAT (2026-09-06, 20 postli sahifa):
#      lenta (mehmon)   2 so'rov / 128 KB
#      lenta (kirgan)   7 so'rov / 135 KB
#      dard (batafsil)  5 so'rov /  44 KB
#      qidiruv          3 so'rov / 123 KB
#    Byudjet shundan ~2 so'rov va ~15% zaxira bilan qo'yilgan: u
#    tasodifiy tebranishdan yiqilmasin, lekin IKKI BAROBAR o'sishni
#    albatta ushlasin.
SAHIFALAR: tuple[Sahifa, ...] = (
    # Eng ko'p ochiladigan sahifa — mehmon uchun.
    Sahifa(nom="lenta (mehmon)", yol="/", sorovlar=4, bayt=150_000),
    # Kirgan foydalanuvchida: +sessiya, +foydalanuvchi, +ovozlar,
    # +saqlanganlar, +bloklanganlar (D2-T11).
    Sahifa(nom="lenta (kirgan)", yol="/", sorovlar=9, bayt=160_000, kirgan=True),
    # ⚠️ ENG BOY SAHIFA: yechimlar, ovozlar, JSON-LD (D4-T6), o'xshash
    #    muammolar (D4-T7). Ya'ni N+1 xavfi ham eng yuqori shu yerda.
    Sahifa(nom="dard (batafsil)", yol="/dard/{slug}/", sorovlar=8, bayt=60_000),
    # ⚠️ Qidiruv `COUNT(*)` qiladi (D4-T3 dagi ongli qaror) — lentadan
    #    bitta so'rov ko'p bo'lishi KUTILGAN.
    Sahifa(nom="qidiruv", yol="/qidiruv/?q=ipoteka", sorovlar=5, bayt=145_000),
)

# ⚠️ Statik aktivlar — foydalanuvchi HAR sahifada yuklaydigan narsa.
#    Tailwind'da sinf qo'shish arzon ko'rinadi, lekin bundle o'sishi
#    hamma sahifaga tegadi va uni hech kim o'lchamaydi.
AKTIVLAR: tuple[tuple[str, int], ...] = (
    ("static/css/app.css", 75_000),
    ("static/js/vendor/htmx.min.js", 60_000),
    ("static/js/app.js", 40_000),
)


def aktiv_hajmi(nisbiy: str) -> int | None:
    """Aktiv fayl hajmi (bayt). Fayl yo'q bo'lsa `None`.

    ⚠️ `app.css` — QURILISH artefakti (`.gitignore` da). Toza
       checkout'da u YO'Q va bu XATO EMAS: byudjet testi uni
       o'tkazib yuboradi, CI esa testdan OLDIN `npm run build`
       qiladi (workflow'dagi izohga qarang).
    """
    yol = pathlib.Path(settings.BASE_DIR) / nisbiy
    return yol.stat().st_size if yol.exists() else None
