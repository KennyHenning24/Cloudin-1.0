from django.apps import AppConfig


class ImporterConfig(AppConfig):
    """Importa la semilla `cloudin/menu.seed.json` de un menú digital (contrato v1, sección 8)."""

    name = "apps.importer"
    label = "importer"
    verbose_name = "Importación de menús"
