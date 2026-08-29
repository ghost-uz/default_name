from django.apps import AppConfig


class ModerationConfig(AppConfig):
    """Report, ModerationAction, AuditLog, avtomatik filtrlar."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.moderation"
    label = "moderation"
    verbose_name = "Moderatsiya"

    def ready(self) -> None:
        """Audit signalini ro'yxatdan o'tkazadi (D2-T7).

        ⚠️ Import SHU YERDA: modul darajasida qilinsa, ilovalar
           hali yuklanmagan paytda model import qilinardi
           (`AppRegistryNotReady`).
        """
        from . import audit  # noqa: F401 — signal ro'yxatga olinadi
