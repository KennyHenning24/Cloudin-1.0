"""Modelos base abstractos. No crean tablas: los heredan los modelos de cada app."""

import uuid

from django.db import models


class TimeStampedModel(models.Model):
    """Fecha de creación y de última modificación."""

    created_at = models.DateTimeField("Creado", auto_now_add=True)
    updated_at = models.DateTimeField("Actualizado", auto_now=True)

    class Meta:
        abstract = True


class PublicIdModel(TimeStampedModel):
    """Además, un identificador público (UUID).

    Es el que se expone en la API: el id autoincremental no sale del servidor
    en las rutas nuevas, porque deja adivinar cuántos registros hay.
    """

    uuid = models.UUIDField("ID público", default=uuid.uuid4, unique=True, editable=False)

    class Meta:
        abstract = True
