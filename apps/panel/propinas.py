"""Propinas: lo que dejaron los clientes y cuánto le toca a cada persona del equipo.

El turno abierto se muestra en vivo (el reparto puede cambiar mientras la gente
sigue marcando); los turnos cerrados leen lo que se congeló al cerrar.
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from apps.shifts.models import TurnoCaja
from apps.shifts.propinas import propinas_del_turno

from .turnos import _quien
from .views import panel_view


def _propinas_de(turno) -> dict:
    if turno.abierto:
        return propinas_del_turno(turno)
    return (turno.resumen or {}).get("propinas") or propinas_del_turno(turno)


@panel_view()
def propinas(request):
    hoy = timezone.localdate()
    desde = parse_date(request.GET.get("desde") or "") or hoy - timedelta(days=30)
    hasta = parse_date(request.GET.get("hasta") or "") or hoy

    abierto = TurnoCaja.abierto_actual()
    vivo = propinas_del_turno(abierto) if abierto else None

    cerrados = list(
        TurnoCaja.objects.filter(estado=TurnoCaja.CERRADO,
                                 abierto_en__date__gte=desde, abierto_en__date__lte=hasta)
        .order_by("-abierto_en")
    )
    historial, acumulado = [], {}
    total_periodo = Decimal("0")
    pendiente = Decimal("0")
    for t in cerrados:
        datos = _propinas_de(t)
        total = Decimal(datos.get("total") or "0")
        total_periodo += total
        if total and not t.propinas_pagadas_en:
            pendiente += total
        historial.append({"t": t, "p": datos, "total": total})
        for fila in datos.get("reparto", []):
            a = acumulado.setdefault(fila["nombre"], {
                "nombre": fila["nombre"], "cargo": fila.get("cargo", ""),
                "horas": Decimal("0"), "valor": Decimal("0"), "pendiente": Decimal("0"), "turnos": 0,
            })
            a["horas"] += Decimal(fila["horas"])
            a["valor"] += Decimal(fila["valor"])
            a["turnos"] += 1
            if not t.propinas_pagadas_en:
                a["pendiente"] += Decimal(fila["valor"])

    return render(request, "panel/propinas.html", {
        "seccion": "propinas",
        "abierto": abierto,
        "vivo": vivo,
        "historial": historial,
        "acumulado": sorted(acumulado.values(), key=lambda a: -a["valor"]),
        "total_periodo": total_periodo,
        "pendiente": pendiente,
        "desde": desde,
        "hasta": hasta,
    })


@panel_view(solo_admin=True)
@require_POST
def propinas_pagadas(request, turno_id):
    """Marca que la propina de un turno cerrado ya se le entregó al equipo (o lo deshace)."""
    turno = get_object_or_404(TurnoCaja, pk=turno_id, estado=TurnoCaja.CERRADO)
    if turno.propinas_pagadas_en:
        turno.propinas_pagadas_en = None
        turno.propinas_pagadas_por = ""
        messages.warning(request, f"La propina del turno {turno.numero} volvió a quedar pendiente.")
    else:
        turno.propinas_pagadas_en = timezone.now()
        turno.propinas_pagadas_por = _quien(request)[:120]
        messages.success(request, f"Propina del turno {turno.numero} marcada como entregada al equipo.")
    turno.save(update_fields=["propinas_pagadas_en", "propinas_pagadas_por"])
    return redirect("panel:propinas")
