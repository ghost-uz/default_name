from django.apps import AppConfig


class PaymentsConfig(AppConfig):
    """Subscription, BoostOrder, Click/Payme integratsiyasi."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.payments"
    label = "payments"
    verbose_name = "To'lovlar"
