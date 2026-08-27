"""Muhit o'zgaruvchilari: `.env` yuklash va turga o'girish.

Nega tashqi kutubxona (django-environ / python-dotenv) EMAS:
loyihada `DATABASE_URL` dan boshqa murakkab tahlil kerak emas, kerakli
funksiyalar esa 100 qatorga sig'adi. Har bir bog'liqlik xavfsizlik
yangilanishi, versiya to'qnashuvi va o'rganish yuki olib keladi.

⚠️ USTUVORLIK QOIDASI: haqiqiy muhit o'zgaruvchisi `.env` dan USTUN turadi.
   Docker va prod'da qiymatlarni orkestrator beradi; obrazga xato bilan
   tushib qolgan eski `.env` ularni bekor qilib, ilovani noto'g'ri
   ma'lumotlar bazasiga ulab yuborishi mumkin edi.
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote, urlparse

from django.core.exceptions import ImproperlyConfigured

__all__ = [
    "database_from_url",
    "env",
    "env_bool",
    "env_int",
    "env_list",
    "load_dotenv",
]


# ---------------------------------------------------------------------------
# .env yuklash
# ---------------------------------------------------------------------------
def _clean_value(raw: str) -> str:
    """Qiymatni tozalaydi: qo'shtirnoq, izoh, bo'sh joy."""
    raw = raw.strip()
    if not raw:
        return ""

    # Qo'shtirnoq ichidagi qiymat — ichidagi hamma narsa saqlanadi
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ("'", '"'):
        value = raw[1:-1]
        # Faqat ikkilamchi qo'shtirnoqda \n va \t maxsus ma'noga ega
        if raw[0] == '"':
            value = value.replace("\\n", "\n").replace("\\t", "\t")
        return value

    # Qo'shtirnoqsiz: satr ichidagi izohni kesamiz (` #` dan keyingisi).
    # ⚠️ Bo'sh joy SHART: "pass#word" paroli buzilmasin.
    if " #" in raw:
        raw = raw.split(" #", 1)[0].rstrip()
    return raw


def load_dotenv(path: str | Path, *, override: bool = False) -> int:
    """`.env` faylini `os.environ` ga yuklaydi.

    Fayl bo'lmasa — jimgina o'tib ketadi (dev va Docker'da u shart emas).

    Args:
        override: True bo'lsa mavjud muhit o'zgaruvchilari ustidan yozadi.
            Standart False — yuqoridagi ustuvorlik qoidasiga qarang.

    Returns:
        Yuklangan o'zgaruvchilar soni.
    """
    path = Path(path)
    if not path.is_file():
        return 0

    # utf-8-sig: Windows muharrirlari fayl boshiga BOM qo'yadi va u
    # birinchi kalit nomiga yopishib qoladi ("﻿DJANGO_SECRET_KEY").
    # Bunday xatoni topish qiyin — kalit "yo'q" bo'lib ko'rinadi.
    text = path.read_text(encoding="utf-8-sig")

    yuklandi = 0
    for xom_qator in text.splitlines():  # CRLF ni ham to'g'ri ajratadi
        qator = xom_qator.strip()

        if not qator or qator.startswith("#"):
            continue

        if qator.startswith("export "):
            qator = qator[len("export ") :].lstrip()

        if "=" not in qator:
            continue  # yaroqsiz qator — jim o'tkazamiz

        kalit, _, xom_qiymat = qator.partition("=")
        kalit = kalit.strip()
        if not kalit:
            continue

        if not override and kalit in os.environ:
            continue  # ⚠️ haqiqiy muhit o'zgaruvchisi ustun

        os.environ[kalit] = _clean_value(xom_qiymat)
        yuklandi += 1

    return yuklandi


# ---------------------------------------------------------------------------
# Turga o'girish
# ---------------------------------------------------------------------------
def env(key: str, default: str | None = None) -> str:
    """Majburiy yoki standart qiymatli matn.

    Standart berilmasa (`default is None`) o'zgaruvchi MAJBURIY hisoblanadi.

    ⚠️ MAJBURIY o'zgaruvchi uchun BO'SH QIYMAT ham "yo'q" bilan barobar.
       Sabab: `.env.example` da kalitlar bo'sh turadi (`DJANGO_SECRET_KEY=`).
       Kimdir uni nusxa olib to'ldirmasa, faqat `None` tekshirilganda
       server BO'SH sir bilan ishga tushib ketardi — ya'ni "yarim
       sozlangan holda ishga tushmasin" qoidasi aynan eng muhim joyda
       ishlamas edi.

       Ixtiyoriy o'zgaruvchilarga bu taalluqli emas: ular ochiq standart
       beradi (`env("SENTRY_DSN", "")`) va bo'sh qiymat ular uchun
       "integratsiya o'chiq" degani.
    """
    value = os.environ.get(key, default)

    if value is None:
        raise ImproperlyConfigured(
            f"'{key}' muhit o'zgaruvchisi berilmagan. .env.example ga qarang."
        )

    if default is None and not value.strip():
        raise ImproperlyConfigured(
            f"'{key}' bo'sh. U majburiy — qiymat bering. .env.example ga qarang."
        )

    return value


def env_bool(key: str, default: bool = False) -> bool:
    raw = os.environ.get(key)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "ha"}


def env_int(key: str, default: int) -> int:
    raw = os.environ.get(key)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ImproperlyConfigured(
            f"'{key}' butun son bo'lishi kerak, kelgan qiymat: {raw!r}"
        ) from exc


def env_list(key: str, default: str = "") -> list[str]:
    """Vergul bilan ajratilgan ro'yxat: "a.uz, b.uz" -> ["a.uz", "b.uz"]"""
    raw = os.environ.get(key)
    if raw is None:
        raw = default
    return [item.strip() for item in raw.split(",") if item.strip()]


# ---------------------------------------------------------------------------
# DATABASE_URL
# ---------------------------------------------------------------------------
def database_from_url(url: str) -> dict[str, object]:
    """`postgres://user:parol@host:port/baza` -> Django DATABASES yozuvi.

    Boshqariladigan ma'lumotlar bazalari (DigitalOcean, Neon, Supabase)
    odatda aynan shu formatda bitta qator beradi.
    """
    parsed = urlparse(url)

    if parsed.scheme not in ("postgres", "postgresql"):
        raise ImproperlyConfigured(
            f"DATABASE_URL faqat postgres:// bo'lishi mumkin, kelgan: {parsed.scheme!r}. "
            "Loyiha PostgreSQL'ga xos imkoniyatlarga tayanadi (M4: to'liq matnli qidiruv)."
        )

    baza = unquote(parsed.path or "").lstrip("/")
    if not baza:
        raise ImproperlyConfigured("DATABASE_URL da ma'lumotlar bazasi nomi yo'q.")

    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": baza,
        # ⚠️ unquote: parolda @ : / kabi belgilar bo'lsa ular URL'da
        #    %40 %3A %2F ko'rinishida keladi va ochilishi SHART.
        "USER": unquote(parsed.username or ""),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": parsed.hostname or "",
        "PORT": str(parsed.port or 5432),
    }
