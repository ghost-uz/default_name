"""D0-T1: apps/ ilovalar skeletini yaratadi.

Bir martalik skript. Ishlatilgandan keyin o'chirib yuborilsa ham bo'ladi —
lekin qanday tuzilish kutilayotganini hujjatlashtirgani uchun saqlangan.

Ishlatish:  python scripts/_scaffold_apps.py
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APPS_DIR = ROOT / "apps"

# (paket nomi, AppConfig sinfi, ko'rinadigan nom, vazifasi)
APPS = [
    (
        "common",
        "CommonConfig",
        "Umumiy",
        "Abstrakt modellar, mixinlar, yordamchilar. Eng quyi qatlam — boshqa ilovalarga BOG'LANMAYDI.",
    ),
    (
        "accounts",
        "AccountsConfig",
        "Foydalanuvchilar",
        "User, Telegram login, sessiyalar, ExpertProfile.",
    ),
    (
        "complaints",
        "ComplaintsConfig",
        "Muammolar",
        "Complaint, Category, Tag, Vote, SavedItem.",
    ),
    (
        "solutions",
        "SolutionsConfig",
        "Yechimlar",
        "Solution, qabul qilish oqimi, Match (kontakt almashinuvi).",
    ),
    (
        "moderation",
        "ModerationConfig",
        "Moderatsiya",
        "Report, ModerationAction, AuditLog, avtomatik filtrlar.",
    ),
    (
        "gamification",
        "GamificationConfig",
        "Gamifikatsiya",
        "KarmaEvent, Badge, reyting.",
    ),
    (
        "notifications",
        "NotificationsConfig",
        "Bildirishnomalar",
        "Notification, Telegram bot dispatch.",
    ),
    (
        "payments",
        "PaymentsConfig",
        "To'lovlar",
        "Subscription, BoostOrder, Click/Payme integratsiyasi.",
    ),
]

APPS_INIT = '''"""Dard.uz domen ilovalari.

Qoidalar:
1. `common` eng quyi qatlam — u boshqa ilovalarga BOG'LANMAYDI.
2. Ilovalar orasidagi bog'liqlik BIR TOMONLAMA bo'lsin
   (solutions -> complaints mumkin, teskarisi yo'q).
   Aylanma import Django'da tez paydo bo'ladi va uni keyin yechish qiyin.
"""
'''

APP_CONFIG = '''from django.apps import AppConfig


class {config}(AppConfig):
    """{purpose}"""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.{pkg}"
    label = "{pkg}"
    verbose_name = "{verbose}"
'''

MODELS_STUB = '''"""{verbose} — modellar.

{purpose}
"""
'''


def main() -> None:
    APPS_DIR.mkdir(exist_ok=True)
    (APPS_DIR / "__init__.py").write_text(APPS_INIT, encoding="utf-8")

    for pkg, config, verbose, purpose in APPS:
        app_dir = APPS_DIR / pkg
        app_dir.mkdir(exist_ok=True)
        (app_dir / "migrations").mkdir(exist_ok=True)

        (app_dir / "__init__.py").write_text("", encoding="utf-8")
        (app_dir / "migrations" / "__init__.py").write_text("", encoding="utf-8")
        (app_dir / "apps.py").write_text(
            APP_CONFIG.format(config=config, pkg=pkg, verbose=verbose, purpose=purpose),
            encoding="utf-8",
        )
        (app_dir / "models.py").write_text(
            MODELS_STUB.format(verbose=verbose, purpose=purpose), encoding="utf-8"
        )
        print(f"  apps/{pkg}/")

    print(f"\n{len(APPS)} ta ilova tayyor.")


if __name__ == "__main__":
    main()
