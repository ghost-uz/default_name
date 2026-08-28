"""⚠️ KO'RINISH INVARIANTI (D2-T3).

Yashirilgan kontent lentada, qidiruvda, profilda, sitemap'da, RSS'da va
API'da CHIQMASLIGI kerak.

Bitta unutilgan so'rov (masalan `sitemap.xml`) yashirilgan kontentni
Google'ga beradi — va u yerdan uni qaytarib olib bo'lmaydi.

⚠️ IKKI XIL GUARD, IKKALASI HAM KERAK

  1. **Ish vaqtida** (`test_HECH_QAYSI_ommaviy_yol_*`): URLconf'dagi
     BARCHA yo'llar avtomatik aylanadi va yashirin markerlar javobda
     yo'qligi tekshiriladi. Yangi ko'rinish qo'shilsa u AVTOMATIK
     qamrab olinadi — ro'yxatni yangilash shart emas.

  2. **Manba kodida** (`test_manba_kodida_*`): `Complaint.objects` yoki
     `Solution.objects` `visible()` siz ishlatilgan joyni topadi.
     Birinchi guard faqat MAVJUD yo'llarni tekshiradi; bu esa hali
     ko'rinishga ulanmagan kodni ham (masalan yangi `selectors`
     funksiyasi) qamrab oladi.

  Faqat birinchisi bo'lsa: sitemap yozilib, unga test yozilmasa —
  hech kim payqamaydi. Faqat ikkinchisi bo'lsa: shablon darajasidagi
  sizib chiqish (masalan `complaint.solutions.all()`) ko'rinmay qoladi.
"""

from __future__ import annotations

import ast
import pathlib

import pytest
from django.conf import settings
from django.test import Client
from django.urls import URLPattern, URLResolver, get_resolver, reverse
from django.urls.exceptions import NoReverseMatch

from apps.common.models import ModerationStatus
from apps.complaints.factories import ComplaintFactory
from apps.complaints.models import SavedComplaint
from apps.solutions.factories import SolutionFactory

pytestmark = pytest.mark.django_db

# Javobda UCHRAMASLIGI kerak bo'lgan noyob satrlar.
YASHIRIN_MUAMMO = "YASHIRINMUAMMOMARKERI"
YASHIRIN_YECHIM = "YASHIRINYECHIMMARKERI"
OCHIRILGAN_MUAMMO = "OCHIRILGANMUAMMOMARKERI"


def _yollarni_yigish(resolver, prefiks: str = "", namespace: str | None = None):
    """URLconf'dagi barcha nomlangan yo'llarni (nom, konvertorlar) qaytaradi."""
    for p in resolver.url_patterns:
        if isinstance(p, URLResolver):
            # ⚠️ Admin ATAYLAB tashlab yuboriladi: u moderator interfeysi va
            #    yashirilgan kontentni KO'RSATISHI KERAK (D2-T2). Uning
            #    himoyasi — staff huquqi, `visible()` emas.
            ns = p.namespace or namespace
            if ns == "admin":
                continue
            yield from _yollarni_yigish(p, prefiks, ns)
        elif isinstance(p, URLPattern) and p.name:
            yield p.name, namespace, dict(p.pattern.converters)


def ommaviy_yollar(*, muammo, username: str) -> list[str]:
    """Sinash mumkin bo'lgan barcha manzillar.

    ⚠️ Manzillar YASHIRIN obyektning o'z qiymatlari bilan quriladi —
       ya'ni `/dard/<yashirin-slug>/` ham sinaladi. Aynan shu eng muhim
       holat: havolani biladigan odam yashirin postni ocha olmasligi kerak.
    """
    qiymatlar = {
        "slug": muammo.slug,
        "pk": muammo.pk,
        "username": username,
    }
    yollar = []
    for nom, ns, konvertorlar in _yollarni_yigish(get_resolver()):
        toliq_nom = f"{ns}:{nom}" if ns else nom
        try:
            kwargs = {k: qiymatlar[k] for k in konvertorlar}
        except KeyError:
            continue  # noma'lum konvertor — qurib bo'lmaydi
        try:
            yollar.append(reverse(toliq_nom, kwargs=kwargs))
        except NoReverseMatch:
            continue
    return sorted(set(yollar))


@pytest.fixture
def yashirin_kontent(user_factory):
    """Yashirilgan muammo + yechim + o'chirilgan muammo."""
    egasi = user_factory(username="yashirinmuallif")

    muammo = ComplaintFactory(
        author=egasi,
        title=f"{YASHIRIN_MUAMMO} sarlavha",
        description=f"{YASHIRIN_MUAMMO} tavsif",
        moderation_status=ModerationStatus.HIDDEN,
    )
    SolutionFactory(complaint=muammo, content=f"{YASHIRIN_YECHIM} matni")

    # Ko'rinadigan muammoda YASHIRILGAN yechim — alohida holat.
    korinadigan = ComplaintFactory(title="Ochiq muammo")
    SolutionFactory(
        complaint=korinadigan,
        content=f"{YASHIRIN_YECHIM} ochiq postda",
        moderation_status=ModerationStatus.HIDDEN,
    )

    ochirilgan = ComplaintFactory(
        title=f"{OCHIRILGAN_MUAMMO} sarlavha",
        description=f"{OCHIRILGAN_MUAMMO} tavsif",
    )
    ochirilgan.delete()  # yumshoq

    return {
        "yashirin": muammo,
        "korinadigan": korinadigan,
        "ochirilgan": ochirilgan,
        "egasi": egasi,
    }


# ===========================================================================
# 1. Ish vaqtidagi guard — BARCHA yo'llar avtomatik
# ===========================================================================
def test_HECH_QAYSI_ommaviy_yolda_yashirin_kontent_YOQ(yashirin_kontent, user_factory):
    """⚠️ D2-T3 ning asosiy testi.

    URLconf'dagi barcha yo'llar aylanadi — ro'yxat QO'LDA yuritilmaydi,
    ya'ni yangi ko'rinish (sitemap, RSS, API) qo'shilganda u avtomatik
    qamrab olinadi va bu test uni tekshiradi.
    """
    begona = user_factory(username="begonaodam")
    mehmon = Client()
    kirgan = Client()
    kirgan.force_login(begona)

    yollar = ommaviy_yollar(
        muammo=yashirin_kontent["yashirin"], username=begona.username
    )
    assert len(yollar) >= 8, (
        f"Faqat {len(yollar)} yo'l topildi — test o'z ma'nosini yo'qotgan "
        "bo'lishi mumkin (URLconf o'zgarganmi?)"
    )

    sinalgan = 0
    for yol in yollar:
        for nom, mijoz in (("mehmon", mehmon), ("kirgan", kirgan)):
            javob = mijoz.get(yol)
            if javob.status_code == 405:
                continue  # faqat POST qabul qiladigan endpoint
            if javob.status_code >= 300:
                continue  # yo'naltirish yoki 404 — kontent chiqmaydi
            sinalgan += 1

            matn = javob.content.decode()
            for marker in (YASHIRIN_MUAMMO, YASHIRIN_YECHIM, OCHIRILGAN_MUAMMO):
                assert marker not in matn, (
                    f"KO'RINISH INVARIANTI BUZILDI: {marker} `{yol}` da "
                    f"({nom}) ko'rindi. `visible()` unutilganmi?"
                )

    assert sinalgan >= 6, f"Faqat {sinalgan} ta javob sinaldi — juda kam"


def test_yashirin_postning_OZ_MANZILI_begonaga_404(yashirin_kontent, user_factory):
    """Havolani biladigan odam ham ocha olmasligi kerak."""
    begona = user_factory()
    c = Client()
    c.force_login(begona)

    assert (
        Client().get(yashirin_kontent["yashirin"].get_absolute_url()).status_code == 404
    )
    assert c.get(yashirin_kontent["yashirin"].get_absolute_url()).status_code == 404


def test_MUALLIF_ozining_yashirin_postini_KORADI(yashirin_kontent):
    """⚠️ Bu invariantning ATAYLAB qilingan istisnosi.

    Posti yashirilgan foydalanuvchi buni BILISHI kerak — aks holda post
    "yo'qolgan" bo'lib ko'rinadi va ishonch yo'qoladi (D1-T10 da
    hujjatlashtirilgan).
    """
    c = Client()
    c.force_login(yashirin_kontent["egasi"])

    javob = c.get(yashirin_kontent["yashirin"].get_absolute_url())
    assert javob.status_code == 200
    assert "hozircha ko'rinmaydi" in javob.content.decode()


def test_STAFF_yashirin_postni_koradi(yashirin_kontent, staff):
    """Moderator qarorni ko'rib chiqishi kerak (D2-T2)."""
    c = Client()
    c.force_login(staff)
    assert c.get(yashirin_kontent["yashirin"].get_absolute_url()).status_code == 200


def test_ochiq_postdagi_YASHIRIN_YECHIM_korinmaydi(yashirin_kontent):
    """⚠️ Muammo ko'rinadi, LEKIN undagi yashirilgan yechim yo'q.

    Bu oson unutiladigan holat: post ochiq bo'lgani uchun sahifa
    ochiladi va yechimlar ro'yxatida filtr qo'yish esdan chiqadi.
    """
    matn = (
        Client()
        .get(yashirin_kontent["korinadigan"].get_absolute_url())
        .content.decode()
    )

    assert "Ochiq muammo" in matn
    assert YASHIRIN_YECHIM not in matn


def test_saqlanganlar_royxatida_ham_korinmaydi(yashirin_kontent, user):
    """Foydalanuvchi postni saqlagan, keyin u yashirilgan."""
    SavedComplaint.objects.create(user=user, complaint=yashirin_kontent["yashirin"])
    SavedComplaint.objects.create(user=user, complaint=yashirin_kontent["ochirilgan"])

    c = Client()
    c.force_login(user)
    matn = c.get(reverse("saqlanganlar")).content.decode()

    assert YASHIRIN_MUAMMO not in matn
    assert OCHIRILGAN_MUAMMO not in matn


def test_yon_panel_sanogida_ham_hisobga_olinadi(yashirin_kontent):
    """Sanoq ham "ko'rinadigan" ma'nosini saqlashi kerak: aks holda
    "Moliya 12" deydi, ochsangiz 9 ta chiqadi."""
    javob = Client().get("/")
    jami = sum(k.postlar_soni for k in javob.context["kategoriyalar"])

    # Faqat bitta ko'rinadigan muammo bor (yashirin va o'chirilgan sanalmaydi)
    assert jami == 1


# ===========================================================================
# 2. Manba kodidagi guard — kelajakdagi kod uchun
# ===========================================================================
# ⚠️ ISTISNO BELGISI: ataylab `visible()` siz ishlatilgan joyga shu izoh
#    qo'yiladi. Maqsad — istisnoni TAQIQLASH emas, uni KO'RINADIGAN va
#    IZOHLANGAN qilish. Sababsiz istisno qo'shib bo'lmaydi.
ISTISNO_BELGISI = "korinish-istisno"

# Skanerdan tashqarida qoladigan fayllar (har biri sabab bilan).
SKANER_ISTISNOLARI = {
    # Admin — moderator interfeysi, u yashirilgan kontentni KO'RSATISHI
    # kerak. Himoyasi `visible()` emas, staff huquqi (D2-T2).
    "admin.py",
}


def _manba_fayllari():
    ildiz = pathlib.Path(settings.BASE_DIR) / "apps"
    for yol in ildiz.rglob("*.py"):
        nisbiy = yol.relative_to(ildiz).as_posix()
        if "/tests/" in f"/{nisbiy}" or "migrations/" in nisbiy:
            continue
        if yol.name.startswith(("test_", "tests")) or yol.name in (
            "factories.py",
            *SKANER_ISTISNOLARI,
        ):
            continue
        yield yol


def test_manba_kodida_visible_SIZ_sorov_YOQ():
    """⚠️ Qabul mezoni: "`visible()` manager metodi yagona kirish nuqtasi".

    `Complaint.objects` yoki `Solution.objects` ishlatilgan HAR BIR
    ifodada `visible()` bo'lishi yoki `# korinish-istisno: <sabab>`
    izohi turishi shart.

    Nega ish vaqtidagi test yetarli emas: u faqat MAVJUD yo'llarni
    tekshiradi. Yangi `selectors` funksiyasi yozilib, hali ko'rinishga
    ulanmagan bo'lsa — u qamrab olinmaydi va bir kuni sitemap yoki
    API'ga ulanadi.
    """
    NAZORATDAGI = {"Complaint", "Solution"}
    MENEJERLAR = {"objects", "all_objects"}

    buzuqlar: list[str] = []

    for yol in _manba_fayllari():
        manba = yol.read_text(encoding="utf-8")
        daraxt = ast.parse(manba)
        qatorlar = manba.splitlines()

        # ⚠️ AST bo'yicha ANIQ tugun tekshiruvi, SATR QIDIRISH emas.
        #    `"Complaint.objects" in matn` `SavedComplaint.objects` ni ham
        #    ushlaydi (qism satr). Guardda yolg'on ogohlantirish eng
        #    zararli nuqson: odam unga ko'nikadi va bir kuni haqiqiysini
        #    ham e'tiborsiz qoldiradi. Bu testning birinchi versiyasida
        #    aynan shu bo'lgan edi.
        ota: dict[ast.AST, ast.AST] = {}
        for tugun in ast.walk(daraxt):
            for bola in ast.iter_child_nodes(tugun):
                ota[bola] = tugun

        for tugun in ast.walk(daraxt):
            if not (
                isinstance(tugun, ast.Attribute)
                and tugun.attr in MENEJERLAR
                and isinstance(tugun.value, ast.Name)
                and tugun.value.id in NAZORATDAGI
            ):
                continue

            # Eng yaqin ifodani (statement) topamiz — kontekst shu.
            ifoda: ast.AST | None = tugun
            while ifoda is not None and not isinstance(ifoda, ast.stmt):
                ifoda = ota.get(ifoda)
            if ifoda is None:
                continue

            parcha = ast.get_source_segment(manba, ifoda) or ""
            if "visible()" in parcha:
                continue

            # Istisno izohi: ifodaning o'zida yoki undan oldingi 12 qatorda
            boshi = max(0, (ifoda.lineno or 1) - 13)
            oxiri = ifoda.end_lineno or ifoda.lineno or 1
            atrof = "\n".join(qatorlar[boshi:oxiri])
            if ISTISNO_BELGISI in atrof:
                continue

            birinchi_qator = (parcha.splitlines() or [""])[0].strip()
            buzuqlar.append(f"{yol.name}:{tugun.lineno}  {birinchi_qator[:70]}")

    assert buzuqlar == [], (
        "KO'RINISH INVARIANTI: `visible()` siz so'rov topildi.\n  "
        + "\n  ".join(buzuqlar)
        + f"\n\nAgar bu ATAYLAB bo'lsa, ifodaga `# {ISTISNO_BELGISI}: <sabab>` "
        "izohini qo'ying — istisno ko'rinadigan va izohlangan bo'lsin."
    )
