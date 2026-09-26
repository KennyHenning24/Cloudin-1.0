"""Paso 2 de la carta v1: mueve los datos de la forma vieja a la nueva.

- Crea el menú «Carta» y le cuelga todas las categorías.
- Da a cada categoría y producto su `uuid` y su `key`. La clave vieja
  (`clave_externa`) se conserva tal cual; si no había, queda `cloudin-<id>`, que
  es exactamente el `id` que la carta vieja ya publicaba. Así los sitios
  conectados (Cultura Brisket, El Bembé) no notan el cambio.
- Convierte el JSON `opciones` de cada producto en grupos de adiciones y opciones:
  «uno» + obligatorio → mínimo 1 y máximo 1; «uno» → máximo 1;
  «varios» → mínimo 0 y máximo el que tuviera (o sin tope).
- Siembra las 7 etiquetas del contrato.

Tiene reversa: vuelve a armar `clave_externa` y `opciones` desde las tablas nuevas.
"""

import re
import uuid
from decimal import Decimal

from django.db import migrations
from django.utils.text import slugify

KEY_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
ETIQUETAS = [
    ("vegetariano", "Vegetariano"), ("vegano", "Vegano"), ("picante", "Picante"),
    ("sin-gluten", "Sin gluten"), ("nuevo", "Nuevo"), ("recomendado", "Recomendado"),
    ("para-compartir", "Para compartir"),
]


def _clave(texto, respaldo):
    clave = slugify(str(texto or ""))[:60].strip("-")
    return clave or respaldo


def _unica(base, usadas):
    base = base[:60].strip("-")
    candidata, n = base, 2
    while candidata in usadas:
        sufijo = f"-{n}"
        candidata = base[: 60 - len(sufijo)].rstrip("-") + sufijo
        n += 1
    usadas.add(candidata)
    return candidata


def _clave_heredada(clave_externa, pk, usadas):
    """La clave vieja tal cual si ya es válida; si no, normalizada; si no hay, cloudin-<id>."""
    vieja = (clave_externa or "").strip()
    if vieja and KEY_RE.match(vieja) and len(vieja) <= 60:
        base = vieja
    elif vieja:
        base = _clave(vieja, f"cloudin-{pk}")
    else:
        base = f"cloudin-{pk}"
    return _unica(base, usadas)


def adelante(apps, schema_editor):
    db = schema_editor.connection.alias
    Menu = apps.get_model("catalog", "Menu")
    Category = apps.get_model("catalog", "Category")
    Product = apps.get_model("catalog", "Product")
    Tag = apps.get_model("catalog", "Tag")
    ModifierGroup = apps.get_model("catalog", "ModifierGroup")
    ModifierOption = apps.get_model("catalog", "ModifierOption")
    ProductModifierGroup = apps.get_model("catalog", "ProductModifierGroup")

    for posicion, (clave, nombre) in enumerate(ETIQUETAS):
        Tag.objects.using(db).get_or_create(key=clave, defaults={"name": nombre, "position": posicion,
                                                                 "uuid": uuid.uuid4()})

    categorias = list(Category.objects.using(db).order_by("pk"))
    if not categorias:
        return  # base nueva: el menú se crea cuando se cree la primera categoría

    menu = Menu.objects.using(db).filter(key="carta").first()
    if menu is None:
        menu = Menu.objects.using(db).create(key="carta", name="Carta", uuid=uuid.uuid4())

    usadas_categorias = set()
    for c in categorias:
        c.menu_id = menu.pk
        c.uuid = c.uuid or uuid.uuid4()
        c.key = _clave_heredada(c.clave_externa, c.pk, usadas_categorias)
        c.save(update_fields=["menu", "uuid", "key"])

    usadas_grupos = set(ModifierGroup.objects.using(db).values_list("key", flat=True))
    usadas_por_categoria = {}
    for p in Product.objects.using(db).order_by("pk"):
        usadas = usadas_por_categoria.setdefault(p.category_id, set())
        p.uuid = p.uuid or uuid.uuid4()
        p.key = _clave_heredada(p.clave_externa, p.pk, usadas)
        if p.price is None:
            p.is_available = False
        p.save(update_fields=["uuid", "key", "is_available"])

        for posicion, g in enumerate(p.opciones or []):
            if not isinstance(g, dict) or not g.get("nombre"):
                continue
            if g.get("tipo") == "uno":
                minimo, maximo = (1 if g.get("obligatorio") else 0), 1
            else:
                minimo = 0
                try:
                    maximo = int(g.get("maximo")) if g.get("maximo") else None
                except (TypeError, ValueError):
                    maximo = None
            grupo = ModifierGroup.objects.using(db).create(
                uuid=uuid.uuid4(),
                key=_unica(f"{p.key}-{_clave(g['nombre'], 'grupo')}", usadas_grupos),
                name=str(g["nombre"])[:60], min_select=minimo, max_select=maximo,
            )
            usadas_opciones = set()
            for j, v in enumerate(g.get("valores") or []):
                if not isinstance(v, dict) or not v.get("nombre"):
                    continue
                ModifierOption.objects.using(db).create(
                    uuid=uuid.uuid4(), group=grupo,
                    key=_unica(_clave(v["nombre"], "opcion"), usadas_opciones),
                    name=str(v["nombre"])[:60], price_delta=Decimal(str(v.get("precio") or 0)), position=j,
                )
            ProductModifierGroup.objects.using(db).create(product=p, group=grupo, position=posicion)


def atras(apps, schema_editor):
    db = schema_editor.connection.alias
    Category = apps.get_model("catalog", "Category")
    Product = apps.get_model("catalog", "Product")
    ModifierOption = apps.get_model("catalog", "ModifierOption")
    ProductModifierGroup = apps.get_model("catalog", "ProductModifierGroup")

    def vieja(clave):
        return "" if (clave or "").startswith("cloudin-") else (clave or "")

    for c in Category.objects.using(db).all():
        c.clave_externa = vieja(c.key)
        c.save(update_fields=["clave_externa"])
    for p in Product.objects.using(db).all():
        grupos = []
        enlaces = ProductModifierGroup.objects.using(db).filter(product=p).select_related("group").order_by(
            "position", "pk")
        for enlace in enlaces:
            g = enlace.group
            valores = [{"nombre": o.name, "precio": int(o.price_delta)}
                       for o in ModifierOption.objects.using(db).filter(group_id=g.pk).order_by("position", "pk")]
            if g.max_select == 1:
                grupos.append({"nombre": g.name, "tipo": "uno", "obligatorio": g.min_select >= 1, "valores": valores})
            else:
                grupo = {"nombre": g.name, "tipo": "varios", "obligatorio": False, "valores": valores}
                if g.max_select:
                    grupo["maximo"] = g.max_select
                grupos.append(grupo)
        p.clave_externa = vieja(p.key)
        p.opciones = grupos
        p.save(update_fields=["clave_externa", "opciones"])


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0006_v1_estructura"),
    ]

    operations = [
        migrations.RunPython(adelante, atras),
    ]
