"""API de Cloudin.

Dos audiencias:
  - pública: la web del restaurante que abre el cliente al escanear el QR.
    Se identifica con la cabecera X-API-Key y el token de la mesa en la URL.
  - staff:   el panel del restaurante. Sesión de Django + pertenencia al tenant.
"""

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response

from apps.catalog.models import Category, Product
from apps.catalog.opciones import aplicar as aplicar_opciones
from apps.dining.models import Table
from apps.orders.models import Order, OrderItem, TableSession
from apps.shifts.services import MENSAJE_SIN_TURNO_CLIENTE, exigir_turno, turno_actual

from .permissions import IsTenantAdminParaEscribir, IsTenantStaff
from .serializers import (
    PREFETCH_PRODUCTOS,
    CategorySerializer,
    CategoryWriteSerializer,
    MenuCategorySerializer,
    OrderCreateSerializer,
    OrderSerializer,
    ProductSerializer,
    ProductWriteSerializer,
    TableSerializer,
    TableSessionSerializer,
    TableWriteSerializer,
)

# --------------------------------------------------------------- utilidades


def _crear_pedido(session, items, note="", source=Order.SOURCE_QR, customer_name="",
                  mesero=None):
    """Crea una comanda con sus ítems, congelando nombre y precio."""
    with transaction.atomic(using=session._state.db):
        order = Order.objects.create(
            session=session, note=note or "", source=source, customer_name=customer_name or "",
            mesero=mesero, mesero_nombre=mesero.nombre if mesero else "",
        )
        ids = [i["product_id"] for i in items if i.get("product_id")]
        productos = {p.id: p for p in Product.objects.filter(id__in=ids)}
        for item in items:
            producto = productos.get(item.get("product_id"))
            if producto:
                # Del menú: nombre, precio y toppings los calcula el servidor.
                nombre, precio, opciones, nota = aplicar_opciones(
                    producto, item.get("opciones"), item.get("note", ""))
            else:
                # Si la línea no es del menú, el nombre y el precio los manda el sitio.
                nombre, precio, opciones, nota = item["name"], item["unit_price"], [], item.get("note", "")
            OrderItem.objects.create(
                order=order,
                product=producto,
                product_name=nombre,
                unit_price=precio,
                quantity=item.get("quantity", 1),
                note=nota,
                opciones=opciones,
            )
    return order


def _sesion_abierta(table, guests=None, customer_name="", mesero=None):
    """Devuelve la cuenta abierta de la mesa; la abre si la mesa estaba libre.

    La cuenta queda colgada del turno de caja abierto. Sin turno abierto no se
    abre ninguna cuenta ni se agrega nada: lanza `SinTurno`.
    """
    turno = exigir_turno(table._state.db)
    session = table.open_session
    if session is None:
        return TableSession.objects.create(
            table=table, guests=guests or 1, customer_name=customer_name or "",
            turno=turno, mesero=mesero,
        )

    cambios = []
    # Una mesa abierta por QR que luego toma un mesero queda a su nombre.
    if mesero and not session.mesero_id:
        session.mesero = mesero
        cambios.append("mesero")
    if guests:
        session.guests = guests
        cambios.append("guests")
    # El nombre del cliente se completa si la cuenta se abrió sin él.
    if customer_name and not session.customer_name:
        session.customer_name = customer_name
        cambios.append("customer_name")
    if cambios:
        session.save(update_fields=cambios)
    return session


# ------------------------------------------------------------------ pública


@api_view(["GET"])
@authentication_classes([])  # se identifica con la API key, no con sesión
def ping(request):
    tenant = getattr(request, "tenant", None)
    return Response(
        {
            "ok": True,
            "servicio": "cloudin",
            "restaurante": tenant.name if tenant else None,
            "hora": timezone.now(),
        }
    )


@api_view(["GET"])
@authentication_classes([])  # se identifica con la API key, no con sesión
def menu(request):
    # ?formato=cloudin devuelve la carta en el mismo formato con que el sitio la
    # entrega (ver CONECTAR-MENU-A-CLOUDIN.md): así el sitio se pinta con lo del panel.
    if request.GET.get("formato") == "cloudin":
        from apps.catalog.formato import exportar

        return Response(exportar(request.tenant.name, request.build_absolute_uri))
    categorias = Category.objects.filter(is_active=True, deleted_at__isnull=True).prefetch_related(
        *PREFETCH_PRODUCTOS)
    return Response(
        {
            "restaurante": request.tenant.name,
            "categorias": CategorySerializer(categorias, many=True, context={"request": request}).data,
        }
    )


@api_view(["GET"])
@authentication_classes([])  # se identifica con la API key, no con sesión
def table_detail(request, token):
    table = get_object_or_404(Table, token=token, is_active=True)
    session = table.open_session
    return Response(
        {
            "mesa": TableSerializer(table).data,
            "cuenta": TableSessionSerializer(session).data if session else None,
        }
    )


def autoservicio_apagado():
    """Respuesta para el QR cuando el restaurante solo trabaja con meseros."""
    return Response(
        {"detail": "En este restaurante los pedidos los toma el mesero. Llámalo y con gusto te atiende.",
         "codigo": "solo_meseros"},
        status=status.HTTP_403_FORBIDDEN,
    )


def sin_turno():
    """Respuesta para quien intenta pedir cuando el restaurante no ha abierto turno."""
    return Response(
        {"detail": MENSAJE_SIN_TURNO_CLIENTE, "codigo": "sin_turno"},
        status=status.HTTP_409_CONFLICT,
    )


@api_view(["POST"])
@authentication_classes([])  # se identifica con la API key, no con sesión
def table_create_order(request, token):
    """El cliente envía su pedido desde la web del QR."""
    from .limites import demasiados, permitido

    if not permitido(request, "pedido-qr", 20, 600):
        return demasiados()
    if not request.tenant.usa_autoservicio:
        return autoservicio_apagado()
    if turno_actual() is None:
        return sin_turno()
    table = get_object_or_404(Table, token=token, is_active=True)
    serializer = OrderCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    datos = serializer.validated_data

    session = _sesion_abierta(table, datos.get("guests"), datos.get("customer_name", ""))
    order = _crear_pedido(
        session,
        datos["items"],
        datos.get("note", ""),
        source=Order.SOURCE_QR,
        customer_name=datos.get("customer_name", ""),
    )
    return Response(
        {"pedido": OrderSerializer(order).data, "cuenta_id": session.id},
        status=status.HTTP_201_CREATED,
    )


# ------------------------------------- sitio web del restaurante (tablet)
# Se autentica con la API key del restaurante. Mientras no haya un QR por mesa,
# el mesero elige la mesa en una lista y escribe el nombre del cliente.


def _marcar_sitio_conectado(tenant):
    """Registra que el sitio del restaurante habló con la API."""
    tenant.site_last_seen = timezone.now()
    tenant.save(update_fields=["site_last_seen"])


@api_view(["GET"])
@authentication_classes([])  # se identifica con la API key, no con sesión
def site_info(request):
    """Todo lo que el sitio necesita para pintar su pantalla: mesas y menú."""
    tenant = request.tenant
    _marcar_sitio_conectado(tenant)
    mesas = Table.objects.filter(is_active=True)
    categorias = Category.objects.filter(is_active=True, deleted_at__isnull=True).prefetch_related(
        *PREFETCH_PRODUCTOS)
    return Response(
        {
            "restaurante": tenant.name,
            "mesas": [
                {
                    "id": m.id,
                    "numero": m.number,
                    "nombre": str(m),
                    "puestos": m.seats,
                    "ocupada": m.is_occupied,
                }
                for m in mesas
            ],
            "categorias": CategorySerializer(categorias, many=True, context={"request": request}).data,
        }
    )


@api_view(["GET"])
@authentication_classes([])  # se identifica con la API key, no con sesión
def site_tables(request):
    """Estado del salón para el sitio: qué mesas hay y cuáles están ocupadas.

    Más liviano que /site/info/, pensado para refrescarse cada pocos segundos.
    """
    _marcar_sitio_conectado(request.tenant)
    reservas = _reservas_proximas()
    mesas = []
    for m in Table.objects.filter(is_active=True).order_by("number"):
        sesion = m.open_session
        reserva = reservas.get(m.id)
        mesas.append(
            {
                "numero": m.number,
                "puestos": m.seats,
                "zona": m.zona,
                "ocupada": sesion is not None,
                "desde": sesion.opened_at if sesion else None,
                # Una reserva que llega pronto a esa mesa (sin nombres: solo la hora).
                "reservada": reserva is not None,
                "reserva_hora": reserva,
            }
        )
    return Response({"mesas": mesas})


def _reservas_proximas():
    """Mesas con una reserva de hoy que llega en la próxima hora y media (o que se
    retrasó hasta 30 min): {mesa_id: "7:00 p. m."}."""
    from datetime import timedelta

    from apps.reservas.models import Reserva
    from apps.reservas.services import _hora_texto

    ahora = timezone.now()
    proximas = {}
    qs = Reserva.objects.filter(
        fecha=timezone.localdate(), mesa__isnull=False,
        estado__in=[Reserva.PENDING, Reserva.CONFIRMED, Reserva.ARRIVED],
    ).select_related("servicio")
    for r in sorted(qs, key=lambda r: r.inicio):
        if ahora - timedelta(minutes=30) <= r.inicio <= ahora + timedelta(minutes=90):
            proximas.setdefault(r.mesa_id, _hora_texto(timezone.localtime(r.inicio)))
    return proximas


@api_view(["GET"])
@authentication_classes([])  # se identifica con la API key, no con sesión
def site_table_orders(request, numero):
    """Lo que lleva pedido una mesa y en qué va cada pedido.

    El cliente sentado en la mesa consulta esto para ver su pedido avanzar:
    recibido -> en preparación -> listo.
    """
    table = Table.objects.filter(number=numero, is_active=True).first()
    if table is None:
        return Response({"detail": f"La mesa {numero} no existe."}, status=status.HTTP_404_NOT_FOUND)

    sesion = table.open_session
    if sesion is None:
        return Response({"mesa": table.number, "ocupada": False, "pedidos": [], "total": 0})

    pedidos = [
        {
            "id": o.id,
            "estado": o.status,
            "estado_texto": o.get_status_display(),
            "creado": o.created_at,
            "cliente": o.customer_name,
            "total": o.total(),
            "items": [
                {"nombre": i.product_name, "cantidad": i.quantity, "nota": i.note}
                for i in o.items.all()
            ],
        }
        for o in sesion.orders.exclude(status=Order.STATUS_CANCELLED).order_by("created_at")
    ]
    return Response(
        {
            "mesa": table.number,
            "ocupada": True,
            "cuenta_id": sesion.id,
            "cliente": sesion.customer_name,
            "abierta_desde": sesion.opened_at,
            "total": sesion.current_total(),
            "pedidos": pedidos,
        }
    )


@api_view(["POST"])
@authentication_classes([])  # se identifica con la API key, no con sesión
def site_create_order(request):
    """El mesero manda el pedido desde la tablet: mesa + nombre + productos."""
    from .limites import demasiados, permitido

    if not permitido(request, "pedido-sitio", 30, 600):
        return demasiados()
    if turno_actual() is None:
        return sin_turno()
    numero = request.data.get("table_number")
    if numero in (None, ""):
        return Response(
            {"detail": "Falta 'table_number' (el número de la mesa)."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    table = Table.objects.filter(number=numero, is_active=True).first()
    if table is None:
        disponibles = sorted(Table.objects.filter(is_active=True).values_list("number", flat=True))
        return Response(
            {
                "detail": f"La mesa {numero} no existe en el panel."
                + (
                    f" Las mesas activas son: {', '.join(map(str, disponibles))}."
                    if disponibles
                    else " El restaurante todavía no ha creado ninguna mesa."
                ),
                "mesas_disponibles": disponibles,
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    serializer = OrderCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    datos = serializer.validated_data

    _marcar_sitio_conectado(request.tenant)
    nombre = datos.get("customer_name", "").strip()
    session = _sesion_abierta(table, datos.get("guests"), nombre)
    order = _crear_pedido(
        session,
        datos["items"],
        datos.get("note", ""),
        source=Order.SOURCE_PANEL,
        customer_name=nombre,
    )
    return Response(
        {
            "ok": True,
            "pedido_id": order.id,
            "mesa": table.number,
            "cliente": nombre,
            "total": order.total(),
            "cuenta_id": session.id,
            "cuenta_total": session.current_total(),
        },
        status=status.HTTP_201_CREATED,
    )


# -------------------------------------------------------------------- staff


@api_view(["GET", "POST"])
@permission_classes([IsTenantAdminParaEscribir])
def staff_tables(request):
    if request.method == "POST":
        serializer = TableWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        table = serializer.save()
        return Response(TableSerializer(table).data, status=status.HTTP_201_CREATED)

    incluir_inactivas = request.GET.get("todas") == "1"
    tables = Table.objects.all() if incluir_inactivas else Table.objects.filter(is_active=True)
    return Response(TableSerializer(tables, many=True).data)


@api_view(["PATCH", "DELETE"])
@permission_classes([IsTenantAdminParaEscribir])
def staff_table_detail(request, table_id):
    table = get_object_or_404(Table, pk=table_id)

    if request.method == "DELETE":
        if table.sessions.exists():
            # Tiene historial de cuentas: se desactiva en vez de borrarse, para
            # no perder los pedidos que ya pasaron por ella.
            table.is_active = False
            table.save(update_fields=["is_active"])
            return Response({"desactivada": True, "eliminada": False})
        table.delete()
        return Response({"desactivada": False, "eliminada": True})

    serializer = TableWriteSerializer(table, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(TableSerializer(table).data)


@api_view(["GET"])
@permission_classes([IsTenantStaff])
def staff_session(request, session_id):
    session = get_object_or_404(TableSession, pk=session_id)
    return Response(TableSessionSerializer(session).data)


@api_view(["POST"])
@permission_classes([IsTenantStaff])
def staff_open_table(request, table_id):
    table = get_object_or_404(Table, pk=table_id, is_active=True)
    session = _sesion_abierta(table, request.data.get("guests"))
    return Response(TableSessionSerializer(session).data, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsTenantStaff])
def staff_create_order(request, table_id):
    """El mesero toma el pedido desde el panel."""
    table = get_object_or_404(Table, pk=table_id, is_active=True)
    serializer = OrderCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    datos = serializer.validated_data

    session = _sesion_abierta(table, datos.get("guests"))
    order = _crear_pedido(
        session, datos["items"], datos.get("note", ""), source=Order.SOURCE_PANEL
    )
    return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)


@api_view(["PATCH"])
@permission_classes([IsTenantStaff])
def staff_order_status(request, order_id):
    order = get_object_or_404(Order, pk=order_id)
    nuevo = request.data.get("status")
    validos = dict(Order.STATUS)
    if nuevo not in validos:
        return Response(
            {"detail": f"Estado inválido. Opciones: {list(validos)}"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if nuevo == Order.STATUS_CANCELLED:
        # Anular deja rastro (motivo y autorización): va por la cuenta de la mesa.
        return Response(
            {"detail": "Para anular usa «Anular» en la cuenta de la mesa: pide el motivo y la autorización."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    order.cambiar_estado(nuevo)
    return Response(OrderSerializer(order).data)


@api_view(["GET"])
@permission_classes([IsTenantStaff])
def staff_kitchen(request):
    """Comandas activas, para la vista de cocina (se refresca por polling)."""
    turno = turno_actual()
    if turno is None:
        return Response([])
    pedidos = (
        Order.objects.filter(
            status__in=[Order.STATUS_PENDING, Order.STATUS_PREPARING],
            session__status=TableSession.STATUS_OPEN,
            session__turno=turno,
        )
        .select_related("session", "session__table")
        .prefetch_related("items")
        .order_by("created_at")
    )
    return Response(OrderSerializer(pedidos, many=True).data)


# ------------------------------------------------------------- menú (panel)


@api_view(["GET"])
@permission_classes([IsTenantStaff])
def staff_site_status(request):
    """Estado de la conexión con el sitio web del restaurante.

    'Conectado' significa que el sitio llamó a la API hace poco, que es la
    única señal real de que está funcionando.
    """
    tenant = request.tenant
    ultima = tenant.site_last_seen
    hoy = timezone.localdate()
    return Response(
        {
            "site_url": tenant.site_url,
            "origen": tenant.site_origin,
            "ultima_conexion": ultima,
            "conectado": bool(ultima and (timezone.now() - ultima).total_seconds() < 300),
            "pedidos_hoy": Order.objects.filter(created_at__date=hoy).count(),
            "pedidos_total": Order.objects.count(),
        }
    )


@api_view(["GET"])
@permission_classes([IsTenantStaff])
def staff_menu(request):
    """El menú completo para editarlo: incluye categorías y productos apagados."""
    categorias = Category.objects.filter(deleted_at__isnull=True).prefetch_related(*PREFETCH_PRODUCTOS)
    return Response(MenuCategorySerializer(categorias, many=True).data)


@api_view(["POST"])
@permission_classes([IsTenantAdminParaEscribir])
def staff_categories(request):
    serializer = CategoryWriteSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    categoria = serializer.save()
    return Response(MenuCategorySerializer(categoria).data, status=status.HTTP_201_CREATED)


@api_view(["PATCH", "DELETE"])
@permission_classes([IsTenantAdminParaEscribir])
def staff_category_detail(request, category_id):
    categoria = get_object_or_404(Category, pk=category_id)

    if request.method == "DELETE":
        if categoria.products.exists():
            return Response(
                {"detail": "La categoría tiene productos. Muévelos o bórralos primero."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        categoria.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    serializer = CategoryWriteSerializer(categoria, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(MenuCategorySerializer(categoria).data)


@api_view(["POST"])
@permission_classes([IsTenantAdminParaEscribir])
def staff_products(request):
    serializer = ProductWriteSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    producto = serializer.save()
    return Response(ProductSerializer(producto).data, status=status.HTTP_201_CREATED)


@api_view(["PATCH", "DELETE"])
@permission_classes([IsTenantAdminParaEscribir])
def staff_product_detail(request, product_id):
    producto = get_object_or_404(Product, pk=product_id)

    if request.method == "DELETE":
        # Sale de la carta en todas partes (panel, sitio, meseros, QR). Se
        # conserva por debajo para no romper pedidos ni facturas viejas y para
        # que reimportar la carta del sitio no lo vuelva a crear.
        producto.eliminado = True
        producto.is_available = False
        producto.save(update_fields=["eliminado", "is_available"])
        return Response({"ocultado": False, "eliminado": True})

    # Nombre, precio y categoría de un plato que ya existe solo los cambia Cloudin
    # (la misma regla de la ficha del producto en el panel).
    if not request.user.is_superuser and any(c in request.data for c in ("name", "price", "category")):
        return Response({"detail": "El nombre, el precio y la categoría de un plato los cambia Cloudin. "
                                   "Escríbenos si necesitas ajustarlos."}, status=status.HTTP_403_FORBIDDEN)
    serializer = ProductWriteSerializer(producto, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(ProductSerializer(producto).data)


# --------------------------------------------------------- mensajes (panel)


@api_view(["GET"])
@permission_classes([IsTenantStaff])
def staff_messages(request):
    """Bandeja de pedidos: lo último que llegó, con su mesa y su cliente.

    El panel la consulta cada pocos segundos. `sin_ver` le sirve para avisar
    cuántos mensajes nuevos hay desde la última mirada.
    """
    limite = min(int(request.GET.get("limite", 40)), 200)
    # Solo el turno abierto: al cerrar el turno la bandeja queda vacía y lo
    # anterior se consulta en el informe de ese turno, no aquí.
    turno = turno_actual()
    pedidos = Order.objects.none()
    sin_ver = 0

    # El contador de la barra lateral: cuántos pedidos llegaron desde la última
    # vez que esta persona abrió Mensajes. Abrir la bandeja (`?leer=1`) lo deja
    # en cero; si no la abre, cada pedido nuevo lo sube uno.
    clave = f"mensajes_leidos:{request.tenant.slug}"
    if request.GET.get("leer") == "1":
        request.session[clave] = timezone.now().isoformat()
    leido_hasta = request.session.get(clave)

    if turno is not None:
        base = Order.objects.filter(session__turno=turno)
        pedidos = (
            base.select_related("session", "session__table")
            .prefetch_related("items")
            .order_by("-created_at")[:limite]
        )
        if leido_hasta:
            sin_ver = base.filter(created_at__gt=leido_hasta).count()
        else:
            sin_ver = base.filter(seen_at__isnull=True).count()
    return Response(
        {
            "sin_ver": sin_ver,
            "turno": turno.numero if turno else None,
            "turno_abierto": turno is not None,
            "mensajes": OrderSerializer(pedidos, many=True).data,
        }
    )


@api_view(["POST"])
@permission_classes([IsTenantStaff])
def staff_order_seen(request, order_id):
    order = get_object_or_404(Order, pk=order_id)
    order.mark_seen()
    return Response(OrderSerializer(order).data)


@api_view(["POST"])
@permission_classes([IsTenantStaff])
def staff_order_printed(request, order_id):
    """La comanda salió por la impresora: suma una impresión."""
    order = get_object_or_404(Order, pk=order_id)
    order.mark_printed()
    return Response({"id": order.id, "impresiones": order.impresiones})


@api_view(["POST"])
@permission_classes([IsTenantStaff])
def staff_close_session(request, session_id):
    """Cierra la cuenta y libera la mesa.

    Fase 2: aquí se llamará al proveedor de facturación electrónica antes de
    devolver la respuesta, y se guardará el CUFE / PDF / XML.
    """
    from django.core.exceptions import ValidationError

    from apps.shifts.propinas import registrar_propina

    session = get_object_or_404(TableSession, pk=session_id)
    if session.status != TableSession.STATUS_OPEN:
        return Response(
            {"detail": "La cuenta ya estaba cerrada."}, status=status.HTTP_400_BAD_REQUEST
        )
    session.close()
    try:
        registrar_propina(session, request.data.get("propina") or 0,
                          str(request.data.get("propina_medio") or "10")[:4])
    except ValidationError as e:
        return Response({"detail": e.messages[0], "cerrada": True}, status=status.HTTP_400_BAD_REQUEST)
    return Response(TableSessionSerializer(session).data)
