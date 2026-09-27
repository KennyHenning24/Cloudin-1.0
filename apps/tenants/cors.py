"""Permite CORS solo a los sitios web asignados a cada restaurante.

Cada restaurante tiene registrados sus sitios: el de pedidos (site_url), la página
de su menú digital (menu_page, a la que lleva el QR) y otros orígenes autorizados
(allowed_origins: el dominio propio y el de Cloudflare Pages, por ejemplo). Solo
esos orígenes (esquema + host + puerto) pueden llamar a la API desde el navegador.
Así no hace falta tocar la configuración del servidor cada vez que entra un cliente.

La API pública del menú (/api/public/…) no pasa por aquí: responde con CORS abierto.
"""

from corsheaders.signals import check_request_enabled
from django.dispatch import receiver

from .models import Tenant


def origenes_permitidos() -> set[str]:
    origenes = set()
    for t in Tenant.objects.filter(is_active=True).only("site_url", "menu_page", "allowed_origins"):
        origenes |= t.origenes_permitidos
    return origenes


@receiver(check_request_enabled)
def permitir_sitio_del_restaurante(sender, request, **kwargs):
    origen = request.headers.get("Origin", "")
    return bool(origen) and origen in origenes_permitidos()
