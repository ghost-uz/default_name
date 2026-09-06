"""Schema.org QAPage — JSON-LD strukturaviy ma'lumoti (D4-T6).

⚠️ NEGA BU M4 DAGI ENG YUQORI DAROMADLI ISH
   Savol-javob sayti uchun Google natijada javobning O'ZINI ko'rsatishi
   mumkin (ovoz soni bilan birga). Ya'ni sahifa qidiruv natijasida
   boshqa havolalardan ko'ra ko'proq joy egallaydi va bosilish darajasi
   sezilarli oshadi. Buning yagona sharti — sahifada to'g'ri
   strukturaviy ma'lumot bo'lishi.

⚠️⚠️ JAVOBSIZ SAVOLGA QAPage YOZILMAYDI
   Google `QAPage` uchun kamida bitta javob kutadi: `acceptedAnswer`
   yoki `suggestedAnswer`. Javobsiz savolda ular bo'lmaydi va Rich
   Results Test XATO beradi — D4-T6 qabul mezoni esa aynan "xatosiz
   o'tadi" deydi.

   Shuning uchun javob bo'lmasa JSON-LD UMUMAN chiqarilmaydi. Sahifa
   baribir indekslanadi (kanonik va OG metalari joyida), faqat boyitilgan
   natija bo'lmaydi — javob paydo bo'lgan zahoti u ham paydo bo'ladi.

⚠️⚠️ ANONIMLIK: `author` FAQAT `public_author` DAN
   Anonim postda muallif maydoni UMUMAN chiqarilmaydi. Bu D1-T6
   invariantining uchinchi joyi (shablon, OG metalari, endi JSON-LD) —
   va eng oson unutiladigani, chunki JSON-LD sahifada KO'RINMAYDI.

⚠️⚠️ KO'RINISH INVARIANTI: yechimlar ro'yxati `complaint_detail` dan
   keladi (u `ozi_korinadigan()` dan o'tgan). Bu modul o'zi so'rov
   QILMAYDI — aks holda yashirilgan yechim JSON-LD orqali Google'ga
   tushib ketardi va uni sahifada hech kim ko'rmasdi.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from django.http import HttpRequest
from django.utils.safestring import SafeString, mark_safe

from .models import Complaint

# ⚠️ Django'ning `json_script` filtri aynan shu jadvalni ishlatadi.
#    Sabab: `</script>` ketma-ketligi JSON ichida bo'lsa ham brauzer
#    skript blokini SHU YERDA tugatadi va qolgan matn HTML bo'lib
#    o'qiladi — ya'ni foydalanuvchi yozgan matn orqali teg kiritish
#    mumkin bo'lardi. `<`, `>` va `&` ni kodlash buni butunlay yopadi.
#
#    Django'ning tayyor `json_script` filtri ishlatilmadi: u `<script>`
#    tegini O'ZI yasaydi va turini `application/json` qilib qotiradi,
#    bizga esa `application/ld+json` kerak.
JSON_QOCHISH = {
    ord(">"): "\\u003E",
    ord("<"): "\\u003C",
    ord("&"): "\\u0026",
}


def _javob(yechim, *, muammo_url: str) -> dict[str, Any]:
    """Bitta yechim -> schema.org `Answer`.

    ⚠️⚠️ `muammo_url` TASHQARIDAN BERILADI, `yechim.complaint` DAN OLINMAYDI.

       Birinchi versiyada shunday yozilgandi va D1-T14 ning N+1 qo'riqchisi
       darhol yiqildi: `complaint_detail` yechimlarni
       `.select_related("author")` bilan oladi — `complaint` unda YO'Q,
       chunki u ilgari hech qayerda kerak bo'lmagan. Natijada HAR yechim
       uchun bitta qo'shimcha so'rov ketardi.

       Eng muhimi: bu regressiya BUTUNLAY BOSHQA MAVZUDAGI (SEO)
       o'zgarishdan keldi. `select_related` ga `complaint` qo'shish ham
       yechim edi, lekin u kerak bo'lmagan JOIN'ni har detal sahifasiga
       qo'shardi — muammo esa allaqachon qo'limizda turibdi.
    """
    javob: dict[str, Any] = {
        "@type": "Answer",
        "text": yechim.content,
        # ⚠️ Langar bilan — Google javobga TO'G'RIDAN-TO'G'RI olib boradi.
        #    Langar `templates/components/_solution.html` da
        #    (`id="yechim-<pk>"`); ikkalasi bir-biriga bog'liq va buni
        #    test qotiradi.
        "url": f"{muammo_url}#yechim-{yechim.pk}",
        # ⚠️ `upvoteCount` — Google buni natijada KO'RSATADI. Manba
        #    `score_cached` (GENERATED ustun), ya'ni u sanoqchilardan
        #    farq qila olmaydi.
        "upvoteCount": max(0, yechim.score_cached),
        "dateCreated": yechim.created_at.isoformat(),
    }

    # ⚠️ ANONIMLIK: `public_author` anonim yechimda `None` qaytaradi
    #    va o'shanda maydon UMUMAN qo'shilmaydi (bo'sh nom emas).
    muallif = yechim.public_author
    if muallif is not None:
        javob["author"] = {"@type": "Person", "name": muallif.display_name}

    return javob


def qapage_json(
    *, muammo: Complaint, yechimlar: Sequence[Any], request: HttpRequest
) -> SafeString | None:
    """QAPage JSON-LD — javob bo'lmasa `None`.

    ⚠️ `yechimlar` TASHQARIDAN beriladi (`complaint_detail` dan) va bu
       ataylab: ro'yxat allaqachon ko'rinish filtridan o'tgan. Bu modul
       o'zi so'rov qilsa, filtr ikkinchi marta yozilardi — va bir kuni
       ular bir-biridan farq qilardi.
    """
    if not yechimlar:
        return None

    # ⚠️ BIR MARTA hisoblanadi va barcha javoblarga beriladi (yuqoridagi
    #    N+1 izohiga qarang).
    muammo_url = request.build_absolute_uri(muammo.get_absolute_url())

    qabul_qilingan = [y for y in yechimlar if y.is_accepted]
    boshqalar = [y for y in yechimlar if not y.is_accepted]

    savol: dict[str, Any] = {
        "@type": "Question",
        "name": muammo.title,
        "text": muammo.description,
        "answerCount": len(yechimlar),
        "upvoteCount": max(0, muammo.score_cached),
        "dateCreated": muammo.created_at.isoformat(),
    }

    muallif = muammo.public_author
    if muallif is not None:
        savol["author"] = {"@type": "Person", "name": muallif.display_name}

    if qabul_qilingan:
        # ⚠️ `accepted_solution` bitta bo'lishi BAZA darajasida
        #    kafolatlangan (D1-T4), lekin bu yerda ro'yxatdan
        #    olinayotgani uchun birinchisini olamiz — schema.org ham
        #    bitta `acceptedAnswer` kutadi.
        savol["acceptedAnswer"] = _javob(qabul_qilingan[0], muammo_url=muammo_url)
    if boshqalar:
        savol["suggestedAnswer"] = [_javob(y, muammo_url=muammo_url) for y in boshqalar]

    hujjat = {
        "@context": "https://schema.org",
        "@type": "QAPage",
        "mainEntity": savol,
    }

    xom = json.dumps(hujjat, ensure_ascii=False, separators=(",", ":"))
    # ⚠️ `mark_safe` XAVFSIZ: `JSON_QOCHISH` `<`, `>` va `&` ni kodlaydi,
    #    ya'ni foydalanuvchi matni skript blokidan chiqa olmaydi.
    return mark_safe(xom.translate(JSON_QOCHISH))  # noqa: S308
