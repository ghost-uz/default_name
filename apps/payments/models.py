"""To'lovlar — modellar (D6-T1).

⚠️⚠️ NEGA OBUNA ALOHIDA MODEL, `User` DAGI SANA EMAS
   Task `nega` bo'limi: «PRO tekshiruvi kod bo'ylab tarqalsa, muddati
   tugagan obuna qayerdadir ishlab qolaveradi». Sana maydonini modelga
   qo'yish aynan shunga olib boradi — har chaqiruv joyi o'zicha
   `pro_until > now()` yozadi va biri albatta unutiladi yoki
   noto'g'ri yoziladi.

   Yagona kirish nuqtasi — `User.has_pro` (qabul mezoni). Guard test
   manba kodida `expires_at` / `status` ni `apps/payments/` dan
   TASHQARIDA taqqoslashni taqiqlaydi (D2-T3 ko'rinish invarianti va
   D2-T7 audit guard'i bilan bir xil naqsh).

⚠️⚠️ IKKI XIL «PRO» — BITTA SO'Z, IKKI BOSHQA TUSHUNCHA

   | | `User.has_pro` | `ExpertProfile.pro_faolmi` |
   |---|---|---|
   | Ma'nosi | TO'LOV amalda | PRO **nishoni** ko'rsatiladi |
   | Kimga tegishli | har qanday foydalanuvchi | faqat ekspert |
   | Sharti | faol obuna | tasdiqlangan malaka **VA** `has_pro` |

   Ikkinchisi birinchisining ISTE'MOLCHISI, parallel manba EMAS.
   D3-T5 dagi qoida kuchda qoladi: tasdiqlanmagan odam pul to'lab
   «Tasdiqlangan PRO» nishonini ololmaydi — aks holda pul bilan
   ishonch sotib olinardi.

   Oddiy foydalanuvchi ham PRO bo'la oladi: `ExpertProfile.contact_visible`
   yordam matni buni allaqachon nazarda tutgan («PRO obunachilar siz
   bilan bog'lana olishi uchun»).
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.common.models import TimeStampedModel


class ObunaRejasi(models.TextChoices):
    """⚠️ Qiymatlar bazaga yoziladi — o'zgartirilmaydi, yangisi qo'shiladi."""

    PRO = "pro", "PRO"


class ObunaHolati(models.TextChoices):
    """⚠️ «BEKOR QILINGAN» holati ATAYLAB YO'Q.

    Bekor qilish = `auto_renew = False`, holat esa `FAOL` bo'lib
    QOLAVERADI. Odam to'lagan muddati uchun xizmatni oladi; bekor
    qilish tugmasi allaqachon to'langan narsani tortib olmaydi.
    Muddat tugagach vazifa uni `TUGAGAN` ga o'tkazadi.
    """

    FAOL = "faol", "Faol"
    TUGAGAN = "tugagan", "Muddati tugagan"


class Subscription(TimeStampedModel):
    """Foydalanuvchining PRO obunasi (D6-T1).

    ⚠️ `OneToOne` — JORIY holat. To'lovlar TARIXI bu yerda emas:
       u D6-T2/T3 dagi tranzaksiya jadvalida bo'ladi va idempotentlik
       ham o'sha yerda ta'minlanadi (`transaction_id` noyob).
       Bu yerda tarix saqlashga urinish ikkita yarim-manba yasardi.

    ⚠️ QATOR HAR FOYDALANUVCHI UCHUN YARATILMAYDI — hech qachon
       to'lamagan odamda u umuman yo'q (`BildirishnomaSozlamasi` bilan
       bir xil qaror, D5-T4). `has_pro` buni `getattr(..., None)` bilan
       hal qiladi.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        verbose_name="foydalanuvchi",
        on_delete=models.CASCADE,
        related_name="obuna",
    )
    plan = models.CharField(
        "reja",
        max_length=16,
        choices=ObunaRejasi.choices,
        default=ObunaRejasi.PRO,
    )
    status = models.CharField(
        "holat",
        max_length=16,
        choices=ObunaHolati.choices,
        default=ObunaHolati.FAOL,
        db_index=True,
    )
    started_at = models.DateTimeField("boshlangan vaqt", default=timezone.now)
    expires_at = models.DateTimeField("tugash vaqti", db_index=True)
    auto_renew = models.BooleanField(
        "avtomatik yangilanadi",
        default=False,
        help_text="O'chirilsa obuna joriy muddat oxirida tugaydi.",
    )

    class Meta:
        verbose_name = "obuna"
        verbose_name_plural = "obunalar"
        ordering = ("-expires_at", "-id")
        indexes = [
            # Celery vazifasi: muddati o'tgan FAOL qatorlar.
            models.Index(fields=["status", "expires_at"], name="obuna_muddat_idx"),
        ]

    def __str__(self) -> str:
        return (
            f"{self.user_id}: {self.get_plan_display()} -> {self.expires_at:%Y-%m-%d}"
        )

    @property
    def faolmi(self) -> bool:
        """⚠️⚠️ IKKALA SHART HAM TEKSHIRILADI — `status` YOLG'IZ YETARLI EMAS.

        `status` ni `TUGAGAN` ga o'tkazadigan Celery vazifasi kuniga bir
        marta ishlaydi. Muddat tugagan payt bilan vazifaning keyingi
        ishga tushishi orasida `status` hamon `FAOL` turadi — faqat
        unga qarasak, obuna bir kungacha BEPUL uzayardi.

        Ya'ni vazifa — TOZALASH, HAQIQAT MANBAI emas. Guard test
        buni vazifani UMUMAN ishlatmasdan tekshiradi.
        """
        return self.status == ObunaHolati.FAOL and self.expires_at > timezone.now()

    @property
    def tugashiga_kun(self) -> int:
        """Necha kun qolgani (o'tib ketgan bo'lsa 0)."""
        qoldi = self.expires_at - timezone.now()
        return max(0, qoldi.days)
