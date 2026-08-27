from django.apps import AppConfig


class AccountsConfig(AppConfig):
    """User, Telegram login, sessiyalar, ExpertProfile."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    label = "accounts"
    verbose_name = "Foydalanuvchilar"
