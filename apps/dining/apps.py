from django.apps import AppConfig


class DiningConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.dining"
    label = "dining"
    verbose_name = "Salón y mesas"
