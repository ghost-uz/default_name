"""Bildirishnoma sozlamalari formasi (D5-T4)."""

from __future__ import annotations

from django import forms

from .models import BildirishnomaSozlamasi, BildirishnomaTuri
from .sozlama import standart_yoqilganmi

# Loyiha konvensiyasi (`rozilik.html`, `ekspert_ariza.html`): katakcha
# `mt-0.5 h-4 w-4` bilan matnning BIRINCHI qatoriga tekislanadi — aks
# holda ikki qatorli yorliqda u vertikal markazga tushib ketadi.
#
# Sinf VIDJETDA turadi, shablonda emas: maydonlar `BildirishnomaTuri` dan
# avtomatik quriladi va shablon ularni `{{ maydon }}` deb chiqaradi.
KATAKCHA_SINFI = "mt-0.5 h-4 w-4 shrink-0"


def _katakcha() -> forms.CheckboxInput:
    """Loyiha sinfi bilan katakcha vidjeti.

    Modul darajasidagi BITTA nusxani ulashish ham xavfsiz bo'lardi —
    `Field.__init__` berilgan vidjetni `copy.deepcopy` qiladi
    (`django/forms/fields.py`), ya'ni nusxa maydonlar orasida
    ulashilmaydi. Funksiya shunchaki ikki chaqiruv joyini bitta
    ta'rifga bog'lab turadi.
    """
    return forms.CheckboxInput(attrs={"class": KATAKCHA_SINFI})


class SozlamaForm(forms.Form):
    """Turlar bo'yicha yoqish/o'chirish + jim soatlar.

    ⚠️ `ModelForm` EMAS: `turlar` — JSON lug'at va uni bitta maydon
       sifatida ko'rsatish foydalanuvchiga JSON yozdirish degani bo'lardi.
       Bu yerda esa har tur alohida katakcha bo'lishi kerak.

    ⚠️ MAYDONLAR `BildirishnomaTuri` DAN AVTOMATIK quriladi: yangi tur
       qo'shilganda forma o'zi kengayadi va uni yangilashni unutish
       mumkin emas.
    """

    jim_soatlar = forms.BooleanField(
        label="Jim soatlar (22:00 – 08:00)",
        required=False,
        help_text="Kechasi kelgan xabar ertalabgacha kechiktiriladi.",
        widget=_katakcha(),
    )

    def __init__(self, *args, sozlama: BildirishnomaSozlamasi | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.sozlama = sozlama

        for turi in BildirishnomaTuri:
            joriy = (
                sozlama.yoqilganmi(turi.value)
                if sozlama is not None
                else standart_yoqilganmi(turi.value)
            )
            self.fields[self._maydon(turi.value)] = forms.BooleanField(
                label=turi.label, required=False, initial=joriy, widget=_katakcha()
            )

        if not self.is_bound and sozlama is not None:
            self.fields["jim_soatlar"].initial = sozlama.jim_soatlar
        elif not self.is_bound:
            self.fields["jim_soatlar"].initial = True

    @staticmethod
    def _maydon(turi: str) -> str:
        return f"tur_{turi}"

    def saqlash(self, *, user) -> BildirishnomaSozlamasi:
        """Sozlamani yozadi (kerak bo'lsa yaratadi).

        ⚠️ Qator FAQAT SHU YERDA yaratiladi: sozlamaga tegmagan
           foydalanuvchida u umuman bo'lmaydi va standart xulq
           ishlatiladi (model docstring'i).
        """
        turlar = {
            turi.value: bool(self.cleaned_data[self._maydon(turi.value)])
            for turi in BildirishnomaTuri
        }
        sozlama, _ = BildirishnomaSozlamasi.objects.update_or_create(
            user=user,
            defaults={
                "turlar": turlar,
                "jim_soatlar": bool(self.cleaned_data["jim_soatlar"]),
            },
        )
        return sozlama

    @property
    def tur_maydonlari(self):
        """Shablon uchun: faqat tur katakchalari."""
        return [self[nom] for nom in self.fields if nom.startswith("tur_")]
