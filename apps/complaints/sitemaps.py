"""sitemap.xml (D4-T5).

⚠️⚠️ BU FAYLNING ASOSIY XAVFI — YASHIRILGAN KONTENT.

   Moderatsiya qilingan post sitemap'ga tushsa, Google uni indekslaydi
   va yashirishning MA'NOSI QOLMAYDI: sahifa saytda ko'rinmaydi, lekin
   qidiruv natijasida turadi. Indeksdan chiqarish esa haftalar oladi.

   Shuning uchun `items()` `visible()` dan o'tadi (D2-T3 dagi "yagona
   kirish nuqtasi" qoidasi) va buni ikki qatlam qo'riqlaydi:
     · shu fayldagi ochiq testlar (`test_sitemap.py`);
     · manba kodi skaneri (`test_korinish_invarianti.py`) — u
       `visible()` siz so'rovni umuman yozdirmaydi.

⚠️ NEGA `apps/complaints/` DA, `apps/common/` DA EMAS
   `common` eng quyi qatlam va boshqa ilovalarni import qilmaydi
   (`apps/common/models.py` docstring'i). Sitemap esa `Complaint` va
   `Category` ga tayanadi. Statik sahifalar ro'yxati ham shu yerda:
   uni alohida faylga ajratish uchta kichik faylni hosil qilardi va
   ularning hammasi baribir birga o'zgarardi.
"""

from __future__ import annotations

from datetime import datetime

from django.contrib.sitemaps import Sitemap
from django.db import models
from django.urls import reverse

from .models import Category, Complaint, ComplaintStatus

# ⚠️ `protocol` ATAYLAB QOTIRILMAGAN. Django uni bermaganda so'rov
#    sxemasidan oladi (`request.scheme`) — ya'ni dev'da `http`, prod'da
#    `https` (nginx ortida `SECURE_PROXY_SSL_HEADER` orqali).
#
#    `protocol = "https"` deb yozish dev'da yolg'on manzil berardi va
#    testda ham `https://testserver/...` chiqib, kanonik bilan mos
#    kelmasdi — sitemap va kanonik esa AYNAN bir xil manzilni
#    ko'rsatishi shart (aks holda "Duplicate, not canonical").


class MuammoSitemap(Sitemap):
    """Ko'rinadigan muammolar.

    ⚠️ `changefreq` va `priority` — TAVSIYA, kafolat emas: Google
       ularni ko'pincha e'tiborsiz qoldiradi. Asosiy qiymat `lastmod`
       da: u qayta skanerlash tartibini haqiqatan o'zgartiradi.
    """

    changefreq = "weekly"

    def items(self) -> models.QuerySet[Complaint]:
        # ⚠️ `visible()` — bu faylning butun ma'nosi (yuqoridagi izoh).
        #    `select_related` YO'Q: sitemap faqat slug va sanani
        #    ishlatadi, kategoriya va muallif kerak emas.
        return (
            Complaint.objects.visible()
            .only("slug", "updated_at", "status")
            .order_by("-updated_at")
        )

    def lastmod(self, obj: Complaint) -> datetime:
        return obj.updated_at

    def priority(self, obj: Complaint) -> float:
        """Yechilgan muammo qimmatroq: unda SAVOL ham, JAVOB ham bor.

        Aynan shunday sahifa Google natijasida foydali bo'ladi —
        javobsiz savol esa foydalanuvchini bo'sh sahifaga olib keladi.
        """
        return 0.8 if obj.status == ComplaintStatus.SOLVED else 0.5


class KategoriyaSitemap(Sitemap):
    """Kategoriya bo'yicha filtrlangan lenta.

    ⚠️⚠️ MANZIL SO'ROV PARAMETRI BILAN (`/?category=moliya`) VA BU
       KANONIK BILAN MOS BO'LISHI SHART.

       Boshqa loyihada aynan shu joyda xato bo'lgan: sitemap
       `/?category=moliya` ni bergan, kanonik esa faqat `request.path`
       dan qurilib bosh sahifani ko'rsatgan. Search Console barcha
       kategoriya sahifalarini "Duplicate, not canonical" deb rad
       etgan — ya'ni sitemap ish bermagan, faqat ogohlantirish
       yaratgan.

       D4-T4 da kanonik `?category=` ni ATAYLAB saqlaydi
       (`apps/common/templatetags/seo.py`), shuning uchun bu yerda
       manzillar o'z-o'ziga kanonik bo'ladi.
    """

    changefreq = "daily"
    priority = 0.6

    def items(self) -> models.QuerySet[Category]:
        return Category.objects.filter(is_active=True).order_by("order", "name")

    def location(self, obj: Category) -> str:
        return obj.get_absolute_url()


class StatikSitemap(Sitemap):
    """O'zgarmas sahifalar.

    ⚠️ RO'YXAT QO'LDA — URLconf'dan avtomatik olinmaydi. Sabab: ommaviy
       yo'llarning ko'pi sitemap'ga TUSHMASLIGI kerak (kirish, chiqish,
       rozilik, hisob, moderatsiya, ovoz berish...). Avtomatik ro'yxat
       ularni qo'shib yuborardi va istisnolar ro'yxati baribir qo'lda
       yuritilardi — faqat teskari, ya'ni xato tomonga qarab.

    ⚠️ PROFIL SAHIFALARI ATAYLAB YO'Q. Ular yupqa (thin) kontent —
       asosan boshqa sahifalarga havolalar — va minglab bo'lishi
       mumkin. Bundan tashqari sitemap foydalanuvchi nomlarining
       to'liq ro'yxatini beradi, bu esa profil skraperlariga tayyor
       ma'lumot.
    """

    changefreq = "monthly"

    # ⚠️ `priority` SINF ATRIBUTI SIFATIDA BERILMAYDI — u pastda METOD.
    #    Ikkalasi bir vaqtda yozilgan edi va metod atributni jimgina
    #    bosib ketardi (ruff F811 va mypy no-redef ushladi): ya'ni
    #    `priority = 0.4` o'lik kod bo'lib, uni o'qigan odam qiymat
    #    shundan kelayapti deb o'ylardi.

    # ⚠️ Bosh sahifa alohida ustuvorlikda — u saytning kirish nuqtasi.
    YOLLAR = (
        ("feed", 1.0),
        ("category_list", 0.7),
        ("expert_list", 0.7),
        ("landing", 0.5),
        ("shartlar", 0.3),
        ("maxfiylik", 0.3),
        ("qoidalar", 0.3),
        ("boglanish", 0.3),
    )

    def items(self) -> list[tuple[str, float]]:
        return list(self.YOLLAR)

    def location(self, obj: tuple[str, float]) -> str:
        return reverse(obj[0])

    def priority(self, obj: tuple[str, float]) -> float:
        return obj[1]


SITEMAPLAR = {
    "muammolar": MuammoSitemap,
    "kategoriyalar": KategoriyaSitemap,
    "sahifalar": StatikSitemap,
}
