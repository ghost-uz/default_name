"""Foydalanuvchi fabrikalari (test ma'lumoti).

Nega fabrika, `objects.create()` emas:
testda faqat SINALAYOTGAN maydon ko'rinib tursin. `create_user(...)` da
har safar username, parol va boshqalarni yozish testning maqsadini
ko'mib yuboradi.

    UserFactory(karma_cached=5000)   -> qolgani avtomatik va noyob
"""

from __future__ import annotations

import factory
from django.contrib.auth import get_user_model

User = get_user_model()


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        # ⚠️ username bo'yicha qidiradi — bir xil nom bilan ikki marta
        #    chaqirilsa IntegrityError o'rniga mavjudini qaytaradi.
        django_get_or_create = ("username",)
        skip_postgeneration_save = True

    # ⚠️ Sequence, Faker EMAS: username DB darajasida registrga sezgir
    #    bo'lmagan noyoblikka ega (D0-T2). Tasodifiy ismlar to'qnashishi
    #    mumkin va test vaqti-vaqti bilan yiqiladigan bo'lib qoladi.
    username = factory.Sequence(lambda n: f"foydalanuvchi{n}")
    first_name = factory.Faker("first_name")
    email = factory.LazyAttribute(lambda o: f"{o.username}@example.uz")

    @factory.post_generation
    def password(obj, create: bool, extracted: str | None, **kwargs) -> None:
        """Parol standart bo'yicha ISHLATIB BO'LMAYDIGAN qilib qo'yiladi.

        Sabab: haqiqiy foydalanuvchilar Telegram orqali kiradi va parolga
        ega emas (D1-T1). Fabrika shu holatni takrorlaydi — test hayotga
        yaqin bo'lsin.

        Parol kerak bo'lsa:  UserFactory(password="sirsuz")
        """
        if not create:
            return
        if extracted:
            obj.set_password(extracted)
        else:
            obj.set_unusable_password()
        obj.save(update_fields=["password"])


class TelegramUserFactory(UserFactory):
    """Telegram orqali kirgan oddiy foydalanuvchi."""

    telegram_id = factory.Sequence(lambda n: 100_000_000 + n)


class ExpertFactory(TelegramUserFactory):
    """Tasdiqlangan ekspert.

    ⚠️ `is_expert` — keshlangan bayroq (D0-T2). Haqiqiy manba ExpertProfile
       (D3-T5). Fabrika qo'shilgach, u ham shu yerda yaratiladi.
    """

    is_expert = True
    karma_cached = factory.Sequence(lambda n: 1000 + n * 100)


class StaffFactory(UserFactory):
    """Moderator / admin — parol bilan (admin paneliga kirish uchun)."""

    is_staff = True
    username = factory.Sequence(lambda n: f"moderator{n}")
    password = "test-parol"


class BannedUserFactory(TelegramUserFactory):
    """Bloklangan foydalanuvchi: o'qiy oladi, yoza olmaydi."""

    is_banned = True
    ban_reason = "Test uchun bloklangan"
