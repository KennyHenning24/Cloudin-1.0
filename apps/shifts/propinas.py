"""Propinas: anotarlas al cobrar y repartirlas entre el equipo del turno.

En Colombia la propina es voluntaria (Ley 1935 de 2018): se sugiere, el cliente
decide si la da y cuánto, no es ingreso del restaurante y no hace parte de la
factura electrónica. Por eso vive en la cuenta de la mesa y no en el documento
fiscal, y se reparte a los trabajadores.

Regla de reparto elegida por el restaurante: **bolsa común por horas**. Todo lo
recogido en el turno se suma y se divide según las horas que cada empleado
marcó en el reloj de Cloudin Employees dentro de ese turno.
"""

from decimal import ROUND_DOWN, Decimal

from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.utils import timezone

PESO = Decimal("1")
EFECTIVO = "10"
SUGERIDA = Decimal("0.10")


def registrar_propina(session, valor, medio=EFECTIVO):
    """Anota la propina que dejó la mesa. `valor` en pesos; 0 = sin propina."""
    try:
        valor = Decimal(str(valor or "0")).quantize(PESO)
    except Exception:
        raise ValidationError("La propina no es un número válido.")
    if valor < 0:
        raise ValidationError("La propina no puede ser negativa.")
    total = session.total if session.total else session.current_total()
    if total and valor > total:
        raise ValidationError("La propina no puede ser mayor que la cuenta. Revisa el valor.")
    session.propina = valor
    session.propina_medio = (medio or EFECTIVO) if valor else ""
    session.save(update_fields=["propina", "propina_medio"])
    return session


def sugerida(total) -> Decimal:
    """El 10 % sugerido, redondeado a pesos."""
    return (Decimal(str(total or 0)) * SUGERIDA).quantize(PESO)


def _repartir(total: Decimal, empleados: list) -> list:
    """Divide `total` por horas. Los pesos que sobran al redondear van a quien
    más horas tiene, para que la suma dé exacto."""
    horas_total = sum((Decimal(e["horas"]) for e in empleados), Decimal("0"))
    if total <= 0 or horas_total <= 0:
        return []
    filas = []
    for e in empleados:
        horas = Decimal(e["horas"])
        parte = (total * horas / horas_total).quantize(PESO, rounding=ROUND_DOWN)
        filas.append({
            "nombre": e["nombre"], "cargo": e.get("cargo", ""),
            "horas": str(horas), "porcentaje": str((horas * 100 / horas_total).quantize(Decimal("0.1"))),
            "valor": parte,
        })
    sobrante = total - sum((f["valor"] for f in filas), Decimal("0"))
    if filas and sobrante:
        max(filas, key=lambda f: Decimal(f["horas"]))["valor"] += sobrante
    for f in filas:
        f["valor"] = str(f["valor"])
    return filas


def propinas_del_turno(turno, empleados=None) -> dict:
    """Cuánta propina se recogió en el turno, cómo se pagó y cuánto le toca a cada quien."""
    from apps.billing.models import DocumentoFiscal
    from apps.orders.models import TableSession

    from .services import _empleados_del_turno

    db = turno._state.db
    sesiones = (TableSession.objects.using(db).filter(turno=turno, propina__gt=0)
                .select_related("table", "mesero").order_by("closed_at", "opened_at"))
    nombres_medio = dict(DocumentoFiscal.MEDIOS_PAGO)

    mesas, por_medio = [], {}
    total = Decimal("0")
    for s in sesiones:
        cuenta = s.total or s.current_total()
        medio = s.propina_medio or EFECTIVO
        total += s.propina
        por_medio[medio] = por_medio.get(medio, Decimal("0")) + s.propina
        mesas.append({
            "mesa": s.table.number,
            "cuenta": str(cuenta),
            "propina": str(s.propina),
            "porcentaje": str((s.propina * 100 / cuenta).quantize(Decimal("0.1"))) if cuenta else "0",
            "medio": nombres_medio.get(medio, medio),
            "mesero": s.mesero.nombre if s.mesero_id else "",
            "hora": timezone.localtime(s.closed_at).strftime("%H:%M") if s.closed_at else "",
        })

    empleados = empleados if empleados is not None else _empleados_del_turno(turno)
    ventas = (TableSession.objects.using(db).filter(turno=turno, status=TableSession.STATUS_CLOSED)
              .aggregate(t=Sum("total"))["t"] or Decimal("0"))
    return {
        "total": str(total),
        "mesas_con_propina": len(mesas),
        "efectivo": str(por_medio.get(EFECTIVO, Decimal("0"))),
        "por_medio": [{"medio": nombres_medio.get(k, k), "total": str(v)} for k, v in por_medio.items()],
        "porcentaje_ventas": str((total * 100 / ventas).quantize(Decimal("0.1"))) if ventas else "0",
        "mesas": mesas,
        "reparto": _repartir(total, empleados),
        "horas_equipo": str(sum((Decimal(e["horas"]) for e in empleados), Decimal("0"))),
    }
