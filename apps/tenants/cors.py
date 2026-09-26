"""Permite CORS solo a los sitios web asignados a cada restaurante.

Cada restaurante registra en su panel la dirección de su página. Solo esa
dirección (su origen: esquema + host + puerto) puede llamar a la API desde el
navegador. Así no hace falta tocar la configuración del servidor cada vez que
entra un cliente nuevo.
"""

from corsheaders.signals import check_request_enabled
from django.dispatch import receiver

from .models import Tenant


def origenes_permitidos() -> set[str]:
    return {
        t.site_origin
        for t in Tenant.objects.filter(is_active=True).exclude(site_url="")
        if t.site_origin
    }


@receiver(check_request_enabled)
def permitir_sitio_del_restaurante(sender, request, **kwargs):
    origen = request.headers.get("Origin", "")
    return bool(origen) and origen in origenes_permitidos()
