"""Spam evristikasi: honeypot + signallar (D2-T5).

⚠️ NEGA CAPTCHA EMAS
   Task tavsifidagi sabab: "CAPTCHA foydalanuvchini qochiradi". Bu
   Dard.uz uchun oddiy qulaylik masalasi emas. Platformaning butun
   va'dasi — odam eng og'ir shaxsiy holatini AYTA OLISHI. Jo'natish
   tugmasi oldiga "svetofor rasmlarini tanlang" qo'yish aynan eng
   qiyin lahzada, eng ikkilanayotgan odamni to'xtatadi.

   Evristika esa KO'RINMAYDI: oddiy foydalanuvchi uning borligini
   sezmaydi ham.

⚠️⚠️ SHUBHALI KONTENT YASHIRILMAYDI — MAHSULOT QARORI (foydalanuvchi
   tanlagan, 2026-08-29).

   Shubhali post E'LON QILINADI va moderatsiya navbatiga tushadi
   (`avtomatik_belgilash`). Sabab: yolg'on ijobiy holatning narxi bu
   yerda odatdagidan ancha yuqori. Spam bir necha soat ko'rinib
   tursa — noqulay; og'ir dardini yozgan odamning posti jimgina
   yo'qolsa — u boshqa qaytmaydi.

   YAGONA ISTISNO — honeypot. To'ldirilgan yashirin maydon mexanik
   aniqlik: ko'rinmaydigan maydonni odam to'ldira olmaydi. Faqat shu
   holat DARHOL RAD ETILADI.

   Boshqa hech qanday signal blok qilmaydi — hattoki ularning yig'indisi
   ham. "Bir soniyada to'ldirilgan" degan signal ham aslida odamni
   ko'rsatishi mumkin: boshqa joyda yozib qo'yib, keyin nusxa
   ko'chirgan odam formani 2 soniyada yuboradi.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import timedelta

from django import forms
from django.core import signing
from django.utils import timezone

# ⚠️ QABUL MEZONI: "3 sekunddan tez to'ldirilgan forma shubhali deb
#    belgilanadi". Shuning uchun tez to'ldirish balli YOLG'IZ O'ZI
#    shubha chegarasiga yetadi — boshqa signal talab qilinmaydi.
MIN_TOLDIRISH_VAQTI = 3  # soniya
JUDA_TEZ_VAQTI = 1  # soniya — bundan tezi deyarli aniq skript

# Hisob shu muddatdan yosh bo'lsa "yangi" hisoblanadi.
YANGI_HISOB_MUDDATI = timedelta(hours=24)

# Shu balldan boshlab kontent navbatga tushadi (lekin YASHIRILMAYDI).
SHUBHA_BALLI = 3

# Imzolangan vaqt belgisi shu muddatdan keyin "eskirgan" sanaladi.
# ⚠️ Uzoq: qoralama saqlab qo'yib, ertasiga davom ettirgan odam
#    jazolanmasligi kerak. Eskirgan belgi SHUBHALI EMAS — u "juda uzoq
#    to'ldirilgan" degani, ya'ni bot xulqiga umuman o'xshamaydi.
VAQT_BELGISI_MUDDATI = 7 * 24 * 3600

# ⚠️ Honeypot maydonining nomi ATAYLAB "website"/"email"/"url" EMAS.
#    Brauzer va parol menejerlari aynan shunday nomlarni AVTOMATIK
#    TO'LDIRADI — ko'rinmaydigan maydon bo'lsa ham. Natijada honeypot
#    haqiqiy odamlarni ushlab, eng yomon turdagi yolg'on ijobiy berardi.
#    Neytral nom autofill uchun ma'nosiz, "hamma maydonni to'ldiruvchi"
#    oddiy botlar uchun esa farqi yo'q.
HONEYPOT_MAYDONI = "qoshimcha_izoh"
VAQT_MAYDONI = "forma_ochilgan"

# Faqat aniq havolalar sanaladi. Yalang'och domen (`example.com`) ATAYLAB
# sanalmaydi: "fanfics.uz da o'qigandim" degan oddiy jumla ham unga
# tushardi.
HAVOLA_NAQSHI = re.compile(r"(?i)\b(?:https?://|www\.)\S+")


@dataclass
class Baho:
    """Spam bahosi — ball va uning sabablari.

    ⚠️ `sabablar` MODERATORGA ko'rsatiladi (navbatdagi izoh sifatida).
       "Shubhali" degan yorliq o'zi hech narsa bermaydi: moderator
       NEGA shubhali ekanini bilmasa, qarorni tasodifiy qabul qiladi.
    """

    ball: int = 0
    sabablar: list[str] = field(default_factory=list)
    bot_aniq: bool = False

    def qosh(self, ball: int, sabab: str) -> None:
        self.ball += ball
        self.sabablar.append(sabab)

    @property
    def shubhalimi(self) -> bool:
        return self.bot_aniq or self.ball >= SHUBHA_BALLI

    @property
    def izoh(self) -> str:
        """Navbatdagi shikoyat izohi."""
        return f"Avtomatik filtr ({self.ball} ball): " + "; ".join(self.sabablar)


def vaqt_belgisi() -> str:
    """Formani ochish vaqti — imzolangan.

    ⚠️ IMZOLANGAN, oddiy `hidden` maydon EMAS. Aks holda skript
       qiymatni o'tmishga surib qo'yardi va "sekin to'ldirdim" deb
       ko'rsatardi. Imzo `SECRET_KEY` ga bog'liq va uni soxtalashtirib
       bo'lmaydi.
    """
    return signing.dumps({"t": int(time.time())})


def _vaqtni_baholash(baho: Baho, xom: str) -> None:
    if not xom:
        # Formani umuman ochmasdan to'g'ridan-to'g'ri POST yuborilgan.
        baho.qosh(3, "forma ochilish vaqti yo'q")
        return

    try:
        malumot = signing.loads(xom, max_age=VAQT_BELGISI_MUDDATI)
    except signing.SignatureExpired:
        # Uzoq turgan qoralama — bot xulqiga o'xshamaydi.
        return
    except signing.BadSignature:
        baho.qosh(3, "forma vaqti buzilgan (imzo mos kelmadi)")
        return

    otgan = int(time.time()) - int(malumot.get("t", 0))
    if otgan < 0:
        baho.qosh(3, "forma vaqti kelajakda")
    elif otgan < JUDA_TEZ_VAQTI:
        baho.qosh(4, f"{otgan} soniyada to'ldirilgan")
    elif otgan < MIN_TOLDIRISH_VAQTI:
        baho.qosh(3, f"{otgan} soniyada to'ldirilgan")


def _havolalarni_baholash(baho: Baho, matn: str) -> None:
    soni = len(HAVOLA_NAQSHI.findall(matn))
    if soni >= 5:
        baho.qosh(3, f"{soni} ta havola")
    elif soni >= 3:
        baho.qosh(2, f"{soni} ta havola")
    elif soni == 2:
        baho.qosh(1, "2 ta havola")


def _hisobni_baholash(baho: Baho, foydalanuvchi) -> None:
    """Yangi hisob — signal, LEKIN yolg'iz o'zi yetarli emas.

    ⚠️ Bu ball ataylab KICHIK (1). Eng himoyasiz foydalanuvchi ham
       yangi hisob bilan keladi: odam dardini yozish uchun ro'yxatdan
       o'tadi, ro'yxatdan o'tib keyin dard kutib o'tirmaydi. Yangi
       hisobni o'zi bilan jazolash aynan shu odamni jazolardi.
    """
    qoshilgan = getattr(foydalanuvchi, "date_joined", None)
    if qoshilgan and timezone.now() - qoshilgan < YANGI_HISOB_MUDDATI:
        baho.qosh(1, "hisob 24 soatdan yosh")


def bahola(*, honeypot: str, vaqt: str, matn: str, foydalanuvchi=None) -> Baho:
    """Signallarni yig'ib ball chiqaradi."""
    baho = Baho()

    if honeypot.strip():
        # Ko'rinmaydigan maydonni odam to'ldira olmaydi.
        baho.bot_aniq = True
        baho.qosh(0, "yashirin maydon to'ldirilgan")
        return baho

    _vaqtni_baholash(baho, vaqt)
    _havolalarni_baholash(baho, matn)
    if foydalanuvchi is not None:
        _hisobni_baholash(baho, foydalanuvchi)
    return baho


class SpamHimoyaliForm(forms.Form):
    """Honeypot + vaqt belgisi qo'shadigan aralashma (mixin).

    Ishlatilishi::

        class ComplaintForm(SpamHimoyaliForm, forms.ModelForm):
            SPAM_MATN_MAYDONLARI = ("title", "description")

    Ko'rinish `form.spam_bahosi` ni o'qib, shubhali bo'lsa kontentni
    navbatga qo'yadi (`apps.moderation.services.avtomatik_belgilash`).

    ⚠️ `forms.Form` dan meros olinadi, `object` dan emas: aks holda
       `declared_fields` mexanizmi ishlamaydi va maydonlar formaga
       qo'shilmasdi. `ModelForm` bilan birga ishlatilganda MRO to'g'ri
       chiqadi (aralashma BIRINCHI turishi shart).
    """

    # Qaysi maydonlardagi matn havolalarga tekshiriladi.
    SPAM_MATN_MAYDONLARI: tuple[str, ...] = ()

    def __init__(self, *args, foydalanuvchi=None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.foydalanuvchi = foydalanuvchi
        self.spam_bahosi = Baho()

        self.fields[HONEYPOT_MAYDONI] = forms.CharField(
            required=False,
            label="Bu maydonni bo'sh qoldiring",
            widget=forms.TextInput(
                attrs={
                    # ⚠️ `type="hidden"` EMAS: ko'p oddiy botlar yashirin
                    #    maydonlarni o'tkazib yuboradi, ko'rinadigan matn
                    #    maydonini esa to'ldiradi. Yashirish CSS bilan.
                    "class": "honeypot",
                    "tabindex": "-1",
                    "autocomplete": "off",
                    # Ekran o'quvchi ham ko'rmasin (a11y): `aria-hidden`
                    # fokuslanadigan elementda faqat `tabindex="-1"`
                    # bilan birga to'g'ri bo'ladi.
                    "aria-hidden": "true",
                }
            ),
        )
        self.fields[VAQT_MAYDONI] = forms.CharField(
            required=False,
            widget=forms.HiddenInput(),
            initial=vaqt_belgisi,
        )

    def spam_matni(self) -> str:
        return " ".join(
            str(self.data.get(nom, "") or "") for nom in self.SPAM_MATN_MAYDONLARI
        )

    def clean(self):
        tozalangan = super().clean() or {}

        self.spam_bahosi = bahola(
            honeypot=tozalangan.get(HONEYPOT_MAYDONI, "") or "",
            vaqt=tozalangan.get(VAQT_MAYDONI, "") or "",
            matn=self.spam_matni(),
            foydalanuvchi=self.foydalanuvchi,
        )

        if self.spam_bahosi.bot_aniq:
            # ⚠️ Xabar UMUMIY. "Yashirin maydonni to'ldirdingiz" deb
            #    yozish botni yozgan odamga aynan nimani chetlab o'tish
            #    kerakligini aytib berardi.
            raise forms.ValidationError(
                "Formani yuborib bo'lmadi. Sahifani yangilab, qaytadan urinib ko'ring."
            )

        return tozalangan
