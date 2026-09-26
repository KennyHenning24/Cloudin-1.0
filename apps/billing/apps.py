"""App retirada: Facturación electrónica (Factus / DIAN).

Cloudin quedó enfocado en el menú digital, los pedidos por QR, las mesas y los
meseros. De esta app solo quedan sus migraciones: la última borra sus tablas, así
las bases que ya existían se actualizan sin romperse y las nuevas quedan igual.
No le agregues código. Ver «Apps retiradas» en CONTEXTO-PARA-CODEX.md.
"""

from django.apps import AppConfig


class BillingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.billing"
    label = "billing"
    verbose_name = "Facturación electrónica (Factus / DIAN) (retirada)"
