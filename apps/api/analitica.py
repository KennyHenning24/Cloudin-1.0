"""Datos para el tablero de ventas y facturación.

Todo se calcula sobre la base del restaurante: ventas de sus pedidos e
impuestos de sus documentos fiscales. Un solo endpoint para que la pantalla
cargue de una vez y no haga seis llamadas.
"""

from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Sum
from django.db.models.functions import ExtractHour, ExtractIsoWeekDay, TruncDate
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.billing.models import DocumentoFiscal
from apps.orders.models import Order, OrderItem, TableSession

from .permissions import IsTenantStaff

# El valor de una línea: precio unitario por cantidad.
LINEA = ExpressionWrapper(
    F("unit_price") * F("quantity"), output_field=DecimalField(max_digits=14, decimal_places=2)
)
DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]


def _lineas():
    # Lo anulado, las cortesías y las devoluciones no son ventas.
    return OrderItem.objects.exclude(order__status=Order.STATUS_CANCELLED).filter(novedad="")


def _ventas(desde=None, hasta=None) -> dict:
    qs = _lineas()
    if desde:
        qs = qs.filter(order__created_at__date__gte=desde)
    if hasta:
        qs = qs.filter(order__created_at__date__lte=hasta)
    datos = qs.aggregate(total=Sum(LINEA), pedidos=Count("order", distinct=True))
    cuentas = TableSession.objects.all()
    if desde:
        cuentas = cuentas.filter(opened_at__date__gte=desde)
    if hasta:
        cuentas = cuentas.filter(opened_at__date__lte=hasta)
    descuentos = cuentas.aggregate(t=Sum("descuento"))["t"] or Decimal("0")
    total = (datos["total"] or Decimal("0")) - descuentos
    pedidos = datos["pedidos"] or 0
    return {
        "total": total,
        "pedidos": pedidos,
        "ticket": (total / pedidos) if pedidos else Decimal("0"),
    }


def _variacion(actual: Decimal, anterior: Decimal):
    """Cuánto subió o bajó contra el período anterior, en porcentaje."""
    if not anterior:
        return None
    return round(float((actual - anterior) / anterior * 100), 1)


@api_view(["GET"])
@permission_classes([IsTenantStaff])
def staff_analitica(request):
    dias = max(1, min(int(request.GET.get("dias", 30)), 365))
    hoy = timezone.localdate()
    ayer = hoy - timedelta(days=1)
    desde = hoy - timedelta(days=dias - 1)
    desde_previo = desde - timedelta(days=dias)

    periodo = _ventas(desde, hoy)
    previo = _ventas(desde_previo, desde - timedelta(days=1))
    de_hoy = _ventas(hoy, hoy)
    de_ayer = _ventas(ayer, ayer)

    # --- ventas día a día, sin huecos ---
    por_dia = {
        d["dia"]: d
        for d in _lineas()
        .filter(order__created_at__date__gte=desde)
        .annotate(dia=TruncDate("order__created_at"))
        .values("dia")
        .annotate(total=Sum(LINEA), pedidos=Count("order", distinct=True))
    }
    serie = []
    for i in range(dias):
        dia = desde + timedelta(days=i)
        fila = por_dia.get(dia)
        serie.append({
            "fecha": dia.isoformat(),
            "etiqueta": dia.strftime("%d/%m"),
            "total": fila["total"] if fila else 0,
            "pedidos": fila["pedidos"] if fila else 0,
        })

    # --- lo que más se vende ---
    top = list(
        _lineas()
        .filter(order__created_at__date__gte=desde)
        .values("product_name")
        .annotate(cantidad=Sum("quantity"), ingresos=Sum(LINEA))
        .order_by("-ingresos")[:10]
    )

    # --- mapa de calor: día de la semana × hora ---
    celdas = (
        _lineas()
        .filter(order__created_at__date__gte=desde)
        .annotate(dia_sem=ExtractIsoWeekDay("order__created_at"), hora=ExtractHour("order__created_at"))
        .values("dia_sem", "hora")
        .annotate(total=Sum(LINEA), pedidos=Count("order", distinct=True))
    )
    heatmap = [{"dia": c["dia_sem"] - 1, "hora": c["hora"], "total": c["total"],
                "pedidos": c["pedidos"]} for c in celdas]

    # --- facturación electrónica ---
    docs = DocumentoFiscal.objects.filter(fecha_generacion__date__gte=desde)
    por_estado = {
        d["estado"]: d["n"] for d in docs.values("estado").annotate(n=Count("id"))
    }
    impuestos = docs.filter(estado=DocumentoFiscal.ACEPTADA).aggregate(
        base=Sum("total_base"), impuesto=Sum("total_impuestos"), total=Sum("total_general")
    )

    # --- lo último que se facturó, para el inicio ---
    ultimos = [
        {
            "id": d.id,
            "numero": d.numero_completo,
            "estado": d.estado,
            "estado_texto": d.get_estado_display(),
            "total": d.total_general,
            "fecha": d.fecha_generacion,
            "mesa": d.sesion.table.number if d.sesion_id else None,
        }
        for d in DocumentoFiscal.objects.select_related("sesion__table")[:6]
    ]

    # --- desde siempre, para saber cuánto lleva el negocio ---
    historico = _ventas()

    return Response({
        "dias": dias,
        "desde": desde.isoformat(),
        "hasta": hoy.isoformat(),
        "historico": {"total": historico["total"], "pedidos": historico["pedidos"]},
        "ultimos_documentos": ultimos,
        "resumen": {
            "hoy": de_hoy["total"],
            "hoy_pedidos": de_hoy["pedidos"],
            "vs_ayer": _variacion(de_hoy["total"], de_ayer["total"]),
            "periodo": periodo["total"],
            "periodo_pedidos": periodo["pedidos"],
            "vs_periodo_anterior": _variacion(periodo["total"], previo["total"]),
            "ticket": periodo["ticket"],
        },
        "serie": serie,
        "top_productos": top,
        "heatmap": heatmap,
        "dias_semana": DIAS,
        "facturacion": {
            "por_estado": por_estado,
            "aceptadas": por_estado.get(DocumentoFiscal.ACEPTADA, 0),
            "rechazadas": por_estado.get(DocumentoFiscal.RECHAZADA, 0),
            "contingencia": por_estado.get(DocumentoFiscal.CONTINGENCIA, 0),
            "base": impuestos["base"] or 0,
            "impuestos": impuestos["impuesto"] or 0,
            "total": impuestos["total"] or 0,
        },
    })
