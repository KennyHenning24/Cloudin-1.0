"""Correr los detectores, guardar las alertas y consolidar el Detector de fugas."""

import time
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.utils import timezone

from . import detectores as d
from .models import AjustesControl, AlertaControl, Analisis

CERO = Decimal("0")
CADA_CUANTO = timedelta(minutes=10)
SEMANAS = 4


def _guardar(datos, contador):
    """Crea la alerta o actualiza la que ya existía con la misma huella.

    Una alerta que alguien ya resolvió o descartó no se vuelve a abrir, salvo
    que la situación haya empeorado de forma clara (el impacto creció un 25%).
    """
    existente = AlertaControl.objects.filter(huella=datos["huella"]).first()
    if existente is None:
        AlertaControl.objects.create(**datos)
        contador["nuevas"] += 1
        return
    empeoro = datos["impacto_estimado"] > (existente.impacto_estimado or CERO) * Decimal("1.25") + 1000
    campos = ["tipo", "severidad", "titulo", "descripcion", "recomendacion", "impacto_estimado",
              "categoria_fuga", "entidad_tipo", "entidad_id", "enlace", "periodo_desde", "periodo_hasta",
              "metadata"]
    for campo in campos:
        setattr(existente, campo, datos[campo])
    if existente.estado in (AlertaControl.RESOLVED, AlertaControl.DISMISSED) and empeoro:
        existente.estado = AlertaControl.NEW
        existente.resuelta_en = None
        existente.nota = (existente.nota + "\n" if existente.nota else "") + "Se reabrió: la situación creció."
    existente.save()
    contador["actualizadas"] += 1


def analizar(usuario="", semanas=SEMANAS):
    """Revisa el negocio completo: turnos, semanas y lo que está pasando ahora."""
    inicio = time.monotonic()
    ajustes = AjustesControl.actuales()
    hoy = timezone.localdate()
    lunes_actual, _ = d.semana_de(hoy)
    desde = lunes_actual - timedelta(weeks=semanas - 1)
    contador = {"nuevas": 0, "actualizadas": 0}
    por_detector = {}

    def correr(nombre, funcion, *args):
        try:
            resultado = funcion(*args)
        except Exception as e:  # noqa: BLE001 — un detector roto no apaga a los demás
            por_detector[nombre] = f"error: {e}"
            return
        por_detector[nombre] = por_detector.get(nombre, 0) + len(resultado)
        for datos in resultado:
            _guardar(datos, contador)

    from apps.shifts.models import TurnoCaja

    turnos = TurnoCaja.objects.filter(Q(abierto_en__date__gte=desde) | Q(estado=TurnoCaja.ABIERTO))
    for turno in turnos:
        for detector in d.DETECTORES_TURNO:
            correr(detector.__name__, detector, turno, ajustes)

    for i in range(semanas):
        lunes = lunes_actual - timedelta(weeks=i)
        domingo = lunes + timedelta(days=6)
        for detector in d.DETECTORES_SEMANA:
            correr(detector.__name__, detector, lunes, domingo, ajustes)

    for i in range(1, 8):
        correr("ventas_del_dia", d.ventas_del_dia, hoy - timedelta(days=i), ajustes)
    correr("cuentas_largas", d.cuentas_largas, ajustes)
    correr("empleados", d.empleados, ajustes)

    return Analisis.objects.create(
        desde=desde, hasta=hoy, duracion_ms=int((time.monotonic() - inicio) * 1000),
        alertas_nuevas=contador["nuevas"], alertas_actualizadas=contador["actualizadas"],
        por_detector=por_detector, usuario=usuario[:120],
    )


def ultimo_analisis():
    return Analisis.objects.order_by("-momento").first()


def analizar_si_hace_falta(usuario=""):
    """Las pantallas lo llaman al abrir: si el último análisis es reciente, no repite."""
    ultimo = ultimo_analisis()
    if ultimo and timezone.now() - ultimo.momento < CADA_CUANTO:
        return ultimo
    return analizar(usuario)


# ----------------------------------------------------------- detector de fugas


def periodo(nombre: str):
    """Los períodos que ofrece el Detector de fugas."""
    hoy = timezone.localdate()
    if nombre == "hoy":
        return hoy, hoy, "Hoy"
    if nombre == "mes":
        return hoy.replace(day=1), hoy, "Este mes"
    if nombre == "30":
        return hoy - timedelta(days=29), hoy, "Últimos 30 días"
    if nombre == "anterior":
        lunes, _ = d.semana_de(hoy)
        return lunes - timedelta(days=7), lunes - timedelta(days=1), "Semana pasada"
    lunes, _ = d.semana_de(hoy)
    return lunes, hoy, "Esta semana"


def fugas(desde, hasta):
    """Las posibles fugas de plata del período, por categoría.

    Lo que se puede medir directo sale de los datos (caja, inventario, mermas,
    anulaciones, descuentos, cortesías, devoluciones); lo que requiere comparar
    precios en el tiempo (recetas, compras, otras) sale de las alertas.
    Son posibles fugas, no pérdidas confirmadas.
    """
    from apps.inventory.models import Movimiento
    from apps.orders.models import NovedadCuenta
    from apps.shifts.models import TurnoCaja

    ajustes = AjustesControl.actuales()
    categorias = {clave: {"clave": clave, "nombre": nombre, "valor": CERO, "casos": 0}
                  for clave, nombre in AlertaControl.FUGAS}

    turnos = TurnoCaja.objects.filter(estado=TurnoCaja.CERRADO, cerrado_en__date__gte=desde,
                                      cerrado_en__date__lte=hasta, diferencia__isnull=False)
    for t in turnos:
        if abs(t.diferencia) >= ajustes.tolerancia_caja:
            categorias["caja"]["valor"] += abs(t.diferencia)
            categorias["caja"]["casos"] += 1

    movs = Movimiento.objects.filter(momento__date__gte=desde, momento__date__lte=hasta)
    falta = movs.filter(tipo__in=[Movimiento.AJUSTE_NEGATIVO, Movimiento.CONTEO_NEGATIVO]).aggregate(
        v=Sum("valor_total"), n=Count("id"))
    sobra = movs.filter(tipo__in=[Movimiento.AJUSTE_POSITIVO, Movimiento.CONTEO_POSITIVO]).aggregate(
        v=Sum("valor_total"))
    neto = (falta["v"] or CERO) - (sobra["v"] or CERO)
    if neto > 0:
        categorias["inventario"].update(valor=neto, casos=falta["n"] or 0)
    merma = movs.filter(tipo=Movimiento.MERMA).aggregate(v=Sum("valor_total"), n=Count("id"))
    categorias["mermas"].update(valor=merma["v"] or CERO, casos=merma["n"] or 0)

    novedades = NovedadCuenta.objects.filter(creado__date__gte=desde, creado__date__lte=hasta)
    for tipo, clave in ((NovedadCuenta.ANULACION, "anulaciones"), (NovedadCuenta.CORTESIA, "cortesias"),
                        (NovedadCuenta.DEVOLUCION, "devoluciones")):
        agg = novedades.filter(tipo=tipo).aggregate(v=Sum("valor"), n=Count("id"))
        categorias[clave].update(valor=agg["v"] or CERO, casos=agg["n"] or 0)
    excepcionales = novedades.filter(tipo=NovedadCuenta.DESCUENTO, porcentaje__gte=ajustes.descuento_pct)
    agg = excepcionales.aggregate(v=Sum("valor"), n=Count("id"))
    categorias["descuentos"].update(valor=agg["v"] or CERO, casos=agg["n"] or 0)
    todos_descuentos = novedades.filter(tipo=NovedadCuenta.DESCUENTO).aggregate(v=Sum("valor"))["v"] or CERO

    alertas = AlertaControl.objects.filter(
        categoria_fuga__in=["recetas", "compras", "otras"], periodo_desde__lte=hasta,
        periodo_hasta__gte=desde,
    ).exclude(estado=AlertaControl.DISMISSED)
    for fila in alertas.values("categoria_fuga").annotate(v=Sum("impacto_estimado"), n=Count("id")):
        categorias[fila["categoria_fuga"]].update(valor=fila["v"] or CERO, casos=fila["n"])

    lista = [c for c in categorias.values()]
    total = sum((c["valor"] for c in lista), CERO)
    mayor = max((c["valor"] for c in lista), default=CERO) or Decimal("1")
    for c in lista:
        c["proporcion"] = float(c["valor"] / mayor * 100) if c["valor"] else 0
        c["del_total"] = float(c["valor"] / total * 100) if total else 0
    lista.sort(key=lambda c: -c["valor"])

    from .detectores import _ventas_entre

    ventas = _ventas_entre(desde, hasta)
    return {
        "desde": desde, "hasta": hasta, "categorias": lista, "total": total,
        "ventas": ventas, "sobre_ventas": float(total / ventas * 100) if ventas else None,
        "descuentos_todos": todos_descuentos,
    }


def resumen_alertas():
    abiertas = AlertaControl.objects.filter(estado__in=AlertaControl.ABIERTAS)
    por_severidad = {f["severidad"]: f["n"] for f in abiertas.values("severidad").annotate(n=Count("id"))}
    return {
        "abiertas": abiertas.count(),
        "nuevas": AlertaControl.objects.filter(estado=AlertaControl.NEW).count(),
        "criticas": por_severidad.get(AlertaControl.CRITICAL, 0),
        "advertencias": por_severidad.get(AlertaControl.WARNING, 0),
        "info": por_severidad.get(AlertaControl.INFO, 0),
    }


def cambiar_estado(alerta, estado, usuario="", nota=""):
    alerta.estado = estado
    alerta.revisada_por = usuario[:120]
    if nota:
        alerta.nota = (alerta.nota + "\n" if alerta.nota else "") + nota.strip()[:1000]
    alerta.resuelta_en = timezone.now() if estado in (AlertaControl.RESOLVED, AlertaControl.DISMISSED) else None
    alerta.save()
    return alerta
