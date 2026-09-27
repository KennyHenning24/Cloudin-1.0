from django.apps import AppConfig


class CommonConfig(AppConfig):
    """Piezas compartidas: modelos base, claves estables, dinero e historial."""

    name = "apps.common"
    label = "common"
    verbose_name = "Común"

    def ready(self):
        from . import history  # noqa: F401  (registra la señal que guarda el nombre del autor)
