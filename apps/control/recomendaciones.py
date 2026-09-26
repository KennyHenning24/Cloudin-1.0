"""Qué se vende, qué deja plata y qué conviene hacer: el analista de datos del panel.

Tres herramientas clásicas del análisis de restaurantes, en lenguaje sencillo:

1. Ranking de productos: unidades, ingresos, participación y tendencia contra
   el período anterior.
2. Ingeniería de menú (Kasavana y Smith): cada plato según qué tanto se pide y
   cuánto deja. Estrellas, caballos de batalla, enigmas y perros, traducidos a
   «protégelo», «súbele un poco», «dale vitrina» y «replantéalo».
3. Canasta: qué productos se piden juntos, para armar combos.

Todo sale de las comandas cobradas (sin anulaciones ni cortesías) y, cuando
hay receta, del costo real de los insumos.
"""

from collections import Counter
from datetime import timedelta
from decimal import Decimal
from itertools import combinations

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Sum
from django.db.models.functions import ExtractHour, ExtractIsoWeekDay
from django.urls import reverse
from django.utils import timezone

from .detectores import pct, pesos

CERO = Decimal("0")
LINEA = ExpressionWrapper(F("unit_price") * F("quantity"), output_field=DecimalField(max_digits=14, decimal_places=2))
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábados", "domingos"]
DIA = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def plato_de(producto_menu, nombre_linea) -> str:
    """El plato sin sus opciones: «Sandwich Brisket · Papas» cuenta como «Sandwich Brisket»."""
    if producto_menu:
        return producto_menu
    return (nombre_linea or "").split(" · ")[0].strip()


def _por_plato(qs, con_cuentas=False):
    extra = {"cuentas": Count("order__session", distinct=True)} if con_cuentas else {}
    agrupado = {}
    for f in qs.values("product__name", "product_name").annotate(unidades=Sum("quantity"), ingresos=Sum(LINEA), **extra):
        clave = plato_de(f["product__name"], f["product_name"])
        d = agrupado.setdefault(clave, {"product_name": clave, "unidades": 0, "ingresos": CERO, "cuentas": 0})
        d["unidades"] += f["unidades"] or 0
        d["ingresos"] += f["ingresos"] or CERO
        d["cuentas"] += f.get("cuentas") or 0
    return agrupado

CLASES = {
    "estrella": {"nombre": "Estrella", "color": "menta",
                 "idea": "Se vende mucho y deja buena ganancia. Protégelo: siempre disponible, igual receta, en un lugar visible."},
    "caballo": {"nombre": "Caballo de batalla", "color": "durazno",
                "idea": "Se vende mucho pero deja poco. Súbele un poco el precio o ajusta la porción o el costo de la receta."},
    "enigma": {"nombre": "Enigma", "color": "lavanda",
               "idea": "Deja buena ganancia pero se pide poco. Dale vitrina: foto, primer lugar en la carta y que el mesero lo recomiende."},
    "perro": {"nombre": "Por replantear", "color": "rosa",
              "idea": "Se pide poco y deja poco. Renuévalo o considera sacarlo de la carta."},
}


def _lineas(desde, hasta):
    from apps.orders.models import Order, OrderItem

    return (OrderItem.objects.filter(order__created_at__date__gte=desde, order__created_at__date__lte=hasta,
                                     novedad="")
            .exclude(order__status=Order.STATUS_CANCELLED))


def _costos():
    """Costo actual de la receta de cada producto, por nombre en minúsculas."""
    from apps.catalog.models import Product
    from apps.inventory.models import Receta

    costos = {}
    for receta in Receta.objects.filter(producto__isnull=False, activa=True).select_related("producto"):
        costos[receta.producto.name.strip().lower()] = receta.costo()
    fotos = {p.name.strip().lower(): bool(p.foto) for p in Product.objects.filter(eliminado=False)}
    return costos, fotos


def productos(desde, hasta):
    """El ranking de productos del período, con tendencia y margen."""
    dias = (hasta - desde).days + 1
    previo_desde, previo_hasta = desde - timedelta(days=dias), desde - timedelta(days=1)
    actual = _por_plato(_lineas(desde, hasta), con_cuentas=True)
    previo = _por_plato(_lineas(previo_desde, previo_hasta))
    total = sum((f["ingresos"] or CERO for f in actual.values()), CERO)
    costos, fotos = _costos()

    filas = []
    for nombre, f in actual.items():
        unidades = f["unidades"] or 0
        ingresos = f["ingresos"] or CERO
        if not unidades:
            continue
        precio = ingresos / unidades
        costo = costos.get(nombre.strip().lower())
        antes = previo.get(nombre)
        cambio = None
        if antes and antes["ingresos"]:
            cambio = float((ingresos - antes["ingresos"]) / antes["ingresos"] * 100)
        filas.append({
            "nombre": nombre,
            "unidades": unidades,
            "ingresos": ingresos,
            "participacion": float(ingresos / total * 100) if total else 0,
            "precio": precio,
            "costo": costo,
            "margen": (precio - costo) if costo is not None else None,
            "margen_pct": float((precio - costo) / precio * 100) if costo is not None and precio else None,
            "utilidad": (precio - costo) * unidades if costo is not None else None,
            "cambio": cambio,
            "unidades_antes": antes["unidades"] if antes else 0,
            "tiene_foto": fotos.get(nombre.strip().lower()),
        })
    filas.sort(key=lambda x: -x["ingresos"])
    mayor = filas[0]["ingresos"] if filas else Decimal("1")
    for i, fila in enumerate(filas, 1):
        fila["puesto"] = i
        fila["barra"] = float(fila["ingresos"] / mayor * 100) if mayor else 0
    return {"filas": filas, "total": total, "desde": desde, "hasta": hasta}


def matriz(filas):
    """Ingeniería de menú. Sin costos, el margen se reemplaza por el precio promedio
    (y se avisa), para que la matriz igual sirva de guía."""
    if len(filas) < 4:
        return {"cuadrantes": {}, "con_costos": False, "suficiente": False}
    con_costos = sum(1 for f in filas if f["margen"] is not None) >= max(3, len(filas) // 2)
    unidades_total = sum(f["unidades"] for f in filas)
    umbral_popularidad = 0.7 / len(filas)

    def valor(f):
        if con_costos:
            return f["margen"] if f["margen"] is not None else None
        return f["precio"]

    medibles = [f for f in filas if valor(f) is not None]
    peso = sum(f["unidades"] for f in medibles) or 1
    umbral_margen = sum((valor(f) * f["unidades"] for f in medibles), CERO) / peso
    cuadrantes = {k: [] for k in CLASES}
    for f in medibles:
        popular = f["unidades"] / unidades_total >= umbral_popularidad
        rentable = valor(f) >= umbral_margen
        clase = ("estrella" if popular and rentable else "caballo" if popular else
                 "enigma" if rentable else "perro")
        f["clase"] = clase
        cuadrantes[clase].append(f)
    return {
        "cuadrantes": {k: {"info": CLASES[k], "platos": v} for k, v in cuadrantes.items()},
        "con_costos": con_costos, "suficiente": True,
    }


def pares(desde, hasta, minimo=3):
    """Qué se pide junto en la misma cuenta."""
    por_cuenta = {}
    for fila in _lineas(desde, hasta).values("order__session", "product__name", "product_name").distinct():
        por_cuenta.setdefault(fila["order__session"], set()).add(plato_de(fila["product__name"], fila["product_name"]))
    apariciones = Counter()
    juntos = Counter()
    for productos_cuenta in por_cuenta.values():
        apariciones.update(productos_cuenta)
        for a, b in combinations(sorted(productos_cuenta), 2):
            juntos[(a, b)] += 1
    resultado = []
    for (a, b), n in juntos.most_common(20):
        if n < minimo:
            break
        base, otro = (a, b) if apariciones[a] <= apariciones[b] else (b, a)
        resultado.append({"a": base, "b": otro, "veces": n,
                          "confianza": round(n * 100 / apariciones[base]), "cuentas": len(por_cuenta)})
    resultado.sort(key=lambda x: (-x["confianza"], -x["veces"]))
    return resultado


def ritmo(desde, hasta):
    """Ventas por día de la semana y por hora."""
    lineas = _lineas(desde, hasta)
    por_dia = {f["d"]: f["t"] or CERO for f in lineas.annotate(d=ExtractIsoWeekDay("order__created_at"))
               .values("d").annotate(t=Sum(LINEA))}
    por_hora = {f["h"]: f["t"] or CERO for f in lineas.annotate(h=ExtractHour("order__created_at"))
                .values("h").annotate(t=Sum(LINEA))}
    # Cuántas veces aparece cada día de la semana en el período, para promediar bien.
    veces = Counter((desde + timedelta(days=i)).isoweekday() for i in range((hasta - desde).days + 1))
    dias = [{"dia": DIAS[d - 1], "dia_uno": DIA[d - 1], "total": por_dia.get(d, CERO),
             "promedio": por_dia.get(d, CERO) / veces[d] if veces[d] else CERO} for d in range(1, 8)]
    return {"dias": dias, "horas": sorted(por_hora.items())}


def _hora_texto(h):
    sufijo = "a. m." if h < 12 else "p. m."
    return f"{h % 12 or 12}:00 {sufijo}"


def recomendaciones(desde=None, hasta=None, limite=8):
    """Las tarjetas de recomendación, de la más importante a la menos."""
    hasta = hasta or timezone.localdate()
    desde = desde or hasta - timedelta(days=29)
    datos = productos(desde, hasta)
    filas = datos["filas"]
    tarjetas = []
    enlace_carta = reverse("panel:configuracion") + "?paso=menu"

    def agregar(prioridad, icono, color, titulo, texto, accion="", enlace=""):
        tarjetas.append({"prioridad": prioridad, "icono": icono, "color": color, "titulo": titulo,
                         "texto": texto, "accion": accion, "enlace": enlace})

    if not filas:
        agregar(1, "info", "cielo", "Todavía no hay ventas para analizar",
                "Cuando el restaurante empiece a vender, aquí aparecerán los platos que más dinero generan y qué hacer con cada uno.")
        return tarjetas, datos

    top = filas[0]
    agregar(10, "estrella", "menta", f"{top['nombre']} genera el {pct(top['participacion'], 0)}% de tus ventas",
            f"Es tu plato más importante: {top['unidades']} vendidos por {pesos(top['ingresos'])} en el período. "
            "Tenlo siempre disponible, con sus insumos asegurados y en el primer lugar de la carta.",
            "Ver en la carta", enlace_carta)

    top3 = sum(f["participacion"] for f in filas[:3])
    if len(filas) >= 6 and top3 >= 50:
        nombres = ", ".join(f["nombre"] for f in filas[:3])
        agregar(8, "capas", "durazno", f"Tres platos hacen el {pct(top3, 0)}% de tus ventas",
                f"{nombres}. Si alguno se agota, se nota en la caja: revisa su inventario antes de cada servicio.")

    subiendo = [f for f in filas if f["cambio"] is not None and f["cambio"] >= 30 and f["unidades"] >= 5]
    if subiendo:
        f = max(subiendo, key=lambda x: x["cambio"])
        agregar(7, "sube", "menta", f"{f['nombre']} subió {pct(f['cambio'], 0)}%",
                f"Pasó de {f['unidades_antes']} a {f['unidades']} unidades frente al período anterior. "
                "Es buen momento para mostrarlo en redes o recomendarlo en la mesa.")
    bajando = [f for f in filas if f["cambio"] is not None and f["cambio"] <= -30 and f["unidades_antes"] >= 5]
    if bajando:
        f = min(bajando, key=lambda x: x["cambio"])
        agregar(7, "baja", "rosa", f"{f['nombre']} bajó {pct(abs(f['cambio']), 0)}%",
                f"Pasó de {f['unidades_antes']} a {f['unidades']} unidades. Revisa si cambió algo: precio, "
                "porción, disponibilidad o un comentario de los clientes.")

    tabla = matriz(filas)
    if tabla["suficiente"]:
        cuad = tabla["cuadrantes"]
        if cuad["caballo"]["platos"]:
            f = max(cuad["caballo"]["platos"], key=lambda x: x["unidades"])
            detalle = (f" Hoy deja {pesos(f['margen'])} por plato ({pct(f['margen_pct'], 0)}%)."
                       if f["margen"] is not None else "")
            agregar(9, "balanza", "durazno", f"{f['nombre']}: se vende mucho y deja poco",
                    "Subirle $1.000 o $2.000, o ajustar la porción, casi no afecta cuánto se pide y mejora tu "
                    "ganancia en cada venta." + detalle, "Ver receta", reverse("panel:recetas"))
        if cuad["enigma"]["platos"]:
            f = max(cuad["enigma"]["platos"], key=lambda x: (x["margen"] or x["precio"]))
            agregar(8, "lupa", "lavanda", f"{f['nombre']} deja buena ganancia pero se pide poco",
                    "Dale vitrina: una buena foto en la carta digital, el primer lugar de su categoría y que el "
                    "mesero lo recomiende.", "Editar en la carta", enlace_carta)
        if cuad["perro"]["platos"] and len(filas) >= 8:
            nombres = ", ".join(f["nombre"] for f in cuad["perro"]["platos"][:3])
            agregar(5, "reciclar", "rosa", "Platos por replantear",
                    f"{nombres} se piden poco y dejan poco. Renuévalos o considera sacarlos: una carta más corta "
                    "es más fácil de preparar y de elegir.")

    juntos = pares(desde, hasta)
    if juntos:
        p = juntos[0]
        if p["confianza"] >= 30:
            agregar(8, "combo", "cielo", f"Quien pide {p['a']} suele pedir {p['b']}",
                    f"Pasó en el {p['confianza']}% de las cuentas con {p['a']} ({p['veces']} veces). Ofrécelos "
                    "juntos como combo o que el mesero sugiera el segundo.")

    r = ritmo(desde, hasta)
    promedios = [d for d in r["dias"] if d["promedio"] > 0]
    if len(promedios) >= 4:
        media = sum((d["promedio"] for d in promedios), CERO) / len(promedios)
        flojo = min(promedios, key=lambda d: d["promedio"])
        fuerte = max(promedios, key=lambda d: d["promedio"])
        if media and flojo["promedio"] <= media * Decimal("0.6"):
            menos = (media - flojo["promedio"]) * 100 / media
            agregar(6, "calendario", "amarillo", f"Los {flojo['dia']} vendes {pct(menos, 0)}% menos",
                    f"Un {flojo['dia_uno']} promedio vende "
                    f"{pesos(flojo['promedio'])}, contra {pesos(fuerte['promedio'])} de los {fuerte['dia']}. "
                    "Una promoción o un plato especial ese día ayuda a llenarlo.")
    if r["horas"]:
        hora, total = max(r["horas"], key=lambda x: x[1])
        if total:
            agregar(4, "reloj", "cielo", f"Tu hora más fuerte es a las {_hora_texto(hora)}",
                    "Ten la cocina y el equipo listos antes de esa hora: ahí se juega la mayor parte de la venta.")

    sin_foto = [f for f in filas[:6] if f["tiene_foto"] is False]
    if sin_foto:
        nombres = ", ".join(f["nombre"] for f in sin_foto[:3])
        agregar(5, "foto", "lavanda", f"{len(sin_foto)} de tus platos más vendidos no tienen foto",
                f"{nombres}. En la carta digital la foto es lo primero que mira el cliente: súbela desde el panel.",
                "Subir fotos", enlace_carta)

    from apps.catalog.models import Product

    vendidos = {f["nombre"].strip().lower() for f in filas}
    olvidados = [p.name for p in Product.objects.filter(eliminado=False, is_available=True,
                                                       created_at__date__lt=desde)
                 if p.name.strip().lower() not in vendidos]
    if olvidados and len(filas) >= 5:
        agregar(3, "dormido", "gris", f"{len(olvidados)} productos no se vendieron en el período",
                ", ".join(olvidados[:5]) + ("…" if len(olvidados) > 5 else "")
                + ". Revisa si siguen teniendo sentido en la carta.", "Ver la carta", enlace_carta)

    tarjetas.sort(key=lambda t: -t["prioridad"])
    return tarjetas[:limite], datos
