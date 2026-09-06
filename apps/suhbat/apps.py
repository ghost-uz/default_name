from django.apps import AppConfig


class SuhbatConfig(AppConfig):
    """Kontakt so'rovi va yopiq suhbat (D6-T5)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.suhbat"
    label = "suhbat"
    verbose_name = "Suhbatlar"
