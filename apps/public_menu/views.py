"""API pública del menú (`cloudin.menu/v1`).

Cloudin no crea ni sirve menús: cada restaurante tiene el suyo, diseñado aparte (su
sitio en Cloudflare Pages), y dentro va el runtime `cloudin-menu.v1.js`, que lee esta
API. Guía para conectar un menú y recibir pedidos: GUIA-MENU-DIGITAL.md.

Rutas (el restaurante va en la ruta; el subdominio funciona igual si hay dominio):
    GET /api/public/<slug>/menu/[?table=<token|número>]
    GET /api/public/menu/                 (en <slug>.<dominio>)

Sin autenticación y solo lectura. Con ETag (sube con cada cambio del menú), caché
y CORS abierto: son datos públicos, sin cookies, y así funcionan igual en
pages.dev, en un dominio propio o en localhost.
"""

import time

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponseNotModified, JsonResponse
from django.shortcuts import redirect
from django.views.decorators.http import require_GET

from apps.api.limites import permitido
from apps.tenants.context import tenant_context
from apps.tenants.models import Tenant

from . import selectors, serializers

TOPE_POR_IP = 600          # peticiones…
VENTANA_TOPE = 10 * 60     # …cada 10 minutos (un restaurante lleno comparte la IP del wifi)
CACHE_CONTROL = "public, max-age=30"


def _restaurante(request, slug=None):
    from apps.tenants.middleware import _tenant_from_debug_hint, _tenant_from_host

    if slug:
        return Tenant.objects.filter(slug=slug, is_active=True).first()
    return _tenant_from_host(request) or _tenant_from_debug_hint(request)


def _constructor_de_urls(request):
    base = (getattr(settings, "CLOUDIN_PUBLIC_URL", "") or "").rstrip("/")
    if base:
        return base, (lambda ruta: base + ruta)
    return request.build_absolute_uri("/").rstrip("/"), request.build_absolute_uri


def _cors(respuesta):
    respuesta["Access-Control-Allow-Origin"] = "*"
    respuesta["Access-Control-Expose-Headers"] = "ETag"
    respuesta["Cache-Control"] = CACHE_CONTROL
    return respuesta


def _marcar_visto(tenant):
    """Recuerda en la caché cuándo se pidió el menú por última vez (el «En línea» del
    Inicio). No toca `Tenant.site_last_seen`: ese es el indicador del sitio conectado
    con llave de la pantalla de Configuración."""
    cache.set(f"menu_visto:{tenant.slug}", time.time(), 24 * 60 * 60)


def datos_del_menu(tenant, request) -> dict:
    """El JSON completo del restaurante (se guarda en caché por versión del menú)."""
    base, construir_url = _constructor_de_urls(request)
    version = selectors.ajustes().menu_version
    llave = f"menu_publico:{tenant.slug}:{version}:{base}"
    datos = cache.get(llave)
    if datos is None:
        datos = serializers.menu_publico(
            tenant, selectors.menus_publicos(), selectors.ajustes(), selectors.horario(),
            selectors.etiquetas(), construir_url,
        )
        cache.set(llave, datos, 60 * 60)
    return datos


@require_GET
def menu_api(request, slug=None):
    tenant = _restaurante(request, slug)
    if tenant is None:
        return _cors(JsonResponse({"detail": "Ese restaurante no existe o no está activo."}, status=404))
    request.tenant = tenant
    if not permitido(request, "menu_publico", TOPE_POR_IP, VENTANA_TOPE):
        return _cors(JsonResponse({"detail": "Demasiadas consultas seguidas. Intenta en unos minutos."},
                                  status=429))

    with tenant_context(tenant):
        mesa = selectors.mesa_por_token_o_numero(request.GET.get("table", ""))
        version = selectors.ajustes().menu_version
        etag = f'W/"{tenant.slug}-{version}{f"-m{mesa.number}" if mesa else ""}"'
        if request.GET.get("vista") != "panel":  # la vista previa del dueño no es una visita
            _marcar_visto(tenant)
        if etag in [e.strip() for e in request.headers.get("If-None-Match", "").split(",")]:
            respuesta = HttpResponseNotModified()
            respuesta["ETag"] = etag
            return _cors(respuesta)
        datos = dict(datos_del_menu(tenant, request))
        if mesa is not None:
            datos["table"] = {"number": mesa.number}

    respuesta = JsonResponse(datos, json_dumps_params={"ensure_ascii": False})
    respuesta["ETag"] = etag
    return _cors(respuesta)


def raiz(request):
    """`<slug>.<dominio>/` lleva al menú del restaurante (su página); sin restaurante, al panel."""
    from apps.tenants.middleware import _tenant_from_host

    tenant = _tenant_from_host(request)
    if tenant is not None and tenant.menu_page:
        return redirect(tenant.menu_page)
    return redirect("panel:inicio")
