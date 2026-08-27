from django.apps import AppConfig


class ModerationConfig(AppConfig):
    """Report, ModerationAction, AuditLog, avtomatik filtrlar."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.moderation"
    label = "moderation"
    verbose_name = "Moderatsiya"
