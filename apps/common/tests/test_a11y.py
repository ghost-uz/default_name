"""Kirish imkoniyati (a11y) qo'riqchilari.

⚠️⚠️ NEGA LIGHTHOUSE YETARLI EMAS
   D7-T4 dagi Lighthouse ishi bu uchta nuqsonni TOPDI, lekin u:
     • faqat BITTA sahifani (`/`) tekshiradi;
     • CI'da ishlaydi, ya'ni javob 2 daqiqadan keyin keladi;
     • `continue-on-error` — ya'ni YIQITMAYDI.

   Bu testlar esa hamma asosiy sahifani qamraydi, sekundlarda ishlaydi
   va YIQITADI. Lighthouse ularning ustiga o'zi topa oladigan
   narsalarni (rang, fokus, ARIA) qo'shadi.

⚠️ UCHALA TEST HAM HAQIQIY, TOPILGAN NUQSONDAN TUG'ILGAN — taxminiy
   emas. Har biri o'sha nuqsonni qayta hosil qilib tekshirilgan.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from itertools import pairwise

import pytest

from apps.complaints.factories import ComplaintFactory
from apps.solutions.factories import SolutionFactory

pytestmark = pytest.mark.django_db

# Tekshiriladigan sahifalar: `(nom, yo'l)`.
SAHIFALAR = (
    ("lenta", "/"),
    ("qidiruv (bo'sh)", "/qidiruv/"),
    ("qidiruv (natijali)", "/qidiruv/?q=ipoteka"),
    # ⚠️ D6-T2: PRO — ommaviy NARX sahifasi, ya'ni u qidiruvdan ham,
    #    maketdagi havoladan ham kiriladigan nuqta. Yangi ommaviy
    #    sahifa qo'shilganda ro'yxatga qo'shilmasa, u qo'riqchidan
    #    TASHQARIDA qolardi va buni hech narsa aytmasdi.
    ("PRO obuna", "/pro/"),
)


class _Yigib(HTMLParser):
    """Sarlavhalar va havolalarni yig'adi.

    ⚠️ `hidden` sinfi bilan yashirilgan matn KIRISH DARAXTIDA YO'Q:
       `display:none` elementni ekran o'quvchidan butunlay olib
       tashlaydi. Shuning uchun u nom sifatida SANALMAYDI — aynan shu
       xato kirish havolasida bo'lgan edi.

    ⚠️⚠️ FAQAT HAVOLA ICHIDAGI yashirish sanaladi, AJDODINIKI EMAS.
       Tailwind'da `hidden lg:flex` «lg dan PASTDA yashirin» degani —
       ya'ni element BOSHQA o'lchamda KO'RINADI. Sarlavhadagi desktop
       navigatsiya aynan shunday: u mobilda umuman yo'q (o'rniga
       boshqa menyu bor), demak uning havolalari «nomsiz havola»
       EMAS.

       Birinchi versiya ajdodni ham hisoblab, 16 ta YOLG'ON
       ogohlantirish bergandi. Haqiqiy nuqson esa boshqa shakl:
       havolaning O'ZI ko'rinadi, lekin uning MATNI ichkarida
       yashirilgan (kirish havolasidagi `hidden lg:inline`).
    """

    YASHIRIN = re.compile(r"(?:^|\s)(?:hidden|invisible)(?:\s|$)")

    # ⚠️⚠️ VOID elementlar YOPILISH TEGI BERMAYDI.
    #    Birinchi versiyada ular ham stekka qo'yilardi va stek
    #    BUZILARDI: `_yashirin_chuqurlik` hech qachon nolga
    #    qaytmasdi va HAMMA havola "nomsiz" bo'lib ko'rinardi
    #    (50 ta yolg'on ogohlantirish). Guardda yolg'on
    #    ogohlantirish eng zararli nuqson.
    VOID = frozenset(
        {
            "area",
            "base",
            "br",
            "col",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "param",
            "source",
            "track",
            "wbr",
        }
    )

    def __init__(self) -> None:
        super().__init__()
        self.sarlavhalar: list[int] = []
        self.havolalar: list[dict] = []
        self._havola: dict | None = None
        self._yashirin_chuqurlik = 0
        self._stek: list[bool] = []

    def handle_starttag(self, teg: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: (v or "") for k, v in attrs}
        yashirinmi = bool(self.YASHIRIN.search(a.get("class", ""))) or (
            "hidden" in a and a.get("hidden") is not None
        )
        # `aria-hidden` ham kirish daraxtidan olib tashlaydi.
        yashirinmi = yashirinmi or a.get("aria-hidden") == "true"

        if teg in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.sarlavhalar.append(int(teg[1]))

        if teg == "a":
            self._havola = {
                "href": a.get("href", ""),
                "aria_label": a.get("aria-label", "") or a.get("title", ""),
                "matn": "",
            }
            # ⚠️⚠️ Hisob HAVOLADAN boshlab qayta ochiladi VA havolaning
            #    O'Z `hidden` sinfi ham SANALMAYDI. `btn-primary hidden
            #    sm:inline-flex` — havolaning o'zi kichik ekranda yo'q,
            #    lekin katta ekranda BOR va u yerda matni ko'rinadi.
            #    Birinchi versiya buni ham hisoblab, «Dard yozish»
            #    havolasini yolg'ondan nomsiz deb ko'rsatdi.
            self._yashirin_chuqurlik = 0
            yashirinmi = False

        if teg in self.VOID:
            # Void element ichida bola yo'q — stekka qo'yilmaydi.
            return
        if yashirinmi:
            self._yashirin_chuqurlik += 1
        self._stek.append(yashirinmi)

    def handle_startendtag(self, teg, attrs) -> None:
        """`<path ... />` — ochilish VA yopilish bir teg.

        ⚠️ Standart amalga oshirish `handle_starttag` + `handle_endtag`
           ni chaqiradi; bu yerda ikkalasi ham stekni o'zgartirar va
           natija to'g'ri bo'lardi, LEKIN `a` teglari uchun yolg'on
           yopilish yasardi. Shuning uchun ochiq qayta yozilgan.
        """
        if teg in ("h1", "h2", "h3", "h4", "h5", "h6", "a"):
            self.handle_starttag(teg, attrs)
            self.handle_endtag(teg)

    def handle_endtag(self, teg: str) -> None:
        if teg in self.VOID:
            return
        if self._stek and self._stek.pop():
            self._yashirin_chuqurlik -= 1
        if teg == "a" and self._havola is not None:
            self.havolalar.append(self._havola)
            self._havola = None

    def handle_data(self, matn: str) -> None:
        if self._havola is not None and self._yashirin_chuqurlik == 0:
            self._havola["matn"] += matn


def _tahlil(html: str) -> _Yigib:
    y = _Yigib()
    y.feed(html)
    return y


def _toldirish() -> None:
    muammo = ComplaintFactory(title="Ipoteka olish qiyinmi")
    SolutionFactory.create_batch(2, complaint=muammo)
    ComplaintFactory.create_batch(4)


# ===========================================================================
# 1. ⚠️⚠️ Havolada o'qiladigan nom BO'LSIN
# ===========================================================================
@pytest.mark.parametrize("nom,yol", SAHIFALAR, ids=lambda x: str(x))
def test_HAR_HAVOLADA_oqiladigan_nom_bor(nom, yol, client):
    """⚠️⚠️ D7-T4 topilmasi: kirish havolasi ekran o'quvchi uchun
    NOMSIZ edi — matni `hidden lg:inline` bilan yashirilgandi.

    ⚠️ Bu test `hidden` sinfini HISOBGA OLADI. Oddiy «matn bormi?»
       tekshiruvi bu xatoni O'TKAZIB YUBORARDI: HTML'da matn BOR,
       lekin u `display:none` va kirish daraxtida YO'Q.
    """
    _toldirish()

    y = _tahlil(client.get(yol).content.decode())

    nomsiz = [
        h["href"]
        for h in y.havolalar
        if not h["matn"].strip() and not h["aria_label"].strip()
    ]
    assert nomsiz == [], (
        f"{nom}: o'qiladigan nomsiz havola(lar): {nomsiz}\n"
        "  Ikonka-havolaga `aria-label` qo'shing (matn `hidden` bo'lsa "
        "u kirish daraxtida YO'Q)."
    )


# ===========================================================================
# 2. ⚠️ Sarlavha darajalari SAKRAMASIN
# ===========================================================================
@pytest.mark.parametrize("nom,yol", SAHIFALAR, ids=lambda x: str(x))
def test_SARLAVHA_darajalari_SAKRAMAYDI(nom, yol, client):
    """⚠️ D7-T4 topilmasi: bo'sh holat `h3` ishlatardi va lentada
    undan oldingi yagona sarlavha `h1` edi — `h2` sakrab o'tilardi.

    Ekran o'quvchi sarlavhalar bo'yicha harakatlanadi; sakrash
    "ichma-ich bo'lim" degan yolg'on tuzilma yaratadi.
    """
    _toldirish()

    darajalar = _tahlil(client.get(yol).content.decode()).sarlavhalar

    assert darajalar, f"{nom}: sahifada umuman sarlavha yo'q"

    # ⚠️⚠️ «BIRINCHI SARLAVHA h1 BO'LSIN» TALAB QILINMAYDI — ATAYLAB.
    #    Birinchi versiyada shunday edi va u yon paneldagi
    #    `<h2>Kategoriyalar</h2>` uchun yiqilardi. Lekin bu WCAG
    #    buzilishi EMAS: axe'ning `heading-order` qoidasi faqat
    #    SAKRASHNI taqiqlaydi, DOM tartibida h1 birinchi bo'lishini
    #    emas. Standartdan qattiqroq qo'riqcha = yolg'on
    #    ogohlantirish = e'tiborsiz qolgan qo'riqcha.
    #
    #    `h1` MAVJUDLIGI esa alohida testda tekshiriladi.
    for oldingi, keyingi in pairwise(darajalar):
        assert keyingi <= oldingi + 1, (
            f"{nom}: h{oldingi} -> h{keyingi} sakrash. "
            "Sarlavha darajasi BIRDAN ortiq oshmasin."
        )


@pytest.mark.parametrize("nom,yol", SAHIFALAR, ids=lambda x: str(x))
def test_BITTA_h1(nom, yol, client):
    """⚠️ `h1` — sahifaning yagona nomi."""
    _toldirish()

    darajalar = _tahlil(client.get(yol).content.decode()).sarlavhalar

    assert darajalar.count(1) == 1, f"{nom}: {darajalar.count(1)} ta h1"


# ===========================================================================
# 3. ⚠️⚠️ Rang kontrasti — TOKENLAR darajasida
# ===========================================================================
def _yorqinlik(hex_rang: str) -> float:
    def kanal(c: float) -> float:
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    h = hex_rang.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * kanal(r) + 0.7152 * kanal(g) + 0.0722 * kanal(b)


def kontrast(old: str, orqa: str) -> float:
    a, b = _yorqinlik(old), _yorqinlik(orqa)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


# ⚠️ Qo'lda yozilgan juftliklar — CSS'ni to'liq tahlil qilishga
#    urinish (kaskad, `@apply`, opacity) mo'rt bo'lardi va yolg'on
#    ogohlantirish berardi. Bu ro'yxat esa HAQIQIY, sahifada
#    UCHRAYDIGAN juftliklarni qamraydi.
MATN_JUFTLIKLARI = (
    ("fg-muted / surface", "#5a6a80", "#ffffff"),
    ("fg-muted / surface-2", "#5a6a80", "#f1f5f9"),
    ("fg-muted / PRO kartasi", "#5a6a80", "#edf2fb"),
    ("telegram-ink / surface", "#177a9e", "#ffffff"),
    # ⚠️⚠️ QORONG'I REJIM ALOHIDA TEKSHIRILADI. Yorug' rejimda matnni
    #    QORAYTIRISH kerak, qorong'ida esa OCHROQ qilish — ya'ni bitta
    #    tuzatish ikkinchi rejimni BUZISHI mumkin va aynan shunday
    #    bo'ldi: `telegram-ink` yorug'da tuzalgach qorong'ida 3.57 ga
    #    tushdi.
    ("fg-muted (qorong'i) / bg", "#94a3b8", "#0b1220"),
    ("fg-muted (qorong'i) / surface", "#94a3b8", "#111a2c"),
    ("fg-muted (qorong'i) / surface-2", "#94a3b8", "#17223a"),
    ("telegram-ink (qorong'i) / surface", "#229ed9", "#111a2c"),
    ("telegram-ink (qorong'i) / surface-2", "#229ed9", "#17223a"),
)


@pytest.mark.parametrize("nom,old,orqa", MATN_JUFTLIKLARI, ids=lambda x: str(x))
def test_MATN_kontrasti_WCAG_AA(nom, old, orqa):
    """⚠️⚠️ D7-T4 topilmasi: `fg-muted` (slate-500) RANGLI fonlarda
    yiqilardi (4.34 va 4.23), oq fonda esa o'tardi (4.76) — shuning
    uchun uni ko'z bilan payqash deyarli imkonsiz edi.

    ⚠️ Bu test RANGLARNI o'zini tekshiradi, sahifani emas: u
       sekundning mingdan biri ichida ishlaydi va CSS o'zgargan
       zahoti yiqiladi.
    """
    k = kontrast(old, orqa)

    assert k >= 4.5, (
        f"{nom}: kontrast {k:.2f}, WCAG AA 4.5:1 talab qiladi.\n"
        f"  {old} / {orqa} — matn rangini qoraytiring yoki fonni "
        "ochroq qiling."
    )


def test_TOKENLAR_CSS_bilan_MOS():
    """⚠️⚠️ Yuqoridagi ro'yxat CSS'dan AJRALIB QOLMASIN.

    Rang testlari qo'lda yozilgan qiymatlar ustida ishlaydi — CSS
    o'zgarsa-yu ro'yxat qolsa, test yashil bo'lib turardi va
    HECH NARSANI tekshirmasdi. Bu tekshiruv ikkalasini bog'lab
    turadi.
    """
    import pathlib

    from django.conf import settings

    css = (pathlib.Path(settings.BASE_DIR) / "tailwind" / "input.css").read_text(
        encoding="utf-8"
    )

    assert "--p-slate-550: #5a6a80;" in css, "fg-muted rangi o'zgargan"
    assert "--c-fg-muted: var(--p-slate-550);" in css, "fg-muted tokeni o'zgargan"
    assert "--c-telegram-ink: #177a9e;" in css, "telegram matn rangi o'zgargan"
    assert "--c-telegram-ink: var(--c-telegram);" in css, (
        "qorong'i rejim uchun `telegram-ink` override'i yo'q"
    )
