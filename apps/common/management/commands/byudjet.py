"""Ish faoliyati byudjeti hisoboti (D7-T4).

⚠️⚠️ BU BUYRUQ HECH QACHON YIQITMAYDI (`--qatiy` berilmasa).
   Qat'iy tekshiruv `apps/common/tests/test_byudjet.py` da va u
   deterministik o'lchamlarni ushlaydi. Bu buyruq esa VAQTNI ham
   o'lchaydi — u runner yukiga bog'liq va uni qat'iy chegara qilish
   CI'ni yolg'on yiqitardi.

⚠️⚠️ BU BUYRUQ CI'DA ISHLATILMAYDI — ATAYLAB.
   CI'dagi baza faqat migratsiyalardan iborat va BO'SH: u yerdagi
   o'lchov «2 ta so'rov, 24 KB» kabi ma'nosiz raqamlar berardi va
   byudjet hech qachon hech narsani ushlamasdi.

   CI'da byudjetni `apps/common/tests/test_byudjet.py` tekshiradi —
   u realistik ma'lumot yaratadi. Bu buyruq esa DASTURCHI vositasi:
   HAQIQIY ma'lumot ustida (dev yoki prod nusxasi) byudjet qanday
   turganini ko'rish uchun.
"""

from __future__ import annotations

import time

from django.core.management.base import BaseCommand
from django.test import Client
from django.test.utils import CaptureQueriesContext, override_settings

from apps.common.byudjet import AKTIVLAR, RENDER_MS, SAHIFALAR, aktiv_hajmi


class Command(BaseCommand):
    help = "Ish faoliyati byudjeti bo'yicha hisobot (D7-T4)."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--github",
            action="store_true",
            help="GitHub Actions uchun ::warning:: va bosqich xulosasi.",
        )
        parser.add_argument(
            "--qatiy",
            action="store_true",
            help="Ogohlantirish bo'lsa 1 kodi bilan chiqadi (ATAYLAB standart EMAS).",
        )

    def handle(self, *args, **opts) -> None:
        ogohlar: list[str] = []
        qatorlar: list[str] = []

        from django.db import connection

        # ⚠️ `ALLOWED_HOSTS` — `Client` `testserver` nomidan so'raydi.
        with override_settings(ALLOWED_HOSTS=["*"]):
            for sahifa in SAHIFALAR:
                if "{slug}" in sahifa.yol:
                    # ⚠️ Dinamik sahifa uchun HAQIQIY post kerak; bo'sh
                    #    bazada uni o'lchash ma'nosiz.
                    manzil = self._birinchi_dard(sahifa)
                    if manzil is None:
                        qatorlar.append(f"| {sahifa.nom} | — | — | — | post yo'q |")
                        continue
                else:
                    manzil = sahifa.yol

                mijoz = Client()
                if sahifa.kirgan:
                    # ⚠️ `kirgan` sahifani mehmon sifatida o'lchash
                    #    YOLG'ON raqam berardi: ovozlar, saqlanganlar va
                    #    bloklanganlar so'rovlari umuman ketmasdi.
                    kim = self._birinchi_foydalanuvchi()
                    if kim is None:
                        qatorlar.append(
                            f"| {sahifa.nom} | — | — | — | foydalanuvchi yo'q |"
                        )
                        continue
                    mijoz.force_login(kim)
                mijoz.get(manzil)  # keshni ilitamiz

                boshi = time.perf_counter()
                with CaptureQueriesContext(connection) as sorovlar:
                    javob = mijoz.get(manzil)
                ms = (time.perf_counter() - boshi) * 1000

                hajm = len(javob.content)
                belgi = []
                if len(sorovlar) > sahifa.sorovlar:
                    belgi.append("so'rov")
                if hajm > sahifa.bayt:
                    belgi.append("hajm")
                if ms > RENDER_MS:
                    belgi.append("vaqt")
                    ogohlar.append(
                        f"{sahifa.nom}: render {ms:.0f} ms (chegara {RENDER_MS} ms)"
                    )

                qatorlar.append(
                    f"| {sahifa.nom} | {len(sorovlar)}/{sahifa.sorovlar} "
                    f"| {hajm:,}/{sahifa.bayt:,} | {ms:.0f} ms "
                    f"| {' '.join(belgi) or 'ok'} |"
                )

        for nisbiy, chegara in AKTIVLAR:
            # ⚠️ Nom `hajm` DAN FARQLI: yuqoridagi sikl `hajm` ni `int`
            #    deb belgilagan va uni `int | None` bilan qayta
            #    ishlatish mypy xatosi berardi.
            aktiv = aktiv_hajmi(nisbiy)
            if aktiv is None:
                qatorlar.append(f"| {nisbiy} | — | — | — | qurilmagan |")
                continue
            holat = "ok" if aktiv <= chegara else "OSHDI"
            qatorlar.append(f"| {nisbiy} | — | {aktiv:,}/{chegara:,} | — | {holat} |")

        sarlavha = "| sahifa | so'rov | bayt | render | holat |\n|---|---|---|---|---|"
        jadval = sarlavha + "\n" + "\n".join(qatorlar)
        self.stdout.write(jadval)

        if opts["github"]:
            self._github(jadval, ogohlar)

        if ogohlar and opts["qatiy"]:
            raise SystemExit(1)

    def _birinchi_foydalanuvchi(self):
        from django.contrib.auth import get_user_model

        return get_user_model().objects.filter(is_active=True).first()

    def _birinchi_dard(self, sahifa) -> str | None:
        from apps.complaints.models import Complaint

        muammo = Complaint.objects.visible().order_by("-id").first()
        return None if muammo is None else sahifa.manzil(slug=muammo.slug)

    def _github(self, jadval: str, ogohlar: list[str]) -> None:
        """GitHub Actions bosqich xulosasi va ogohlantirishlari."""
        import os
        import pathlib

        xulosa = os.environ.get("GITHUB_STEP_SUMMARY")
        if xulosa:
            with pathlib.Path(xulosa).open("a", encoding="utf-8") as f:
                f.write("### Ish faoliyati byudjeti (D7-T4)\n\n")
                f.write(jadval + "\n")

        for ogoh in ogohlar:
            # ⚠️ `::warning::` — CI'ni YIQITMAYDI, lekin PR'da ko'rinadi.
            self.stdout.write(f"::warning title=Byudjet::{ogoh}")
