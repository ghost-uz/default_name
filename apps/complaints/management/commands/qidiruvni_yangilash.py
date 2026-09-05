"""Qidiruv ustunlarini normallashtirish qoidalari bo'yicha qayta quradi (D4-T1).

⚠️ NEGA MIGRATSIYA EMAS, BUYRUQ
   `qidiruv_sarlavha` / `qidiruv_tavsif` — SAQLANGAN qiymat. Ya'ni
   `apps/common/matn.py::qidiruv_uchun()` o'zgarganda eski yozuvlar ESKI
   qoidalar bilan normallashtirilgan holda qolaveradi va buni hech narsa
   bildirmaydi: xato chiqmaydi, natija shunchaki topilmaydi.

   Har o'zgarish uchun yangi migratsiya yozish mumkin edi, lekin u ikki
   sababdan yomonroq: (1) migratsiya bir marta ishlaydi va uni qayta
   ishga tushirib bo'lmaydi, (2) migratsiya ichida ilova kodiga tayanish
   vaqt o'tishi bilan buziladi — kod o'zgaradi, migratsiya esa muzlagan
   tarixni tasvirlashi kerak.

   Buyruq esa istalgan payt qayta ishlaydi va HOZIRGI kodni ishlatadi.

⚠️ D4-T2 (transliteratsiya) shu buyruq bilan yopiladi — o'shanda
   normallashtirish qoidalari o'zgaradi va butun baza qayta indekslanadi.

Ishlatilishi:
    python manage.py qidiruvni_yangilash            # yozadi
    python manage.py qidiruvni_yangilash --tekshir  # faqat sanaydi
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.common.matn import qidiruv_uchun
from apps.complaints.models import Complaint

STANDART_PARTIYA = 500


class Command(BaseCommand):
    help = "Qidiruv matni ustunlarini hozirgi normallashtirish qoidalari bilan qayta quradi."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--partiya",
            type=int,
            default=STANDART_PARTIYA,
            help=f"Bir marta yoziladigan yozuvlar soni (standart {STANDART_PARTIYA}).",
        )
        parser.add_argument(
            "--tekshir",
            action="store_true",
            help="Hech narsa yozmaydi — faqat eskirgan yozuvlarni sanaydi.",
        )

    def handle(self, *args, **sozlamalar) -> None:
        partiya_hajmi: int = sozlamalar["partiya"]
        faqat_tekshir: bool = sozlamalar["tekshir"]

        # ⚠️ `all_objects`: yumshoq o'chirilgan va yashirilgan yozuvlar HAM
        #    qayta indekslanadi. Tiklangan post (D2-T2) qidiruvda darhol
        #    paydo bo'lishi kerak — buning uchun uni qayta saqlash talab
        #    qilinmasin.
        # korinish-istisno: bu indeks ta'mirlash ishi, kontent
        # ko'rsatilmaydi. Ko'rinish filtri qidiruv SO'ROVIDA qo'llanadi
        # (`selectors.qidiruv_queryset`), indeksda emas.
        queryset = Complaint.all_objects.order_by("pk")

        jami = 0
        eskirgan = 0
        partiya: list[Complaint] = []

        for muammo in queryset.iterator(chunk_size=partiya_hajmi):
            jami += 1
            sarlavha = qidiruv_uchun(muammo.title)
            tavsif = qidiruv_uchun(muammo.description)

            if sarlavha == muammo.qidiruv_sarlavha and tavsif == muammo.qidiruv_tavsif:
                continue

            eskirgan += 1
            if faqat_tekshir:
                continue

            muammo.qidiruv_sarlavha = sarlavha
            muammo.qidiruv_tavsif = tavsif
            partiya.append(muammo)

            if len(partiya) >= partiya_hajmi:
                self._yozish(partiya)
                partiya.clear()

        if partiya:
            self._yozish(partiya)

        if faqat_tekshir:
            xabar = f"Tekshirildi: {jami} ta yozuv, {eskirgan} tasi eskirgan."
            uslub = self.style.WARNING if eskirgan else self.style.SUCCESS
        else:
            xabar = f"Ko'rildi: {jami} ta yozuv, {eskirgan} tasi yangilandi."
            uslub = self.style.SUCCESS

        self.stdout.write(uslub(xabar))

    @staticmethod
    def _yozish(partiya: list[Complaint]) -> None:
        """⚠️ `bulk_update` — `save()` ni CHETLAB O'TADI va bu ATAYLAB.

        `save()` chaqirilsa u matnni yana normallashtirardi (biz endigina
        qilgan ishni), `updated_at` ni yangilardi (kontent o'zgarmagan!)
        va har yozuv uchun alohida so'rov ketardi.

        `search_vector` esa GENERATED ustun — uni PostgreSQL o'zi qayta
        hisoblaydi, ya'ni bu yerda unutish MUMKIN EMAS.
        """
        with transaction.atomic():
            # korinish-istisno: indeks ta'mirlash — yozuvlar hech qayerda
            # KO'RSATILMAYDI, faqat qidiruv ustunlari qayta yoziladi.
            # Yashirilgan va o'chirilgan yozuvlar ham to'g'ri indekslangan
            # bo'lishi kerak: tiklangandan keyin ular qidiruvda darhol
            # paydo bo'lsin (ko'rinish filtri SO'ROVDA qo'llanadi).
            Complaint.all_objects.bulk_update(
                partiya, ["qidiruv_sarlavha", "qidiruv_tavsif"]
            )
