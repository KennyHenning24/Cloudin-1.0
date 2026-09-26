"""API pública `cloudin.menu/v1` y menú de respaldo."""

from datetime import datetime, time
from decimal import Decimal

import pytest
from django.core.management import call_command

from apps.business.models import OpeningHours, RestaurantSettings
from apps.catalog.models import Category, Menu, ModifierGroup, ModifierOption, Product, ProductModifierGroup, Tag
from apps.dining.models import Table
from apps.public_menu.horario import BOGOTA, abierto_ahora, horario_de_hoy
from apps.tenants.models import Tenant

URL = "/api/public/{}/menu/"


@pytest.fixture
def restaurante(crear_restaurante, en_restaurante):
    t = crear_restaurante("la-esquina", nombre="La Esquina", nit="900123456", legal_name="La Esquina SAS")
    with en_restaurante(t):
        ajustes = RestaurantSettings.load()
        ajustes.whatsapp = "+573001234567"
        ajustes.city = "Cali"
        ajustes.color_primary = "#B3261E"
        ajustes.services = {"dine_in": True, "takeaway": True}
        ajustes.payment_methods = ["efectivo", "nequi"]
        ajustes.save()
        OpeningHours.objects.create(day=1, opens=time(12), closes=time(21))
        OpeningHours.objects.create(day=5, opens=time(12), closes=time(15))
        OpeningHours.objects.create(day=5, opens=time(18), closes=time(22))
        menu = Menu.objects.create(name="Carta")
        hamb = Category.objects.create(menu=menu, name="Hamburguesas", position=1)
        bebidas = Category.objects.create(menu=menu, name="Bebidas", position=2)
        Category.objects.create(menu=menu, name="Postres", position=3)  # vacía: no sale
        clasica = Product.objects.create(category=hamb, name="Hamburguesa clásica", price=Decimal("24000"),
                                         is_featured=True, tax_type="INC8", description="Carne, queso y papas.")
        clasica.variants.create(name="Doble carne", price=Decimal("32000"))
        clasica.tags.add(Tag.objects.get(key="recomendado"))
        salsa = ModifierGroup.objects.create(name="Elige tu salsa", min_select=1, max_select=1)
        ModifierOption.objects.create(group=salsa, name="Verde", price_delta=0)
        ModifierOption.objects.create(group=salsa, name="Roja picante", price_delta=Decimal("1500"))
        ProductModifierGroup.objects.create(product=clasica, group=salsa)
        Product.objects.create(category=hamb, name="Vegetariana", price=Decimal("26000"), is_available=False)
        Product.objects.create(category=hamb, name="Sin precio aún", price=None)
        Product.objects.create(category=hamb, name="Borrada", price=Decimal("1000"), eliminado=True)
        Product.objects.create(category=bebidas, name="Limonada de coco", price=Decimal("8500"))
        Table.objects.create(number=5)
    return t


@pytest.mark.django_db
def test_la_respuesta_sigue_el_contrato(client, restaurante):
    r = client.get(URL.format(restaurante.slug))
    assert r.status_code == 200
    datos = r.json()
    assert datos["schema"] == "cloudin.menu/v1"
    negocio = datos["business"]
    assert negocio["slug"] == "la-esquina" and negocio["name"] == "La Esquina"
    # Nada privado: ni dueño, ni NIT, ni razón social.
    texto = r.content.decode()
    for privado in ("owner", "legal_name", "nit", "900123456", "La Esquina SAS"):
        assert privado not in texto
    assert negocio["contact"]["whatsapp"] == "+573001234567"
    assert negocio["brand"]["primary"] == "#B3261E"
    assert negocio["services"] == {"dine_in": True, "takeaway": True, "delivery": False}
    assert {"day": "mon", "closed": True} in negocio["hours"]
    assert [h for h in negocio["hours"] if h["day"] == "sat"] == [
        {"day": "sat", "open": "12:00", "close": "15:00"}, {"day": "sat", "open": "18:00", "close": "22:00"}]

    menu = datos["menus"][0]
    assert set(menu) >= {"id", "key", "name", "categories"}
    assert [c["key"] for c in menu["categories"]] == ["hamburguesas", "bebidas"]  # sin la vacía
    hamb = menu["categories"][0]
    # Mismo orden (posición y nombre); la borrada no sale.
    assert [p["key"] for p in hamb["products"]] == ["hamburguesa-clasica", "sin-precio-aun", "vegetariana"]
    sin_precio = hamb["products"][1]  # sale, pero no disponible y sin precio
    assert sin_precio["price"] is None and sin_precio["available"] is False
    clasica = hamb["products"][0]
    assert clasica["price"] == 24000 and isinstance(clasica["price"], int)
    assert clasica["featured"] is True and clasica["tax"] == "INC8" and clasica["tags"] == ["recomendado"]
    assert clasica["variants"][0]["name"] == "Doble carne" and clasica["variants"][0]["price"] == 32000
    grupo = clasica["modifier_groups"][0]
    assert (grupo["min"], grupo["max"]) == (1, 1)
    assert [(o["key"], o["price"]) for o in grupo["options"]] == [("verde", 0), ("roja-picante", 1500)]
    for entidad in (menu, hamb, clasica, clasica["variants"][0], grupo, grupo["options"][0]):
        assert len(entidad["id"]) == 36 and entidad["key"]
    assert hamb["products"][2]["available"] is False
    assert {"key": "recomendado", "name": "Recomendado"} in datos["tags"]


@pytest.mark.django_db
def test_etag_304_cors_y_cache(client, restaurante, en_restaurante):
    url = URL.format(restaurante.slug)
    r = client.get(url, HTTP_ORIGIN="https://la-esquina.pages.dev")
    etag = r["ETag"]
    assert etag.startswith('W/"la-esquina-')
    assert r["Access-Control-Allow-Origin"] == "*"
    assert "ETag" in r["Access-Control-Expose-Headers"]
    assert "max-age" in r["Cache-Control"]
    r2 = client.get(url, HTTP_IF_NONE_MATCH=etag)
    assert r2.status_code == 304 and r2["ETag"] == etag
    # Un cambio del dueño (precio) cambia el ETag y se ve de inmediato.
    with en_restaurante(restaurante):
        p = Product.objects.get(key="hamburguesa-clasica")
        p.price = Decimal("25000")
        p.save()
    r3 = client.get(url, HTTP_IF_NONE_MATCH=etag)
    assert r3.status_code == 200 and r3["ETag"] != etag
    assert r3.json()["menus"][0]["categories"][0]["products"][0]["price"] == 25000


@pytest.mark.django_db
def test_marcar_agotado_sube_la_version(client, restaurante, en_restaurante):
    url = URL.format(restaurante.slug)
    antes = client.get(url)["ETag"]
    with en_restaurante(restaurante):
        Product.objects.get(key="limonada-de-coco").tags.add(Tag.objects.get(key="nuevo"))
    assert client.get(url)["ETag"] != antes


@pytest.mark.django_db
def test_mesa_por_token_o_numero(client, restaurante, en_restaurante):
    with en_restaurante(restaurante):
        token = Table.objects.get(number=5).token
    url = URL.format(restaurante.slug)
    for valor in (token, "5"):
        r = client.get(url, {"table": valor})
        assert r.json()["table"] == {"number": 5}
        assert r["ETag"].endswith('-m5"')
    assert "table" not in client.get(url, {"table": "no-existe"}).json()


@pytest.mark.django_db
def test_sin_n_mas_1(client, restaurante, en_restaurante, django_assert_max_num_queries):
    from django.core.cache import cache

    with en_restaurante(restaurante):
        cat = Category.objects.get(key="bebidas")
        for i in range(30):
            p = Product.objects.create(category=cat, name=f"Bebida {i}", price=Decimal("5000"))
            p.variants.create(name="Grande", price=Decimal("7000"))
    cache.clear()
    # Pocas consultas fijas, sin importar cuántos productos haya (control + restaurante).
    with django_assert_max_num_queries(20):
        assert client.get(URL.format(restaurante.slug)).status_code == 200


@pytest.mark.django_db
def test_restaurante_inexistente_o_inactivo(client, restaurante):
    assert client.get(URL.format("no-existe")).status_code == 404
    Tenant.objects.filter(pk=restaurante.pk).update(is_active=False)
    r = client.get(URL.format(restaurante.slug))
    assert r.status_code == 404 and r["Access-Control-Allow-Origin"] == "*"


@pytest.mark.django_db
def test_tope_por_ip(client, restaurante, monkeypatch):
    from apps.public_menu import views

    monkeypatch.setattr(views, "TOPE_POR_IP", 3)
    url = URL.format(restaurante.slug)
    codigos = [client.get(url).status_code for _ in range(4)]
    assert codigos == [200, 200, 200, 429]


@pytest.mark.django_db
def test_por_subdominio_tambien(client, restaurante):
    r = client.get("/api/public/menu/", HTTP_HOST="la-esquina.localhost")
    assert r.status_code == 200 and r.json()["business"]["slug"] == "la-esquina"


@pytest.mark.django_db
def test_la_sesion_de_otro_restaurante_no_se_mezcla(client, restaurante, crear_restaurante, crear_usuario):
    otro = crear_restaurante("otro-lugar")
    client.force_login(crear_usuario(otro))
    assert client.get(URL.format(restaurante.slug)).json()["business"]["slug"] == "la-esquina"


def test_horario_de_hoy_y_abierto():
    horas = [{"day": "sat", "open": "12:00", "close": "15:00"}, {"day": "sat", "open": "18:00", "close": "02:00"},
             {"day": "sun", "closed": True}]
    sabado_13 = datetime(2026, 9, 26, 13, 0, tzinfo=BOGOTA)
    assert horario_de_hoy(horas, sabado_13) == "Hoy: 12:00 – 15:00 y 18:00 – 02:00"
    assert abierto_ahora(horas, sabado_13)
    assert not abierto_ahora(horas, datetime(2026, 9, 26, 16, 0, tzinfo=BOGOTA))
    assert abierto_ahora(horas, datetime(2026, 9, 27, 1, 30, tzinfo=BOGOTA))  # domingo 1:30, sigue lo del sábado
    assert horario_de_hoy(horas, datetime(2026, 9, 27, 12, 0, tzinfo=BOGOTA)) == "Hoy: cerrado"
    assert horario_de_hoy([], sabado_13) == ""


@pytest.mark.django_db
def test_cloudin_no_sirve_un_menu_propio(client, restaurante):
    """El menú digital lo construye cada restaurante aparte (su sitio, p. ej. en
    Cloudflare Pages) y lee la API; Cloudin no tiene una página de menú."""
    assert client.get(f"/m/{restaurante.slug}/", {"mesa": "5"}).status_code == 404


@pytest.mark.django_db
def test_raiz_por_subdominio_lleva_a_la_pagina_del_menu(client, restaurante):
    restaurante.menu_page = "https://la-esquina.pages.dev/"
    restaurante.save()
    r = client.get("/", HTTP_HOST="la-esquina.localhost")
    assert r.status_code == 302 and r.url == "https://la-esquina.pages.dev/"
    assert client.get("/").status_code == 302  # sin restaurante: al panel


def test_runtime_minificado_al_dia_y_bajo_8kb():
    call_command("build_runtime", "--check")
