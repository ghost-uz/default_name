"""Foydalanuvchi formalari (D3-T5)."""

from __future__ import annotations

from typing import cast

from django import forms

from apps.complaints.models import Category

from .models import ExpertProfile

# ⚠️ 5 MB — `FILE_UPLOAD_MAX_MEMORY_SIZE` bilan bir xil. Kattaroq fayl
#    baribir diskka yozilardi va maxfiy katalogda katta fayllar
#    to'planardi; diplom skani esa bunchadan kichik bo'ladi.
HUJJAT_MAX_BAYT = 5 * 1024 * 1024


class EkspertArizaForm(forms.ModelForm):
    """Ekspert bo'lish arizasi.

    ⚠️ `verification_status` FORMADA YO'Q va bo'lmasligi ham kerak:
       holatni faqat `services` o'zgartiradi. Uni `fields` ga qo'shish
       foydalanuvchiga o'zini tasdiqlash imkonini berardi — ya'ni task
       `nega` bo'limidagi "yolg'on nishon" muammosining eng to'g'ridan
       to'g'ri ko'rinishi.

    ⚠️ `pro_until` ham yo'q: u to'lovdan keladi (D6-T1), formadan emas.
    """

    class Meta:
        model = ExpertProfile
        fields = (
            "specialty",
            "experience_years",
            "kasbiy_tavsif",
            "hujjat",
            "contact_visible",
        )
        widgets = {
            "kasbiy_tavsif": forms.Textarea(attrs={"rows": 5}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # ⚠️ Faqat FAOL kategoriyalar: nofaol kategoriya yangi kontent
        #    uchun taklif qilinmaydi (`Category` docstring'i) va bu
        #    qoida ekspert sohasiga ham taalluqli.
        #
        # ⚠️ `cast` — `self.fields[...]` umumiy `Field` qaytaradi va mypy
        #    unda `queryset` yo'q deydi. Tip aniqlashtirish, e'tiborsiz
        #    qoldirish emas.
        soha = cast("forms.ModelChoiceField", self.fields["specialty"])
        soha.queryset = Category.objects.filter(is_active=True)
        soha.empty_label = "Sohani tanlang"

    def clean_hujjat(self):
        """⚠️ Hajm SERVERDA tekshiriladi.

        Brauzerdagi `accept` va JavaScript tekshiruvi qulaylik uchun;
        so'rovni qo'lda yuborgan odam ularni chetlab o'tadi.
        """
        hujjat = self.cleaned_data.get("hujjat")
        if hujjat and hujjat.size > HUJJAT_MAX_BAYT:
            raise forms.ValidationError(
                f"Fayl juda katta ({hujjat.size // 1024 // 1024} MB). "
                f"Chegara: {HUJJAT_MAX_BAYT // 1024 // 1024} MB."
            )
        return hujjat
