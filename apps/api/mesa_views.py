"""API de una mesa con QR: carta, carrito compartido y estado del pedido.

Todo cuelga del token de la mesa, que es lo que lleva su código QR. Varios
comensales pueden escanear el mismo QR: comparten el carrito y ven lo mismo,
porque el carrito vive aquí y no en el teléfono de cada uno.

La identificación es doble: la API key dice de qué restaurante es la petición,
y el token dice de qué mesa. Nadie tiene que registrarse.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes
from rest_framework.response import Response

from apps.catalog.models import Category, Product
from apps.catalog.opciones import aplicar as aplicar_opciones
from apps.dining.models import Table
from apps.orders.models import Order, OrderItem, TableDraft, TableSession
from apps.shifts.services import turno_actual

from .serializers import PREFETCH_PRODUCTOS, CategorySerializer

MAX_ITEMS = 60


def _mesa(token):
    return Table.objects.filter(token=token, is_active=True).first()


def _borrador(table) -> TableDraft:
    draft, _ = TableDraft.objects.get_or_create(table=table)
    return draft


def _pedidos_de(session):
    return [
        {
            "id": o.id,
            "estado": o.status,
            "estado_texto": o.get_status_display(),
            "creado": o.created_at,
            "por": o.customer_name,
            "total": o.total(),
            "items": [
                {"nombre": i.product_name, "cantidad": i.quantity, "nota": i.note}
                for i in o.items.all()
            ],
        }
        for o in session.orders.exclude(status=Order.STATUS_CANCELLED).order_by("created_at")
    ]


def _estado(table) -> dict:
    """La foto completa de la mesa: lo pedido, lo que se está armando y avisos."""
    session = table.open_session
    draft = _borrador(table)
    return {
        "mesa": table.number,
        "ocupada": session is not None,
        "cuenta": (
            {
                "id": session.id,
                "abierta_desde": session.opened_at,
                "total": session.current_total(),
                "pedidos": _pedidos_de(session),
            }
            if session
            else None
        ),
        "borrador": {
            "items": draft.items,
            "version": draft.version,
            "total": draft.total(),
            "actualizado": draft.updated_at,
        },
        "aviso": draft.aviso_vigente(),
        "servidor": timezone.now(),
    }


def _linea_del_menu(i):
    """Una línea con product_id: nombre y precio salen del panel, nunca del teléfono."""
    try:
        producto = Product.objects.filter(pk=int(i.get("product_id")), is_available=True).first()
    except (TypeError, ValueError):
        return None
    if producto is None:
        return None
    opciones = i.get("opciones") if isinstance(i.get("opciones"), list) else []
    nombre, precio, _, nota = aplicar_opciones(producto, opciones, str(i.get("note", "")))
    return producto, nombre, precio, opciones, nota


def _limpiar_items(items):
    """Deja los ítems del carrito en una forma segura y mínima.

    Acepta las dos formas de línea: del menú del panel (`product_id` + `opciones`)
    o armada en el sitio (`name` + `unit_price`)."""
    limpios = []
    for i in items[:MAX_ITEMS]:
        base = {
            "quantity": max(1, min(int(i.get("quantity", 1) or 1), 99)),
            "by": str(i.get("by", ""))[:60],
        }
        if i.get("product_id"):
            try:
                linea = _linea_del_menu(i)
            except ValidationError:
                continue  # le falta un topping obligatorio o ya no existe: no entra al carrito
            if linea is None:
                continue
            producto, nombre, precio, opciones, nota = linea
            limpios.append({**base, "key": str(i.get("key", producto.id))[:120], "product_id": producto.id,
                            "opciones": opciones, "name": nombre, "unit_price": float(precio), "note": nota})
            continue
        nombre = str(i.get("name", "")).strip()[:120]
        if not nombre:
            continue
        # Línea armada en el sitio: tiene que ser de la carta y no más barata que ella.
        from .limites import precio_seguro

        try:
            _, precio = precio_seguro(nombre, i.get("unit_price", 0))
        except ValueError:
            continue
        limpios.append({**base, "key": str(i.get("key", nombre))[:120], "name": nombre,
                        "unit_price": float(precio), "note": str(i.get("note", ""))[:200]})
    return limpios


# --------------------------------------------------------------- endpoints


@api_view(["GET"])
@authentication_classes([])  # se identifica con la API key, no con sesión
def mesa_inicio(request, token):
    """Carga inicial: la carta del panel (si la hay) y el estado de la mesa."""
    table = _mesa(token)
    if table is None:
        return Response(
            {"detail": "Este código QR no corresponde a ninguna mesa activa."},
            status=status.HTTP_404_NOT_FOUND,
        )
    tenant = request.tenant
    tenant.site_last_seen = timezone.now()
    tenant.save(update_fields=["site_last_seen"])

    categorias = Category.objects.filter(is_active=True, deleted_at__isnull=True).prefetch_related(
        *PREFETCH_PRODUCTOS)
    datos = _estado(table)
    datos["restaurante"] = tenant.name
    datos["categorias"] = CategorySerializer(categorias, many=True, context={"request": request}).data
    return Response(datos)


@api_view(["GET"])
@authentication_classes([])  # se identifica con la API key, no con sesión
def mesa_estado(request, token):
    """Sondeo liviano: lo que cambió en la mesa. Sin la carta."""
    table = _mesa(token)
    if table is None:
        return Response({"detail": "Mesa no encontrada."}, status=status.HTTP_404_NOT_FOUND)
    return Response(_estado(table))


@api_view(["PUT"])
@authentication_classes([])  # se identifica con la API key, no con sesión
def mesa_borrador(request, token):
    """Guarda el carrito compartido. Gana el último que escribe.

    Si el cliente manda `version` y no es la actual, se le responde 409 con el
    estado al día para que no pise lo que otro acabó de agregar.
    """
    from .limites import demasiados, permitido

    if not permitido(request, "mesa-borrador", 240, 600):
        return demasiados()
    table = _mesa(token)
    if table is None:
        return Response({"detail": "Mesa no encontrada."}, status=status.HTTP_404_NOT_FOUND)

    draft = _borrador(table)
    version_cliente = request.data.get("version")
    if version_cliente is not None and int(version_cliente) != draft.version:
        return Response(
            {"detail": "El pedido de la mesa cambió mientras editabas.", **_estado(table)},
            status=status.HTTP_409_CONFLICT,
        )

    draft.items = _limpiar_items(request.data.get("items", []))
    draft.version += 1
    draft.save(update_fields=["items", "version", "updated_at"])
    return Response(_estado(table))


@api_view(["POST"])
@authentication_classes([])  # se identifica con la API key, no con sesión
def mesa_aviso(request, token):
    """«Voy a enviar el pedido»: los demás lo ven en su pantalla."""
    table = _mesa(token)
    if table is None:
        return Response({"detail": "Mesa no encontrada."}, status=status.HTTP_404_NOT_FOUND)

    draft = _borrador(table)
    draft.announcing_by = str(request.data.get("by", "Alguien"))[:60]
    draft.announcing_at = timezone.now()
    draft.save(update_fields=["announcing_by", "announcing_at"])
    return Response(_estado(table))


@api_view(["POST"])
@authentication_classes([])  # se identifica con la API key, no con sesión
def mesa_enviar(request, token):
    """Convierte el carrito compartido en un pedido para la cocina."""
    from .limites import demasiados, permitido

    if not permitido(request, "mesa-enviar", 20, 600):
        return demasiados()
    if not request.tenant.usa_autoservicio:
        from .views import autoservicio_apagado

        return autoservicio_apagado()
    turno = turno_actual()
    if turno is None:
        from .views import sin_turno

        return sin_turno()
    table = _mesa(token)
    if table is None:
        return Response({"detail": "Mesa no encontrada."}, status=status.HTTP_404_NOT_FOUND)

    draft = _borrador(table)
    if not draft.items:
        return Response(
            {"detail": "El pedido de la mesa está vacío."}, status=status.HTTP_400_BAD_REQUEST
        )

    quien = str(request.data.get("by", ""))[:80]
    nota = str(request.data.get("note", ""))[:500]

    # Las líneas del menú se recalculan al enviar: el precio o los toppings pudieron cambiar.
    lineas = []
    for i in draft.items:
        if i.get("product_id"):
            try:
                linea = _linea_del_menu(i)
            except ValidationError as e:
                return Response({"detail": e.messages[0], "codigo": "opciones"},
                                status=status.HTTP_400_BAD_REQUEST)
            if linea is None:
                return Response({"detail": f"«{i.get('name', 'Un producto')}» ya no está disponible.",
                                 "codigo": "agotado"}, status=status.HTTP_409_CONFLICT)
            producto, nombre, precio, opciones, nota_linea = linea
            lineas.append((producto, nombre, precio, opciones, nota_linea, i["quantity"]))
        else:
            lineas.append((None, i["name"], Decimal(str(i["unit_price"])), [], i.get("note", ""), i["quantity"]))

    with transaction.atomic(using=table._state.db):
        session = table.open_session
        if session is None:
            session = TableSession.objects.create(
                table=table, customer_name=quien, turno=turno
            )
        order = Order.objects.create(
            session=session, source=Order.SOURCE_QR, customer_name=quien, note=nota
        )
        for producto, nombre, precio, opciones, nota_linea, cantidad in lineas:
            OrderItem.objects.create(
                order=order,
                product=producto,
                product_name=nombre,
                unit_price=precio,
                quantity=cantidad,
                note=nota_linea,
                opciones=opciones,
            )
        draft.limpiar()

    datos = _estado(table)
    datos["pedido_enviado"] = order.id
    return Response(datos, status=status.HTTP_201_CREATED)
