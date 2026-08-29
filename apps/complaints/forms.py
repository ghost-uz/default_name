"""Muammo formasi (D1-T9)."""

from __future__ import annotations

from typing import cast

from django import forms
from django.core.validators import MinLengthValidator

from apps.common.spam import SpamHimoyaliForm

from .models import Category, Complaint, Generation

# ⚠️ MIN UZUNLIK SERVER TOMONDA (D1-T9 qabul mezoni).
#    Maketdagi `data-minlen` faqat brauzerda ishlaydi va uni o'chirish
#    uchun DevTools'da bitta atributni olib tashlash yetarli. Mijoz
#    tomonidagi tekshiruv — QULAYLIK, himoya emas.
#
#    Qiymatlar maketdagi `data-minlen` bilan bir xil bo'lishi shart,
#    aks holda foydalanuvchi "hammasi yashil" deb yuboradi va server
#    rad etadi — bu eng bezovta qiladigan holat.
SARLAVHA_MIN = 15
TAVSIF_MIN = 50


class ComplaintForm(SpamHimoyaliForm, forms.ModelForm):
    """Muammo yaratish va tahrirlash.

    ⚠️ `is_anonymous` TAHRIRLASHDA YO'Q — pastdagi `__init__` ga qarang.
    """

    class Meta:
        model = Complaint
        fields = ["title", "description", "category", "generation_tag", "is_anonymous"]
        error_messages = {
            "title": {"required": "Sarlavha kerak."},
            "description": {"required": "Tavsif kerak."},
            "category": {"required": "Kategoriyani tanlang."},
        }
        # ⚠️ Vidjet atributlari SHABLONDA emas, SHU YERDA.
        #    Maketda ular qo'lda yozilgan edi; forma orqali render
        #    qilinganda `maxlength` model chegarasidan avtomatik olinadi
        #    va ikkisi bir-biridan uzilib qolmaydi.
        #
        #    ⚠️ Maketda `maxlength="8000"` yozilgan edi, modelda esa 5000 —
        #       foydalanuvchi 6000 belgi yozib, yuborishda rad javob
        #       olardi. Endi bitta manba: model.
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "input",
                    "data-minlen": str(SARLAVHA_MIN),
                    "data-mirror-source": "",
                    "autocomplete": "off",
                    "placeholder": (
                        "Masalan: Ish beruvchi 3 oydan beri maosh bermayapti"
                    ),
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "input",
                    "rows": 7,
                    "data-minlen": str(TAVSIF_MIN),
                    "data-autogrow": "",
                    "placeholder": (
                        "Vaziyatni tushuntiring: nima bo'ldi, nimalarni sinab "
                        "ko'rdingiz, aynan nimada yordam kerak?"
                    ),
                }
            ),
            "category": forms.Select(attrs={"class": "input"}),
            # `peer sr-only` — maketdagi toggle: input ko'rinmaydi, yonidagi
            # `<span>` `peer-checked:` bilan uning holatini chizadi.
            "is_anonymous": forms.CheckboxInput(attrs={"class": "peer sr-only"}),
        }

    # Havolalar shu maydonlarda sanaladi (D2-T5).
    SPAM_MATN_MAYDONLARI = ("title", "description")

    def __init__(self, *args, tahrirlash: bool = False, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.fields["title"].validators.append(
            MinLengthValidator(
                SARLAVHA_MIN,
                message=f"Sarlavha kamida {SARLAVHA_MIN} ta belgidan iborat bo'lsin.",
            )
        )
        self.fields["description"].validators.append(
            MinLengthValidator(
                TAVSIF_MIN,
                message=f"Tavsif kamida {TAVSIF_MIN} ta belgidan iborat bo'lsin.",
            )
        )

        # ⚠️ FAQAT FAOL kategoriyalar. Usiz o'chirilgan kategoriya tanlov
        #    ro'yxatida qolib ketardi va "faol emas" degan tushuncha
        #    ma'nosini yo'qotardi.
        # `cast` — `self.fields[...]` umumiy `Field` deb tiplangan, lekin bu
        # yerda u aniq `ModelChoiceField` (ModelForm shunday quradi).
        kategoriya = cast(forms.ModelChoiceField, self.fields["category"])
        kategoriya.queryset = Category.objects.filter(is_active=True)
        kategoriya.empty_label = "Tanlang…"

        # Avlod — maketda majburiy (`*` bilan). Modelda `blank=True`, chunki
        # eski/import qilingan yozuvlarda u bo'lmasligi mumkin.
        #
        # ⚠️ Bo'sh variant ATAYLAB QOLDIRILADI va oldindan TANLANMAYDI.
        #    Maketda "Gen Z" `checked` edi — bu hammani Gen Z deb taxmin
        #    qilish va ma'lumotni buzish degani: foydalanuvchi e'tibor
        #    bermasa, posti noto'g'ri avlod bilan yorliqlanadi.
        self.fields["generation_tag"] = forms.ChoiceField(
            label="Avlod",
            choices=Generation.choices,
            required=True,
            widget=forms.RadioSelect(attrs={"class": "peer sr-only"}),
            error_messages={"required": "Avlodni tanlang."},
        )

        if tahrirlash:
            # ⚠️ ANONIMLIKNI KEYIN O'ZGARTIRIB BO'LMAYDI (maketda ham shunday
            #    yozilgan). Sabab: post allaqachon ko'rilgan va ulashilgan
            #    bo'lishi mumkin. "Anonim" dan "ismli" ga o'tish odamning
            #    o'zini fosh qilishi bo'lardi — va u buni tugmani bosgan
            #    lahzada anglamasligi mumkin. Qaytarib bo'lmaydigan
            #    harakatni tasodifan qilib bo'lmasin.
            del self.fields["is_anonymous"]

    def clean_title(self) -> str:
        # ⚠️ `strip()` validatsiyadan OLDIN emas, KEYIN ham kerak:
        #    50 ta bo'sh joy `MinLengthValidator` dan o'tib ketardi.
        return (self.cleaned_data["title"] or "").strip()

    def clean_description(self) -> str:
        return (self.cleaned_data["description"] or "").strip()

    def clean(self):
        """Bo'sh joylardan keyin uzunlik yana tekshiriladi.

        ⚠️ `clean_<field>` `MinLengthValidator` dan KEYIN ishlaydi, ya'ni
           "               " (50 ta bo'sh joy) validatordan o'tib, keyin
           `strip()` bilan bo'sh satrga aylanardi va bazaga shunday
           tushardi. Bu jim ma'lumot buzilishi.
        """
        # `super().clean()` `None` qaytarishi mumkin (Django imzosi) —
        # amalda `self.cleaned_data`, lekin tip tekshiruvi buni bilmaydi.
        tozalangan = super().clean() or {}
        for maydon, eng_kam in (("title", SARLAVHA_MIN), ("description", TAVSIF_MIN)):
            qiymat = tozalangan.get(maydon)
            if qiymat is not None and len(qiymat) < eng_kam:
                self.add_error(
                    maydon,
                    f"Kamida {eng_kam} ta belgi kerak (bo'sh joylar hisobga olinmaydi).",
                )
        return tozalangan
