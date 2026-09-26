"""Lógica de negocio de la carta.

Las vistas y la API llaman aquí; no cambian modelos por su cuenta. Esta etapa
trae lo mínimo que usa la API pública (la versión del menú); la API de
administración agrega el resto (reordenar, acciones masivas, fotos…).
"""

from django.db.models import F


def subir_version_del_menu(db: str | None = None) -> None:
    """Marca que el menú cambió: la API pública responde con un ETag nuevo.

    Se llama desde las señales de guardar/borrar y desde las operaciones
    masivas (que no disparan señales). `update()` no dispara señales, así que
    no hay ciclo. Se usa la base del objeto que cambió (`db`), no la del
    restaurante activo: así funciona también en comandos y scripts.
    """
    from apps.business.models import RestaurantSettings

    qs = RestaurantSettings.objects.using(db) if db else RestaurantSettings.objects
    if not qs.filter(pk=1).update(menu_version=F("menu_version") + 1):
        qs.get_or_create(pk=1)
