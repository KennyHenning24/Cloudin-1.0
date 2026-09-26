"""«Hoy: 12:00 – 21:00» y «¿abierto ahora?», igual que el runtime.

Colombia no tiene horario de verano: la hora local es siempre UTC−5. El runtime
de JavaScript hace exactamente las mismas cuentas; las pruebas comparan ambos.
"""

from datetime import datetime, timedelta, timezone

DIAS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
BOGOTA = timezone(timedelta(hours=-5))


def _minutos(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _tramos(horas: list, dia: str) -> list:
    return [(h["open"], h["close"]) for h in horas if h.get("day") == dia and not h.get("closed")]


def horario_de_hoy(horas: list, ahora: datetime | None = None) -> str:
    """«Hoy: 12:00 – 15:00 y 18:00 – 22:00», «Hoy: cerrado», o vacío si no hay horario."""
    if not horas:
        return ""
    ahora = (ahora or datetime.now(BOGOTA)).astimezone(BOGOTA)
    tramos = _tramos(horas, DIAS[ahora.weekday()])
    if not tramos:
        return "Hoy: cerrado"
    return "Hoy: " + " y ".join(f"{a} – {c}" for a, c in tramos)


def abierto_ahora(horas: list, ahora: datetime | None = None) -> bool:
    """Si está abierto en este momento (incluye tramos que pasan la medianoche)."""
    if not horas:
        return False
    ahora = (ahora or datetime.now(BOGOTA)).astimezone(BOGOTA)
    minuto = ahora.hour * 60 + ahora.minute
    hoy, ayer = DIAS[ahora.weekday()], DIAS[(ahora.weekday() - 1) % 7]
    for a, c in _tramos(horas, hoy):
        abre, cierra = _minutos(a), _minutos(c)
        if (abre < cierra and abre <= minuto < cierra) or (cierra <= abre and minuto >= abre):
            return True
    for a, c in _tramos(horas, ayer):
        abre, cierra = _minutos(a), _minutos(c)
        if cierra <= abre and minuto < cierra:  # tramo de anoche que sigue abierto
            return True
    return False
