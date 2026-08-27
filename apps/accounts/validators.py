"""Foydalanuvchi nomi validatsiyasi.

Foydalanuvchi nomi URL'da ko'rinadi (`/@sardor92/`), shuning uchun u
marshrutlar bilan to'qnashmasligi va boshqa odamni taqlid qilishga imkon
bermasligi kerak.
"""

import re

from django.core.exceptions import ValidationError

USERNAME_RE = re.compile(r"^[a-z][a-z0-9_]{2,29}$", re.IGNORECASE)

USERNAME_HELP = "3-30 belgi. Harf bilan boshlanadi; harflar, raqamlar va pastki chiziq."

# ---------------------------------------------------------------------------
# Band nomlar
# ---------------------------------------------------------------------------
# 1) Marshrutlar bilan to'qnashuv: /@admin/ yoki /@kirish/ mavjud sahifani
#    bosib qolishi mumkin.
# 2) ⚠️ TAQLID: eng muhim qism. "anonim" nomli hisob anonim postlar muallifi
#    kabi ko'rinadi — bu anonimlik va'dasini buzadi (14-bo'lim).
RESERVED_USERNAMES = frozenset(
    {
        # tizim / marshrutlar
        "admin",
        "administrator",
        "api",
        "static",
        "media",
        "health",
        "sitemap",
        "robots",
        "manifest",
        "sw",
        "favicon",
        "assets",
        "login",
        "logout",
        "signup",
        "register",
        "auth",
        "oauth",
        # o'zbekcha marshrutlar (config/urls.py ga qarang)
        "kirish",
        "chiqish",
        "royxat",
        "dard",
        "dardlar",
        "muammo",
        "muammolar",
        "yechim",
        "yechimlar",
        "kategoriya",
        "kategoriyalar",
        "ekspert",
        "ekspertlar",
        "profil",
        "sozlamalar",
        "qidiruv",
        "yordam",
        "qoidalar",
        "maxfiylik",
        "shartlar",
        "boglanish",
        # ⚠️ taqlid xavfi
        "anonim",
        "anonymous",
        "nomalum",
        "ochirilgan",
        "deleted",
        "moderator",
        "moderatorlar",
        "support",
        "dardu",
        "darduz",
        "dard_uz",
        "official",
        "rasmiy",
        "system",
        "tizim",
        "bot",
    }
)


def validate_username(value: str) -> None:
    """Shakl va band nomlarni tekshiradi.

    Case-insensitive noyoblik BU YERDA emas — u ma'lumotlar bazasi
    darajasida (UniqueConstraint + Lower) kafolatlanadi, chunki forma
    validatsiyasi poyga holatidan (race condition) himoya qilmaydi.
    """
    if not USERNAME_RE.match(value):
        raise ValidationError(USERNAME_HELP, code="invalid_username")

    if value.lower() in RESERVED_USERNAMES:
        raise ValidationError(
            "Bu nom band. Boshqasini tanlang.", code="reserved_username"
        )
