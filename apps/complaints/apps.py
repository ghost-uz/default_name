from django.apps import AppConfig


class ComplaintsConfig(AppConfig):
    """Complaint, Category, Tag, Vote, SavedItem."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.complaints"
    label = "complaints"
    verbose_name = "Muammolar"
