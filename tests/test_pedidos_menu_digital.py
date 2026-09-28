"""El menú digital de cada restaurante (su sitio, p. ej. en Cloudflare Pages) lee la
carta pública y manda pedidos a la mesa. Sin turno de caja: los pedidos entran
siempre, la mesa se ocupa sola con el primero y queda libre al cerrar la cuenta.
Ver GUIA-MENU-DIGITAL.md."""

from decimal import Decimal

import pytest

from apps.catalog.models import Category, ModifierGroup, ModifierOption, Product, ProductModifierGroup
from apps.dining.models import Table
from apps.tenants.models import TenantMembership

PAGINA = "https://la-casa.pages.dev/menu.html"
ORIGEN = "https://la-casa.pages.dev"


@pytest.fixture
def casa(crear_restaurante, crear_usuario, en_restaurante):
    tenant = crear_restaurante("la-casa", menu_page=PAGINA)
    admin = crear_usuario(tenant, rol=TenantMembership.ROLE_ADMIN)
    with en_restaurante(tenant):
        cat = Category.objects.create(name="Hamburguesas")
        hamb = Product.objects.create(category=cat, name="Hamburguesa", price=Decimal("24000"))
        doble = hamb.variants.create(name="Doble carne", price=Decimal("32000"))
        # Un grupo sin opciones antes de los demás: no cuenta en las posiciones.
        vacio = ModifierGroup.objects.create(name="Sin opciones todavía")
        ProductModifierGroup.objects.create(product=hamb, group=vacio, position=0)
        salsa = ModifierGroup.objects.create(name="Salsa", min_select=1, max_select=1)
        verde = ModifierOption.objects.create(group=salsa, name="Verde", price_delta=0, position=0)
        roja = ModifierOption.objects.create(group=salsa, name="Roja", price_delta=Decimal("1500"), position=1)
        ProductModifierGroup.objects.create(product=hamb, group=salsa, position=1)
        adiciones = ModifierGroup.objects.create(name="Adiciones", min_select=0, max_select=3)
        ModifierOption.objects.create(group=adiciones, name="Queso", price_delta=Decimal("3000"), position=0)
        tocineta = ModifierOption.objects.create(group=adiciones, name="Tocineta", price_delta=Decimal("4000"),
                                                 position=1)
        ProductModifierGroup.objects.create(product=hamb, group=adiciones, position=2)
        limonada = Product.objects.create(category=cat, name="Limonada", price=Decimal("8500"))
        mesa = Table.objects.create(number=1)
        Table.objects.create(number=2)
    return {"t": tenant, "admin": admin, "hamb": hamb, "doble": doble, "verde": verde, "roja": roja,
            "tocineta": tocineta, "limonada": limonada, "mesa": mesa}


def _llave(casa):
    return {"HTTP_X_API_KEY": casa["t"].api_key}


def _linea(casa, cantidad=2):
    """Hamburguesa doble con salsa roja y tocineta: 32.000 + 1.500 + 4.000 = 37.500."""
    return {"product": str(casa["hamb"].uuid), "variant": str(casa["doble"].uuid),
            "options": [str(casa["roja"].uuid), str(casa["tocineta"].uuid)], "quantity": cantidad}


@pytest.mark.django_db
def test_la_carta_publica_trae_los_id_y_reconoce_la_mesa(client, casa):
    r = client.get(f"/api/public/la-casa/menu/?table={casa['mesa'].token}")
    assert r.status_code == 200 and r["Access-Control-Allow-Origin"] == "*"
    datos = r.json()
    assert datos["table"] == {"number": 1}
    producto = next(p for p in datos["menus"][0]["categories"][0]["products"] if p["name"] == "Hamburguesa")
    assert producto["id"] == str(casa["hamb"].uuid) and producto["price"] == 24000
    assert producto["variants"][0] == {"id": str(casa["doble"].uuid), "key": casa["doble"].key,
                                       "name": "Doble carne", "price": 32000}
    grupos = {g["name"]: g for g in producto["modifier_groups"]}
    assert [o["id"] for o in grupos["Salsa"]["options"]] == [str(casa["verde"].uuid), str(casa["roja"].uuid)]


@pytest.mark.django_db
def test_carrito_compartido_y_pedido_con_los_id_de_la_carta(client, casa):
    token = casa["mesa"].token
    base = f"/api/v1/mesa/{token}/"
    # El carrito vive en el servidor: el precio lo pone Cloudin, no el teléfono.
    r = client.put(base + "borrador/", {"items": [_linea(casa), {"product": str(casa["limonada"].uuid),
                                                                 "unit_price": 1}]},
                   content_type="application/json", **_llave(casa))
    assert r.status_code == 200, r.content
    lineas = r.json()["borrador"]["items"]
    assert [ln["unit_price"] for ln in lineas] == [37500, 8500]
    assert lineas[0]["name"] == "Hamburguesa · Doble carne, Roja, Tocineta (+$4.000)"
    assert lineas[0]["product"] == str(casa["hamb"].uuid) and lineas[0]["options"] == _linea(casa)["options"]
    assert r.json()["ocupada"] is False  # armar el carrito no ocupa la mesa

    r = client.post(base + "enviar/", {"by": "Ana"}, content_type="application/json", **_llave(casa))
    assert r.status_code == 201, r.content
    estado = r.json()
    assert estado["ocupada"] is True and estado["cuenta"]["total"] == Decimal("83500")
    assert estado["borrador"]["items"] == []

    # El panel lo ve: mesa ocupada, el pedido en Mensajes y en Cocina.
    client.force_login(casa["admin"])
    mesas = {m["number"]: m for m in client.get("/api/v1/staff/tables/").json()}
    assert mesas[1]["is_occupied"] and not mesas[2]["is_occupied"]
    assert len(client.get("/api/v1/staff/messages/").json()["mensajes"]) == 1
    assert len(client.get("/api/v1/staff/kitchen/").json()) == 1
    assert client.get("/api/v1/staff/avisos/").json() == {"mensajes": 1}

    # Cerrar la cuenta libera la mesa y saca sus pedidos de las pantallas.
    r = client.post(f"/api/v1/staff/sessions/{mesas[1]['session_id']}/close/")
    assert r.status_code == 200 and r.json()["status"] == "closed"
    assert client.get("/api/v1/staff/messages/").json()["mensajes"] == []
    assert client.get("/api/v1/staff/kitchen/").json() == []
    assert client.get(base + "estado/", **_llave(casa)).json()["ocupada"] is False


@pytest.mark.django_db
def test_pedido_directo_a_la_mesa_con_los_id_de_la_carta(client, casa):
    r = client.post(f"/api/v1/tables/{casa['mesa'].token}/orders/",
                    {"customer_name": "Ana", "items": [_linea(casa, 1), {"product": str(casa["limonada"].uuid)}]},
                    content_type="application/json", **_llave(casa))
    assert r.status_code == 201, r.content
    pedido = r.json()["pedido"]
    assert pedido["total"] == Decimal("46000") and pedido["table_number"] == 1
    assert pedido["items"][0]["opciones"] == [
        {"grupo": "Presentación", "nombre": "Doble carne", "precio": 8000},
        {"grupo": "Salsa", "nombre": "Roja", "precio": 1500},
        {"grupo": "Adiciones", "nombre": "Tocineta", "precio": 4000},
    ]


@pytest.mark.django_db
def test_opcion_que_no_existe_o_falta_la_obligatoria(client, casa):
    url = f"/api/v1/tables/{casa['mesa'].token}/orders/"
    mala = {**_linea(casa), "options": ["00000000-0000-0000-0000-000000000000"]}
    r = client.post(url, {"items": [mala]}, content_type="application/json", **_llave(casa))
    assert r.status_code == 400 and "ya no existe" in str(r.json())
    sin_salsa = {"product": str(casa["hamb"].uuid), "quantity": 1}
    r = client.post(url, {"items": [sin_salsa]}, content_type="application/json", **_llave(casa))
    assert r.status_code == 400 and "Falta elegir «Salsa»" in str(r.json())


@pytest.mark.django_db
def test_sin_pedidos_por_el_qr_cuando_el_restaurante_los_apaga(client, casa):
    """El administrador apaga los pedidos por QR en su panel: el menú digital lo sabe por
    `recibe_pedidos` y Cloudin rechaza los envíos, con o sin la app de meseros."""
    token = casa["mesa"].token
    base = f"/api/v1/mesa/{token}/"
    assert client.get(base + "estado/", **_llave(casa)).json()["recibe_pedidos"] is True
    client.put(base + "borrador/", {"items": [_linea(casa)]}, content_type="application/json", **_llave(casa))
    for meseros in (False, True):
        casa["t"].pedidos_qr, casa["t"].app_meseros = False, meseros
        casa["t"].save()
        assert client.get(base + "estado/", **_llave(casa)).json()["recibe_pedidos"] is False
        r = client.post(base + "enviar/", {"by": "Ana"}, content_type="application/json", **_llave(casa))
        assert r.status_code == 403 and r.json()["codigo"] == "sin_pedidos"
        r = client.post(f"/api/v1/tables/{token}/orders/", {"items": [_linea(casa)]},
                        content_type="application/json", **_llave(casa))
        assert r.status_code == 403 and r.json()["codigo"] == "sin_pedidos"
    assert client.get(base + "estado/", **_llave(casa)).json()["ocupada"] is False
    # Al encenderlos otra vez, el mismo carrito se envía.
    casa["t"].pedidos_qr = True
    casa["t"].save()
    r = client.post(base + "enviar/", {"by": "Ana"}, content_type="application/json", **_llave(casa))
    assert r.status_code == 201


@pytest.mark.django_db
def test_sin_la_llave_no_se_puede_pedir(client, casa):
    r = client.post(f"/api/v1/tables/{casa['mesa'].token}/orders/", {"items": [_linea(casa)]},
                    content_type="application/json")
    assert r.status_code == 400  # no se identificó el restaurante


@pytest.mark.django_db
def test_cors_para_la_pagina_del_menu_digital(client, casa):
    """El navegador pregunta antes (preflight) porque el pedido lleva X-API-Key y JSON."""
    url = f"/api/v1/mesa/{casa['mesa'].token}/borrador/"
    preflight = {"HTTP_ACCESS_CONTROL_REQUEST_METHOD": "PUT",
                 "HTTP_ACCESS_CONTROL_REQUEST_HEADERS": "x-api-key, content-type"}
    r = client.options(url, HTTP_ORIGIN=ORIGEN, **preflight)
    assert r.status_code == 200 and r["Access-Control-Allow-Origin"] == ORIGEN
    assert "x-api-key" in r["Access-Control-Allow-Headers"].lower()
    r = client.options(url, HTTP_ORIGIN="https://otro-sitio.example", **preflight)
    assert "Access-Control-Allow-Origin" not in r
    # Otros dominios del mismo restaurante (el propio además de *.pages.dev) se autorizan aparte.
    casa["t"].allowed_origins = ["https://menu.lacasa.co"]
    casa["t"].save()
    r = client.options(url, HTTP_ORIGIN="https://menu.lacasa.co", **preflight)
    assert r["Access-Control-Allow-Origin"] == "https://menu.lacasa.co"


@pytest.mark.django_db
def test_el_mesero_envia_sin_turno_de_caja(client, casa, en_restaurante):
    from apps.waiters.models import Mesero

    casa["t"].app_meseros = True
    casa["t"].save()
    with en_restaurante(casa["t"]):
        mesero = Mesero(nombre="Laura", usuario="laura")
        mesero.set_password("clave-laura-1")
        mesero.save()
    slug = casa["t"].slug
    r = client.post(f"/mesero/{slug}/entrar/", {"usuario": "laura", "clave": "clave-laura-1"})
    assert r.status_code == 302
    r = client.post(f"/mesero/{slug}/api/mesa/2/pedido/",
                    {"items": [{"product_id": casa["limonada"].pk, "quantity": 2}], "llave": "k1"},
                    content_type="application/json")
    assert r.status_code == 201, r.content
    mesas = {m["numero"]: m for m in client.get(f"/mesero/{slug}/api/mesas/").json()["mesas"]}
    assert mesas[2]["ocupada"]


@pytest.mark.django_db
def test_el_comando_de_qr_usa_la_pagina_del_menu(casa):
    """Los QR que genera la consola son los mismos del panel: página del menú + ?mesa=<token>."""
    from io import StringIO

    from django.core.management import call_command

    salida = StringIO()
    call_command("tenant_qr", "--slug", "la-casa", "--no-png", stdout=salida)
    assert f"Mesa 1: {PAGINA}?mesa={casa['mesa'].token}" in salida.getvalue()
