from django.apps import AppConfig


class TenantsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.tenants"
    label = "tenants"
    verbose_name = "Restaurantes (panel maestro)"

    def ready(self):
        from . import cors  # noqa: F401  — conecta la señal de CORS
