"""Compatibilidad con la forma vieja de las opciones de un producto.

Antes, cada producto guardaba sus toppings como una lista JSON de grupos y los
pedidos elegían por posición: `[{"grupo": 0, "valor": 1}]`. Desde la carta v1
la fuente de verdad son las tablas (tamaños, grupos de adiciones y opciones),
pero los pedidos por QR, la app de meseros, el panel y los sitios con la carta
vieja (`?formato=cloudin`) siguen hablando la forma vieja. Este módulo la arma
desde las tablas, idéntica a la de antes:

    [{"nombre": "Elige la carne", "tipo": "uno", "obligatorio": true,
      "valores": [{"nombre": "Brisket", "precio": 0}, …]}, …]

Si el producto tiene tamaños, van primero como un grupo «Presentación» (elige
uno, obligatorio) y el precio base pasa a ser el del tamaño más barato; cada
opción lleva la diferencia. Así «precio base + lo que suman las opciones» da
siempre el precio correcto.

Para que las listas no hagan una consulta por producto, prefetch con
`PREFETCH_LEGACY`.
"""

from decimal import Decimal

from django.db import transaction

from apps.common.keys import key_from, unique_key

GRUPO_PRESENTACION = "Presentación"
NOMBRE_BASE = "Normal"
PREFETCH_LEGACY = ("variants", "modifier_links__group__options")


def _variantes(producto) -> list:
    if not producto.pk:
        return []
    return list(producto.variants.all())


def precio_legacy(producto) -> Decimal | None:
    """Precio desde el que suman las opciones: el del producto, o el menor de sus tamaños."""
    if producto.price is None:
        return None
    variantes = _variantes(producto)
    if not variantes:
        return producto.price
    return min([producto.price, *(v.price for v in variantes)])


def opciones_legacy(producto, incluir_variantes: bool = True) -> list:
    """Tamaños y adiciones del producto en la forma vieja (lista de grupos)."""
    if not producto.pk:
        return []
    grupos = []
    variantes = _variantes(producto) if incluir_variantes else []
    if variantes and producto.price is not None:
        base = precio_legacy(producto)
        valores = [{"nombre": producto.base_label or NOMBRE_BASE, "precio": int(producto.price - base)}]
        valores += [{"nombre": v.name, "precio": int(v.price - base)} for v in variantes]
        grupos.append({"nombre": GRUPO_PRESENTACION, "tipo": "uno", "obligatorio": True, "valores": valores})

    for enlace in producto.modifier_links.all():
        g = enlace.group
        valores = [{"nombre": o.name, "precio": int(o.price_delta)} for o in g.options.all()]
        if not valores:
            continue
        if g.max_select == 1:
            grupos.append({"nombre": g.name, "tipo": "uno", "obligatorio": g.min_select >= 1, "valores": valores})
            continue
        grupo = {"nombre": g.name, "tipo": "varios", "obligatorio": g.min_select >= 1, "valores": valores}
        if g.max_select:
            grupo["maximo"] = g.max_select
        if g.min_select:
            grupo["minimo"] = g.min_select
        grupos.append(grupo)
    return grupos


def guardar_opciones_legacy(producto, grupos: list) -> None:
    """Reemplaza las adiciones del producto con una lista en la forma vieja.

    La usan el formulario viejo del panel y la importación de la carta vieja.
    Los tamaños (variantes) no se tocan: la forma vieja no los distingue.
    Los grupos que queden sin ningún producto se borran.
    """
    with transaction.atomic(using=producto._state.db):
        _guardar_opciones_legacy(producto, grupos)


def _guardar_opciones_legacy(producto, grupos: list) -> None:
    from .models import ModifierGroup, ModifierOption, ProductModifierGroup

    anteriores = list(producto.modifier_links.select_related("group"))
    producto.modifier_links.all().delete()
    for enlace in anteriores:
        if not enlace.group.product_links.exists():
            enlace.group.delete()

    for posicion, g in enumerate(grupos or []):
        uno = g.get("tipo") == "uno"
        maximo = 1 if uno else (int(g["maximo"]) if g.get("maximo") else None)
        minimo = (1 if g.get("obligatorio") else 0) if uno else int(g.get("minimo") or 0)
        base = f"{producto.key}-{key_from(g['nombre'], 'grupo')}"
        grupo = ModifierGroup.objects.create(
            key=unique_key(base, lambda k: ModifierGroup.objects.filter(key=k).exists()),
            name=str(g["nombre"])[:60], min_select=minimo, max_select=maximo,
        )
        for j, v in enumerate(g.get("valores") or []):
            ModifierOption.objects.create(group=grupo, name=str(v["nombre"])[:60],
                                          price_delta=Decimal(str(v.get("precio") or 0)), position=j)
        ProductModifierGroup.objects.create(product=producto, group=grupo, position=posicion)
