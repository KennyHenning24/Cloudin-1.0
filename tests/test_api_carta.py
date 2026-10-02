"""API de administración de la carta (panel del dueño): roles, CRUD, masivos, fotos, ajustes, mesas y QR."""

import io
from decimal import Decimal

import pytest
from PIL import Image

from apps.catalog.models import Category, Menu, Product
from apps.dining.models import Table
from apps.tenants.models import TenantMembership

B = "/api/v1/staff/"


def foto_png(ancho=1200, alto=900, color=(200, 80, 40)) -> io.BytesIO:
    archivo = io.BytesIO()
    Image.new("RGB", (ancho, alto), color).save(archivo, "PNG")
    archivo.seek(0)
    archivo.name = "plato.png"
    return archivo


@pytest.fixture
def local(crear_restaurante, crear_usuario, en_restaurante):
    t = crear_restaurante("el-local")
    dueno = crear_usuario(t, "dueno", rol=TenantMembership.ROLE_OWNER, nombre="Ana Ruiz")
    cajero = crear_usuario(t, "caja", rol=TenantMembership.ROLE_STAFF)
    with en_restaurante(t):
        menu = Menu.objects.create(name="Carta")
        cat = Category.objects.create(menu=menu, name="Platos")
        bandeja = Product.objects.create(category=cat, name="Bandeja paisa", price=Decimal("25000"))
        sopa = Product.objects.create(category=cat, name="Sopa del día", price=Decimal("12500"))
    return {"t": t, "dueno": dueno, "cajero": cajero, "menu": menu, "cat": cat, "bandeja": bandeja, "sopa": sopa}


@pytest.mark.django_db
def test_el_dueno_crea_y_edita_sin_turno(client, local, en_restaurante):
    client.force_login(local["dueno"])  # sin abrir turno: la carta no lo exige
    r = client.post(B + "catalog/products/", {"category": str(local["cat"].uuid), "name": "Limonada de coco",
                                              "price": 8500, "tags": ["nuevo"]}, content_type="application/json")
    assert r.status_code == 201, r.content
    nuevo = r.json()
    assert nuevo["key"] == "limonada-de-coco" and nuevo["price"] == "8500" and nuevo["tags"] == ["nuevo"]
    assert nuevo["is_available"] is True
    # Precio en línea (3 toques): solo el precio.
    r = client.patch(B + f"catalog/products/{nuevo['id']}/", {"price": 9000}, content_type="application/json")
    assert r.status_code == 200 and r.json()["price"] == "9000"
    # Sin precio queda no disponible, y no se puede activar.
    r = client.post(B + "catalog/products/", {"category": str(local["cat"].uuid), "name": "Jugo natural"},
                    content_type="application/json")
    assert r.status_code == 201 and r.json()["is_available"] is False
    r = client.patch(B + f"catalog/products/{r.json()['id']}/availability/", {"available": True},
                     content_type="application/json")
    assert r.status_code == 400 and "precio" in r.json()["detail"]


@pytest.mark.django_db
def test_etiqueta_nueva_desde_el_editor(client, local):
    client.force_login(local["dueno"])
    r = client.post(B + "catalog/tags/", {"name": "  Ahumado   al carbón "}, content_type="application/json")
    assert r.status_code == 201, r.content
    assert r.json()["name"] == "Ahumado al carbón" and r.json()["key"] == "ahumado-al-carbon"
    # La misma con otras mayúsculas no se duplica; vacía, tampoco.
    r = client.post(B + "catalog/tags/", {"name": "ahumado AL carbón"}, content_type="application/json")
    assert r.status_code == 400 and "Ya existe la etiqueta" in str(r.json())
    assert client.post(B + "catalog/tags/", {"name": "   "}, content_type="application/json").status_code == 400
    # Queda en la lista para todos los platos y un plato la puede llevar.
    assert "ahumado-al-carbon" in [t["key"] for t in client.get(B + "catalog/tags/").json()]
    r = client.patch(B + f"catalog/products/{local['bandeja'].uuid}/", {"tags": ["ahumado-al-carbon"]},
                     content_type="application/json")
    assert r.status_code == 200 and r.json()["tags"] == ["ahumado-al-carbon"]
    publico = client.get(f"/api/public/{local['t'].slug}/menu/").json()
    assert {"key": "ahumado-al-carbon", "name": "Ahumado al carbón"} in publico["tags"]
    # El cajero no crea etiquetas.
    client.force_login(local["cajero"])
    assert client.post(B + "catalog/tags/", {"name": "Otra"}, content_type="application/json").status_code == 403


@pytest.mark.django_db
def test_el_cajero_agota_pero_no_edita(client, local):
    client.force_login(local["cajero"])
    bandeja = local["bandeja"]
    assert client.get(B + "catalog/products/").status_code == 200
    r = client.patch(B + f"catalog/products/{bandeja.uuid}/availability/", {"available": False},
                     content_type="application/json")
    assert r.status_code == 200 and r.json()["available"] is False
    r = client.post(B + "catalog/bulk/", {"action": "available", "ids": [str(bandeja.uuid)]},
                    content_type="application/json")
    assert r.status_code == 200 and r.json()["changed"] == 1
    assert client.patch(B + f"catalog/products/{bandeja.uuid}/", {"price": 1},
                        content_type="application/json").status_code == 403
    assert client.post(B + "catalog/bulk/", {"action": "price_percent", "ids": [str(bandeja.uuid)], "value": 5},
                       content_type="application/json").status_code == 403


@pytest.mark.django_db
def test_subir_precios_en_porcentaje_y_deshacer(client, local, en_restaurante):
    client.force_login(local["dueno"])
    ids = [str(local["bandeja"].uuid), str(local["sopa"].uuid)]
    r = client.post(B + "catalog/bulk/", {"action": "price_percent", "ids": ids, "value": 5},
                    content_type="application/json")
    assert r.status_code == 200 and r.json()["changed"] == 2
    with en_restaurante(local["t"]):
        assert sorted(int(p.price) for p in Product.objects.all()) == [13100, 26300]  # redondeado a $100
        ultimo = Product.history.filter(id=local["bandeja"].pk).latest("history_date")
        assert ultimo.history_user_name == "Ana Ruiz"
    r = client.post(B + "catalog/bulk/", {"action": "set_prices", "ids": ids, "value": r.json()["undo"]},
                    content_type="application/json")
    with en_restaurante(local["t"]):
        assert sorted(int(p.price) for p in Product.objects.all()) == [12500, 25000]


@pytest.mark.django_db
def test_borrar_con_deshacer_y_categoria_con_confirmacion(client, local, en_restaurante):
    client.force_login(local["dueno"])
    bandeja = local["bandeja"]
    assert client.delete(B + f"catalog/products/{bandeja.uuid}/").status_code == 204
    assert str(bandeja.uuid) not in client.get(B + "catalog/products/").content.decode()
    assert client.post(B + f"catalog/products/{bandeja.uuid}/restore/").status_code == 200
    cat = local["cat"]
    r = client.delete(B + f"catalog/categories/{cat.uuid}/")
    assert r.status_code == 409 and r.json()["code"] == "confirm"
    assert client.delete(B + f"catalog/categories/{cat.uuid}/?confirm=1").status_code == 204
    assert client.post(B + f"catalog/categories/{cat.uuid}/restore/").status_code == 200


@pytest.mark.django_db
def test_reordenar_cambia_el_orden_y_el_etag(client, local):
    client.force_login(local["dueno"])
    antes = client.get(f"/api/public/{local['t'].slug}/menu/")["ETag"]
    r = client.post(B + "catalog/reorder/", {"kind": "products", "ids": [str(local["sopa"].uuid),
                                                                          str(local["bandeja"].uuid)]},
                    content_type="application/json")
    assert r.status_code == 200
    publico = client.get(f"/api/public/{local['t'].slug}/menu/")
    assert publico["ETag"] != antes
    assert [p["key"] for p in publico.json()["menus"][0]["categories"][0]["products"]] == [
        "sopa-del-dia", "bandeja-paisa"]


@pytest.mark.django_db
def test_tamanos_y_adiciones(client, local, en_restaurante):
    client.force_login(local["dueno"])
    uid = str(local["bandeja"].uuid)
    r = client.put(B + f"catalog/products/{uid}/variants/", [{"name": "Media", "price": 18000},
                                                            {"name": "Completa", "price": 25000}],
                   content_type="application/json")
    assert r.status_code == 200, r.content
    variantes = r.json()["variants"]
    assert [v["key"] for v in variantes] == ["media", "completa"]
    # Renombrar un tamaño conserva su clave; el que no viene se borra.
    r = client.put(B + f"catalog/products/{uid}/variants/", [{"id": variantes[0]["id"], "name": "Media porción",
                                                             "price": 19000}], content_type="application/json")
    assert [(v["key"], v["name"]) for v in r.json()["variants"]] == [("media", "Media porción")]
    r = client.post(B + "catalog/modifier-groups/", {"name": "Elige tu salsa", "min": 1, "max": 1, "options": [
        {"name": "Hogao", "price": 0}, {"name": "Queso extra", "price": 3000}]}, content_type="application/json")
    assert r.status_code == 201, r.content
    grupo = r.json()
    assert [o["key"] for o in grupo["options"]] == ["hogao", "queso-extra"]
    r = client.put(B + f"catalog/products/{uid}/modifier-groups/", [grupo["id"]], content_type="application/json")
    assert r.json()["modifier_groups"][0]["name"] == "Elige tu salsa"
    with en_restaurante(local["t"]):
        opciones = Product.objects.get(pk=local["bandeja"].pk).opciones  # la forma vieja (pedidos) lo ve
        assert [g["nombre"] for g in opciones] == ["Presentación", "Elige tu salsa"]
    r = client.post(B + "catalog/modifier-groups/", {"name": "Mal", "min": 3, "max": 1, "options": [{"name": "x"}]},
                    content_type="application/json")
    assert r.status_code == 400


@pytest.mark.django_db
def test_foto_del_producto_en_webp(client, local, en_restaurante):
    client.force_login(local["dueno"])
    r = client.post(B + f"catalog/products/{local['bandeja'].uuid}/image/", {"file": foto_png()})
    assert r.status_code == 200, r.content
    assert r.json()["image"].endswith(".webp")
    with en_restaurante(local["t"]):
        imagen = Product.objects.get(pk=local["bandeja"].pk).imagen
        with Image.open(imagen.path) as guardada:
            assert guardada.format == "WEBP" and max(guardada.size) == 800
    falso = io.BytesIO(b"esto no es una foto")
    falso.name = "virus.png"
    r = client.post(B + f"catalog/products/{local['bandeja'].uuid}/image/", {"file": falso})
    assert r.status_code == 400 and "foto" in r.json()["detail"]


@pytest.mark.django_db
def test_ajustes_del_negocio(client, local):
    client.force_login(local["dueno"])
    r = client.patch(B + "settings/", {"whatsapp": "300 123 4567", "color_primary": "#0B6E4F",
                                       "payment_methods": ["efectivo", "nequi"],
                                       "services": {"dine_in": True, "delivery": False},
                                       "hours": [{"day": "tue", "open": "12:00", "close": "21:00"},
                                                 {"day": "sat", "open": "18:00", "close": "02:00"}]},
                     content_type="application/json")
    assert r.status_code == 200, r.content
    datos = r.json()
    assert datos["whatsapp"] == "+573001234567"
    # El diseño (colores, logo, portada) es de la página del menú: el panel no lo cambia.
    assert not {"color_primary", "logo", "cover"} & set(datos)
    # Solo Recoger y Domicilio; el que no viene queda como estaba (encendido por defecto).
    assert datos["services"] == {"takeaway": True, "delivery": False}
    assert datos["hours"][1] == {"day": "sat", "open": "18:00", "close": "02:00"}
    assert client.patch(B + "settings/", {"whatsapp": "123"}, content_type="application/json").status_code == 400
    assert client.patch(B + "settings/", {"payment_methods": ["bitcoin"]},
                        content_type="application/json").status_code == 400
    for ruta in ("settings/logo/", "settings/cover/"):
        assert client.post(B + ruta, {"file": foto_png(600, 600)}).status_code == 404, ruta
    publico = client.get(f"/api/public/{local['t'].slug}/menu/").json()["business"]
    assert publico["contact"]["whatsapp"] == "+573001234567" and publico["logo"] is None
    assert publico["brand"] == {"primary": None, "secondary": None, "background": None, "text": None}
    assert publico["services"] == {"dine_in": True, "takeaway": True, "delivery": False}
    assert publico["payment_methods_text"] == "Efectivo y Nequi"
    r = client.patch(B + "settings/", {"services": {"takeaway": False}, "welcome_message": "¡Bienvenido!"},
                     content_type="application/json")
    assert r.json()["services"] == {"takeaway": False, "delivery": False}
    publico = client.get(f"/api/public/{local['t'].slug}/menu/").json()["business"]
    assert publico["services"] == {"dine_in": True, "takeaway": False, "delivery": False}
    assert publico["welcome_message"] == "¡Bienvenido!"


@pytest.mark.django_db
def test_mesas_y_codigos_qr(client, local, en_restaurante):
    client.force_login(local["dueno"])
    r = client.post(B + "mesas/", {"count": 4}, content_type="application/json")
    assert r.status_code == 201 and r.json()["created"] == 4
    assert client.post(B + "mesas/", {"count": 4}, content_type="application/json").json()["created"] == 0
    mesas = client.get(B + "mesas/").json()
    with en_restaurante(local["t"]):
        token = Table.objects.get(number=1).token
    # Cloudin no tiene un menú propio: sin la página del menú digital no hay QR.
    assert mesas[0]["link"] == ""
    assert client.get(B + f"qr/mesa/{mesas[0]['id']}.png").status_code == 404
    # Con la página del menú digital (p. ej. en Cloudflare Pages), el QR lleva allá con el token.
    local["t"].menu_page = "https://el-local.pages.dev/menu.html"
    local["t"].save()
    assert client.get(B + "mesas/").json()[0]["link"] == f"https://el-local.pages.dev/menu.html?mesa={token}"
    png = client.get(B + f"qr/mesa/{mesas[0]['id']}.png")
    assert png["Content-Type"] == "image/png" and png.content[:4] == b"\x89PNG"
    assert client.get(B + "qr/menu.svg")["Content-Type"] == "image/svg+xml"
    pdf = client.get(B + "qr/mesas.pdf")
    assert pdf["Content-Type"] == "application/pdf" and pdf.content[:4] == b"%PDF"


@pytest.mark.django_db
def test_historial_de_cambios(client, local):
    client.force_login(local["dueno"])
    client.patch(B + f"catalog/products/{local['bandeja'].uuid}/", {"price": 27000}, content_type="application/json")
    r = client.get(B + "catalog/history/", {"product": str(local["bandeja"].uuid)})
    assert r.status_code == 200
    assert r.json()[0]["who"] == "Ana Ruiz" and "$ 25.000 → $ 27.000" in r.json()[0]["text"]


@pytest.mark.django_db
def test_aislamiento_en_la_api_de_la_carta(client, local, crear_restaurante, crear_usuario, en_restaurante):
    otro = crear_restaurante("otro-local")
    with en_restaurante(otro):
        cat = Category.objects.create(name="Ajena")
        ajeno = Product.objects.create(category=cat, name="Plato ajeno", price=Decimal("1000"))
    client.force_login(local["dueno"])
    # El UUID de otro restaurante no existe en el mío…
    assert client.patch(B + f"catalog/products/{ajeno.uuid}/", {"price": 1},
                        content_type="application/json").status_code == 404
    # …y por el subdominio del otro no entro.
    assert client.get(B + "catalog/products/", HTTP_HOST="otro-local.localhost").status_code == 403
    with en_restaurante(otro):
        assert Product.objects.get(pk=ajeno.pk).price == Decimal("1000")
