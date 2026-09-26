"""El turno abierto, disponible en cualquier plantilla del panel.

La barra lateral y la cabecera lo muestran siempre: saber si la caja está
abierta o cerrada no debería obligar a entrar a una pantalla especial.
"""


def turno(request):
    tenant = getattr(request, "tenant", None)
    if tenant is None or not getattr(request.user, "is_authenticated", False):
        return {"turno_abierto": None}
    try:
        from .models import TurnoCaja

        return {"turno_abierto": TurnoCaja.abierto_actual()}
    except Exception:
        # Una base sin migrar no puede tumbar el panel entero.
        return {"turno_abierto": None}
