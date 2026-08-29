"""Maxfiy fayl ombori (D3-T5).

⚠️⚠️ NEGA ALOHIDA SINF KERAK — O'LCHANGAN SABAB.

   Dastlab `FileSystemStorage` ni `base_url` siz sozlash yetarli deb
   o'ylangan edi: "`.url` chaqirilsa `ValueError` beradi". BU NOTO'G'RI
   edi va testda ushlandi.

   Django `FileSystemStorage._value_or_setting(base_url, settings.MEDIA_URL)`
   ishlatadi, ya'ni `base_url` berilmasa u `MEDIA_URL` GA QAYTADI.
   Natijada `.url` ochiq ko'rinishdagi `/media/ekspert/...` havolasini
   qaytarardi — fayl u yerda bo'lmasa ham, shablonga chizilgan havola
   "ishlayotgandek" ko'rinardi va yo'lni oshkor qilardi.

   Shuning uchun `url()` ochiq RAD ETADI. Endi ommaviy havola chizib
   qo'yish guard emas, IMKONSIZ.
"""

from __future__ import annotations

from django.core.files.storage import FileSystemStorage


class MaxfiyStorage(FileSystemStorage):
    """`MAXFIY_ROOT` ichidagi, veb orqali UZATILMAYDIGAN fayllar."""

    def url(self, name: str | None) -> str:
        raise ValueError(
            "Maxfiy faylning ommaviy havolasi YO'Q. Uni faqat staff'ga "
            "cheklangan ko'rinish uzatadi (`accounts.views.ekspert_hujjati`)."
        )
