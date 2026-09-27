from django.http import Http404, HttpResponse
from django.views.decorators.http import require_GET

from .models import Archivo


@require_GET
def servir(request, nombre):
    """Una foto guardada en la base (FOTOS_EN_LA_BASE). Pública, como en R2: sale en
    el menú de cada restaurante. Un nombre nunca se reescribe: caché de un año."""
    archivo = Archivo.objects.filter(nombre=nombre).only("contenido", "tipo").first()
    if archivo is None:
        raise Http404("Esa foto no existe.")
    respuesta = HttpResponse(bytes(archivo.contenido), content_type=archivo.tipo or "application/octet-stream")
    respuesta["Cache-Control"] = "public, max-age=31536000, immutable"
    return respuesta
