"""La mecánica del inventario: mover stock, costear y descontar lo vendido.

Todo entra y sale por aquí. Ninguna vista toca `Existencia.cantidad` ni
`Insumo.costo_promedio` directamente: así el kardex siempre explica el saldo.

Costeo por **promedio ponderado**, recalculado en tiempo real:

    promedio nuevo = (valor del saldo + valor de la entrada)
                     / (cantidad del saldo + cantidad que entra)

Las salidas usan el promedio vigente en ese momento y no se recalculan hacia
atrás, que es lo que espera cualquier contador revisando el sistema.
"""

from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Sum
from django.utils import timezone

from .models import (
    Bodega,
    Compra,
    Conteo,
    Existencia,
    Insumo,
    Lote,
    Movimiento,
    Receta,
)

CERO = Decimal("0")
CUATRO = Decimal("0.0001")


def _existencia(insumo, bodega):
    db = insumo._state.db
    ex, _ = Existencia.objects.using(db).get_or_create(
        insumo=insumo, bodega=bodega, defaults={"cantidad": CERO}
    )
    return ex


# ------------------------------------------------------------------ entradas


def registrar_entrada(
    insumo, bodega, cantidad, costo_unitario, *, tipo=Movimiento.COMPRA, motivo="",
    usuario="", compra=None, lote_codigo="", vence=None, turno=None, conteo=None,
    momento=None,
):
    """Mete stock y recalcula el costo promedio ponderado del insumo."""
    cantidad = Decimal(str(cantidad))
    if cantidad <= 0:
        raise ValidationError("La cantidad que entra tiene que ser mayor que cero.")
    costo_unitario = Decimal(str(costo_unitario or 0))
    db = insumo._state.db

    with transaction.atomic(using=db):
        ex = _existencia(insumo, bodega)
        saldo_antes = insumo.stock
        valor_antes = saldo_antes * insumo.costo_promedio
        valor_entra = cantidad * costo_unitario

        nuevo_saldo = saldo_antes + cantidad
        # El promedio solo se mueve si la entrada trae un costo; una entrada sin
        # valor (un regalo, un ajuste sin precio) no debe diluir el costo real.
        if costo_unitario > 0 and nuevo_saldo > 0:
            insumo.costo_promedio = ((valor_antes + valor_entra) / nuevo_saldo).quantize(CUATRO)
        elif saldo_antes <= 0 and costo_unitario > 0:
            insumo.costo_promedio = costo_unitario.quantize(CUATRO)
        insumo.save(update_fields=["costo_promedio", "actualizado"])

        ex.cantidad = ex.cantidad + cantidad
        ex.save(update_fields=["cantidad", "actualizado"])

        lote = None
        if insumo.perecedero and (lote_codigo or vence):
            lote = Lote.objects.using(db).create(
                insumo=insumo, bodega=bodega, codigo=lote_codigo or "",
                vence=vence, cantidad=cantidad, costo_unitario=costo_unitario,
            )

        return Movimiento.objects.using(db).create(
            insumo=insumo, bodega=bodega, tipo=tipo, cantidad=cantidad,
            costo_unitario=costo_unitario,
            valor_total=(cantidad * costo_unitario).quantize(Decimal("0.01")),
            saldo_cantidad=nuevo_saldo, saldo_costo_promedio=insumo.costo_promedio,
            motivo=motivo, usuario=usuario or "", compra=compra, lote=lote, turno=turno,
            conteo=conteo, momento=momento or timezone.now(),
        )


# ------------------------------------------------------------------- salidas


def _descargar_lotes(insumo, bodega, cantidad):
    """Saca del lote que vence primero (rotación PEPS), y devuelve cuál usó."""
    db = insumo._state.db
    restante = cantidad
    usado = None
    lotes = Lote.objects.using(db).filter(
        insumo=insumo, bodega=bodega, cantidad__gt=0
    ).order_by(F("vence").asc(nulls_last=True), "creado")
    for lote in lotes:
        if restante <= 0:
            break
        toma = min(lote.cantidad, restante)
        lote.cantidad -= toma
        lote.save(update_fields=["cantidad"])
        restante -= toma
        usado = usado or lote
    return usado


def registrar_salida(
    insumo, bodega, cantidad, *, tipo=Movimiento.AJUSTE_NEGATIVO, motivo="", usuario="",
    orden=None, turno=None, conteo=None, permitir_negativo=True, momento=None,
):
    """Saca stock al costo promedio vigente.

    `permitir_negativo` en True a propósito: el servicio del restaurante no se
    detiene porque el inventario esté mal cargado. El saldo negativo queda
    visible como alerta para que alguien lo corrija con un conteo.
    """
    cantidad = Decimal(str(cantidad))
    if cantidad <= 0:
        raise ValidationError("La cantidad que sale tiene que ser mayor que cero.")
    db = insumo._state.db

    with transaction.atomic(using=db):
        ex = _existencia(insumo, bodega)
        if not permitir_negativo and ex.cantidad < cantidad:
            raise ValidationError(
                f"No hay suficiente {insumo.nombre}: hay {ex.cantidad} y se piden {cantidad}."
            )

        costo = insumo.costo_promedio
        ex.cantidad = ex.cantidad - cantidad
        ex.save(update_fields=["cantidad", "actualizado"])

        lote = _descargar_lotes(insumo, bodega, cantidad) if insumo.perecedero else None

        return Movimiento.objects.using(db).create(
            insumo=insumo, bodega=bodega, tipo=tipo, cantidad=cantidad, costo_unitario=costo,
            valor_total=(cantidad * costo).quantize(Decimal("0.01")),
            saldo_cantidad=insumo.stock, saldo_costo_promedio=costo,
            motivo=motivo, usuario=usuario or "", orden=orden, turno=turno, lote=lote,
            conteo=conteo, momento=momento or timezone.now(),
        )


# -------------------------------------------------------------------- compras


def registrar_compra(compra, *, usuario="") -> Compra:
    """Pasa la compra de borrador a registrada: crea las entradas del kardex."""
    if compra.estado == Compra.REGISTRADA:
        raise ValidationError("Esa compra ya estaba registrada.")
    if not compra.items.exists():
        raise ValidationError("La compra no tiene líneas.")

    db = compra._state.db
    with transaction.atomic(using=db):
        for item in compra.items.select_related("insumo"):
            registrar_entrada(
                item.insumo,
                compra.bodega,
                item.cantidad_consumo(),
                item.costo_consumo(),
                tipo=Movimiento.COMPRA,
                motivo=f"Compra {compra.numero_factura or compra.pk} · {compra.proveedor.nombre}",
                usuario=usuario or compra.usuario,
                compra=compra,
                lote_codigo=item.lote,
                vence=item.vence,
            )
            insumo = item.insumo
            insumo.ultimo_precio_compra = item.valor_unitario
            insumo.ultima_compra = compra.fecha
            if insumo.proveedor_id is None:
                insumo.proveedor = compra.proveedor
            insumo.save(update_fields=["ultimo_precio_compra", "ultima_compra", "proveedor"])

        compra.total = compra.calcular_total()
        compra.estado = Compra.REGISTRADA
        compra.registrada_en = timezone.now()
        compra.usuario = usuario or compra.usuario
        compra.save(update_fields=["total", "estado", "registrada_en", "usuario"])
    return compra


# -------------------------------------------- descuento automático al vender


def receta_de(producto):
    return getattr(producto, "receta", None)


def _producto_de_linea(item):
    """El producto del menú al que corresponde una línea del pedido.

    Las líneas que llegan del sitio web del restaurante traen nombre y precio,
    no el id del producto (el sitio tiene su propio catálogo con opciones). Para
    que esas ventas también muevan inventario, se busca el producto por nombre.
    """
    from apps.catalog.models import Product

    if item.product_id:
        return item.product
    if not item.product_name:
        return None
    db = item._state.db
    return Product.objects.using(db).filter(name__iexact=item.product_name.strip()).first()


def consumo_de_pedido(order) -> dict:
    """Los insumos que consume una comanda, según las recetas de sus platos."""
    consumo = {}
    for item in order.items.select_related("product"):
        if item.novedad == "anulado":
            # Anulado: no se preparó (o se botó). Si se preparó, la diferencia la
            # muestra el conteo físico y Cloudin Control la cruza con la anulación.
            continue
        producto = _producto_de_linea(item)
        if producto is None:
            continue
        receta = receta_de(producto)
        if receta is None or not receta.activa:
            continue
        for insumo, cantidad in receta.explosion(Decimal(item.quantity)).items():
            consumo[insumo] = consumo.get(insumo, CERO) + cantidad
    return consumo


def descontar_pedido(order, *, bodega=None, usuario="", turno=None) -> list:
    """Descuenta del stock lo que consumió una comanda. Idempotente.

    Se llama al facturar la mesa (no al mandar el pedido a cocina) para que un
    pedido anulado no mueva inventario. Si ya se descontó, no hace nada: el
    kardex recuerda qué comandas ya pasaron por aquí.
    """
    db = order._state.db
    if Movimiento.objects.using(db).filter(orden=order, tipo=Movimiento.VENTA).exists():
        return []

    consumo = consumo_de_pedido(order)
    if not consumo:
        return []

    bodega = bodega or Bodega.predeterminada(db)
    mesa = order.session.table.number if order.session_id else "—"
    movimientos = []
    for insumo, cantidad in consumo.items():
        if cantidad <= 0:
            continue
        movimientos.append(
            registrar_salida(
                insumo, bodega, cantidad, tipo=Movimiento.VENTA,
                motivo=f"Venta · comanda #{order.pk} · mesa {mesa}",
                usuario=usuario, orden=order, turno=turno,
            )
        )
    return movimientos


def descontar_sesion(session, *, usuario="", turno=None) -> list:
    """Descuenta el consumo de todas las comandas de una cuenta de mesa."""
    from apps.orders.models import Order

    movimientos = []
    turno = turno or session.turno
    for order in session.orders.exclude(status=Order.STATUS_CANCELLED):
        movimientos.extend(descontar_pedido(order, usuario=usuario, turno=turno))
    return movimientos


# -------------------------------------------------------------- conteo físico


def preparar_conteo(bodega, *, responsable="", solo_con_stock=False) -> Conteo:
    """Arma la planilla del conteo con el saldo que el sistema cree que hay."""
    db = bodega._state.db
    conteo = Conteo.objects.using(db).create(bodega=bodega, responsable=responsable)
    insumos = Insumo.objects.using(db).filter(activo=True)
    for insumo in insumos:
        esperado = insumo.stock_en(bodega)
        if solo_con_stock and esperado <= 0:
            continue
        conteo.items.create(insumo=insumo, esperado=esperado, contado=esperado)
    return conteo


def aplicar_conteo(conteo, *, usuario="") -> dict:
    """Convierte las diferencias del conteo en ajustes, con motivo obligatorio."""
    if conteo.estado == Conteo.APLICADO:
        raise ValidationError("Ese conteo ya se aplicó.")

    db = conteo._state.db
    resultado = {"sobrantes": 0, "faltantes": 0, "valor": CERO}
    with transaction.atomic(using=db):
        for item in conteo.items.select_related("insumo"):
            diferencia = item.diferencia
            if diferencia == 0:
                continue
            motivo = f"Conteo físico #{conteo.pk} en {conteo.bodega.nombre}"
            if diferencia > 0:
                registrar_entrada(
                    item.insumo, conteo.bodega, diferencia, item.insumo.costo_promedio,
                    tipo=Movimiento.CONTEO_POSITIVO, motivo=motivo, usuario=usuario,
                    conteo=conteo,
                )
                resultado["sobrantes"] += 1
            else:
                registrar_salida(
                    item.insumo, conteo.bodega, -diferencia,
                    tipo=Movimiento.CONTEO_NEGATIVO, motivo=motivo, usuario=usuario,
                    conteo=conteo,
                )
                resultado["faltantes"] += 1
            resultado["valor"] += item.valor_diferencia

        conteo.estado = Conteo.APLICADO
        conteo.aplicado_en = timezone.now()
        conteo.diferencia_valor = resultado["valor"]
        conteo.save(update_fields=["estado", "aplicado_en", "diferencia_valor"])
    return resultado


# ------------------------------------------------------------------- reportes


def valorizacion(db=None) -> dict:
    """Cuánta plata hay parada en insumos ahora mismo."""
    qs = Insumo.objects.using(db) if db else Insumo.objects
    total = CERO
    lineas = []
    for insumo in qs.filter(activo=True).select_related("categoria"):
        valor = insumo.valor_stock
        total += valor
        lineas.append({"insumo": insumo, "stock": insumo.stock, "valor": valor})
    lineas.sort(key=lambda x: -x["valor"])
    return {"total": total.quantize(Decimal("0.01")), "lineas": lineas}


def alertas_inventario(db=None, dias_vencimiento=3) -> list:
    """Lo que el panel tiene que avisar: stock bajo, vencimientos, negativos."""
    insumos = Insumo.objects.using(db) if db else Insumo.objects
    lotes = Lote.objects.using(db) if db else Lote.objects
    avisos = []

    for insumo in insumos.filter(activo=True):
        stock = insumo.stock
        if stock < 0:
            avisos.append({
                "nivel": "malo",
                "texto": f"{insumo.nombre} tiene saldo negativo ({stock} "
                         f"{insumo.unidad_consumo}). Hace falta un conteo físico.",
                "insumo": insumo.id,
            })
        elif insumo.stock_minimo > 0 and stock <= insumo.stock_minimo:
            avisos.append({
                "nivel": "alerta" if stock > 0 else "malo",
                "texto": f"{insumo.nombre}: quedan {stock} {insumo.unidad_consumo} "
                         f"(mínimo {insumo.stock_minimo}).",
                "insumo": insumo.id,
            })

    limite = timezone.localdate() + timedelta(days=dias_vencimiento)
    for lote in lotes.filter(cantidad__gt=0, vence__isnull=False, vence__lte=limite):
        dias = lote.dias_para_vencer
        cuando = "venció" if dias < 0 else ("vence hoy" if dias == 0 else f"vence en {dias} día(s)")
        avisos.append({
            "nivel": "malo" if dias <= 0 else "alerta",
            "texto": f"{lote.insumo.nombre} · lote {lote.codigo or lote.pk} {cuando} "
                     f"({lote.cantidad} {lote.insumo.unidad_consumo}).",
            "insumo": lote.insumo_id,
        })
    return avisos


def rentabilidad_por_plato(db=None) -> list:
    """Precio de venta menos costo de receta: qué platos dejan utilidad."""
    from apps.catalog.models import Product

    qs = Product.objects.using(db) if db else Product.objects
    filas = []
    for producto in (qs.filter(eliminado=False, price__isnull=False)
                     .select_related("category").prefetch_related("receta__items")):
        receta = receta_de(producto)
        costo = receta.costo() if receta else None
        precio = producto.price
        margen = (precio - costo) if costo is not None else None
        filas.append({
            "producto": producto,
            "precio": precio,
            "costo": costo,
            "margen": margen,
            "margen_pct": (float(margen / precio * 100) if margen is not None and precio else None),
            "food_cost_pct": (float(costo / precio * 100) if costo is not None and precio else None),
            "tiene_receta": receta is not None,
        })
    filas.sort(key=lambda f: (f["margen_pct"] is None, f["margen_pct"] or 0))
    return filas


def food_cost(desde, hasta, db=None) -> dict:
    """Food cost teórico (lo que las recetas dicen) contra el real (el kardex).

    La diferencia es la señal que importa: si el real se pasa del teórico por
    más de ~1,5 puntos, hay merma, desperdicio o error de manipulación.
    """
    from apps.orders.models import Order, OrderItem

    items = OrderItem.objects.using(db) if db else OrderItem.objects
    movs = Movimiento.objects.using(db) if db else Movimiento.objects

    lineas = items.filter(
        order__created_at__date__gte=desde, order__created_at__date__lte=hasta
    ).exclude(order__status=Order.STATUS_CANCELLED).select_related("product")

    venta = lineas.aggregate(
        v=Sum(ExpressionWrapper(
            F("unit_price") * F("quantity"),
            output_field=DecimalField(max_digits=16, decimal_places=2),
        ))
    )["v"] or CERO

    teorico = CERO
    sin_receta = 0
    for linea in lineas:
        receta = receta_de(linea.product) if linea.product_id else None
        if receta is None:
            sin_receta += 1
            continue
        teorico += receta.costo() * linea.quantity

    consumo = movs.filter(
        momento__date__gte=desde, momento__date__lte=hasta, tipo__in=Movimiento.SALIDAS
    )
    real = consumo.aggregate(v=Sum("valor_total"))["v"] or CERO
    descontrolado = consumo.filter(tipo__in=Movimiento.DESCONTROLADAS).aggregate(
        v=Sum("valor_total"), n=Count("id")
    )

    def pct(valor):
        return float(valor / venta * 100) if venta else None

    brecha = None
    if venta:
        brecha = round(pct(real) - pct(teorico), 2)

    return {
        "desde": desde,
        "hasta": hasta,
        "venta": venta,
        "teorico": teorico.quantize(Decimal("0.01")),
        "real": Decimal(real).quantize(Decimal("0.01")),
        "teorico_pct": pct(teorico),
        "real_pct": pct(real),
        "brecha": brecha,
        "desviado": bool(brecha is not None and brecha > 1.5),
        "merma_valor": descontrolado["v"] or CERO,
        "merma_movimientos": descontrolado["n"] or 0,
        "lineas_sin_receta": sin_receta,
    }


def rotacion(desde, hasta, db=None, limite=15) -> list:
    """Los insumos que más se mueven: lo que de verdad hay que tener siempre."""
    movs = Movimiento.objects.using(db) if db else Movimiento.objects
    filas = (
        movs.filter(momento__date__gte=desde, momento__date__lte=hasta,
                    tipo__in=Movimiento.SALIDAS)
        .values("insumo__id", "insumo__nombre", "insumo__unidad_consumo")
        .annotate(cantidad=Sum("cantidad"), valor=Sum("valor_total"), veces=Count("id"))
        .order_by("-valor")[:limite]
    )
    return list(filas)


def resumen_inventario(db=None) -> dict:
    """Los números de la portada del módulo."""
    insumos = Insumo.objects.using(db) if db else Insumo.objects
    compras = Compra.objects.using(db) if db else Compra.objects
    recetas = Receta.objects.using(db) if db else Receta.objects

    activos = insumos.filter(activo=True)
    val = valorizacion(db)
    bajos = [i for i in activos if i.bajo_minimo or i.stock < 0]
    hoy = timezone.localdate()
    mes = hoy.replace(day=1)

    gasto_mes = compras.filter(
        estado=Compra.REGISTRADA, fecha__gte=mes
    ).aggregate(v=Sum("total"))["v"] or CERO
    por_pagar = compras.filter(
        estado=Compra.REGISTRADA, medio_pago=Compra.CREDITO, pagada=False
    ).aggregate(v=Sum("total"), n=Count("id"))

    return {
        "insumos": activos.count(),
        "valorizacion": val["total"],
        "bajo_minimo": len(bajos),
        "gasto_mes": gasto_mes,
        "por_pagar": por_pagar["v"] or CERO,
        "por_pagar_n": por_pagar["n"] or 0,
        "recetas": recetas.filter(activa=True, es_subreceta=False).count(),
        "subrecetas": recetas.filter(activa=True, es_subreceta=True).count(),
    }
