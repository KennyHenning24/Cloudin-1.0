"""Abrir y cerrar el turno, y armar su informe.

El informe de cierre es el equivalente al «informe Z» de una caja registradora:
el consolidado de todo lo que pasó entre la apertura y el cierre, con la lista
de facturas emitidas. No reemplaza a las facturas (en Colombia cada venta se
factura aparte): las resume y deja constancia de que cuadran.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Sum
from django.utils import timezone

from .models import TurnoCaja

# El valor de una línea de pedido: precio unitario por cantidad.
LINEA = ExpressionWrapper(
    F("unit_price") * F("quantity"), output_field=DecimalField(max_digits=14, decimal_places=2)
)


MENSAJE_SIN_TURNO = (
    "El restaurante todavía no ha abierto turno. Abre el turno de caja para poder "
    "usar la plataforma."
)
MENSAJE_SIN_TURNO_CLIENTE = (
    "El restaurante todavía no está recibiendo pedidos. Intenta de nuevo en un momento."
)


class SinTurno(ValidationError):
    """No hay turno abierto: nada que mueva la operación puede hacerse."""

    def __init__(self, mensaje=MENSAJE_SIN_TURNO):
        super().__init__(mensaje, code="sin_turno")


def turno_actual(db=None):
    """El turno abierto, o None. El turno nunca se abre solo: lo abre una persona."""
    return TurnoCaja.abierto_actual(db)


def exigir_turno(db=None) -> TurnoCaja:
    """El turno abierto; si no hay, lanza `SinTurno`."""
    turno = TurnoCaja.abierto_actual(db)
    if turno is None:
        raise SinTurno()
    return turno


# La caja no arranca vacía: siempre hay con qué dar vueltas.
BASE_MINIMA = Decimal("10000")


def abrir_turno(*, por="", base_inicial=Decimal("0"), db=None) -> TurnoCaja:
    if (base_inicial or Decimal("0")) < BASE_MINIMA:
        raise ValidationError("La base de caja debe ser de mínimo $10.000 para poder dar vueltas.")
    if TurnoCaja.abierto_actual(db) is not None:
        raise ValidationError("Ya hay un turno abierto. Ciérralo antes de abrir otro.")
    qs = TurnoCaja.objects.using(db) if db else TurnoCaja.objects
    return qs.create(
        numero=TurnoCaja.siguiente_numero(db),
        abierto_por=(por or "")[:120],
        base_inicial=base_inicial or Decimal("0"),
    )


# ------------------------------------------------------------------- informe


def _sesiones(turno):
    from apps.orders.models import TableSession

    db = turno._state.db
    return TableSession.objects.using(db).filter(turno=turno)


def _lineas(turno):
    from apps.orders.models import Order, OrderItem

    db = turno._state.db
    return (
        OrderItem.objects.using(db)
        .filter(order__session__turno=turno)
        .exclude(order__status=Order.STATUS_CANCELLED)
    )


def _documentos(turno):
    from apps.billing.models import DocumentoFiscal

    db = turno._state.db
    return DocumentoFiscal.objects.using(db).filter(turno=turno)


def resumen_turno(turno) -> dict:
    """Todo lo que pasó en el turno, listo para mostrar o congelar."""
    from apps.billing.models import DocumentoFiscal
    from apps.orders.models import NovedadCuenta, Order, TableSession

    lineas = _lineas(turno)
    ventas = lineas.aggregate(total=Sum(LINEA), pedidos=Count("order", distinct=True))
    # Los descuentos de cuenta no están en las líneas: se restan aparte.
    descuentos = _sesiones(turno).aggregate(t=Sum("descuento"))["t"] or Decimal("0")
    total_ventas = (ventas["total"] or Decimal("0")) - descuentos
    novedades = {
        n["tipo"]: {"cantidad": n["n"], "valor": str(n["valor"] or Decimal("0"))}
        for n in NovedadCuenta.objects.using(turno._state.db).filter(turno=turno)
        .values("tipo").annotate(n=Count("id"), valor=Sum("valor"))
    }
    lineas = lineas.filter(novedad="")

    productos = [
        {
            "nombre": p["product_name"],
            "cantidad": p["cantidad"],
            "total": str(p["total"] or Decimal("0")),
        }
        for p in lineas.values("product_name")
        .annotate(cantidad=Sum("quantity"), total=Sum(LINEA))
        .order_by("-total")
    ]

    sesiones = list(_sesiones(turno).select_related("table").order_by("opened_at"))
    mesas = []
    for s in sesiones:
        cerrada = s.status == TableSession.STATUS_CLOSED
        total = s.total if cerrada and s.total else s.current_total()
        doc = s.documentos.order_by("-fecha_generacion").first()
        mesas.append({
            "sesion_id": s.id,
            "mesa": s.table.number,
            "cliente": s.customer_name,
            "personas": s.guests,
            "abierta": timezone.localtime(s.opened_at).strftime("%H:%M"),
            "cerrada": timezone.localtime(s.closed_at).strftime("%H:%M") if s.closed_at else "",
            "estado": s.status,
            "total": str(total),
            "documento": doc.numero_completo if doc else "",
            "documento_id": doc.id if doc else None,
            "documento_estado": doc.estado if doc else "",
        })

    docs = _documentos(turno).order_by("fecha_generacion")
    documentos = [
        {
            "id": d.id,
            "numero": d.numero_completo,
            "estado": d.estado,
            "estado_texto": d.get_estado_display(),
            "mesa": d.sesion.table.number if d.sesion_id else None,
            "base": str(d.total_base),
            "impuestos": str(d.total_impuestos),
            "total": str(d.total_general),
            "cufe": d.cufe,
            "hora": timezone.localtime(d.fecha_generacion).strftime("%H:%M"),
        }
        for d in docs.select_related("sesion__table")
    ]
    facturado = docs.exclude(estado=DocumentoFiscal.ANULADA).aggregate(
        base=Sum("total_base"), imp=Sum("total_impuestos"), total=Sum("total_general")
    )
    por_estado = {d["estado"]: d["n"] for d in docs.values("estado").annotate(n=Count("id"))}

    pedidos_estado = {
        p["status"]: p["n"]
        for p in Order.objects.using(turno._state.db)
        .filter(session__turno=turno)
        .values("status")
        .annotate(n=Count("id"))
    }

    total_facturado = facturado["total"] or Decimal("0")

    # Lo que NO entró a la caja: facturas pagadas con tarjeta o transferencia.
    # Una mesa cerrada sin factura no tiene medio de pago registrado; se cuenta
    # como efectivo, que es lo más común cuando no se factura.
    no_efectivo = docs.exclude(estado=DocumentoFiscal.ANULADA).exclude(
        medio_pago=DocumentoFiscal.EFECTIVO
    )
    por_medio = {
        m["medio_pago"]: m["total"] or Decimal("0")
        for m in no_efectivo.values("medio_pago").annotate(total=Sum("total_general"))
    }
    ventas_no_efectivo = sum(por_medio.values(), Decimal("0"))
    nombres_medio = dict(DocumentoFiscal.MEDIOS_PAGO)
    empleados = _empleados_del_turno(turno)
    from .propinas import propinas_del_turno

    return {
        "ventas_efectivo": str(total_ventas - ventas_no_efectivo),
        "ventas_otros_medios": [
            {"medio": nombres_medio.get(k, k), "total": str(v)} for k, v in por_medio.items()
        ],
        "total_ventas": str(total_ventas),
        "descuentos": str(descuentos),
        "novedades": novedades,
        "total_pedidos": ventas["pedidos"] or 0,
        "total_mesas": len(sesiones),
        "total_comensales": sum(s.guests for s in sesiones),
        "productos": productos,
        "mesas": mesas,
        "documentos": documentos,
        "facturado": {
            "base": str(facturado["base"] or Decimal("0")),
            "impuestos": str(facturado["imp"] or Decimal("0")),
            "total": str(total_facturado),
        },
        "docs_por_estado": por_estado,
        "pedidos_por_estado": pedidos_estado,
        "sin_facturar": str(total_ventas - total_facturado),
        "empleados": empleados,
        "inventario": _inventario_del_turno(turno),
        "propinas": propinas_del_turno(turno, empleados),
    }


def _empleados_del_turno(turno) -> list:
    """Quién trabajó durante el turno y cuántas horas puso dentro de él."""
    from apps.staffing.models import Turno as TurnoEmpleado

    db = turno._state.db
    desde, hasta = turno.abierto_en, turno.fin_efectivo
    filas = {}
    marcaciones = (
        TurnoEmpleado.objects.using(db)
        .select_related("empleado")
        .filter(entrada__lt=hasta)
        .exclude(salida__lt=desde)
    )
    for t in marcaciones:
        # Solo la parte de su jornada que cae dentro del turno de caja.
        ini = max(t.entrada, desde)
        fin = min(t.fin_efectivo(), hasta)
        horas = Decimal(max(0, (fin - ini).total_seconds())) / Decimal("3600")
        if horas <= 0:
            continue
        fila = filas.setdefault(
            t.empleado_id,
            {
                "nombre": t.empleado.nombre,
                "cargo": t.empleado.cargo,
                "horas": Decimal("0"),
                "costo": Decimal("0"),
            },
        )
        fila["horas"] += horas
        fila["costo"] += horas * t.empleado.costo_hora()
    return [
        {
            "nombre": f["nombre"],
            "cargo": f["cargo"],
            "horas": str(f["horas"].quantize(Decimal("0.01"))),
            "costo": str(f["costo"].quantize(Decimal("0.01"))),
        }
        for f in sorted(filas.values(), key=lambda x: -x["horas"])
    ]


def _inventario_del_turno(turno) -> dict:
    """Qué insumos se consumieron en el turno y cuánto costaron."""
    try:
        from apps.inventory.models import Movimiento
    except Exception:  # el módulo de inventario es opcional
        return {"valor": "0", "movimientos": 0, "insumos": []}

    db = turno._state.db
    movs = Movimiento.objects.using(db).filter(turno=turno, tipo__in=Movimiento.SALIDAS)
    insumos = [
        {
            "nombre": m["insumo__nombre"],
            "unidad": m["insumo__unidad_consumo"],
            "cantidad": str(m["cantidad"] or Decimal("0")),
            "valor": str(m["valor"] or Decimal("0")),
        }
        for m in movs.values("insumo__nombre", "insumo__unidad_consumo")
        .annotate(cantidad=Sum("cantidad"), valor=Sum("valor_total"))
        .order_by("-valor")[:40]
    ]
    total = movs.aggregate(v=Sum("valor_total"))["v"] or Decimal("0")
    return {"valor": str(total), "movimientos": movs.count(), "insumos": insumos}


# -------------------------------------------------------------------- cierre


def cerrar_turno(turno, *, por="", efectivo_contado=None, notas="", facturar_abiertas=True):
    """Cierra el turno: liquida las mesas abiertas, congela el informe y listo.

    Igual que al facturar una mesa: si el proveedor falla, el turno **se cierra
    de todas formas**. El documento queda en contingencia y se reintenta solo.
    """
    from apps.billing.models import DocumentoFiscal
    from apps.billing.services import facturar_sesion
    from apps.orders.models import TableSession

    if not turno.abierto:
        raise ValidationError("Ese turno ya estaba cerrado.")

    resultado = {"cerradas": [], "facturadas": [], "sin_facturar": []}
    abiertas = list(
        _sesiones(turno).filter(status=TableSession.STATUS_OPEN).select_related("table")
    )
    for sesion in abiertas:
        sesion.close()
        resultado["cerradas"].append(sesion.table.number)
        if not facturar_abiertas:
            resultado["sin_facturar"].append((sesion.table.number, "no se pidió facturar"))
            continue
        try:
            documento = facturar_sesion(sesion)
            resultado["facturadas"].append((sesion.table.number, documento.numero_completo))
        except ValidationError as e:
            resultado["sin_facturar"].append((sesion.table.number, e.messages[0]))

    # Con todo cerrado ya se puede congelar el informe.
    resumen = resumen_turno(turno)
    estados = resumen["docs_por_estado"]

    turno.estado = TurnoCaja.CERRADO
    turno.cerrado_en = timezone.now()
    turno.cerrado_por = (por or "")[:120]
    turno.notas = notas or ""
    turno.total_ventas = Decimal(resumen["total_ventas"])
    turno.total_pedidos = resumen["total_pedidos"]
    turno.total_mesas = resumen["total_mesas"]
    turno.total_comensales = resumen["total_comensales"]
    turno.total_facturado = Decimal(resumen["facturado"]["total"])
    turno.total_base = Decimal(resumen["facturado"]["base"])
    turno.total_impuestos = Decimal(resumen["facturado"]["impuestos"])
    turno.docs_aceptados = estados.get(DocumentoFiscal.ACEPTADA, 0)
    turno.docs_pendientes = (
        estados.get(DocumentoFiscal.CONTINGENCIA, 0)
        + estados.get(DocumentoFiscal.PENDIENTE, 0)
        + estados.get(DocumentoFiscal.ENVIADA, 0)
    )
    turno.docs_rechazados = estados.get(DocumentoFiscal.RECHAZADA, 0)
    turno.costo_inventario = Decimal(resumen["inventario"]["valor"])
    turno.resumen = resumen
    if efectivo_contado is not None:
        turno.efectivo_contado = Decimal(efectivo_contado)
        turno.diferencia = turno.efectivo_contado - turno.efectivo_esperado
    turno.save()
    return turno, resultado
