"""Los detectores de Cloudin Control.

Cada detector mira una parte del negocio en un período, la compara con lo
esperado y devuelve alertas como diccionarios. No escriben en la base: eso lo
hace `services.analizar`, que también evita repetir alertas (cada una trae su
«huella»: la misma situación siempre da la misma huella).

Lenguaje: «diferencia», «posible fuga», «situación a revisar», «variación
detectada». Nunca «robo»: hay muchas explicaciones honestas para cada cosa.
"""

from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Avg, Count, Q, Sum
from django.urls import reverse
from django.utils import timezone

CERO = Decimal("0")


# ------------------------------------------------------------------ ayudas


def pesos(valor) -> str:
    valor = Decimal(str(valor or 0)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    signo = "-" if valor < 0 else ""
    return f"{signo}${abs(valor):,.0f}".replace(",", ".")


def pct(valor, decimales=1) -> str:
    texto = f"{float(valor):.{decimales}f}".replace(".", ",")
    return texto[:-2] if texto.endswith(",0") else texto


def fecha_corta(fecha) -> str:
    dias = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
    return f"{dias[fecha.weekday()]} {fecha:%d/%m}"


def semana_de(fecha):
    lunes = fecha - timedelta(days=fecha.weekday())
    return lunes, lunes + timedelta(days=6)


def id_semana(lunes) -> str:
    anio, semana, _ = lunes.isocalendar()
    return f"{anio}-S{semana:02d}"


def texto_semana(lunes) -> str:
    domingo = lunes + timedelta(days=6)
    return f"semana del {lunes:%d/%m} al {domingo:%d/%m}"


def _enlace(nombre, **kwargs) -> str:
    try:
        return reverse(nombre, kwargs=kwargs or None)
    except Exception:  # noqa: BLE001 — un enlace roto no debe tumbar el análisis
        return ""


def alerta(**campos) -> dict:
    base = {
        "tipo": "", "severidad": "info", "titulo": "", "descripcion": "", "recomendacion": "",
        "impacto_estimado": CERO, "categoria_fuga": "", "entidad_tipo": "", "entidad_id": "",
        "enlace": "", "periodo_desde": None, "periodo_hasta": None, "metadata": {}, "huella": "",
    }
    base.update(campos)
    base["impacto_estimado"] = Decimal(str(base["impacto_estimado"] or 0)).quantize(Decimal("0.01"))
    return base


def _ventas_de_turno(turno) -> Decimal:
    if not turno.abierto and turno.total_ventas:
        return turno.total_ventas
    from apps.shifts.services import LINEA, _lineas

    return _lineas(turno).filter(novedad="").aggregate(t=Sum(LINEA))["t"] or CERO


def _ventas_entre(desde, hasta) -> Decimal:
    from apps.orders.models import Order, OrderItem, TableSession
    from apps.shifts.services import LINEA

    lineas = (OrderItem.objects.filter(order__created_at__date__gte=desde, order__created_at__date__lte=hasta,
                                       novedad="")
              .exclude(order__status=Order.STATUS_CANCELLED).aggregate(t=Sum(LINEA))["t"] or CERO)
    descuentos = (TableSession.objects.filter(opened_at__date__gte=desde, opened_at__date__lte=hasta)
                  .aggregate(t=Sum("descuento"))["t"] or CERO)
    return lineas - descuentos


# ============================================================ por turno


def caja(turno, ajustes):
    """Diferencias al contar el efectivo del cierre."""
    if turno.abierto:
        return []
    enlace = _enlace("panel:turno-detalle", turno_id=turno.id)
    cuando = fecha_corta(timezone.localtime(turno.abierto_en).date())
    if turno.efectivo_contado is None:
        return [alerta(
            tipo="turnos", severidad="info",
            titulo=f"El turno {turno.numero} se cerró sin contar el efectivo",
            descripcion=(f"Al cerrar el turno {turno.numero} ({cuando}) no se escribió cuánto efectivo había. "
                         "Sin ese dato no se puede saber si la caja cuadró."),
            recomendacion="Al cerrar cada turno, cuenta el efectivo y escríbelo: toma un minuto y deja la caja cuadrada.",
            entidad_tipo="turno", entidad_id=str(turno.id), enlace=enlace,
            periodo_desde=timezone.localtime(turno.abierto_en).date(),
            periodo_hasta=timezone.localtime(turno.cerrado_en or turno.abierto_en).date(),
            huella=f"caja-sin-contar:{turno.id}",
        )]
    diferencia = turno.diferencia or CERO
    if abs(diferencia) < ajustes.tolerancia_caja:
        return []
    faltante = diferencia < 0
    valor = abs(diferencia)
    if faltante:
        severidad = "critical" if valor >= 50000 else "warning" if valor >= 10000 else "info"
        titulo = f"Caja con diferencia de {pesos(valor)} (faltante) en el turno {turno.numero}"
        recomendacion = ("Revisa si algún pago con tarjeta o transferencia quedó registrado como efectivo, "
                         "si hubo gastos o vueltas pagados de la caja sin anotar, y vuelve a contar con la "
                         "persona responsable del turno.")
    else:
        severidad = "warning" if valor >= 20000 else "info"
        titulo = f"Caja con diferencia de {pesos(valor)} (sobrante) en el turno {turno.numero}"
        recomendacion = ("Un sobrante suele ser una venta que no quedó registrada o un pago anotado con otro "
                         "medio. Revisa las cuentas que se cerraron sin factura en ese turno.")
    return [alerta(
        tipo="caja", severidad=severidad, titulo=titulo,
        descripcion=(f"Al cerrar el turno {turno.numero} ({cuando}) se contaron {pesos(turno.efectivo_contado)} "
                     f"y el sistema esperaba {pesos(turno.efectivo_esperado)} (base, ventas en efectivo y "
                     f"propinas en efectivo). La variación detectada es de {pesos(diferencia)}."),
        recomendacion=recomendacion, impacto_estimado=valor, categoria_fuga="caja",
        entidad_tipo="turno", entidad_id=str(turno.id), enlace=enlace,
        periodo_desde=timezone.localtime(turno.abierto_en).date(),
        periodo_hasta=timezone.localtime(turno.cerrado_en).date(),
        metadata={"contado": str(turno.efectivo_contado), "esperado": str(turno.efectivo_esperado),
                  "diferencia": str(diferencia)},
        huella=f"caja:{turno.id}",
    )]


def turno_largo(turno, ajustes):
    if not turno.abierto:
        return []
    horas = (timezone.now() - turno.abierto_en).total_seconds() / 3600
    if horas < ajustes.turno_horas:
        return []
    return [alerta(
        tipo="turnos", severidad="warning",
        titulo=f"El turno {turno.numero} lleva {int(horas)} horas abierto",
        descripcion=(f"El turno se abrió el {fecha_corta(timezone.localtime(turno.abierto_en).date())} a las "
                     f"{timezone.localtime(turno.abierto_en):%H:%M} y sigue abierto. Un turno muy largo mezcla "
                     "las ventas de varios días y hace difícil cuadrar la caja."),
        recomendacion="Cierra el turno al final de cada jornada, contando el efectivo, y abre uno nuevo al empezar.",
        entidad_tipo="turno", entidad_id=str(turno.id), enlace=_enlace("panel:turnos"),
        periodo_desde=timezone.localtime(turno.abierto_en).date(), periodo_hasta=timezone.localdate(),
        huella=f"turno-largo:{turno.id}",
    )]


def _quien_concentra(novedades) -> tuple:
    """Si una persona registró la mayoría de los casos, quién y cuántos."""
    conteo = {}
    for n in novedades:
        persona = n.mesero_nombre or n.registrado_por or "Sin nombre"
        conteo[persona] = conteo.get(persona, 0) + 1
    if not conteo:
        return None, 0
    persona, veces = max(conteo.items(), key=lambda x: x[1])
    return (persona, veces) if veces >= 3 and veces / len(novedades) >= 0.6 else (None, 0)


def anulaciones(turno, ajustes):
    from apps.orders.models import NovedadCuenta

    qs = list(NovedadCuenta.objects.filter(turno=turno, tipo=NovedadCuenta.ANULACION))
    if len(qs) < ajustes.anulaciones_por_turno:
        return []
    valor = sum((n.valor for n in qs), CERO)
    preparadas = [n for n in qs if n.ya_preparado]
    persona, veces = _quien_concentra(qs)
    descripcion = (f"En el turno {turno.numero} se anularon {len(qs)} productos por {pesos(valor)}. "
                   f"Lo normal para este restaurante es menos de {ajustes.anulaciones_por_turno} por turno.")
    if preparadas:
        descripcion += (f" {len(preparadas)} de ellas ya estaban en preparación o servidas, así que la cocina "
                        "sí gastó insumos.")
    if persona:
        descripcion += f" {veces} de las {len(qs)} quedaron a nombre de {persona}."
    motivos = {}
    for n in qs:
        motivos[n.motivo] = motivos.get(n.motivo, 0) + 1
    return [alerta(
        tipo="anulaciones", severidad="critical" if len(qs) >= 2 * ajustes.anulaciones_por_turno else "warning",
        titulo=f"Se registraron {len(qs)} anulaciones durante el turno {turno.numero}",
        descripcion=descripcion,
        recomendacion=("Revisa los motivos con el equipo. Si son errores al tomar el pedido, confirmar el pedido "
                       "en voz alta con el cliente las reduce. Una anulación después de cobrar es una situación "
                       "a revisar con más cuidado."),
        impacto_estimado=valor, categoria_fuga="anulaciones",
        entidad_tipo="turno", entidad_id=str(turno.id), enlace=_enlace("panel:turno-detalle", turno_id=turno.id),
        periodo_desde=timezone.localtime(turno.abierto_en).date(),
        periodo_hasta=timezone.localtime(turno.cerrado_en or timezone.now()).date(),
        metadata={"cantidad": len(qs), "preparadas": len(preparadas),
                  "motivos": sorted(motivos.items(), key=lambda x: -x[1])[:5],
                  "persona": persona or ""},
        huella=f"anulaciones:{turno.id}",
    )]


def descuentos(turno, ajustes):
    from apps.orders.models import NovedadCuenta

    salida = []
    qs = NovedadCuenta.objects.filter(turno=turno, tipo=NovedadCuenta.DESCUENTO).select_related("sesion__table")
    for n in qs:
        if n.porcentaje < ajustes.descuento_pct:
            continue
        mesa = n.sesion.table.number if n.sesion_id else "—"
        salida.append(alerta(
            tipo="descuentos",
            severidad="critical" if n.porcentaje >= 50 else "warning" if n.porcentaje >= 30 else "info",
            titulo=f"Descuento del {pct(n.porcentaje, 0)}% ({pesos(n.valor)}) en la mesa {mesa}",
            descripcion=(f"El {fecha_corta(timezone.localtime(n.creado).date())} a las "
                         f"{timezone.localtime(n.creado):%H:%M} se hizo un descuento de {pesos(n.valor)} sobre la "
                         f"cuenta de la mesa {mesa}. Motivo: «{n.motivo}». Lo registró "
                         f"{n.registrado_por or 'alguien del equipo'} y lo autorizó {n.autorizado_por or 'el mismo usuario'}."),
            recomendacion=("Es un descuento por encima de lo habitual. Confirma que el motivo corresponde a una "
                           "política del restaurante (cumpleaños, cliente frecuente, reclamo)."),
            impacto_estimado=n.valor, categoria_fuga="descuentos",
            entidad_tipo="sesion", entidad_id=str(n.sesion_id),
            enlace=_enlace("panel:turno-detalle", turno_id=turno.id),
            periodo_desde=timezone.localtime(n.creado).date(), periodo_hasta=timezone.localtime(n.creado).date(),
            metadata={"porcentaje": str(n.porcentaje), "motivo": n.motivo, "autorizo": n.autorizado_por},
            huella=f"descuento:{n.id}",
        ))
    return salida


def cortesias_y_devoluciones(turno, ajustes):
    from apps.orders.models import NovedadCuenta

    salida = []
    ventas = _ventas_de_turno(turno)
    periodo = dict(periodo_desde=timezone.localtime(turno.abierto_en).date(),
                   periodo_hasta=timezone.localtime(turno.cerrado_en or timezone.now()).date())
    enlace = _enlace("panel:turno-detalle", turno_id=turno.id)

    cortesias = list(NovedadCuenta.objects.filter(turno=turno, tipo=NovedadCuenta.CORTESIA))
    valor = sum((n.valor for n in cortesias), CERO)
    if cortesias and ventas and valor * 100 / ventas >= ajustes.cortesias_pct:
        proporcion = valor * 100 / ventas
        salida.append(alerta(
            tipo="cortesias", severidad="warning" if proporcion >= 2 * ajustes.cortesias_pct else "info",
            titulo=f"Cortesías por {pesos(valor)} ({pct(proporcion)}% de las ventas) en el turno {turno.numero}",
            descripcion=(f"Se dieron {len(cortesias)} productos en cortesía por {pesos(valor)}, "
                         f"el {pct(proporcion)}% de lo vendido en el turno. El límite configurado es "
                         f"{pct(ajustes.cortesias_pct)}%."),
            recomendacion="Define quién puede dar cortesías y en qué casos, y revisa que cada una tenga su motivo.",
            impacto_estimado=valor, categoria_fuga="cortesias", entidad_tipo="turno", entidad_id=str(turno.id),
            enlace=enlace, metadata={"cantidad": len(cortesias)}, huella=f"cortesias:{turno.id}", **periodo,
        ))

    devoluciones = list(NovedadCuenta.objects.filter(turno=turno, tipo=NovedadCuenta.DEVOLUCION))
    valor_dev = sum((n.valor for n in devoluciones), CERO)
    if len(devoluciones) >= 3 or valor_dev >= 60000:
        platos = {}
        for n in devoluciones:
            platos[n.producto_nombre] = platos.get(n.producto_nombre, 0) + n.cantidad
        lista = ", ".join(f"{k} ({v})" for k, v in sorted(platos.items(), key=lambda x: -x[1])[:4])
        salida.append(alerta(
            tipo="devoluciones", severidad="warning",
            titulo=f"{len(devoluciones)} platos devueltos en el turno {turno.numero}",
            descripcion=f"Los clientes devolvieron {lista}, por {pesos(valor_dev)} en total.",
            recomendacion=("Revisa con la cocina la preparación y la temperatura de esos platos. Si se repite el "
                           "mismo plato, puede ser la receta o la porción."),
            impacto_estimado=valor_dev, categoria_fuga="devoluciones", entidad_tipo="turno",
            entidad_id=str(turno.id), enlace=enlace, metadata={"platos": platos},
            huella=f"devoluciones:{turno.id}", **periodo,
        ))
    return salida


def cocina(turno, ajustes):
    from apps.orders.models import Order

    servidas = [o for o in Order.objects.filter(session__turno=turno, servido_en__isnull=False)]
    if len(servidas) < 5:
        return []
    minutos = [o.minutos_cocina() for o in servidas]
    lentas = [m for m in minutos if m > ajustes.cocina_minutos]
    promedio = sum(minutos) / len(minutos)
    if len(lentas) < 3 or len(lentas) / len(minutos) < 0.2:
        return []
    return [alerta(
        tipo="cocina", severidad="warning" if len(lentas) / len(minutos) >= 0.35 else "info",
        titulo=f"{len(lentas)} comandas tardaron más de {ajustes.cocina_minutos} minutos en el turno {turno.numero}",
        descripcion=(f"De {len(minutos)} comandas servidas, {len(lentas)} pasaron de {ajustes.cocina_minutos} "
                     f"minutos entre el pedido y la mesa. El promedio fue de {pct(promedio, 0)} minutos y la más "
                     f"lenta, {pct(max(minutos), 0)}."),
        recomendacion=("Mira en qué horas se acumulan: si es la hora pico, conviene reforzar la cocina o dejar "
                       "preparaciones listas antes del servicio."),
        entidad_tipo="turno", entidad_id=str(turno.id), enlace=_enlace("panel:turno-detalle", turno_id=turno.id),
        periodo_desde=timezone.localtime(turno.abierto_en).date(),
        periodo_hasta=timezone.localtime(turno.cerrado_en or timezone.now()).date(),
        metadata={"promedio": round(promedio, 1), "lentas": len(lentas), "total": len(minutos)},
        huella=f"cocina:{turno.id}",
    )]


DETECTORES_TURNO = [caja, turno_largo, anulaciones, descuentos, cortesias_y_devoluciones, cocina]


# ============================================================ por semana


def inventario(lunes, domingo, ajustes):
    """Consumo real contra el teórico, insumo por insumo."""
    from apps.inventory.models import Movimiento

    filas = (
        Movimiento.objects.filter(momento__date__gte=lunes, momento__date__lte=domingo)
        .values("insumo", "insumo__nombre", "insumo__unidad_consumo", "tipo")
        .annotate(cantidad=Sum("cantidad"), valor=Sum("valor_total"))
    )
    por_insumo = {}
    for f in filas:
        d = por_insumo.setdefault(f["insumo"], {"nombre": f["insumo__nombre"], "unidad": f["insumo__unidad_consumo"],
                                                "teorico": CERO, "falta": CERO, "falta_valor": CERO,
                                                "sobra": CERO, "sobra_valor": CERO})
        if f["tipo"] == Movimiento.VENTA:
            d["teorico"] += f["cantidad"] or CERO
        elif f["tipo"] in (Movimiento.AJUSTE_NEGATIVO, Movimiento.CONTEO_NEGATIVO):
            d["falta"] += f["cantidad"] or CERO
            d["falta_valor"] += f["valor"] or CERO
        elif f["tipo"] in (Movimiento.AJUSTE_POSITIVO, Movimiento.CONTEO_POSITIVO):
            d["sobra"] += f["cantidad"] or CERO
            d["sobra_valor"] += f["valor"] or CERO

    salida = []
    for insumo_id, d in por_insumo.items():
        neto = d["falta"] - d["sobra"]
        valor = d["falta_valor"] - d["sobra_valor"]
        if neto <= 0 or valor < 5000:
            continue
        if d["teorico"] > 0:
            exceso = neto * 100 / d["teorico"]
            if exceso < ajustes.inventario_pct:
                continue
            titulo = f"{d['nombre']} presenta consumo real {pct(exceso, 0)}% superior al consumo teórico"
            descripcion = (f"En la {texto_semana(lunes)}, las recetas de lo vendido explican "
                           f"{pct(d['teorico'], 0)} {d['unidad']} de {d['nombre']}, pero el conteo y los ajustes "
                           f"muestran {pct(neto, 0)} {d['unidad']} más. Esa variación vale {pesos(valor)}.")
            severidad = "critical" if exceso >= 25 or valor >= 150000 else "warning" if exceso >= 15 else "info"
        else:
            exceso = None
            titulo = f"Diferencia de {pesos(valor)} en {d['nombre']} sin ventas que la expliquen"
            descripcion = (f"En la {texto_semana(lunes)} faltan {pct(neto, 0)} {d['unidad']} de {d['nombre']} "
                           "según el conteo, y no hubo ventas con receta que lo usen.")
            severidad = "warning" if valor >= 20000 else "info"
        salida.append(alerta(
            tipo="inventario", severidad=severidad, titulo=titulo, descripcion=descripcion,
            recomendacion=("Revisa porciones en la cocina, que las recetas estén completas y que las mermas se "
                           "registren. Un nuevo conteo de este insumo en unos días confirma si la diferencia sigue."),
            impacto_estimado=valor, categoria_fuga="inventario", entidad_tipo="insumo", entidad_id=str(insumo_id),
            enlace=_enlace("panel:insumo-detalle", insumo_id=insumo_id),
            periodo_desde=lunes, periodo_hasta=domingo,
            metadata={"teorico": str(d["teorico"]), "diferencia": str(neto), "unidad": d["unidad"],
                      "exceso_pct": float(exceso) if exceso is not None else None},
            huella=f"inventario:{insumo_id}:{id_semana(lunes)}",
        ))
    return salida


def mermas(lunes, domingo, ajustes):
    from apps.inventory.models import Movimiento

    qs = Movimiento.objects.filter(momento__date__gte=lunes, momento__date__lte=domingo, tipo=Movimiento.MERMA)
    total = qs.aggregate(v=Sum("valor_total"))["v"] or CERO
    if total < 10000:
        return []
    ventas = _ventas_entre(lunes, domingo)
    proporcion = total * 100 / ventas if ventas else None
    top = list(qs.values("insumo__nombre").annotate(v=Sum("valor_total")).order_by("-v")[:3])
    lista = ", ".join(f"{t['insumo__nombre']} ({pesos(t['v'])})" for t in top)
    severidad = ("critical" if proporcion and proporcion >= 5 else
                 "warning" if (proporcion and proporcion >= 2) or total >= 80000 else "info")
    return [alerta(
        tipo="mermas", severidad=severidad,
        titulo=f"Mermas por {pesos(total)} en la {texto_semana(lunes)}",
        descripcion=(f"Se registraron mermas por {pesos(total)}"
                     + (f", el {pct(proporcion)}% de las ventas de la semana" if proporcion else "")
                     + f". Lo que más se perdió: {lista}."),
        recomendacion=("Revisa el almacenamiento y las fechas de vencimiento de esos insumos, y compra en "
                       "cantidades más cercanas a lo que se vende."),
        impacto_estimado=total, categoria_fuga="mermas", entidad_tipo="semana", entidad_id=id_semana(lunes),
        enlace=_enlace("panel:inventario-reportes"), periodo_desde=lunes, periodo_hasta=domingo,
        metadata={"top": [{"insumo": t["insumo__nombre"], "valor": str(t["v"])} for t in top]},
        huella=f"mermas:{id_semana(lunes)}",
    )]


def _costo_promedio_al(insumo_id, momento):
    """El costo promedio que tenía un insumo en un momento dado (según el kardex)."""
    from apps.inventory.models import Insumo, Movimiento

    mov = (Movimiento.objects.filter(insumo_id=insumo_id, momento__lt=momento)
           .order_by("-momento", "-id").values_list("saldo_costo_promedio", flat=True).first())
    if mov is not None:
        return mov
    return Insumo.objects.filter(pk=insumo_id).values_list("costo_promedio", flat=True).first() or CERO


def recetas(lunes, domingo, ajustes):
    """Productos sin receta y márgenes que cayeron porque subieron los insumos."""
    from datetime import datetime

    from apps.inventory.models import Receta
    from apps.orders.models import Order, OrderItem

    if not Receta.objects.exists():
        return []  # el restaurante todavía no usa recetas: nada que comparar
    vendidos = (
        OrderItem.objects.filter(order__created_at__date__gte=lunes, order__created_at__date__lte=domingo,
                                 novedad="", product__isnull=False)
        .exclude(order__status=Order.STATUS_CANCELLED)
        .values("product", "product__name", "product__price").annotate(unidades=Sum("quantity"))
    )
    salida, sin_receta = [], []
    inicio = timezone.make_aware(datetime.combine(lunes, datetime.min.time()))
    fin = min(timezone.now(), timezone.make_aware(datetime.combine(domingo, datetime.max.time())))
    recetas_por_producto = {r.producto_id: r for r in Receta.objects.filter(producto__isnull=False, activa=True)}
    for v in vendidos:
        receta = recetas_por_producto.get(v["product"])
        if receta is None:
            sin_receta.append(v["product__name"])
            continue
        precio = v["product__price"] or CERO
        if not precio:
            continue
        explosion = receta.explosion(Decimal("1"))
        costo_antes = sum((cant * _costo_promedio_al(ins.id, inicio) for ins, cant in explosion.items()), CERO)
        costo_ahora = sum((cant * _costo_promedio_al(ins.id, fin) for ins, cant in explosion.items()), CERO)
        if not costo_antes:
            continue
        margen_antes = (precio - costo_antes) * 100 / precio
        margen_ahora = (precio - costo_ahora) * 100 / precio
        caida = margen_antes - margen_ahora
        if caida < ajustes.margen_caida_puntos:
            continue
        impacto = (costo_ahora - costo_antes) * v["unidades"]
        salida.append(alerta(
            tipo="recetas", severidad="warning" if caida >= 2 * ajustes.margen_caida_puntos else "info",
            titulo=f"El margen del producto {v['product__name']} cayó {pct(caida)} puntos",
            descripcion=(f"En la {texto_semana(lunes)} el costo de la receta pasó de {pesos(costo_antes)} a "
                         f"{pesos(costo_ahora)} porque subieron sus insumos. Con el precio de {pesos(precio)} el "
                         f"margen bajó de {pct(margen_antes)}% a {pct(margen_ahora)}%. Se vendieron "
                         f"{v['unidades']}, así que la diferencia de la semana es de {pesos(impacto)}."),
            recomendacion=("Revisa el precio de venta, la porción o busca otro proveedor para el insumo que "
                           "más subió."),
            impacto_estimado=impacto, categoria_fuga="recetas", entidad_tipo="producto",
            entidad_id=str(v["product"]), enlace=_enlace("panel:receta-producto", producto_id=v["product"]),
            periodo_desde=lunes, periodo_hasta=domingo,
            metadata={"costo_antes": str(costo_antes.quantize(Decimal('0.01'))),
                      "costo_ahora": str(costo_ahora.quantize(Decimal('0.01'))),
                      "margen_antes": round(float(margen_antes), 1), "margen_ahora": round(float(margen_ahora), 1)},
            huella=f"margen:{v['product']}:{id_semana(lunes)}",
        ))
    if sin_receta:
        salida.append(alerta(
            tipo="recetas", severidad="info",
            titulo=f"{len(sin_receta)} productos vendidos sin receta en la {texto_semana(lunes)}",
            descripcion=("Sin receta no se puede saber cuánto cuestan ni descontar su inventario: "
                         + ", ".join(sin_receta[:6]) + ("…" if len(sin_receta) > 6 else "") + "."),
            recomendacion="Arma la receta de los que más se venden primero: es donde más se nota el control.",
            entidad_tipo="semana", entidad_id=id_semana(lunes), enlace=_enlace("panel:recetas"),
            periodo_desde=lunes, periodo_hasta=domingo, metadata={"productos": sin_receta[:30]},
            huella=f"sin-receta:{id_semana(lunes)}",
        ))
    return salida


def compras(lunes, domingo, ajustes):
    """Compras en las que un insumo llegó bastante más caro que su promedio."""
    from apps.inventory.models import Compra, CompraItem, Movimiento

    salida = []
    items = CompraItem.objects.filter(compra__estado=Compra.REGISTRADA, compra__fecha__gte=lunes,
                                      compra__fecha__lte=domingo).select_related("insumo", "compra__proveedor")
    for item in items:
        mov = (Movimiento.objects.filter(compra=item.compra, insumo=item.insumo, tipo=Movimiento.COMPRA)
               .order_by("momento", "id").first())
        if mov is None:
            continue
        anterior = (Movimiento.objects.filter(insumo=item.insumo, momento__lt=mov.momento)
                    .order_by("-momento", "-id").values_list("saldo_costo_promedio", flat=True).first())
        if not anterior:
            continue
        nuevo = item.costo_consumo()
        alza = (nuevo - anterior) * 100 / anterior
        if alza < ajustes.compra_alza_pct:
            continue
        impacto = (nuevo - anterior) * item.cantidad_consumo()
        salida.append(alerta(
            tipo="compras",
            severidad="critical" if alza >= 30 else "warning" if alza >= 15 else "info",
            titulo=f"El costo de {item.insumo.nombre.lower()} aumentó {pct(alza, 0)}% respecto al promedio anterior",
            descripcion=(f"En la compra a {item.compra.proveedor.nombre} del {item.compra.fecha:%d/%m} "
                         f"({item.compra.numero_factura or 'sin número'}) el {item.insumo.nombre} llegó a "
                         f"{pesos(nuevo)} por {item.insumo.unidad_consumo}, contra un promedio de "
                         f"{pesos(anterior)}. Esa compra cuesta {pesos(impacto)} más de lo habitual."),
            recomendacion=("Pregunta al proveedor por el alza y compara con otro. Si el alza se queda, revisa el "
                           "precio de los platos que usan este insumo."),
            impacto_estimado=impacto, categoria_fuga="compras", entidad_tipo="compra",
            entidad_id=str(item.compra_id), enlace=_enlace("panel:compra-detalle", compra_id=item.compra_id),
            periodo_desde=item.compra.fecha, periodo_hasta=item.compra.fecha,
            metadata={"anterior": str(anterior), "nuevo": str(nuevo), "alza_pct": round(float(alza), 1)},
            huella=f"compra:{item.id}",
        ))
    return salida


def costos(lunes, domingo, ajustes):
    from apps.inventory.models import Receta
    from apps.inventory.services import food_cost

    if not Receta.objects.exists():
        return []
    datos = food_cost(lunes, min(domingo, timezone.localdate()))
    real = datos.get("real_pct")
    if real is None or datos["venta"] < 200000 or real <= float(ajustes.food_cost_objetivo) + 3:
        return []
    return [alerta(
        tipo="costos", severidad="warning" if real <= float(ajustes.food_cost_objetivo) + 8 else "critical",
        titulo=f"Food cost de {pct(real, 0)}% en la {texto_semana(lunes)}",
        descripcion=(f"Por cada $100 vendidos, ${pct(real, 0)} se fueron en insumos. El objetivo del "
                     f"restaurante es {pct(ajustes.food_cost_objetivo, 0)}%. Según las recetas debería haber sido "
                     f"{pct(datos['teorico_pct'] or 0, 0)}%."),
        recomendacion="Mira primero las mermas y las diferencias de inventario de esta semana, y los platos con menor margen.",
        entidad_tipo="semana", entidad_id=id_semana(lunes), enlace=_enlace("panel:inventario-reportes"),
        periodo_desde=lunes, periodo_hasta=domingo,
        metadata={"real": real, "teorico": datos["teorico_pct"], "objetivo": float(ajustes.food_cost_objetivo)},
        huella=f"food-cost:{id_semana(lunes)}",
    )]


def pedidos(lunes, domingo, ajustes):
    """Cuentas cerradas sin factura y mesas abiertas demasiado tiempo."""
    from apps.billing.models import EmpresaFiscal
    from apps.orders.models import TableSession

    salida = []
    if EmpresaFiscal.objects.exists():
        sin_factura = (TableSession.objects.filter(status=TableSession.STATUS_CLOSED,
                                                   closed_at__date__gte=lunes, closed_at__date__lte=domingo,
                                                   total__gt=0)
                       .annotate(docs=Count("documentos")).filter(docs=0))
        n = sin_factura.count()
        if n:
            valor = sin_factura.aggregate(t=Sum("total"))["t"] or CERO
            salida.append(alerta(
                tipo="pedidos", severidad="warning" if n >= 3 else "info",
                titulo=(f"1 cuenta por {pesos(valor)} se cerró sin factura en la {texto_semana(lunes)}" if n == 1 else
                        f"{n} cuentas por {pesos(valor)} se cerraron sin factura en la {texto_semana(lunes)}"),
                descripcion=("Una venta sin factura no queda reportada ante la DIAN y es más difícil de cruzar con "
                             "la caja. Puede ser un cierre por error o una cuenta que se pagó por fuera."),
                recomendacion="Usa «Cerrar y facturar» siempre que el cliente pague; revisa estas cuentas con el cajero.",
                entidad_tipo="semana", entidad_id=id_semana(lunes), enlace=_enlace("panel:facturacion"),
                periodo_desde=lunes, periodo_hasta=domingo, metadata={"cuentas": n, "valor": str(valor)},
                huella=f"sin-factura:{id_semana(lunes)}",
            ))
    return salida


def cuentas_largas(ajustes):
    from apps.orders.models import TableSession

    limite = timezone.now() - timedelta(hours=5)
    salida = []
    for s in TableSession.objects.filter(status=TableSession.STATUS_OPEN, opened_at__lt=limite).select_related("table"):
        horas = int((timezone.now() - s.opened_at).total_seconds() // 3600)
        salida.append(alerta(
            tipo="pedidos", severidad="info",
            titulo=f"La mesa {s.table.number} lleva {horas} horas con la cuenta abierta",
            descripcion=(f"La cuenta se abrió a las {timezone.localtime(s.opened_at):%H:%M} y sigue abierta con "
                         f"{pesos(s.current_total())}. Puede ser una mesa que ya se fue sin cerrar."),
            recomendacion="Confirma si el cliente sigue en la mesa; si ya se fue, cierra y factura la cuenta.",
            entidad_tipo="sesion", entidad_id=str(s.id), enlace=_enlace("panel:table-detail", table_id=s.table_id),
            periodo_desde=timezone.localtime(s.opened_at).date(), periodo_hasta=timezone.localdate(),
            huella=f"cuenta-larga:{s.id}",
        ))
    return salida


def empleados(ajustes):
    from apps.staffing.models import Turno

    limite = timezone.now() - timedelta(hours=14)
    salida = []
    for t in Turno.objects.filter(salida__isnull=True, entrada__lt=limite).select_related("empleado"):
        horas = int((timezone.now() - t.entrada).total_seconds() // 3600)
        salida.append(alerta(
            tipo="empleados", severidad="info",
            titulo=f"{t.empleado.nombre} lleva {horas} horas marcado sin salida",
            descripcion=(f"Marcó entrada el {fecha_corta(timezone.localtime(t.entrada).date())} a las "
                         f"{timezone.localtime(t.entrada):%H:%M} y no ha marcado salida. Si se le olvidó, sus "
                         "horas y su parte de la propina quedan mal calculadas."),
            recomendacion="Pídele que marque la salida o corrígela con la hora real.",
            entidad_tipo="empleado", entidad_id=str(t.empleado_id), enlace=_enlace("panel:empleados"),
            periodo_desde=timezone.localtime(t.entrada).date(), periodo_hasta=timezone.localdate(),
            huella=f"sin-salida:{t.id}",
        ))
    return salida


def ventas_del_dia(fecha, ajustes):
    """Un día que vendió mucho menos que ese mismo día de la semana normalmente."""
    ventas = _ventas_entre(fecha, fecha)
    anteriores = [_ventas_entre(fecha - timedelta(weeks=i), fecha - timedelta(weeks=i)) for i in range(1, 5)]
    con_ventas = [v for v in anteriores if v > 0]
    if len(con_ventas) < 2:
        return []
    normal = sum(con_ventas, CERO) / len(con_ventas)
    if normal < 100000 or ventas >= normal * Decimal("0.7"):
        return []
    caida = (normal - ventas) * 100 / normal
    dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    return [alerta(
        tipo="ventas", severidad="info",
        titulo=f"El {dias[fecha.weekday()]} {fecha:%d/%m} vendiste {pct(caida, 0)}% menos que un {dias[fecha.weekday()]} normal",
        descripcion=(f"Ese día se vendieron {pesos(ventas)}; los últimos {dias[fecha.weekday()]} vendieron en "
                     f"promedio {pesos(normal)}."),
        recomendacion=("Puede ser el clima, un festivo o la competencia. Si se repite, una promoción para ese "
                       "día ayuda a moverlo."),
        entidad_tipo="dia", entidad_id=fecha.isoformat(), enlace=_enlace("panel:ventas"),
        periodo_desde=fecha, periodo_hasta=fecha,
        metadata={"ventas": str(ventas), "normal": str(normal.quantize(Decimal('1')))},
        huella=f"ventas-dia:{fecha.isoformat()}",
    )]


def reservas(lunes, domingo, ajustes):
    from apps.reservas.models import Reserva

    qs = Reserva.objects.filter(fecha__gte=lunes, fecha__lte=domingo, estado=Reserva.NO_SHOW)
    n = qs.count()
    if n < 3:
        return []
    personas = qs.aggregate(p=Sum("personas"))["p"] or 0
    return [alerta(
        tipo="reservas", severidad="info",
        titulo=f"{n} reservas no llegaron en la {texto_semana(lunes)} ({personas} personas)",
        descripcion=("Cada reserva que no llega deja una mesa vacía que se le pudo dar a otro cliente."),
        recomendacion=("Envía el recordatorio por WhatsApp el día anterior (en Reservas hay un botón para eso) y "
                       "pide que confirmen su asistencia."),
        entidad_tipo="semana", entidad_id=id_semana(lunes), enlace=_enlace("panel:reservas"),
        periodo_desde=lunes, periodo_hasta=domingo, metadata={"reservas": n, "personas": personas},
        huella=f"no-show:{id_semana(lunes)}",
    )]


DETECTORES_SEMANA = [inventario, mermas, recetas, compras, costos, pedidos, reservas]
