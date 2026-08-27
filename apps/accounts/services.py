"""Foydalanuvchi bilan bog'liq biznes mantiq.

Model faqat ma'lumot va invariantlarni saqlaydi; qaror qabul qiladigan mantiq
shu yerda turadi — u testlanadigan va ko'rinishlardan mustaqil bo'lsin.
"""

from __future__ import annotations

from django.db import IntegrityError, transaction

from .models import User
from .validators import RESERVED_USERNAMES, USERNAME_RE


def username_bandmi(nom: str) -> bool:
    """Nom band yoki ishlatib bo'lmaydiganmi (registrga sezgir EMAS)."""
    if not USERNAME_RE.match(nom) or nom.lower() in RESERVED_USERNAMES:
        return True
    return User.objects.filter(username__iexact=nom).exists()


# ---------------------------------------------------------------------------
# QAROR KUTILMOQDA — D1-T1 (Telegram login) shu funksiyani chaqiradi
# ---------------------------------------------------------------------------
def telegramdan_username_yasash(telegram_data: dict) -> str:
    """Telegram ma'lumotidan Dard.uz foydalanuvchi nomini yasaydi.

    Telegram quyidagilarni beradi (hammasi ham kafolatlanmagan):

        id          -> 123456789        (har doim bor)
        first_name  -> "Sardor"         (har doim bor)
        last_name   -> "Rasulov"        (BO'LMASLIGI mumkin)
        username    -> "sardor_92"      (BO'LMASLIGI mumkin, o'zgarishi mumkin)

    Bizga esa quyidagilarga mos nom kerak:
    - 3-30 belgi, harf bilan boshlanadi, [a-z0-9_]
    - band nomlar ro'yxatida emas (validators.py)
    - mavjud nom bilan registrdan qat'i nazar to'qnashmaydi

    TODO: qarorni shu yerga yozing (5-10 qator).

    Yordamchi: `username_bandmi(nom)` tekshiruvni bitta chaqiruvda qiladi.

    ⚠️ Bu MAHSULOT qarori, texnik emas. Rejangizdagi "Telegram orqali 1
       soniyada avtorizatsiya" va'dasi bilan "foydalanuvchi o'z nomiga ega
       bo'lsin" ehtiyoji aynan shu yerda to'qnashadi:

       A. Telegram username'ini olish, bo'lmasa ismdan yasash, oxiriga
          raqam qo'shish.
          + Nol ishqalanish, va'daga sodiq.
          - Telegram username o'zgaruvchan; ism kirilcha yoki emoji bo'lsa
            yasab bo'lmaydi; "sardor_4831" kabi chiroyli bo'lmagan nom chiqadi.

       B. Birinchi kirishda foydalanuvchidan nom so'rash.
          + Yaxshi identifikatsiya, odam o'z nomini biladi.
          - "1 soniya" va'dasi buziladi; ro'yxatdan o'tishning eng ko'p
            tashlab ketiladigan qadami aynan shunday oynalar.

       C. Avtomatik yasash + keyin bir marta o'zgartirish imkoni.
          + Ikkalasining foydasi.
          - Nom URL'da (`/@sardor92/`) — o'zgarganda eski havolalar buziladi,
            ya'ni yo'naltirish (redirect) va eski nomni band qilib turish
            kerak bo'ladi.

       Qaysi biri Dard.uz uchun to'g'ri — sizning qaroringiz. Anonimlik
       platformaning markazida ekanini ham hisobga oling: ba'zi
       foydalanuvchilar uchun nomning tanib bo'lmasligi afzallik bo'lishi
       mumkin.
    """
    raise NotImplementedError(
        "telegramdan_username_yasash() hali yozilmagan — D1-T1 uchun qaror kutilmoqda"
    )


def telegram_foydalanuvchisini_olish_yoki_yaratish(
    telegram_data: dict,
) -> tuple[User, bool]:
    """Telegram ma'lumoti bo'yicha foydalanuvchini topadi yoki yaratadi.

    D1-T1 da to'ldiriladi. Skelet shu yerda, chunki u yuqoridagi qarorga
    bog'liq.

    ⚠️ Poyga holati: ikki parallel so'rov bir xil nomni yasashi mumkin —
       shuning uchun yaratish `IntegrityError` ni ushlab, qayta urinishi kerak.
       DB cheklovi (Lower(username) unique) oxirgi himoya chizig'i.
    """
    telegram_id = int(telegram_data["id"])

    mavjud = User.objects.filter(telegram_id=telegram_id).first()
    if mavjud is not None:
        return mavjud, False

    for _ in range(5):  # nom to'qnashuvida qayta urinish
        nom = telegramdan_username_yasash(telegram_data)
        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    username=nom,
                    telegram_id=telegram_id,
                    first_name=telegram_data.get("first_name", "")[:150],
                    last_name=telegram_data.get("last_name", "")[:150],
                )
                user.set_unusable_password()  # parol ishlatilmaydi
                user.save(update_fields=["password"])
                return user, True
        except IntegrityError:
            continue

    raise RuntimeError("Bo'sh foydalanuvchi nomi topilmadi (5 urinish)")
