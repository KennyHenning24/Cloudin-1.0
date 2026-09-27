"""La migración de la carta vieja (JSON de opciones, clave_externa) a la carta v1.

Arma una base de restaurante en el estado anterior (catalog 0005), le mete una
carta vieja y la migra hasta el final. Además de esta prueba, antes de migrar
las bases reales se corre la misma migración sobre copias de ellas y se compara
la carta que publican (ver docs/BASE_DE_DATOS.md).
"""

import json
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.conf import settings
from django.db import connections
from django.db.migrations.executor import MigrationExecutor

from apps.catalog.formato import exportar
from apps.catalog.models import Category, ModifierGroup, Product
from apps.tenants.context import tenant_context

ANTES = [("catalog", "0005_category_secciones")]


@pytest.mark.django_db
def test_migra_la_carta_vieja_sin_cambiar_lo_que_publica(tmp_path):
    alias = "tenant_migracion"
    config = {**settings.DATABASES["default"], "NAME": str(tmp_path / "vieja.sqlite3"), "TEST": {}}
    settings.DATABASES[alias] = config
    connections.databases[alias] = config
    try:
        conexion = connections[alias]
        ejecutor = MigrationExecutor(conexion)
        ejecutor.migrate(ANTES)
        viejas = ejecutor.loader.project_state(ANTES[0]).apps
        Cat = viejas.get_model("catalog", "Category")
        Prod = viejas.get_model("catalog", "Product")
        sandwiches = Cat.objects.using(alias).create(name="Sándwiches", position=1, clave_externa="sandwiches")
        bebidas = Cat.objects.using(alias).create(name="Bebidas", position=2)  # sin clave
        opciones = [
            {"nombre": "Elige la carne", "tipo": "uno", "obligatorio": True,
             "valores": [{"nombre": "Brisket", "precio": 0}, {"nombre": "Pastrami", "precio": 2000}]},
            {"nombre": "Hazlo combo", "tipo": "varios", "obligatorio": False,
             "valores": [{"nombre": "Papas y gaseosa", "precio": 10000}]},
        ]
        dos = Prod.objects.using(alias).create(category=sandwiches, name="Sandwich 2 Quesos", price=Decimal("35000"),
                                               clave_externa="dos-quesos", opciones=opciones)
        limonada = Prod.objects.using(alias).create(category=bebidas, name="Limonada", price=Decimal("6000"))

        ejecutor = MigrationExecutor(conexion)
        ejecutor.migrate(ejecutor.loader.graph.leaf_nodes("catalog"))

        with tenant_context(SimpleNamespace(slug="migracion", db_alias=alias, db_name="vieja")):
            cats = {c.name: c for c in Category.objects.all()}
            assert cats["Sándwiches"].key == "sandwiches" and cats["Bebidas"].key == f"cloudin-{bebidas.pk}"
            assert {c.menu.key for c in cats.values()} == {"carta"}
            nuevo_dos = Product.objects.get(pk=dos.pk)
            assert nuevo_dos.key == "dos-quesos"
            assert Product.objects.get(pk=limonada.pk).key == f"cloudin-{limonada.pk}"
            assert nuevo_dos.opciones == opciones
            assert ModifierGroup.objects.get(name="Elige la carne").min_select == 1
            carta = exportar("x", solo_disponibles=False)
            ids = [(c["id"], [p["id"] for p in c["productos"]]) for c in carta["categorias"]]
            assert ids == [("sandwiches", ["dos-quesos"]), (f"cloudin-{bebidas.pk}", [f"cloudin-{limonada.pk}"])]
            assert json.dumps(carta["categorias"][0]["productos"][0]["opciones"]) == json.dumps(opciones)
    finally:
        connections[alias].close()
        connections.databases.pop(alias, None)
        settings.DATABASES.pop(alias, None)
