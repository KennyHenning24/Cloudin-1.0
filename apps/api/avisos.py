"""Endpoints del panel para los avisos de la barra lateral y las novedades de cuenta.

    GET  /api/v1/staff/avisos/                      pedidos nuevos (el contador de Mensajes)
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

from .permissions import IsTenantStaff
from .serializers import TableSessionSerializer


def _nombre(user):
    return user.get_full_name() or user.username


@api_view(["GET"])
@permission_classes([IsTenantStaff])
def staff_avisos(request):
    """El contador de la barra lateral, en una consulta liviana cada pocos segundos:
    los pedidos de las mesas abiertas que llegaron desde la última vez que esta
    persona abrió Mensajes (`?leer=1` lo deja en cero)."""
    clave = f"mensajes_leidos:{request.tenant.slug}"
    if request.GET.get("leer") == "1":
        request.session[clave] = timezone.now().isoformat()
    leido_hasta = request.session.get(clave)
    base = Order.objects.filter(session__status=TableSession.STATUS_OPEN)
    mensajes = (base.filter(created_at__gt=leido_hasta) if leido_hasta
                else base.filter(seen_at__isnull=True)).count()
    return Response({"mensajes": mensajes})


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
