from django.apps import AppConfig


class BusinessConfig(AppConfig):
    """Datos públicos del negocio: marca, contacto, redes, horario, servicios y pagos."""

    name = "apps.business"
    label = "business"
    verbose_name = "Datos del negocio"
