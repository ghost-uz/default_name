"""⚠️ PRO invarianti: `user.has_pro` YAGONA kirish nuqtasi (D6-T1).

Task `nega` bo'limi: «PRO tekshiruvi kod bo'ylab tarqalsa, muddati
tugagan obuna qayerdadir ishlab qolaveradi».

Ish vaqtidagi test buni to'liq ushlay olmaydi: u faqat MAVJUD yo'llarni
qamraydi. Yangi xizmat yozilib, hali ko'rinishga ulanmagan bo'lsa —
u tekshirilmaydi va bir kuni to'lov devorining teshigiga aylanadi.
Shuning uchun manba kodi ham skanerlanadi (D2-T3 va D2-T7 guard'lari
bilan bir xil naqsh).
"""

from __future__ import annotations

import ast
import pathlib

from django.conf import settings

# Obuna ichki tafsilotlari — bu nomlarni `apps/payments/` DAN TASHQARIDA
# ishlatish "PRO ni o'zim hisoblayapman" degani.
TAQIQLANGAN_NOMLAR = {"expires_at", "pro_until", "auto_renew"}

# Ataylab qilingan istisnoga izoh qo'yiladi — ko'rinadigan va izohlangan
# bo'lsin (D2-T3 dagi `korinish-istisno` bilan bir xil mexanizm).
ISTISNO_BELGISI = "pro-istisno"

# `apps/payments/` — invariantning O'Z uyi; u yerda hisoblash TO'G'RI.
OZ_UYI = "payments/"


def _manba_fayllari():
    ildiz = pathlib.Path(settings.BASE_DIR) / "apps"
    for yol in ildiz.rglob("*.py"):
        nisbiy = yol.relative_to(ildiz).as_posix()
        if "migrations/" in nisbiy or nisbiy.startswith(OZ_UYI):
            continue
        if "/tests/" in f"/{nisbiy}":
            continue
        if yol.name.startswith(("test_", "tests")) or yol.name == "factories.py":
            continue
        yield yol, nisbiy


def test_manba_kodida_PRO_ni_QOLDA_hisoblash_YOQ():
    """⚠️⚠️ `apps/payments/` dan tashqarida obuna maydonlariga tegilmaydi.

    Bu guard ATAYLAB buzib tekshirilgan: `apps/accounts/models.py` ga
    `self.obuna.expires_at > timezone.now()` qo'yilganda yiqiladi.
    """
    buzuqlar: list[str] = []

    for yol, nisbiy in _manba_fayllari():
        manba = yol.read_text(encoding="utf-8")
        daraxt = ast.parse(manba)
        qatorlar = manba.splitlines()

        ota: dict[ast.AST, ast.AST] = {}
        for tugun in ast.walk(daraxt):
            for bola in ast.iter_child_nodes(tugun):
                ota[bola] = tugun

        for tugun in ast.walk(daraxt):
            # ⚠️ ANIQ atribut tuguni, SATR QIDIRISH emas: `"expires_at" in
            #    matn` docstring va izohlarni ham ushlab, yolg'on
            #    ogohlantirish berardi. Guardda yolg'on ogohlantirish eng
            #    zararli nuqson — odam unga ko'nikadi.
            if not (
                isinstance(tugun, ast.Attribute) and tugun.attr in TAQIQLANGAN_NOMLAR
            ):
                continue

            ifoda: ast.AST | None = tugun
            while ifoda is not None and not isinstance(ifoda, ast.stmt):
                ifoda = ota.get(ifoda)
            if ifoda is None:
                continue

            boshi = max(0, (ifoda.lineno or 1) - 13)
            oxiri = ifoda.end_lineno or ifoda.lineno or 1
            atrof = "\n".join(qatorlar[boshi:oxiri])
            if ISTISNO_BELGISI in atrof:
                continue

            parcha = ast.get_source_segment(manba, ifoda) or ""
            birinchi = (parcha.splitlines() or [""])[0].strip()
            buzuqlar.append(f"{nisbiy}:{tugun.lineno}  {birinchi}")

    assert buzuqlar == [], (
        "PRO INVARIANTI: obuna maydoni `apps/payments/` dan tashqarida "
        "ishlatilgan.\n    " + "\n    ".join(buzuqlar) + "\n\n"
        "  `user.has_pro` ni ishlating. Ataylab bo'lsa ifodaga "
        f"`# {ISTISNO_BELGISI}: <sabab>` izohini qo'ying."
    )
