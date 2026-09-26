"""API pública del menú (`cloudin.menu/v1`) y menú de respaldo de Cloudin.

Rutas (el restaurante va en la ruta; el subdominio funciona igual si hay dominio):
    GET /api/public/<slug>/menu/[?table=<token|número>]
    GET /api/public/menu/                 (en <slug>.<dominio>)
    GET /m/<slug>/[?mesa=<token|número>]  menú listo para el QR si el restaurante no tiene sitio

Sin autenticación y solo lectura. Con ETag (sube con cada cambio del menú), caché
y CORS abierto: son datos públicos, sin cookies, y así funcionan igual en
pages.dev, en un dominio propio o en localhost.
"""

import time

from django.conf import settings
from django.core.cache import cache
from django.http import Http404, HttpResponseNotModified, JsonResponse
from django.shortcuts import redirect, render
from django.templatetags.static import static
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_GET

from apps.api.limites import permitido
from apps.tenants.context import tenant_context
from apps.tenants.models import Tenant

from . import selectors, serializers
from .horario import horario_de_hoy

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


def _para_plantilla(datos: dict) -> dict:
    """Agrega a una copia de los datos lo que la plantilla necesita ya formateado."""
    from apps.common.money import formato_cop

    nombres = {t["key"]: t["name"] for t in datos["tags"]}
    menus = []
    for m in datos["menus"]:
        categorias = []
        for c in m["categories"]:
            productos = []
            for p in c["products"]:
                precios = [x for x in (p["price"], *(v["price"] for v in p["variants"])) if x is not None]
                texto = formato_cop(min(precios)) if p["variants"] and precios else formato_cop(p["price"])
                productos.append({
                    **p,
                    "price_text": f"Desde {texto}" if p["variants"] else texto,
                    "variants": [{**v, "price_text": formato_cop(v["price"])} for v in p["variants"]],
                    "tag_items": [{"key": k, "name": nombres.get(k, k.replace("-", " ").capitalize())}
                                  for k in p["tags"]],
                })
            categorias.append({**c, "products": productos})
        menus.append({**m, "categories": categorias})
    return {**datos, "menus": menus}


@require_GET
@xframe_options_sameorigin
def menu_page(request, slug=None):
    tenant = _restaurante(request, slug)
    if tenant is None:
        raise Http404("Ese restaurante no existe o no está activo.")
    with tenant_context(tenant):
        datos = _para_plantilla(datos_del_menu(tenant, request))
        mesa = selectors.mesa_por_token_o_numero(request.GET.get("mesa", ""))
    negocio = datos["business"]
    menu = datos["menus"][0] if datos["menus"] else None
    base, _ = _constructor_de_urls(request)
    contexto = {
        "negocio": negocio,
        "menu": menu,
        "mesa": mesa,
        "hoy": horario_de_hoy(negocio["hours"]),
        "whatsapp_link": _whatsapp_link(negocio["contact"]["whatsapp"]),
        "api": f"{base}/api/public/{tenant.slug}/menu/",
        "runtime": base + static("cloudin-menu.v1.js"),
        "slug": tenant.slug,
        "sitio": tenant.site_url,
    }
    return render(request, "public_menu/menu.html", contexto)


def _whatsapp_link(numero) -> str:
    digitos = "".join(ch for ch in str(numero or "") if ch.isdigit())
    return f"https://wa.me/{digitos}" if digitos else ""


def raiz(request):
    """`<slug>.<dominio>/` muestra el menú; la raíz sin restaurante lleva al panel."""
    from apps.tenants.middleware import _tenant_from_host

    tenant = _tenant_from_host(request)
    if tenant is not None:
        return menu_page(request)
    return redirect("panel:inicio")
