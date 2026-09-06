"""Kontakt so'rovi va yopiq suhbat (D6-T5).

⚠️⚠️ NEGA «KONTAKT ALMASHINUVI» EMAS, «YOPIQ SUHBAT»
   Task ikki yo'lni taklif qiladi: kontakt ochish YOKI yopiq chat.
   Ikkinchisi tanlandi va sabab bitta so'z bilan: QAYTARIB BO'LMASLIK.

   Telegram nomini bergan odam uni ORQAGA OLA OLMAYDI. Uy zo'ravonligi
   yoki qarz haqida ANONIM yozgan odam uchun bu platformadagi eng
   xavfli amal bo'lardi — va D2-T11 dagi `UserBlock` ham foydasiz
   bo'lib qolardi: qarshi tomonda sizning nomingiz allaqachon bor.

   Yopiq suhbat esa QAYTARILADI: uni yopish, qarshi tomonni bloklash
   va shikoyat qilish mumkin. Qabul mezoni «chat moderatsiya
   qamrovida» ham faqat shu yo'lda bajariladi — Telegram'ga ko'chgan
   suhbatni moderatsiya qila olmaymiz.

⚠️⚠️ SUHBAT ICHIDA HAM ANONIMLIK SAQLANADI (ATAYLAB).
   Anonim muallif suhbatda ham «Anonim» bo'lib qoladi. Ya'ni qabul
   mezoni «anonim muallifning kontakti roziligisiz OCHILMAYDI» eng
   kuchli shaklda bajariladi: kontakt UMUMAN ochilmaydi, faqat
   taxallusli kanal ochiladi.

   Shaxsni oshkor qilish ATAYLAB QO'SHILMADI: u yagona qaytarib
   bo'lmaydigan amal va suhbat uni keraksiz qiladi. Kerak bo'lsa, u
   ALOHIDA, ikki tomonlama aniq rozilik bilan qo'shiladi.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

from apps.common.models import ContentModel, TimeStampedModel


class SorovHolati(models.TextChoices):
    """⚠️ Qiymatlar bazaga yoziladi — o'zgartirilmaydi."""

    KUTILMOQDA = "kutilmoqda", "Javob kutilmoqda"
    QABUL_QILINDI = "qabul_qilindi", "Qabul qilindi"
    RAD_ETILDI = "rad_etildi", "Rad etildi"


class KontaktSorovi(TimeStampedModel):
    """«Shaxsiy suhbat ochaylikmi?» so'rovi (D6-T5).

    ⚠️ QABUL QILINGAN YECHIMGA bog'lanadi (`OneToOne`): task
       «yechim qabul qilingandan keyin» deydi. Bitta yechimga bitta
       so'rov — teskarisida rad etilgan so'rovni qayta-qayta yuborish
       bezovtalik quroliga aylanardi.

    ⚠️ `soragan` `SET_NULL`: hisob o'chirilsa (D2-T8) so'rov yozuvi
       qoladi, aks holda suhbat ham CASCADE bilan ketardi va qarshi
       tomon yozishmani sababsiz yo'qotardi.
    """

    solution = models.OneToOneField(
        "solutions.Solution",
        verbose_name="qabul qilingan yechim",
        on_delete=models.CASCADE,
        related_name="kontakt_sorovi",
    )
    soragan = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="kim so'radi",
        on_delete=models.SET_NULL,
        null=True,
        related_name="yuborgan_kontakt_sorovlari",
    )
    holat = models.CharField(
        "holat",
        max_length=16,
        choices=SorovHolati.choices,
        default=SorovHolati.KUTILMOQDA,
        db_index=True,
    )
    javob_at = models.DateTimeField("javob berilgan vaqt", null=True, blank=True)

    class Meta:
        verbose_name = "kontakt so'rovi"
        verbose_name_plural = "kontakt so'rovlari"
        ordering = ("-created_at", "-id")

    def __str__(self) -> str:
        return f"So'rov #{self.pk} ({self.get_holat_display()})"

    @property
    def muammo(self):
        return self.solution.complaint

    @property
    def qarshi_tomon_id(self) -> int | None:
        """So'rovni KIM ko'rib chiqishi kerak.

        ⚠️ Ikki ishtirokchi — muammo muallifi va yechim muallifi.
           So'rovni kim yuborgan bo'lsa, javob ikkinchisidan kutiladi.
        """
        muallif_id = self.solution.complaint.author_id
        yechimchi_id = self.solution.author_id
        return yechimchi_id if self.soragan_id == muallif_id else muallif_id


class Suhbat(TimeStampedModel):
    """Ikki tomon roziligi bilan ochilgan yopiq kanal.

    ⚠️ SO'ROV QABUL QILINGANDA yaratiladi va boshqa yo'l YO'Q — bu
       modelni chetlab yaratish rozilik talabini yo'q qilardi.
    """

    sorov = models.OneToOneField(
        KontaktSorovi,
        verbose_name="kontakt so'rovi",
        on_delete=models.CASCADE,
        related_name="suhbat",
    )
    yopilgan_at = models.DateTimeField("yopilgan vaqt", null=True, blank=True)
    yopgan = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="kim yopdi",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="yopgan_suhbatlari",
    )

    class Meta:
        verbose_name = "suhbat"
        verbose_name_plural = "suhbatlar"
        ordering = ("-updated_at", "-id")

    def __str__(self) -> str:
        return f"Suhbat #{self.pk}"

    def get_absolute_url(self) -> str:
        return reverse("suhbat", args=[self.pk])

    @property
    def yopiqmi(self) -> bool:
        return self.yopilgan_at is not None

    @property
    def muammo(self):
        return self.sorov.solution.complaint

    def ishtirokchi_idlari(self) -> set[int]:
        """⚠️ `None` (o'chirilgan hisob) to'plamga TUSHMAYDI."""
        yechim = self.sorov.solution
        return {
            pk
            for pk in (yechim.complaint.author_id, yechim.author_id)
            if pk is not None
        }

    def ishtirokchimi(self, user) -> bool:
        return (
            getattr(user, "is_authenticated", False)
            and user.pk in self.ishtirokchi_idlari()
        )

    def korinadigan_nom(self, kim) -> str:
        """⚠️⚠️ SUHBATDA HAM ANONIMLIK SAQLANADI.

        Ism to'g'ridan-to'g'ri `user.display_name` dan OLINMAYDI —
        u anonim muallifni bir zumda oshkor qilardi. Manba har doim
        kontentning `public_author` i (D1-T6 dagi yagona kirish
        nuqtasi): anonim yozgan odam suhbatda ham «Anonim».

        Bu invariantning TO'RTINCHI joyi (shablon, OG, JSON-LD dan
        keyin) va eng oson unutiladiganlaridan biri, chunki suhbat
        ikki kishilik va «baribir kim ekanini biladi» degan taxmin
        NOTO'G'RI: anonim muallifni qarshi tomon HECH QACHON bilmagan.
        """
        yechim = self.sorov.solution
        if kim is None:
            return "Anonim"

        if kim.pk == yechim.complaint.author_id:
            ochiq = yechim.complaint.public_author
            zaxira = "Anonim (muammo muallifi)"
        else:
            ochiq = yechim.public_author
            zaxira = "Anonim (yechim muallifi)"

        return ochiq.display_name if ochiq is not None else zaxira

    def anonimmi(self, kim) -> bool:
        """Shu ishtirokchi suhbatda anonim ko'rinadimi.

        ⚠️ Satrni tekshirish (`nom.startswith("Anonim")`) EMAS: yorliq
           matni bir kuni o'zgaradi va tekshiruv JIMGINA to'xtardi.
        """
        yechim = self.sorov.solution
        if kim is None:
            return True
        if kim.pk == yechim.complaint.author_id:
            return yechim.complaint.public_author is None
        return yechim.public_author is None


class Xabar(ContentModel):
    """Suhbatdagi bitta xabar.

    ⚠️⚠️ `ContentModel` — QABUL MEZONI «chat moderatsiya qamrovida».
       Bundan xabar BEPUL oladi: moderatsiya holati, yumshoq o'chirish,
       shikoyat qilish (D2-T1), navbat (D2-T2), uch ogohlantirish
       (D2-T11), audit jurnali (D2-T7) VA inqiroz aniqlash (D2-T6).

       Oxirgisi bu yerda alohida qimmatli: eng og'ir gap aynan shaxsiy
       yozishmada aytiladi va u ommaviy lentada hech qachon
       ko'rinmaydi.
    """

    suhbat = models.ForeignKey(
        Suhbat,
        verbose_name="suhbat",
        on_delete=models.CASCADE,
        related_name="xabarlar",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="muallif",
        on_delete=models.SET_NULL,
        null=True,
        related_name="suhbat_xabarlari",
    )
    content = models.TextField("xabar matni", max_length=2000)
    okilgan_at = models.DateTimeField("o'qilgan vaqt", null=True, blank=True)

    class Meta:
        verbose_name = "suhbat xabari"
        verbose_name_plural = "suhbat xabarlari"
        ordering = ("created_at", "id")
        indexes = [
            models.Index(fields=["suhbat", "created_at"], name="xabar_suhbat_idx"),
        ]

    def __str__(self) -> str:
        return f"Xabar #{self.pk}"

    def get_absolute_url(self) -> str:
        return f"{reverse('suhbat', args=[self.suhbat_id])}#xabar-{self.pk}"

    @property
    def okilganmi(self) -> bool:
        return self.okilgan_at is not None

    @property
    def korinadigan_nom(self) -> str:
        """⚠️⚠️ SHABLON SHU XOSSANI ISHLATADI, `author.display_name` NI EMAS.

        Django shabloni argumentli metod chaqira olmaydi, ya'ni
        `Suhbat.korinadigan_nom(author)` ni to'g'ridan-to'g'ri
        ishlatib bo'lmaydi — va eng oson yo'l (`xabar.author.display_name`)
        aynan anonimlikni buzadigan yo'l. Shuning uchun xossa SHU
        YERDA, xabarning o'zida turadi.

        ⚠️ `self.suhbat` ko'rinishda oldindan to'ldiriladi
           (`views.suhbat`), aks holda har xabar bitta qo'shimcha
           so'rov qilardi.
        """
        return self.suhbat.korinadigan_nom(self.author)

    def nom(self, kuzatuvchi) -> str:
        """Kuzatuvchi ko'radigan yorliq.

        ⚠️ O'Z XABARINGIZ «Siz» deb belgilanadi. Jonli tekshiruvda
           anonim muallif O'Z xabarini «Anonim (muammo muallifi)» deb
           ko'rdi va bu chalg'ituvchi: ikki kishilik suhbatda odam
           «bu menmi yoki u?» degan savolga tushib qoladi.

        ⚠️ «Siz (anonim)» shakli ATAYLAB: odam o'z anonimligi
           SAQLANAYOTGANINI ko'rib turishi kerak — aks holda u qarshi
           tomon ismini bilib qoldi deb o'ylashi mumkin.
        """
        if kuzatuvchi is not None and self.author_id == getattr(kuzatuvchi, "pk", None):
            return "Siz (anonim)" if self.suhbat.anonimmi(self.author) else "Siz"
        return self.korinadigan_nom

    def belgilangan_deb_qoyish(self) -> None:
        if self.okilgan_at is None:
            self.okilgan_at = timezone.now()
            self.save(update_fields=["okilgan_at", "updated_at"])
