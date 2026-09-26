"""Cualquier cambio en la carta o en los datos del negocio sube la versión del menú."""

from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver

from .services import subir_version_del_menu

MODELOS_DEL_MENU = {
    ("catalog", "menu"), ("catalog", "category"), ("catalog", "product"), ("catalog", "productvariant"),
    ("catalog", "modifiergroup"), ("catalog", "modifieroption"), ("catalog", "productmodifiergroup"),
    ("catalog", "tag"), ("business", "restaurantsettings"), ("business", "openinghours"),
}


def _es_del_menu(modelo) -> bool:
    meta = getattr(modelo, "_meta", None)
    # Los modelos «de mentira» de las migraciones también mandan señales: se ignoran
    # (en ese momento la tabla de ajustes puede no existir todavía).
    if meta is None or modelo.__module__ == "__fake__":
        return False
    return (meta.app_label, meta.model_name) in MODELOS_DEL_MENU


@receiver(post_save)
@receiver(post_delete)
def _cambio_en_el_menu(sender, instance, **kwargs):
    if kwargs.get("raw") or not _es_del_menu(sender):
        return
    subir_version_del_menu(instance._state.db)


@receiver(m2m_changed)
def _cambio_de_etiquetas_o_grupos(sender, instance, action, **kwargs):
    if action in ("post_add", "post_remove", "post_clear") and _es_del_menu(type(instance)):
        subir_version_del_menu(instance._state.db)
