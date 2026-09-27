"""Panel del restaurante: mesas, mensajes, cocina, configuración e impresión.

Las pantallas del menú digital (Mi menú, Personalizar, Mesas y QR, Cuenta) viven
en apps/panel/duenio.py; las de meseros en apps/panel/meseros.py.
"""

from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.validators import URLValidator, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.clickjacking import xframe_options_sameorigin

from apps.catalog.models import Category
from apps.dining.models import Table
from apps.orders.models import Order, TableSession


def panel_view(solo_admin=False, menu=False):
    """Resuelve el restaurante de la petición y controla quién puede entrar.

    En vez de un 404 seco, cada caso tiene su salida:
      - superusuario sin restaurante elegido -> lo mandamos al panel maestro,
      - usuario de otro restaurante o sin permiso -> página de "sin acceso",
      - plan «Menú digital» en una pantalla del plan completo -> al Inicio.

    `menu=True` marca las pantallas del menú digital (Mi menú, Personalizar,
    Mesas y QR, Cuenta): existen en los dos planes. Las demás (mesas, pedidos,
    cocina, meseros) son del plan completo.
    """

    def decorador(vista):
        @wraps(vista)
        @login_required
        def envoltura(request, *args, **kwargs):
            tenant = getattr(request, "tenant", None)

            if tenant is None:
                if request.user.is_superuser:
                    messages.warning(request, "Elige primero un restaurante.")
                    return redirect("master:home")
                raise PermissionDenied("No se identificó el restaurante de esta dirección.")

            if not request.user.is_superuser:
                membership = getattr(request.user, "tenant_membership", None)
                if membership is None or membership.tenant_id != tenant.id:
                    raise PermissionDenied("No tienes acceso a este restaurante.")
                if solo_admin and not membership.es_admin:
                    raise PermissionDenied(
                        "Esta sección es solo para el administrador del restaurante. "
                        "Pídele a quien administra el local que haga este cambio."
                    )

            request.tenant = tenant

            # El plan «Menú digital» solo tiene las pantallas del menú: lo demás
            # (mesas, pedidos, cocina, meseros) lleva al Inicio.
            if tenant.es_plan_menu and not menu:
                return redirect("panel:inicio")

            # Los términos y la política se aceptan una vez; sin eso no se entra.
            from .legal import ya_acepto

            if not ya_acepto(request):
                from urllib.parse import quote

                return redirect(f"{reverse('legal-aceptar')}?next={quote(request.get_full_path())}")

            # El superusuario no entra a un restaurante solo por tener la sesión
            # del panel maestro abierta: confirma su clave (modo soporte).
            if request.user.is_superuser:
                from urllib.parse import quote

                from .seguridad import soporte_vigente

                if not soporte_vigente(request, tenant):
                    return redirect(f"{reverse('panel:soporte')}?tenant={tenant.slug}&next={quote(request.get_full_path())}")
                request.modo_soporte = True

            return vista(request, *args, **kwargs)

        return envoltura

    return decorador


@panel_view()
def tables(request):
    return render(request, "panel/tables.html",
                  {"mesas": Table.objects.filter(is_active=True), "seccion": "mesas"})


@panel_view()
def table_detail(request, table_id):
    from apps.orders.novedades import es_admin

    table = get_object_or_404(Table, pk=table_id, is_active=True)
    categorias = Category.objects.filter(is_active=True).prefetch_related("products")
    return render(
        request,
        "panel/table_detail.html",
        {
            "mesa": table,
            "cuenta": table.open_session,
            "categorias": categorias,
            "seccion": "mesas",
            # Quien no es admin necesita la clave de uno para anular, dar cortesías o descuentos.
            "es_admin": es_admin(request.user),
            # Lo que el JS necesita para elegir toppings al agregar.
            "productos_js": {
                p.id: {"nombre": p.name, "precio": float(p.precio_legacy), "opciones": p.opciones or [],
                       "observacion": p.permite_observacion, "foto": p.foto}
                for c in categorias for p in c.products.all() if p.is_available
            },
        },
    )


@panel_view()
def kitchen(request):
    return render(request, "panel/kitchen.html", {"seccion": "cocina"})


@panel_view()
def mensajes(request):
    """Bandeja de pedidos que llegan del sitio web, por mesa y cliente."""
    return render(request, "panel/mensajes.html", {"seccion": "mensajes"})


@panel_view(solo_admin=True)
def configuracion(request):
    """Mesas, menú y conexión con el sitio web del restaurante."""
    tenant = request.tenant

    if request.method == "POST":
        url = (request.POST.get("site_url") or "").strip()
        if url:
            try:
                URLValidator(schemes=["http", "https"])(url)
            except ValidationError:
                messages.warning(
                    request, "Esa dirección no es válida. Debe empezar por https:// o http://"
                )
                return redirect("panel:configuracion")
        ruta = (request.POST.get("table_page_path") or "/mesa.html").strip()
        if not ruta.startswith("/"):
            ruta = "/" + ruta
        tenant.table_page_path = ruta[:120]
        tenant.site_url = url
        if not url:
            tenant.site_last_seen = None
        tenant.save(update_fields=["site_url", "site_last_seen", "table_page_path"])
        messages.success(
            request,
            f"Sitio web autorizado: {tenant.site_origin}" if url else "Sitio web desconectado.",
        )
        return redirect("panel:configuracion")

    return render(request, "panel/configuracion.html", {"seccion": "config"})


@panel_view(menu=True)
def inicio(request):
    """La portada del panel: el estado del menú digital (apps/panel/duenio.py) y,
    con el plan completo, además cómo van los pedidos y las mesas."""
    from .duenio import inicio_menu

    return inicio_menu(request)


def resumen_del_servicio() -> dict:
    """Mesas ocupadas, pedidos por atender y pedidos del día (plan completo)."""
    abiertas = TableSession.objects.filter(status=TableSession.STATUS_OPEN)
    return {
        "mesas": Table.objects.filter(is_active=True).count(),
        "ocupadas": abiertas.values("table").distinct().count(),
        "por_atender": Order.objects.filter(
            session__in=abiertas, status__in=[Order.STATUS_PENDING, Order.STATUS_PREPARING]).count(),
        "pedidos_hoy": Order.objects.filter(created_at__date=timezone.localdate())
        .exclude(status=Order.STATUS_CANCELLED).count(),
    }


def _qr_data_uri(texto: str) -> str:
    """El QR como imagen incrustada, para que la hoja se imprima sin pedir nada."""
    import base64
    import io

    import qrcode

    qr = qrcode.QRCode(box_size=10, border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(texto)
    qr.make(fit=True)
    buffer = io.BytesIO()
    qr.make_image(fill_color="black", back_color="white").save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


@panel_view(solo_admin=True)
def mesas_qr(request):
    """Hoja imprimible con un QR por mesa, para pegar en cada una."""
    tenant = request.tenant
    mesas = []
    for mesa in Table.objects.filter(is_active=True):
        enlace = tenant.qr_link(mesa.token)
        mesas.append({"mesa": mesa, "enlace": enlace, "qr": _qr_data_uri(enlace) if enlace else ""})
    return render(request, "panel/mesas_qr.html", {"mesas": mesas, "seccion": "config"})


@panel_view()
@xframe_options_sameorigin
def print_order(request, order_id):
    """Comanda en formato tirilla — dispara el diálogo de impresión del navegador."""
    order = get_object_or_404(Order, pk=order_id)
    return render(request, "panel/print_order.html", {"pedido": order})


@panel_view()
@xframe_options_sameorigin
def print_bill(request, session_id):
    """Precuenta de la mesa, o el comprobante de una mesa ya cerrada.
    No es una factura: lo dice impreso."""
    session = get_object_or_404(TableSession, pk=session_id)
    lineas = []
    for order in session.orders.exclude(status=Order.STATUS_CANCELLED):
        lineas.extend(order.items.all())
    return render(
        request,
        "panel/print_bill.html",
        {"cuenta": session, "lineas": lineas, "total": session.current_total()},
    )
