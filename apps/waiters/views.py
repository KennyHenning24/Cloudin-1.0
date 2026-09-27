"""La app del mesero: entrar, ver las mesas y mandar pedidos a la cocina.

Vive en `/mesero/<slug>/`. El restaurante sale de la dirección y no del usuario
porque las tablets son compartidas y nadie tiene cuenta de Django: el slug dice
de qué base leer, y la sesión dice qué mesero de **esa** base está adentro.

Tres reglas de seguridad, todas en `app_mesero`:
  1. La sesión guarda el slug del restaurante; en otro slug no vale.
  2. El mesero tiene que existir y estar activo en esa base, en cada petición.
  3. Si el administrador le cambia la contraseña, las sesiones abiertas mueren.
"""

import json
from decimal import Decimal
from functools import wraps

from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.cache import cache
from django.db import models, transaction
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac
from django.views.decorators.http import require_GET, require_POST

from apps.catalog.models import Category, Product
from apps.dining.models import Table
from apps.orders.models import Order, TableSession
from apps.panel.seguridad import ip_de
from apps.tenants.context import set_current_tenant
from apps.tenants.models import Tenant

from .models import Mesero

CLAVE_SESION = "cloudin_mesero"
INTENTOS_MAXIMOS = 6
BLOQUEO_SEGUNDOS = 600


# ============================================================ seguridad


def _huella(mesero) -> str:
    """Cambia cuando cambia la contraseña: así se cierran las sesiones viejas."""
    return salted_hmac("cloudin.mesero", mesero.password).hexdigest()[:32]


def _tenant_o_404(slug):
    tenant = Tenant.objects.filter(slug=slug, is_active=True).first()
    if tenant is None:
        raise Http404("Restaurante no encontrado.")
    return tenant


def _activar(request, tenant):
    # Aunque el middleware haya resuelto otro restaurante (p. ej. un admin con
    # sesión abierta en el mismo navegador), aquí manda el de la dirección.
    request.tenant = tenant
    set_current_tenant(tenant)


def mesero_en_sesion(request, tenant):
    datos = request.session.get(CLAVE_SESION) or {}
    if datos.get("tenant") != tenant.slug or not datos.get("id"):
        return None
    mesero = Mesero.objects.filter(pk=datos["id"], activo=True).first()
    if mesero is None or not constant_time_compare(datos.get("huella", ""), _huella(mesero)):
        return None
    return mesero


def app_mesero(api=False):
    def decorador(vista):
        @wraps(vista)
        def envoltura(request, slug, *args, **kwargs):
            tenant = _tenant_o_404(slug)
            _activar(request, tenant)

            if not tenant.usa_meseros:
                if api:
                    return JsonResponse(
                        {"detail": "El servicio de meseros no está activo en este restaurante.",
                         "codigo": "meseros_apagado"}, status=403)
                return render(request, "mesero/desactivado.html", {"t": tenant}, status=403)

            mesero = mesero_en_sesion(request, tenant)
            if mesero is None:
                request.session.pop(CLAVE_SESION, None)
                if api:
                    return JsonResponse(
                        {"detail": "La sesión terminó. Vuelve a entrar.", "codigo": "sin_sesion"},
                        status=401)
                return redirect("mesero:entrar", slug=tenant.slug)

            request.mesero = mesero
            return vista(request, tenant, mesero, *args, **kwargs)

        return envoltura

    return decorador


# =============================================================== pantallas


def entrar(request, slug):
    tenant = _tenant_o_404(slug)
    _activar(request, tenant)
    if not tenant.usa_meseros:
        return render(request, "mesero/desactivado.html", {"t": tenant}, status=403)
    if mesero_en_sesion(request, tenant):
        return redirect("mesero:app", slug=tenant.slug)

    error = ""
    usuario = ""
    clave_bloqueo = f"mesero:intentos:{tenant.slug}:{ip_de(request)}"
    if request.method == "POST":
        usuario = (request.POST.get("usuario") or "").strip().lower()
        clave = request.POST.get("clave") or ""
        intentos = cache.get(clave_bloqueo, 0)
        if intentos >= INTENTOS_MAXIMOS:
            error = "Demasiados intentos. Espera unos minutos y vuelve a intentar."
        else:
            mesero = Mesero.objects.filter(usuario=usuario, activo=True).first()
            if mesero and mesero.check_password(clave):
                cache.delete(clave_bloqueo)
                request.session.cycle_key()
                request.session[CLAVE_SESION] = {
                    "tenant": tenant.slug, "id": mesero.pk, "huella": _huella(mesero),
                }
                # Una tablet de mesero dura la jornada completa y más.
                request.session.set_expiry(60 * 60 * 16)
                mesero.registrar_ingreso()
                return redirect("mesero:app", slug=tenant.slug)
            cache.set(clave_bloqueo, intentos + 1, BLOQUEO_SEGUNDOS)
            error = "Usuario o contraseña incorrectos."

    return render(request, "mesero/entrar.html",
                  {"t": tenant, "error": error, "usuario": usuario})


@require_POST
def salir(request, slug):
    # Solo la llave del mesero: si en el navegador hay un admin, sigue adentro.
    request.session.pop(CLAVE_SESION, None)
    return redirect("mesero:entrar", slug=slug)


@app_mesero()
def app(request, tenant, mesero):
    return render(request, "mesero/app.html", {"t": tenant, "m": mesero})


# ==================================================================== API


def _dinero(valor) -> float:
    return float(valor or 0)


def _pedido_json(order) -> dict:
    return {
        "id": order.id,
        "estado": order.status,
        "estado_texto": order.get_status_display(),
        "creado": timezone.localtime(order.created_at).strftime("%H:%M"),
        "mesero": order.mesero_nombre or ("Cliente (QR)" if order.source == Order.SOURCE_QR else ""),
        "origen": order.source,
        "nota": order.note,
        "total": _dinero(order.total()),
        "items": [
            {"nombre": i.product_name, "cantidad": i.quantity, "nota": i.note,
             "total": _dinero(i.line_total())}
            for i in order.items.all()
        ],
    }


def _mesa_json(table, session, mesero) -> dict:
    datos = {"id": table.id, "numero": table.number, "puestos": table.seats,
             "ocupada": session is not None}
    if session is not None:
        pedidos = [o for o in session.orders.all() if o.status != Order.STATUS_CANCELLED]
        datos.update({
            "cuenta_id": session.id,
            "cliente": session.customer_name,
            "personas": session.guests,
            "total": _dinero(sum((o.total() for o in pedidos), Decimal("0"))),
            "pedidos": len(pedidos),
            "en_cocina": sum(1 for o in pedidos
                             if o.status in (Order.STATUS_PENDING, Order.STATUS_PREPARING)),
            "mesero": session.mesero.nombre if session.mesero_id else "",
            "mia": session.mesero_id == mesero.id,
            "minutos": int((timezone.now() - session.opened_at).total_seconds() // 60),
        })
    return datos


def _sesiones_abiertas():
    return {
        s.table_id: s
        for s in TableSession.objects.filter(status=TableSession.STATUS_OPEN)
        .select_related("mesero").prefetch_related("orders__items")
    }


@require_GET
@app_mesero(api=True)
def api_mesas(request, tenant, mesero):
    abiertas = _sesiones_abiertas()
    mesas = [_mesa_json(t, abiertas.get(t.id), mesero) for t in Table.objects.filter(is_active=True)]
    return JsonResponse({
        "mesas": mesas,
        "hora": timezone.localtime().strftime("%H:%M"),
        "yo": _mis_numeros(mesero, mesas),
    })


def _mis_numeros(mesero, mesas) -> dict:
    """Lo que lleva el mesero hoy: vendido, mesas atendidas y comandas."""
    hoy = timezone.localdate()
    mios = (Order.objects.filter(mesero=mesero, created_at__date=hoy)
            .exclude(status=Order.STATUS_CANCELLED))
    vendido = sum((o.total() for o in mios.prefetch_related("items")), Decimal("0"))
    # Atendida = la mesa quedó a su nombre o él le mandó al menos una comanda.
    atendidas = (TableSession.objects.filter(opened_at__date=hoy)
                 .filter(models.Q(mesero=mesero) | models.Q(orders__mesero=mesero))
                 .distinct().count())
    return {
        "vendido": _dinero(vendido),
        "mesas_atendidas": atendidas,
        "pedidos": mios.count(),
        "mesas_activas": sum(1 for m in mesas if m.get("mia")),
    }


@require_GET
@app_mesero(api=True)
def api_menu(request, tenant, mesero):
    categorias = []
    from apps.catalog.legacy import PREFETCH_LEGACY

    prefetch = ["products", *(f"products__{r}" for r in PREFETCH_LEGACY)]
    for c in Category.objects.filter(is_active=True, deleted_at__isnull=True).prefetch_related(*prefetch):
        productos = [
            {"id": p.id, "nombre": p.name, "precio": _dinero(p.precio_legacy),
             "descripcion": p.description, "imagen": p.foto,
             "opciones": p.opciones or [], "observacion": p.permite_observacion}
            for p in c.products.all() if p.is_available and not p.eliminado
        ]
        if productos:
            categorias.append({"id": c.id, "nombre": c.name, "productos": productos})
    return JsonResponse({"categorias": categorias})


@require_GET
@app_mesero(api=True)
def api_mesa(request, tenant, mesero, numero):
    table = Table.objects.filter(number=numero, is_active=True).first()
    if table is None:
        return JsonResponse({"detail": f"No existe la mesa {numero}."}, status=404)
    session = _sesiones_abiertas().get(table.id)
    datos = _mesa_json(table, session, mesero)
    datos["lista_pedidos"] = (
        [_pedido_json(o) for o in session.orders.all().order_by("-created_at")
         if o.status != Order.STATUS_CANCELLED]
        if session else []
    )
    return JsonResponse(datos)


def _leer_json(request):
    try:
        return json.loads(request.body or b"{}")
    except ValueError:
        return None


@require_POST
@app_mesero(api=True)
def api_pedido(request, tenant, mesero, numero):
    """Manda un pedido a la cocina con el nombre del mesero."""
    from apps.api.views import _crear_pedido, _sesion_abierta

    datos = _leer_json(request)
    if datos is None:
        return JsonResponse({"detail": "El pedido llegó dañado."}, status=400)

    # Si la red se corta justo al enviar, la tablet reintenta con la misma
    # llave y no se duplica la comanda en la cocina.
    llave = str(datos.get("llave") or "")[:64]
    clave_llave = f"mesero:pedido:{tenant.slug}:{mesero.pk}:{llave}" if llave else None
    if clave_llave and cache.get(clave_llave):
        order = Order.objects.filter(pk=cache.get(clave_llave)).first()
        if order:
            return JsonResponse({"pedido": _pedido_json(order), "repetido": True}, status=200)

    table = Table.objects.filter(number=numero, is_active=True).first()
    if table is None:
        return JsonResponse({"detail": f"No existe la mesa {numero}."}, status=404)

    lineas = datos.get("items") or []
    if not isinstance(lineas, list) or not lineas:
        return JsonResponse({"detail": "El pedido está vacío."}, status=400)
    if len(lineas) > 60:
        return JsonResponse({"detail": "Son demasiados productos para una sola comanda."}, status=400)

    ids = []
    for linea in lineas:
        try:
            ids.append(int(linea.get("product_id")))
            cantidad = int(linea.get("quantity", 1))
        except (TypeError, ValueError, AttributeError):
            return JsonResponse({"detail": "Hay una línea del pedido que no se entiende."}, status=400)
        if not 1 <= cantidad <= 99:
            return JsonResponse({"detail": "La cantidad debe estar entre 1 y 99."}, status=400)

    productos = {p.id: p for p in Product.objects.filter(id__in=ids)}
    agotados = [str(i) for i in ids if i not in productos or not productos[i].is_available]
    if agotados:
        nombres = [productos[int(i)].name for i in agotados if int(i) in productos]
        return JsonResponse({
            "detail": ("Ya no está disponible: " + ", ".join(nombres)) if nombres
            else "Algún producto ya no está en el menú. Actualiza la pantalla.",
            "codigo": "agotado",
        }, status=409)

    items = [{
        "product_id": int(ln["product_id"]),
        "quantity": int(ln.get("quantity", 1)),
        "note": str(ln.get("note") or "")[:200],
        "opciones": ln.get("opciones") if isinstance(ln.get("opciones"), list) else [],
    } for ln in lineas]

    # Toppings y observación: se validan contra el producto antes de tocar la cocina.
    from django.core.exceptions import ValidationError

    from apps.catalog.opciones import aplicar

    for item in items:
        try:
            aplicar(productos[item["product_id"]], item["opciones"], item["note"])
        except ValidationError as e:
            return JsonResponse({"detail": e.messages[0], "codigo": "opciones"}, status=400)

    try:
        personas = max(1, min(int(datos.get("guests") or 1), 50))
    except (TypeError, ValueError):
        personas = 1
    cliente = str(datos.get("customer_name") or "")[:80]

    with transaction.atomic(using=table._state.db):
        session = _sesion_abierta(table, personas if not table.open_session else None,
                                  cliente, mesero=mesero)
        order = _crear_pedido(session, items, str(datos.get("note") or "")[:500],
                              source=Order.SOURCE_MESERO, customer_name=cliente, mesero=mesero)

    if clave_llave:
        cache.set(clave_llave, order.pk, 600)
    return JsonResponse({"pedido": _pedido_json(order)}, status=201)


@require_POST
@app_mesero(api=True)
def api_servido(request, tenant, mesero, pedido_id):
    """El mesero llevó el plato a la mesa."""
    order = Order.objects.filter(pk=pedido_id).exclude(status=Order.STATUS_CANCELLED).first()
    if order is None:
        return JsonResponse({"detail": "Pedido no encontrado."}, status=404)
    order.cambiar_estado(Order.STATUS_SERVED)
    return JsonResponse({"pedido": _pedido_json(order)})


# ===================================================================== PWA


@require_GET
def manifest(request, slug):
    tenant = _tenant_o_404(slug)
    base = reverse("mesero:app", kwargs={"slug": tenant.slug})
    contenido = {
        "name": f"Cloudin Meseros · {tenant.name}",
        "short_name": "Meseros",
        "description": f"Toma de pedidos de {tenant.name}",
        "lang": "es-CO",
        "start_url": base,
        "scope": base,
        "display": "standalone",
        "orientation": "any",
        "background_color": "#0e1015",
        "theme_color": "#13151c",
        "icons": [
            {"src": static("img/favicon-512.png"), "sizes": "512x512", "type": "image/png",
             "purpose": "any"},
            {"src": static("img/apple-touch-icon.png"), "sizes": "180x180", "type": "image/png"},
        ],
    }
    return HttpResponse(json.dumps(contenido, ensure_ascii=False),
                        content_type="application/manifest+json")


@require_GET
def service_worker(request):
    """El service worker se sirve desde /mesero/ para que su alcance cubra la app."""
    ruta = finders.find("mesero/sw.js")
    with open(ruta, encoding="utf-8") as archivo:
        codigo = archivo.read().replace("__VERSION__", getattr(settings, "MESERO_APP_VERSION", "1"))
    respuesta = HttpResponse(codigo, content_type="application/javascript")
    respuesta["Service-Worker-Allowed"] = "/mesero/"
    respuesta["Cache-Control"] = "no-cache"
    return respuesta
