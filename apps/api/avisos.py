"""Endpoints del panel para los avisos de la barra lateral y las novedades de cuenta.

    GET  /api/v1/staff/avisos/                      contadores: mensajes, reservas, alertas
    POST /api/v1/staff/items/<id>/novedad/          anular, cortesía o devolución de una línea
    POST /api/v1/staff/sessions/<id>/descuento/     descuento sobre la cuenta
"""

from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.orders import novedades as nv
from apps.orders.models import Order, OrderItem, TableSession
from apps.shifts.services import turno_actual

from .permissions import IsTenantStaff
from .serializers import TableSessionSerializer


def _nombre(user):
    return user.get_full_name() or user.username


@api_view(["GET"])
@permission_classes([IsTenantStaff])
def staff_avisos(request):
    """Todo lo que la barra lateral cuenta, en una sola consulta cada pocos segundos."""
    from apps.control.models import AlertaControl
    from apps.reservas.models import Reserva
    from apps.reservas.services import atrasadas, pendientes_de_recordar

    # Mensajes: los pedidos que llegaron desde la última vez que se abrió la bandeja.
    clave = f"mensajes_leidos:{request.tenant.slug}"
    if request.GET.get("leer") == "1":
        request.session[clave] = timezone.now().isoformat()
    leido_hasta = request.session.get(clave)
    turno = turno_actual()
    mensajes = 0
    if turno is not None:
        base = Order.objects.filter(session__turno=turno)
        mensajes = (base.filter(created_at__gt=leido_hasta) if leido_hasta
                    else base.filter(seen_at__isnull=True)).count()

    if request.GET.get("reservas_vistas") == "1":
        Reserva.objects.filter(vista_en__isnull=True).update(vista_en=timezone.now())
    nuevas = Reserva.objects.filter(vista_en__isnull=True).exclude(estado=Reserva.CANCELLED)
    ultima = nuevas.order_by("-creada_en").first()

    return Response({
        "mensajes": mensajes,
        "reservas_nuevas": nuevas.count(),
        "ultima_reserva": ({"codigo": ultima.codigo, "nombre": ultima.nombre, "cuando": ultima.cuando_texto(),
                            "personas": ultima.personas} if ultima else None),
        "recordatorios": len(pendientes_de_recordar()),
        "atrasadas": len(atrasadas()),
        "alertas": AlertaControl.objects.filter(
            estado=AlertaControl.NEW, severidad__in=[AlertaControl.WARNING, AlertaControl.CRITICAL]).count(),
        "turno_abierto": turno is not None,
    })


def _autorizado(request):
    try:
        return nv.autorizar(request, request.data.get("clave_admin", "")), None
    except PermissionDenied as e:
        return None, Response({"detail": str(e), "codigo": "pide_autorizacion",
                               "es_admin": nv.es_admin(request.user)}, status=status.HTTP_403_FORBIDDEN)


@api_view(["POST"])
@permission_classes([IsTenantStaff])
def staff_item_novedad(request, item_id):
    item = get_object_or_404(OrderItem.objects.select_related("order__session"), pk=item_id)
    quien, error = _autorizado(request)
    if error:
        return error
    try:
        nv.novedad_en_linea(item, request.data.get("tipo"), request.data.get("cantidad", item.quantity),
                            request.data.get("motivo", ""), registrado_por=_nombre(request.user),
                            autorizado_por=quien)
    except ValidationError as e:
        return Response({"detail": e.messages[0]}, status=status.HTTP_400_BAD_REQUEST)
    return Response(TableSessionSerializer(item.order.session).data)


@api_view(["POST"])
@permission_classes([IsTenantStaff])
def staff_session_descuento(request, session_id):
    session = get_object_or_404(TableSession, pk=session_id)
    quien, error = _autorizado(request)
    if error:
        return error
    try:
        nv.aplicar_descuento(session, valor=request.data.get("valor"), porcentaje=request.data.get("porcentaje"),
                             motivo=request.data.get("motivo", ""), registrado_por=_nombre(request.user),
                             autorizado_por=quien)
    except ValidationError as e:
        return Response({"detail": e.messages[0]}, status=status.HTTP_400_BAD_REQUEST)
    session.refresh_from_db()
    return Response(TableSessionSerializer(session).data)
