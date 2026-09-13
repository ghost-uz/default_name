"""Kontekstual reklama joylari (D6-T6).

⚠️⚠️ REKLAMA O'ZIMIZNIKI — TARMOQ EMAS.
   Matn va havola bizning bazamizda; sahifada uchinchi tomon skripti YO'Q
   va foydalanuvchi kuzatilmaydi. Maxfiylik siyosati (8-bo'lim) aynan
   shuni va'da qiladi, D2-T9 dagi CSP esa tashqi skriptni baribir
   bloklaydi. AdSense kabi tarmoq qo'shish uchun IKKALASINI ham qayta
   yozish kerak bo'lardi — ya'ni bu texnik emas, MAHSULOT qarori.

⚠️⚠️ RASM YO'Q — FAQAT MATN.
   Tashqi rasm CSP `img-src` ni ochishni talab qilardi (va reklama
   tarmog'iga eshik ochardi); o'z media'mizga yuklangani esa moderatsiya,
   o'lcham va WebP masalasini keltirardi. Matnli blok yetarli va tez.

⚠️ `faolmi` STANDART HOLATDA `False` — ataylab. Adminda yaratilgan
   zahoti saytga chiqib ketadigan reklama «hali tayyor emas» degan
   holatni umuman qoldirmasdi.

⚠️ Sanoqchilar (`korsatishlar`, `bosishlar`) — `editable=False` va
   adminda faqat o'qish uchun: ular O'LCHOV, tahrir qilinadigan maydon
   emas (D6-T2 dagi `Tolov` bilan bir xil qaror).
"""

from __future__ import annotations

from django.core.validators import URLValidator
from django.db import models
from django.utils import timezone

from apps.common.models import TimeStampedModel


class AdSlotQuerySet(models.QuerySet):
    def faol(self) -> AdSlotQuerySet:
        """Hozir ko'rsatilishi mumkin bo'lganlar.

        ⚠️ Muddat CHEKLARI IXTIYORIY: bo'sh `boshlanish` — «hoziroq»,
           bo'sh `tugash` — «muddatsiz». Shartnoma muddati bo'lmagan
           reklama uchun sun'iy sana yozdirish kerak emas.
        """
        hozir = timezone.now()
        return (
            self.filter(faolmi=True)
            .filter(models.Q(boshlanish__isnull=True) | models.Q(boshlanish__lte=hozir))
            .filter(models.Q(tugash__isnull=True) | models.Q(tugash__gt=hozir))
        )


class AdSlot(TimeStampedModel):
    """Bitta reklama bloki.

    Nomi rejadagi va tracker'dagi bilan bir xil (`AdSlot`) — hujjatdan
    kodga izlash oson bo'lsin.
    """

    nom = models.CharField(
        "ichki nom",
        max_length=60,
        help_text="Faqat adminda ko'rinadi (masalan: «Uy-joy — Golden House, sentabr»).",
    )
    sarlavha = models.CharField("sarlavha", max_length=60)
    matn = models.CharField("matn", max_length=140)
    manzil = models.URLField(
        "havola",
        max_length=300,
        # ⚠️ Faqat `http(s)`: standart validator `ftp` ni ham o'tkazadi va
        #    bunday havola yo'naltirishda kutilmagan xulq berardi.
        validators=[URLValidator(schemes=["http", "https"])],
    )
    tugma_matni = models.CharField("tugma matni", max_length=24, default="Batafsil")

    # ⚠️ MAQSADLASH: bo'sh bo'lsa reklama HAMMA kategoriyada chiqadi.
    #    `SET_NULL` emas, `CASCADE` ham emas — `PROTECT`: kategoriya
    #    o'chirilishi reklamani jimgina «hammaga» aylantirmasin.
    kategoriya = models.ForeignKey(
        "complaints.Category",
        verbose_name="kategoriya",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reklamalar",
        help_text="Bo'sh qoldirilsa — barcha kategoriyalarda ko'rinadi.",
    )

    boshlanish = models.DateTimeField("boshlanishi", null=True, blank=True)
    tugash = models.DateTimeField("tugashi", null=True, blank=True)
    faolmi = models.BooleanField(
        "faol",
        default=False,
        help_text="Yoqilmaguncha saytda ko'rinmaydi.",
    )

    korsatishlar = models.PositiveIntegerField(
        "ko'rsatishlar", default=0, editable=False
    )
    bosishlar = models.PositiveIntegerField("bosishlar", default=0, editable=False)

    objects = AdSlotQuerySet.as_manager()

    class Meta:
        verbose_name = "reklama"
        verbose_name_plural = "reklamalar"
        ordering = ("-created_at", "-id")
        indexes = [
            # Tanlash so'rovi: faol + muddat oynasi.
            models.Index(fields=["faolmi", "tugash"], name="reklama_faol_idx"),
        ]

    def __str__(self) -> str:
        return self.nom

    @property
    def ctr(self) -> float:
        """Bosish ulushi (%). Ko'rsatish bo'lmasa 0."""
        if not self.korsatishlar:
            return 0.0
        return round(self.bosishlar * 100 / self.korsatishlar, 2)
