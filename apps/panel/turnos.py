"""Pantallas del turno de caja: abrir, cerrar y ver el informe.

Cerrar el turno es el gesto más importante del día: liquida las mesas que
quedaron abiertas, factura lo que falte, congela el resultado y deja el panel
listo para volver a empezar.
"""

from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_POST

from apps.billing.services import empresa_actual
from apps.orders.models import TableSession
from apps.shifts.models import TurnoCaja
from apps.shifts.services import abrir_turno, cerrar_turno, resumen_turno
from apps.tenants.models import TenantMembership

from .views import panel_view


def _quien(request) -> str:
    return request.user.get_full_name() or request.user.username


def _es_admin(request) -> bool:
    """Abrir y cerrar la caja es cosa del administrador del restaurante."""
    if request.user.is_superuser:
        return True
    membership = getattr(request.user, "tenant_membership", None)
    return membership is not None and membership.role == TenantMembership.ROLE_ADMIN


def _plata(valor, por_defecto=None):
    """Lee un monto escrito a mano, aguantando puntos y comas de miles."""
    texto = (valor or "").strip().replace("$", "").replace(" ", "")
    if not texto:
        return por_defecto
    texto = texto.replace(".", "").replace(",", ".")
    try:
        return Decimal(texto)
    except InvalidOperation:
        return por_defecto


@panel_view(requiere_turno=False)
def turnos(request):
    """La historia de turnos, con el abierto arriba."""
    abierto = TurnoCaja.abierto_actual()
    vivo = resumen_turno(abierto) if abierto else None
    contexto = {
        "seccion": "turnos",
        "abierto": abierto,
        "vivo": vivo,
        "siguiente": TurnoCaja.siguiente_numero(),
        # Lo que debería haber en la caja: se calcula aquí y no en la plantilla,
        # donde sumar un Decimal con un texto da resultados raros.
        "esperado": (
            (abierto.base_inicial + Decimal(vivo["ventas_efectivo"])
             + Decimal(vivo["propinas"]["efectivo"])) if abierto else Decimal("0")
        ),
        "cerrados": TurnoCaja.objects.filter(estado=TurnoCaja.CERRADO)[:40],
        "mesas_abiertas": (
            TableSession.objects.filter(turno=abierto, status=TableSession.STATUS_OPEN)
            .select_related("table")
            if abierto
            else []
        ),
        "puede_facturar": bool(empresa_actual() and empresa_actual().puede_facturar),
        "puede_abrir": _es_admin(request),
    }
    return render(request, "panel/turnos.html", contexto)


@panel_view(solo_admin=True, requiere_turno=False)
@require_POST
def turno_abrir(request):
    base = _plata(request.POST.get("base_inicial"), None)
    if base is None:
        messages.warning(request, "Escribe con cuánto efectivo arranca la caja (mínimo $10.000).")
        return redirect("panel:turnos")
    try:
        turno = abrir_turno(por=_quien(request), base_inicial=base)
    except ValidationError as e:
        messages.warning(request, e.messages[0])
        return redirect("panel:turnos")
    messages.success(
        request,
        f"Turno {turno.numero} abierto. El panel quedó en blanco y ya puede recibir pedidos.",
    )
    return redirect("panel:inicio")


@panel_view(solo_admin=True, requiere_turno=False)
@require_POST
def turno_cerrar(request):
    turno = TurnoCaja.abierto_actual()
    if turno is None:
        messages.warning(request, "No hay ningún turno abierto.")
        return redirect("panel:turnos")

    contado = _plata(request.POST.get("efectivo_contado"))
    facturar = request.POST.get("facturar_abiertas") == "1"
    try:
        turno, resultado = cerrar_turno(
            turno,
            por=_quien(request),
            efectivo_contado=contado,
            notas=(request.POST.get("notas") or "")[:2000],
            facturar_abiertas=facturar,
        )
    except ValidationError as e:
        messages.warning(request, e.messages[0])
        return redirect("panel:turnos")

    if resultado["facturadas"]:
        detalle = ", ".join(f"mesa {m} → {n}" for m, n in resultado["facturadas"])
        messages.success(request, f"Se facturaron las mesas que quedaron abiertas: {detalle}.")
    if resultado["sin_facturar"]:
        detalle = "; ".join(f"mesa {m}: {por}" for m, por in resultado["sin_facturar"])
        messages.warning(
            request,
            f"El turno se cerró igual, pero estas mesas quedaron sin factura — {detalle}",
        )
    messages.success(
        request,
        f"Turno {turno.numero} cerrado. Abre uno nuevo para volver a recibir pedidos.",
    )
    # Con el turno cerrado, Cloudin Control revisa la caja, las anulaciones y lo demás.
    try:
        from apps.control.services import analizar

        analizar(_quien(request))
    except Exception:  # noqa: BLE001 — el cierre ya quedó hecho; el análisis se repite solo
        pass
    return redirect("panel:turno-detalle", turno_id=turno.id)


@panel_view(requiere_turno=False)
def turno_detalle(request, turno_id):
    """El informe del turno: la cuenta final de todo lo que se hizo en él."""
    turno = get_object_or_404(TurnoCaja, pk=turno_id)
    # Si está abierto, el informe se calcula en vivo; si está cerrado, se lee el
    # que se congeló al cerrar: así el informe de ayer no cambia nunca.
    resumen = resumen_turno(turno) if turno.abierto else (turno.resumen or resumen_turno(turno))
    return render(
        request,
        "panel/turno_detalle.html",
        {
            "seccion": "turnos",
            "t": turno,
            "r": resumen,
            "empresa": empresa_actual(),
        },
    )


@panel_view(requiere_turno=False)
@xframe_options_sameorigin
def turno_imprimir(request, turno_id):
    """El cierre en tirilla, para pegarlo en la carpeta de caja."""
    turno = get_object_or_404(TurnoCaja, pk=turno_id)
    resumen = resumen_turno(turno) if turno.abierto else (turno.resumen or resumen_turno(turno))
    return render(
        request,
        "panel/print_turno.html",
        {"t": turno, "r": resumen, "empresa": empresa_actual()},
    )
