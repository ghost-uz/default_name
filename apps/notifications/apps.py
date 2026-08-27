from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    """Notification, Telegram bot dispatch."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.notifications"
    label = "notifications"
    verbose_name = "Bildirishnomalar"
