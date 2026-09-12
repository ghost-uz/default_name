"""Ovoz endpoint'iga yuk testi (D7-T5): `manage.py ovoz_yuk_testi`.

Misollar:

    manage.py ovoz_yuk_testi                         # 1000 odam, 50 ishchi
    manage.py ovoz_yuk_testi --ovozlar 3000 --parallel 70
    manage.py ovoz_yuk_testi --ip-soni 5             # CGNAT: 5 ta IP ortida

⚠️⚠️ `DEBUG` O'CHIQ MUHITDA RUXSATSIZ ISHLAMAYDI. Buyruq vaqtinchalik post
   va minglab odam yaratadi, post esa test davomida lentada KO'RINADI.
   Prod nusxasida ishlatish ongli qaror bo'lsin: `--prod-ham`.

⚠️ Butunlik buzilsa (5xx, istisno, sanoq yoki biror odamning ovozi
   kutilganidan farq qilsa) 1 kodi bilan chiqadi. 429 — xato EMAS:
   tezlik cheklovi o'z ishini qilgan.

Mantiq va qarorlar: `apps/complaints/yuk_testi.py`.
"""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.complaints.yuk_testi import hisobot, ovoz_yuki


class Command(BaseCommand):
    help = "Ovoz endpoint'iga yuk testi — viral post stsenariysi (D7-T5)."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--ovozlar", type=int, default=1000, help="Nechta odam ovoz beradi."
        )
        parser.add_argument(
            "--parallel", type=int, default=50, help="Bir vaqtda ishlaydigan ishchilar."
        )
        parser.add_argument(
            "--minus-har",
            type=int,
            default=5,
            help="Har N-odam minus bosadi (0 — hech kim).",
        )
        parser.add_argument(
            "--qayta-har",
            type=int,
            default=20,
            help="Har N-odam tugmani bir vaqtda IKKI marta bosadi (0 — hech kim).",
        )
        parser.add_argument(
            "--ip-soni",
            type=int,
            default=None,
            help="Odamlar shuncha IP orasida bo'linadi (CGNAT). "
            "Berilmasa — har odamga alohida IP.",
        )
        parser.add_argument(
            "--saqla",
            action="store_true",
            help="Vaqtinchalik post va odamlarni O'CHIRMAYDI (tahlil uchun).",
        )
        parser.add_argument(
            "--prod-ham",
            action="store_true",
            help="DEBUG o'chiq muhitda ham ishga tushiradi.",
        )

    def handle(self, *args, **opts) -> None:
        if not settings.DEBUG and not opts["prod_ham"]:
            raise CommandError(
                "DEBUG o'chiq. Buyruq vaqtinchalik post va odamlar yaratadi va "
                "post test davomida lentada ko'rinadi. Ongli bo'lsa --prod-ham bering."
            )

        try:
            natija = ovoz_yuki(
                ovozlar=opts["ovozlar"],
                parallel=opts["parallel"],
                minus_har=opts["minus_har"],
                qayta_har=opts["qayta_har"],
                ip_soni=opts["ip_soni"],
                saqlash=opts["saqla"],
            )
        except ValueError as xato:
            raise CommandError(str(xato)) from xato

        self.stdout.write(hisobot(natija))
        if opts["saqla"]:
            self.stdout.write(
                f"\nSaqlandi: post #{natija.muammo_pk}, odamlar '{natija.prefiks}*'."
            )

        if not natija.muvaffaqiyatli:
            raise CommandError("BUTUNLIK BUZILDI — yuqoridagi jadvalga qarang.")
