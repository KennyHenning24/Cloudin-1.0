from django.apps import AppConfig


class PublicMenuConfig(AppConfig):
    """La cara pública del menú: la API `cloudin.menu/v1`, el runtime y el menú de respaldo."""

    name = "apps.public_menu"
    label = "public_menu"
    verbose_name = "Menú público"
