"""Yechim formasi (D1-T10)."""

from __future__ import annotations

from django import forms
from django.core.validators import MinLengthValidator

from apps.common.spam import SpamHimoyaliForm

from .models import Solution

# Maketdagi `data-minlen="30"` bilan bir xil (templates/complaints/detail.html).
YECHIM_MIN = 30


class SolutionForm(SpamHimoyaliForm, forms.ModelForm):
    """Yechim yozish.

    ⚠️ TAHRIRLASH FORMASI YO'Q — ATAYLAB.
       Yechim boshqalar ovoz bergandan keyin tahrirlansa, ular
       BOSHQA MATNGA ovoz bergan bo'lib qoladi. Muammoning o'zida
       tahrirlash oynasi bor, chunki unga hali javob berilmagan
       (`Complaint.tahrirlay_oladimi()`); yechimda esa ovoz birinchi
       daqiqadanoq kelishi mumkin.

       Kerak bo'lsa D2 da tahrir TARIXI bilan qo'shiladi — o'shanda
       ovoz berganlar nima o'zgarganini ko'ra oladi.
    """

    class Meta:
        model = Solution
        fields = ["content", "is_anonymous"]
        labels = {"content": "Yechim matni"}
        error_messages = {"content": {"required": "Yechim matnini yozing."}}
        widgets = {
            "content": forms.Textarea(
                attrs={
                    "class": "input",
                    "rows": 3,
                    "data-minlen": str(YECHIM_MIN),
                    "data-autogrow": "",
                    "placeholder": (
                        "Men ham shunga o'xshash holatda bo'lganman. "
                        "Menga yordam bergan narsa…"
                    ),
                }
            ),
            "is_anonymous": forms.CheckboxInput(attrs={"class": "peer sr-only"}),
        }

    SPAM_MATN_MAYDONLARI = ("content",)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["content"].validators.append(
            MinLengthValidator(
                YECHIM_MIN,
                message=f"Yechim kamida {YECHIM_MIN} ta belgidan iborat bo'lsin.",
            )
        )
        self.fields["is_anonymous"].label = "Anonim javob berish"

    def clean_content(self) -> str:
        return (self.cleaned_data["content"] or "").strip()

    def clean(self):
        """Bo'sh joylardan keyin uzunlik yana tekshiriladi.

        Sabab `ComplaintForm.clean()` dagi bilan bir xil: `clean_<field>`
        validatorlardan KEYIN ishlaydi, ya'ni faqat bo'sh joydan iborat
        matn o'tib ketardi.
        """
        tozalangan = super().clean() or {}
        matn = tozalangan.get("content")
        if matn is not None and len(matn) < YECHIM_MIN:
            self.add_error(
                "content",
                f"Kamida {YECHIM_MIN} ta belgi kerak (bo'sh joylar hisobga olinmaydi).",
            )
        return tozalangan
