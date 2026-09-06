"""Bildirishnomalar — modellar (D5-T1).

⚠️ NEGA ICHKI MARKAZ KERAK, TELEGRAM YETARLI EMAS
   Telegram bildirishnomasi (D5-T2) tezroq va ko'proq ochiladi, lekin
   unga TAYANIB BO'LMAYDI: foydalanuvchi botni bloklashi, Telegram'dan
   umuman chiqib ketishi yoki hisobini boshqa raqamga ko'chirishi
   mumkin. O'shanda u yechim kelganini HECH QACHON bilmaydi.

   Ichki markaz — zaxira kanal: u har doim shu yerda va uni bloklab
   bo'lmaydi.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.urls import reverse

from apps.common.models import TimeStampedModel


class BildirishnomaTuri(models.TextChoices):
    """Bildirishnoma turi.

    ⚠️ QIYMATLAR BAZAGA YOZILADI — o'zgartirilsa migratsiya kerak
       (D2-T6 dagi `AuditAction` bilan bir xil tuzoq: Django `choices`
       o'zgarishini kuzatadi).

    ⚠️ Yangi tur qo'shish ARZON: qiymat, yorliq va
       `Notification.matn` dagi bitta qator. Turlar ATAYLAB kam —
       har biri foydalanuvchining e'tiborini talab qiladi va ortiqcha
       bildirishnoma botdan chiqib ketishga olib keladi (D5-T4).
    """

    YANGI_YECHIM = "yangi_yechim", "Muammoingizga yechim yozildi"
    YECHIM_QABUL = "yechim_qabul", "Yechimingiz qabul qilindi"
    # ⚠️ Ekspertlarga haftalik dayjest (D5-T5). U BITTA muammoga
    #    tegishli emas — `complaint` da ro'yxatning BIRINCHI (eng uzoq
    #    kutgan) savoli turadi va u faqat KATEGORIYANI aniqlash uchun
    #    kerak. To'liq ro'yxat Telegram xabarida va lentada.
    DAYJEST = "dayjest", "Sohangizdagi javobsiz savollar"


class Notification(TimeStampedModel):
    """Bitta foydalanuvchiga bitta bildirishnoma.

    ⚠️⚠️ ANONIMLIK: ANONIM MANBADA `actor` UMUMAN YOZILMAYDI.

       "Ismni ko'rsatmaymiz" degan yondashuv (yozib qo'yib, shablonda
       yashirish) bu loyihada allaqachon uch marta muammo bo'lgan
       (D1-T6, OG metalari, JSON-LD). Bu yerda esa yozuvning O'ZI
       bazada qoladi va uni admin, eksport (D2-T8) yoki kelajakdagi
       API oshkor qilishi mumkin.

       Shuning uchun qoida qattiqroq: anonim yechim uchun
       `actor=None`. Bildirishnoma "Kimdir yechim yozdi" deydi va
       bu — TO'G'RI matn.

    ⚠️ `target` UCHUN `ContentType` ISHLATILMADI (ochiq qaror Q1 bilan
       izchil — `ComplaintVote` / `SavedComplaint` da ham shunday).
       Aniq FK'lar baza darajasida butunlikni beradi: kontent
       o'chirilsa bildirishnoma ham ketadi va yetim yozuv qolmaydi.
    """

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="kimga",
        on_delete=models.CASCADE,
        related_name="bildirishnomalar",
    )

    # ⚠️ SET_NULL: bildirishnoma matni aktyorsiz ham ma'noli
    #    ("Yechimingiz qabul qilindi"). CASCADE bo'lsa hisobini
    #    o'chirgan odam boshqalarning tarixini ham olib ketardi.
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="kim",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Anonim manbada BO'SH — sabab model docstring'ida.",
    )

    turi = models.CharField(
        "turi", max_length=20, choices=BildirishnomaTuri.choices, db_index=True
    )

    complaint = models.ForeignKey(
        "complaints.Complaint",
        verbose_name="muammo",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
    )
    solution = models.ForeignKey(
        "solutions.Solution",
        verbose_name="yechim",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
    )

    # ⚠️ `is_read` BOOLEAN EMAS, SANA.
    #    Boolean bilan "qachon o'qilgan?" savoliga javob yo'qoladi va
    #    D5-T4 (jim soatlar) hamda kelajakdagi tahlil uchun u kerak
    #    bo'ladi. `is_read` esa shundan hisoblanadi — `Complaint.status`
    #    va `is_solved` bilan bir xil naqsh.
    okilgan_at = models.DateTimeField("o'qilgan", null=True, blank=True, editable=False)

    class Meta:
        verbose_name = "bildirishnoma"
        verbose_name_plural = "bildirishnomalar"
        ordering = ("-created_at", "-id")
        indexes = [
            # ⚠️ O'qilmaganlar SANOG'I sarlavhada, ya'ni HAR sahifada
            #    so'raladi (kesh bo'sh bo'lganda). Bu indeks o'sha
            #    so'rovni qoplaydi.
            models.Index(
                fields=["recipient", "okilgan_at"], name="bildirishnoma_oqilm_idx"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.recipient_id}: {self.get_turi_display()}"

    @property
    def okilganmi(self) -> bool:
        return self.okilgan_at is not None

    @property
    def matn(self) -> str:
        """Foydalanuvchi ko'radigan matn.

        ⚠️ Aktyor nomi FAQAT `actor` mavjud bo'lganda qo'shiladi.
           Anonim manbada u `None` va matn "Kimdir..." bo'lib qoladi
           (model docstring'idagi anonimlik qoidasi).
        """
        kim = self.actor.display_name if self.actor else "Kimdir"

        if self.turi == BildirishnomaTuri.YANGI_YECHIM:
            return f"{kim} muammoingizga yechim yozdi"
        if self.turi == BildirishnomaTuri.YECHIM_QABUL:
            return "Yechimingiz to'g'ri javob deb belgilandi"
        if self.turi == BildirishnomaTuri.DAYJEST:
            # ⚠️ SANOQ ATAYLAB YO'Q ("5 ta savol" emas). M3 da uch marta
            #    qaytgan invariant: ko'rsatilgan raqam ko'rsatilgan
            #    ro'yxatga TENG bo'lishi kerak. Bu yerda ro'yxat JONLI
            #    (lenta filtri) va yozuv yaratilgandan keyin o'zgaradi —
            #    ya'ni har qanday saqlangan raqam ertaga yolg'on bo'lardi.
            if self.complaint is not None:
                return f"{self.complaint.category.name} sohasida javobsiz savollar"
            return "Sohangizda javobsiz savollar"
        return self.get_turi_display()

    @property
    def manzil(self) -> str:
        """Bosilganda qayerga olib boradi.

        ⚠️ Yechimga bog'liq bo'lsa LANGAR bilan (`#yechim-<pk>`) —
           foydalanuvchi uzun sahifada javobni qidirib o'tirmasin.
           Langar `templates/components/_solution.html` da.
        """
        # ⚠️ `complaint_id` EMAS, obyektning O'ZI tekshiriladi: `None`
        #    bo'lgan FK uchun Django so'rov QILMAYDI, ya'ni narxi bir xil,
        #    lekin tip tekshiruvchi shartni tushunadi (mypy `union-attr`).
        muammo = self.complaint
        if muammo is None:
            return reverse("bildirishnomalar")

        if self.turi == BildirishnomaTuri.DAYJEST:
            # ⚠️ BITTA savolga emas, RO'YXATGA olib boradi: matn ko'plikda
            #    ("javobsiz savollar") va bitta savolga tushirish
            #    qolganlarini ko'rinmas qilardi.
            #
            # ⚠️ Alohida "dayjest sahifasi" yaratilmadi — mavjud lenta
            #    filtri aynan shu ro'yxatni beradi va u JONLI: dayjest
            #    yuborilgandan keyin javob olgan savol u yerda chiqmaydi.
            return f"{reverse('feed')}?category={muammo.category.slug}&status=open"

        yol = muammo.get_absolute_url()
        if self.solution_id is not None:
            return f"{yol}#yechim-{self.solution_id}"
        return yol


class BildirishnomaSozlamasi(TimeStampedModel):
    """Foydalanuvchining yetkazish sozlamalari (D5-T4).

    ⚠️⚠️ SOZLAMA YETKAZISHNI BOSHQARADI, YOZUVNI EMAS: o'chirilgan tur
       uchun ham `Notification` yaratiladi, faqat Telegram xabari
       yuborilmaydi. Sabab `apps/notifications/sozlama.py` da.

    ⚠️ QATOR HAR FOYDALANUVCHI UCHUN YARATILMAYDI. Sozlamaga tegmagan
       odamda bu yozuv umuman bo'lmaydi va standart xulq ishlatiladi
       (`sozlama.standart_yoqilganmi`). Millionlab bo'sh qator yozish
       bekorga joy va migratsiya yuki bo'lardi.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        verbose_name="foydalanuvchi",
        on_delete=models.CASCADE,
        related_name="bildirishnoma_sozlamasi",
    )

    # ⚠️ JSON, ALOHIDA USTUNLAR EMAS — o'lchangan almashuv:
    #    har yangi tur uchun migratsiya yozish kerak bo'lardi va u
    #    ALLAQACHON kerak (`BildirishnomaTuri` — `choices`), ya'ni
    #    ikkinchi migratsiya faqat takror bo'lardi.
    #
    #    ⚠️ Kalitlar `BildirishnomaTuri` qiymatlari. Noma'lum kalit
    #    JIMGINA e'tiborsiz qoldiriladi (`yoqilganmi` ga qarang):
    #    tur olib tashlangach eski sozlama xato bermasligi kerak.
    turlar = models.JSONField(
        "turlar bo'yicha",
        default=dict,
        blank=True,
        help_text="{tur: yoqilganmi}. Berilmagan tur standart holatda.",
    )

    # ⚠️ Oynaning O'ZI global sozlamada (`JIM_SOATLAR_*`), bu yerda faqat
    #    yoqish/o'chirish. Har foydalanuvchiga vaqt tanlatish sozlamalar
    #    sahifasini murakkablashtirardi, foyda esa kichik: deyarli hamma
    #    tunda uxlaydi.
    jim_soatlar = models.BooleanField(
        "jim soatlar",
        default=True,
        help_text="Kechasi kelgan xabar ertalabgacha kechiktiriladi.",
    )

    class Meta:
        verbose_name = "bildirishnoma sozlamasi"
        verbose_name_plural = "bildirishnoma sozlamalari"

    def __str__(self) -> str:
        return f"{self.user_id} sozlamasi"

    def yoqilganmi(self, turi: str) -> bool:
        """Shu tur Telegram'ga yuborilsinmi.

        ⚠️ Sozlamada YO'Q tur standart holatga qaytadi — ya'ni yangi
           tur qo'shilganda eski foydalanuvchilarda u o'zi paydo
           bo'lmaydi (D5-T4 qabul mezoni: standartda faqat muhimlari).
        """
        from .sozlama import standart_yoqilganmi

        qiymat = self.turlar.get(turi)
        if isinstance(qiymat, bool):
            return qiymat
        return standart_yoqilganmi(turi)
