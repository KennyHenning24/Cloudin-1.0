from django.apps import AppConfig


class CatalogConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.catalog"
    label = "catalog"
    verbose_name = "Menú"

    def ready(self):
        from . import signals  # noqa: F401  (la versión del menú sube con cada cambio)
