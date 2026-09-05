"""Standart Open Graph rasmini yasaydi (D4-T4).

⚠️ NEGA BUYRUQ, QO'LDA CHIZILGAN RASM EMAS
   Standart rasm brend elementlarini (rang, shrift, yozuv) muammo
   kartalari bilan BIR XIL saqlashi kerak. Alohida chizilgan fayl bir
   kuni ulardan uzoqlashardi: palitra o'zgaradi, kartalar yangilanadi,
   standart rasm esa eski ranglar bilan qolaveradi.

   Bu yerda esa aynan `apps/common/og.py` ishlatiladi — ya'ni farq
   qilishning imkoni yo'q.

⚠️ NATIJA REPOGA QO'SHILADI (`static/img/og-default.png`), chunki u
   `collectstatic` ga tushishi kerak va qurilish paytida Pillow
   ishlashiga tayanmaymiz.

Ishlatilishi (brend o'zgarganda):
    python manage.py og_standart
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.common.og import og_rasm_yasash

CHIQISH = Path("static") / "img" / "og-default.png"

# ⚠️ Kategoriya BO'SH: standart rasm butun sayt uchun (bosh sahifa,
#    profil, huquqiy sahifalar) va ularning "kategoriyasi" yo'q.
SARLAVHA = "Hayotiy muammolarga real yechimlar"


class Command(BaseCommand):
    help = "Standart OG rasmini yasaydi (static/img/og-default.png)."

    def handle(self, *args, **sozlamalar) -> None:
        yol = Path(settings.BASE_DIR) / CHIQISH
        yol.parent.mkdir(parents=True, exist_ok=True)

        baytlar = og_rasm_yasash(sarlavha=SARLAVHA, kategoriya="")
        yol.write_bytes(baytlar)

        self.stdout.write(
            self.style.SUCCESS(f"{CHIQISH.as_posix()} yasaldi ({len(baytlar)} bayt)")
        )
