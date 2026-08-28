"""Shikoyat formasi (D2-T1)."""

from __future__ import annotations

from django import forms

from .models import ReportReason


class ReportForm(forms.Form):
    """⚠️ `ModelForm` EMAS, oddiy `Form`.

    Sabab: `Report` da foydalanuvchi to'ldirmaydigan maydonlar ko'p
    (`reporter`, `complaint`/`solution`, `status`, `resolved_*`).
    `ModelForm` bilan ularni har safar `exclude` qilish kerak bo'lardi
    va bir kuni bittasi unutilib, foydalanuvchi `status` ni o'zi
    yuborishi mumkin bo'lardi.
    """

    reason = forms.ChoiceField(
        label="Sabab",
        choices=ReportReason.choices,
        widget=forms.RadioSelect(attrs={"class": "h-4 w-4 accent-[var(--c-primary)]"}),
        error_messages={"required": "Sababni tanlang."},
    )
    comment = forms.CharField(
        label="Qo'shimcha izoh",
        required=False,
        max_length=1000,
        widget=forms.Textarea(
            attrs={
                "class": "input",
                "rows": 3,
                "data-autogrow": "",
                "placeholder": "Moderatorga nima muhimligini yozing (ixtiyoriy).",
            }
        ),
    )

    def clean_comment(self) -> str:
        return (self.cleaned_data.get("comment") or "").strip()
