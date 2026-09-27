"""App retirada: Turnos de caja y propinas.

Cloudin quedó enfocado en el menú digital, los pedidos por QR, las mesas y los
meseros. De esta app solo quedan sus migraciones: la última borra sus tablas, así
las bases que ya existían se actualizan sin romperse y las nuevas quedan igual.
No le agregues código. Ver «Apps retiradas» en CONTEXTO-PARA-CODEX.md.
"""

from django.apps import AppConfig


class ShiftsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.shifts"
    label = "shifts"
    verbose_name = "Turnos de caja y propinas (retirada)"
