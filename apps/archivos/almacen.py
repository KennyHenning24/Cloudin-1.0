"""Almacenamiento de las fotos dentro de la base de datos (settings: FOTOS_EN_LA_BASE).

Para el plan gratis de Render: su disco se borra cada vez que el servicio se duerme o
se despliega, y R2 pide tarjeta. Las fotos del panel llegan convertidas a WebP de
pocos cientos de KB (catalog/images.py), así que caben de sobra en la base de Neon.

Se sirven en MEDIA_URL (/media/<nombre>, ver views.py) con caché de un año: Django
nunca reescribe un nombre, a uno repetido le agrega un sufijo (get_available_name).
Con R2 configurado, R2 gana: este almacenamiento no se usa.
"""

import mimetypes
from urllib.parse import urljoin

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible
from django.utils.encoding import filepath_to_uri

from .models import Archivo


@deconstructible
class AlmacenEnLaBase(Storage):
    def _save(self, name, content):
        datos = b"".join(content.chunks())
        tipo = mimetypes.guess_type(name)[0] or "application/octet-stream"
        Archivo.objects.create(nombre=name, contenido=datos, tipo=tipo)
        return name

    def _open(self, name, mode="rb"):
        archivo = Archivo.objects.filter(nombre=name).only("contenido").first()
        if archivo is None:
            raise FileNotFoundError(f"No hay ningún archivo guardado con el nombre {name}.")
        return ContentFile(bytes(archivo.contenido), name=name)

    def exists(self, name):
        return Archivo.objects.filter(nombre=name).exists()

    def delete(self, name):
        Archivo.objects.filter(nombre=name).delete()

    def size(self, name):
        archivo = Archivo.objects.filter(nombre=name).only("contenido").first()
        if archivo is None:
            raise FileNotFoundError(name)
        return len(archivo.contenido)

    def url(self, name):
        return urljoin(settings.MEDIA_URL, filepath_to_uri(name))
