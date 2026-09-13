from django.apps import AppConfig


class ReklamaConfig(AppConfig):
    """Kontekstual reklama joylari (D6-T6)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.reklama"
    label = "reklama"
    verbose_name = "Reklama"
