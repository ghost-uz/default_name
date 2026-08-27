from django.apps import AppConfig


class CommonConfig(AppConfig):
    """Abstrakt modellar, mixinlar, yordamchilar. Eng quyi qatlam — boshqa ilovalarga BOG'LANMAYDI."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.common"
    label = "common"
    verbose_name = "Umumiy"
