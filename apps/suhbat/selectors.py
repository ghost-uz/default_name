"""Suhbatlar — o'qish so'rovlari (D6-T5)."""

from __future__ import annotations

from django.db import models

from .models import KontaktSorovi, SorovHolati, Suhbat


def _ishtirokchi_filtri(user) -> models.Q:
    """Foydalanuvchi tomon bo'lgan yozuvlar.

    ⚠️ Ikki tomon — muammo muallifi va yechim muallifi. Ular
       `Solution` orqali topiladi, alohida `ishtirokchilar` jadvali
       YARATILMADI: ikkinchi manba bir kuni asosiysidan ajralib
       ketardi va suhbat «egasiz» qolardi.
    """
    return models.Q(sorov__solution__complaint__author=user) | models.Q(
        sorov__solution__author=user
    )


def suhbatlar_royxati(*, user) -> tuple[list[Suhbat], list[KontaktSorovi]]:
    """`(suhbatlar, javob kutayotgan so'rovlar)`.

    ⚠️ Javob kutayotgan so'rovlar ALOHIDA ro'yxatda: ular harakat
       talab qiladi va suhbatlar orasida ko'milib qolmasligi kerak.
    """
    suhbatlar = list(
        Suhbat.objects.filter(_ishtirokchi_filtri(user))
        .select_related(
            "sorov__solution__complaint__author",
            "sorov__solution__author",
            "sorov__solution__complaint",
        )
        .order_by("-updated_at", "-id")
    )

    sorovlar = [
        s
        for s in KontaktSorovi.objects.filter(
            holat=SorovHolati.KUTILMOQDA
        ).select_related(
            "solution__complaint__author", "solution__author", "solution__complaint"
        )
        # ⚠️ Javob QARSHI TOMONDAN kutiladi — o'z so'rovingiz bu
        #    ro'yxatda ko'rinmaydi (unga javob bera olmaysiz).
        if s.qarshi_tomon_id == user.pk
    ]
    return suhbatlar, sorovlar


def oqilmagan_soni(*, user, suhbat: Suhbat) -> int:
    return (
        suhbat.xabarlar.visible()
        .filter(okilgan_at__isnull=True)
        .exclude(author=user)
        .count()
    )
