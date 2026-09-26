"""Toppings, adiciones y variantes de un producto.

Un producto expone sus opciones como una lista de grupos (se arma desde las
tablas del catálogo en `legacy.py`):

    [{"nombre": "Elige la carne", "tipo": "uno", "obligatorio": true,
      "valores": [{"nombre": "Brisket", "precio": 0}, {"nombre": "Pastrami", "precio": 0}]},
     {"nombre": "Adiciones", "tipo": "varios", "obligatorio": false, "maximo": 3,
      "valores": [{"nombre": "Tocineta", "precio": 4000}]}]

- `uno`: se elige exactamente una (radio). Si es obligatorio, no se puede pedir sin elegir.
- `varios`: se eligen cero o más (checkbox), hasta `maximo` si lo hay.
- `precio` es lo que la opción **suma** al precio del producto (0 si no cambia).

Quien pide manda lo que eligió como `[{"grupo": 0, "valor": 1}, …]` (posiciones).
El precio final lo calcula siempre el servidor: nunca se confía en el que manda
la tablet o el sitio.
"""

from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError

TIPOS = ("uno", "varios")
MAX_GRUPOS = 12
MAX_VALORES = 30


def _texto(valor, largo):
    return str(valor or "").strip()[:largo]


def _precio(valor) -> Decimal:
    try:
        precio = Decimal(str(valor if valor not in (None, "") else "0"))
    except (InvalidOperation, ValueError):
        raise ValidationError("Hay un precio de opción que no es un número.")
    if precio < 0:
        raise ValidationError("El precio de una opción no puede ser negativo.")
    return precio.quantize(Decimal("1"))


def limpiar_grupos(grupos) -> list:
    """Valida y normaliza la lista de grupos antes de guardarla en el producto."""
    if grupos in (None, ""):
        return []
    if not isinstance(grupos, list):
        raise ValidationError("Las opciones deben ser una lista de grupos.")
    limpios = []
    for g in grupos[:MAX_GRUPOS]:
        if not isinstance(g, dict):
            continue
        nombre = _texto(g.get("nombre"), 60)
        valores = []
        for v in (g.get("valores") or [])[:MAX_VALORES]:
            if not isinstance(v, dict):
                continue
            nombre_valor = _texto(v.get("nombre"), 60)
            if nombre_valor:
                valores.append({"nombre": nombre_valor, "precio": int(_precio(v.get("precio")))})
        if not nombre or not valores:
            continue
        tipo = g.get("tipo") if g.get("tipo") in TIPOS else "varios"
        grupo = {"nombre": nombre, "tipo": tipo, "obligatorio": bool(g.get("obligatorio")) and tipo == "uno",
                 "valores": valores}
        if tipo == "varios" and g.get("maximo"):
            try:
                grupo["maximo"] = max(1, min(int(g["maximo"]), len(valores)))
            except (TypeError, ValueError):
                pass
        limpios.append(grupo)
    return limpios


def aplicar(producto, elegidas, nota=""):
    """Lo que eligió el cliente, validado contra el producto.

    Devuelve (nombre_linea, precio_unitario, opciones_json, nota). Lanza
    ValidationError con un mensaje para mostrarle a quien pide.

    Las opciones salen de las tablas del catálogo en la forma vieja (ver
    legacy.py): si el producto tiene tamaños, son el primer grupo.
    """
    if producto.price is None:
        raise ValidationError(f"«{producto.name}» todavía no tiene precio.")
    grupos = producto.opciones or []
    elegidas = elegidas or []
    if not isinstance(elegidas, list):
        raise ValidationError("Las opciones elegidas no se entienden.")

    por_grupo = {}
    for e in elegidas:
        try:
            gi, vi = int(e.get("grupo")), int(e.get("valor"))
        except (AttributeError, TypeError, ValueError):
            raise ValidationError("Las opciones elegidas no se entienden.")
        if not (0 <= gi < len(grupos)) or not (0 <= vi < len(grupos[gi]["valores"])):
            raise ValidationError(f"Una opción de «{producto.name}» ya no existe. Actualiza el menú.")
        por_grupo.setdefault(gi, [])
        if vi not in por_grupo[gi]:
            por_grupo[gi].append(vi)

    precio = producto.precio_legacy
    resumen, detalle = [], []
    for gi, grupo in enumerate(grupos):
        vis = por_grupo.get(gi, [])
        if grupo["tipo"] == "uno":
            if len(vis) > 1:
                raise ValidationError(f"En «{grupo['nombre']}» se elige solo una opción.")
            if grupo.get("obligatorio") and not vis:
                raise ValidationError(f"Falta elegir «{grupo['nombre']}» para {producto.name}.")
        else:
            if grupo.get("maximo") and len(vis) > grupo["maximo"]:
                raise ValidationError(f"En «{grupo['nombre']}» se eligen máximo {grupo['maximo']}.")
            if grupo.get("minimo") and len(vis) < grupo["minimo"]:
                raise ValidationError(f"En «{grupo['nombre']}» elige al menos {grupo['minimo']} para {producto.name}.")
        for vi in vis:
            valor = grupo["valores"][vi]
            extra = Decimal(str(valor.get("precio") or 0))
            precio += extra
            # En adiciones se aclara lo que suman; en variantes (peso, tamaño) basta el nombre.
            con_precio = extra and grupo["tipo"] == "varios"
            resumen.append(valor["nombre"] + (f" (+${int(extra):,})".replace(",", ".") if con_precio else ""))
            detalle.append({"grupo": grupo["nombre"], "nombre": valor["nombre"], "precio": int(extra)})

    nombre = producto.name
    if resumen:
        nombre = f"{producto.name} · {', '.join(resumen)}"
    nota = _texto(nota, 200) if producto.permite_observacion else ""
    return nombre[:120], precio, detalle, nota
