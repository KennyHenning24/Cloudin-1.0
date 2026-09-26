"""Historial de cambios (django-simple-history) con bases separadas.

Los modelos del restaurante viven en su propia base y los usuarios en la base
de control: una ForeignKey entre las dos no es posible. Por eso el historial
guarda el id del usuario como número y, además, una copia de su nombre (así la
«Actividad reciente» se lee sin cruzar bases y sobrevive si el usuario se borra).
"""

from django.db import models
from django.dispatch import receiver
from simple_history.models import HistoricalRecords
from simple_history.signals import pre_create_historical_record


def _usuario_del_historial(historial):
    from django.contrib.auth import get_user_model

    if not historial.history_user_id:
        return None
    return get_user_model().objects.filter(pk=historial.history_user_id).first()


def _asignar_usuario(historial, usuario):
    historial.history_user_id = usuario.pk if usuario else None


class HistorialConNombre(models.Model):
    """Campo extra de cada tabla histórica: quién hizo el cambio, en texto."""

    history_user_name = models.CharField("Hecho por", max_length=150, blank=True)

    class Meta:
        abstract = True


def historial(**opciones) -> HistoricalRecords:
    """HistoricalRecords listo para una base de restaurante."""
    excluidos = set(opciones.pop("excluded_fields", [])) | {"updated_at", "import_snapshot"}
    return HistoricalRecords(
        history_user_id_field=models.IntegerField(null=True, blank=True),
        history_user_getter=_usuario_del_historial,
        history_user_setter=_asignar_usuario,
        bases=[HistorialConNombre],
        excluded_fields=sorted(excluidos),
        **opciones,
    )


@receiver(pre_create_historical_record)
def _guardar_nombre_del_autor(sender, instance, history_instance, history_user=None, **kwargs):
    if not hasattr(history_instance, "history_user_name"):
        return
    usuario = history_user or getattr(history_instance, "history_user", None)
    if usuario is not None and getattr(usuario, "pk", None):
        history_instance.history_user_name = (usuario.get_full_name() or usuario.username)[:150]
