"""D0-T6 tuzatishi: HTML izohlari ichidagi shablon sintaksisi.

⚠️ MUAMMO
   Django shablon tahlilchisi HTML izohini KO'RMAYDI. `<!-- ... -->` ichida
   yozilgan `{% url %}` yoki `{% if %}` baribir bajariladi:

       <!-- Django: {% url 'vote' c.pk %} -->   -> NoReverseMatch
       <!-- {% if user == author %} -->         -> yopilmagan blok

   Yechim: bunday izohlar `{% comment %}` ichiga olinadi — u o'zidan
   keyingi hamma narsani `{% endcomment %}` gacha TAHLIL QILMASDAN
   o'tkazib yuboradi.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TPL = ROOT / "templates"

# Ko'p qatorli HTML izohlari
IZOH_RE = re.compile(r"<!--(.*?)-->", re.DOTALL)


def tuzat(matn: str) -> tuple[str, int]:
    sanoq = 0

    def almashtir(m: re.Match) -> str:
        nonlocal sanoq
        ichi = m.group(1)
        if "{%" not in ichi and "{{" not in ichi:
            return m.group(0)  # oddiy izoh — tegilmaydi
        sanoq += 1
        return "{% comment %}" + ichi + "{% endcomment %}"

    return IZOH_RE.sub(almashtir, matn), sanoq


def main() -> None:
    jami = 0
    for yol in sorted(TPL.rglob("*.html")):
        matn = yol.read_text(encoding="utf-8")
        yangi, sanoq = tuzat(matn)
        if sanoq:
            yol.write_text(yangi, encoding="utf-8")
            print(f"  {yol.relative_to(TPL)}: {sanoq} ta izoh")
            jami += sanoq
    print(f"\nJami {jami} ta izoh tuzatildi.")


if __name__ == "__main__":
    main()
