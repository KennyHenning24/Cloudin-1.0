"""Importación de la semilla cloudin.menu/v1 (contrato, sección 8)."""

import copy
import io
import json
import re
import zipfile
from decimal import Decimal
from pathlib import Path

import pytest
from django.core import mail
from django.core.management import call_command
from PIL import Image

from apps.business.models import OpeningHours, RestaurantSettings
from apps.catalog.models import Category, Product, Tag
from apps.dining.models import Table
from apps.importer.assets import Carpeta
from apps.importer.semilla import SemillaInvalida, validar
from apps.importer.services import importar_semilla
from apps.tenants.models import ApiToken, Tenant, TenantMembership

EJEMPLO = Path(__file__).resolve().parent.parent / "client" / "example"
SEMILLA = json.loads((EJEMPLO / "menu.seed.json").read_text(encoding="utf-8"))


def semilla(**cambios):
    datos = copy.deepcopy(SEMILLA)
    datos.update(cambios)
    return datos


def productos(datos):
    return {p["key"]: p for m in datos["menus"] for c in m["categories"] for p in c["products"]}


# --------------------------------------------------------------- validación


def test_la_semilla_de_ejemplo_es_valida():
    limpia, avisos = validar(SEMILLA)
    assert limpia["business"]["slug"] == "restaurante-ejemplo" and limpia["tables"] == 6
    assert [h["day"] for h in limpia["business"]["hours"]][:2] == ["tue", "wed"]


def test_errores_de_la_semilla_dicen_donde_estan():
    malo = semilla(schema="otro")
    with pytest.raises(SemillaInvalida, match="schema"):
        validar(malo)
    malo = semilla()
    hamb = malo["menus"][0]["categories"][0]["products"]
    hamb[1]["key"] = hamb[0]["key"]           # clave repetida
    hamb[0]["price"] = "24.000"               # precio con formato
    malo["business"]["slug"] = "Mi Restaurante"
    with pytest.raises(SemillaInvalida) as e:
        validar(malo)
    texto = " | ".join(e.value.errores)
    assert "menus[0].categories[0].products[1].key" in texto and "repetida" in texto
    assert "products[0].price" in texto and "business.slug" in texto


# ------------------------------------------------------------ importación


@pytest.mark.django_db
def test_importa_el_ejemplo_creando_el_restaurante(client, bases_creadas_en_la_prueba, en_restaurante, settings):
    settings.CLOUDIN_PUBLIC_URL = "https://cloudin.example"
    bases_creadas_en_la_prueba.append("restaurante-ejemplo")
    r = importar_semilla(semilla(), Carpeta(EJEMPLO), crear_restaurante=True)
    assert r.creado and r.contadores["productos"]["creados"] == 4
    t = Tenant.objects.get(slug="restaurante-ejemplo")
    assert t.pedidos_qr and t.site_url == "http://localhost:4431"
    assert t.menu_page == "http://localhost:4431/index.html"

    # El dueño queda creado con su rol y recibe la invitación.
    dueno = TenantMembership.objects.get(tenant=t, role=TenantMembership.ROLE_OWNER).user
    assert dueno.email == "dueno@correo.com" and dueno.username == "restaurante-ejemplo.dueno"
    assert len(mail.outbox) == 1 and "https://cloudin.example/panel/invitacion/" in mail.outbox[0].body

    with en_restaurante(t):
        assert Table.objects.count() == 6
        assert OpeningHours.objects.count() == 7
        ajustes = RestaurantSettings.load()
        assert ajustes.logo.name.endswith(".svg") and ajustes.whatsapp == "+573001234567"
        assert b"<script" not in ajustes.logo.read()
        jugo = Product.objects.get(key="jugo-natural")
        assert jugo.price is None and jugo.is_available is False

    # La API pública devuelve la MISMA estructura que la semilla, sin lo privado.
    api = client.get("/api/public/restaurante-ejemplo/menu/").json()
    for privado in ("owner", "nit", "legal_name"):
        assert privado not in api["business"]
    assert api["business"]["contact"] == {k: v for k, v in SEMILLA["business"]["contact"].items()}
    assert api["business"]["brand"] == SEMILLA["business"]["brand"]
    assert api["business"]["hours"][0] == {"day": "mon", "closed": True}
    assert [m["key"] for m in api["menus"]] == [m["key"] for m in SEMILLA["menus"]]
    esperados, vivos = productos(SEMILLA), productos(api)
    assert list(vivos) == list(esperados)
    for clave, p in esperados.items():
        v = vivos[clave]
        assert (v["name"], v["price"], v["tags"], v["featured"]) == (p["name"], p["price"], p["tags"], p["featured"])
        assert [x["key"] for x in v["variants"]] == [x["key"] for x in p["variants"]]
        assert [(g["key"], g["min"], g["max"], [o["key"] for o in g["options"]]) for g in v["modifier_groups"]] == \
               [(g["key"], g["min"], g["max"], [o["key"] for o in g["options"]]) for g in p["modifier_groups"]]
        assert v["available"] == (p["available"] and p["price"] is not None)
        assert len(v["id"]) == 36


@pytest.fixture
def ejemplo(crear_restaurante):
    """El restaurante del ejemplo ya creado (sin pasar por aprovisionar: más rápido)."""
    t = crear_restaurante("restaurante-ejemplo", nombre="Restaurante Ejemplo")
    importar_semilla(semilla(), Carpeta(EJEMPLO), invitar=False)
    return t


@pytest.mark.django_db
def test_reimportar_no_duplica_y_respeta_al_dueno(ejemplo, en_restaurante):
    r = importar_semilla(semilla(), Carpeta(EJEMPLO), invitar=False)
    assert r.contadores["productos"] == {"creados": 0, "actualizados": 0, "sin_cambios": 4,
                                         "borrados_por_el_dueno": 0}
    assert r.conservados == []

    with en_restaurante(ejemplo):  # el dueño trabaja en su app
        limonada = Product.objects.get(key="limonada-de-coco")
        limonada.price = Decimal("9500")
        limonada.save()
        hamb = Product.objects.get(key="hamburguesa-clasica")
        hamb.is_available = False
        hamb.save()

    nueva = semilla()
    ps = productos(nueva)
    ps["limonada-de-coco"]["price"] = 9000                       # Juan cambia el precio en la semilla…
    ps["hamburguesa-clasica"]["description"] = "Ahora con pan brioche."  # …y una descripción
    r = importar_semilla(nueva, Carpeta(EJEMPLO), invitar=False)
    with en_restaurante(ejemplo):
        assert Product.objects.get(key="limonada-de-coco").price == Decimal("9500")   # manda el dueño
        hamb = Product.objects.get(key="hamburguesa-clasica")
        assert hamb.description == "Ahora con pan brioche."                           # no lo tocó: se actualiza
        assert hamb.is_available is False                                             # su «agotado» se respeta
        assert Product.objects.count() == 4 and Category.objects.count() == 2
    assert any("Limonada de coco · precio" in c for c in r.conservados)


@pytest.mark.django_db
def test_no_revive_lo_que_el_dueno_borro(ejemplo, en_restaurante):
    with en_restaurante(ejemplo):
        Product.objects.filter(key="hamburguesa-vegetariana").update(eliminado=True)
    r = importar_semilla(semilla(), Carpeta(EJEMPLO), invitar=False)
    assert r.contadores["productos"]["borrados_por_el_dueno"] == 1
    with en_restaurante(ejemplo):
        assert Product.objects.get(key="hamburguesa-vegetariana").eliminado is True


@pytest.mark.django_db
def test_revisar_sin_cambiar_nada(ejemplo, en_restaurante):
    nueva = semilla()
    nueva["menus"][0]["categories"][1]["products"].append({
        "key": "agua", "name": "Agua", "price": 3000, "tags": [], "variants": [], "modifier_groups": []})
    r = importar_semilla(nueva, Carpeta(EJEMPLO), aplicar=False)
    assert not r.aplicado and r.contadores["productos"]["creados"] == 1
    with en_restaurante(ejemplo):
        assert not Product.objects.filter(key="agua").exists()


@pytest.mark.django_db
def test_fotos_se_suben_una_vez_y_se_respeta_la_del_dueno(crear_restaurante, en_restaurante, tmp_path):
    t = crear_restaurante("restaurante-ejemplo")
    (tmp_path / "assets" / "menu").mkdir(parents=True)
    Image.new("RGB", (1600, 1200), (180, 60, 30)).save(tmp_path / "assets" / "menu" / "limonada.png")
    datos = semilla()
    productos(datos)["limonada-de-coco"]["image"] = "assets/menu/limonada.png"
    productos(datos)["jugo-natural"]["image"] = "assets/menu/no-existe.webp"
    r = importar_semilla(datos, Carpeta(tmp_path), invitar=False)
    assert r.fotos["subidas"] == 1 and "assets/menu/no-existe.webp" in r.fotos["faltantes"]
    with en_restaurante(t):
        foto = Product.objects.get(key="limonada-de-coco").imagen
        assert foto.name.endswith(".webp")
    assert importar_semilla(datos, Carpeta(tmp_path), invitar=False).fotos["subidas"] == 0
    # El dueño sube otra foto: una foto nueva en la semilla ya no la reemplaza.
    with en_restaurante(t):
        p = Product.objects.get(key="limonada-de-coco")
        p.imagen = "restaurante-ejemplo/menu/del-dueno.webp"
        p.save()
    Image.new("RGB", (900, 900), (20, 120, 60)).save(tmp_path / "assets" / "menu" / "limonada.png")
    importar_semilla(datos, Carpeta(tmp_path), invitar=False)
    with en_restaurante(t):
        assert Product.objects.get(key="limonada-de-coco").imagen.name == "restaurante-ejemplo/menu/del-dueno.webp"


@pytest.mark.django_db
def test_endpoint_de_superadmin(client, crear_restaurante, django_user_model, en_restaurante):
    t = crear_restaurante("restaurante-ejemplo")
    jefe = django_user_model.objects.create_superuser("jefe", "j@example.com", "clave-jefe-123")
    _, token = ApiToken.crear(jefe, "Pruebas")
    zip_fotos = io.BytesIO()
    with zipfile.ZipFile(zip_fotos, "w") as z:
        z.writestr("site/assets/brand/logo.svg", (EJEMPLO / "assets" / "brand" / "logo.svg").read_bytes())
        z.writestr("../../fuera.png", b"no")
    zip_fotos.seek(0)
    zip_fotos.name = "assets.zip"
    semilla_archivo = io.BytesIO(json.dumps(SEMILLA).encode())
    semilla_archivo.name = "menu.seed.json"
    assert client.post("/api/admin/import-menu/", {"seed": semilla_archivo},
                       HTTP_AUTHORIZATION="Bearer cld_malo").status_code == 401
    semilla_archivo.seek(0)
    r = client.post("/api/admin/import-menu/", {"seed": semilla_archivo, "assets": zip_fotos, "invite": "0"},
                    HTTP_AUTHORIZATION=f"Bearer {token}")
    assert r.status_code == 200, r.content
    assert r.json()["counts"]["productos"]["creados"] == 4 and r.json()["photos"]["subidas"] == 1
    with en_restaurante(t):
        assert RestaurantSettings.load().logo.name.endswith(".svg")
        assert Tag.objects.filter(key="vegetariano").exists()


@pytest.mark.django_db
def test_invitacion_crear_clave_y_entrar_con_el_correo(client, bases_creadas_en_la_prueba):
    bases_creadas_en_la_prueba.append("restaurante-ejemplo")
    importar_semilla(semilla(), Carpeta(EJEMPLO), crear_restaurante=True)
    enlace = re.search(r"http\S+/panel/invitacion/\S+/", mail.outbox[0].body).group(0)
    ruta = enlace.split("://", 1)[1].split("/", 1)[1]
    r = client.get("/" + ruta)
    assert r.status_code == 302  # Django esconde el token y lleva a …/set-password/
    formulario = client.get(r["Location"])
    assert formulario.status_code == 200 and "Crea la contraseña" in formulario.content.decode()
    r = client.post(r["Location"], {"new_password1": "Arepa-con-queso-2026", "new_password2": "Arepa-con-queso-2026"})
    assert r.status_code == 302 and r["Location"] == "/panel/"
    membresia = TenantMembership.objects.get(role=TenantMembership.ROLE_OWNER)
    assert membresia.password_visible == "Arepa-con-queso-2026"  # la copia que ve el panel maestro
    client.logout()
    assert client.login(username="dueno@correo.com", password="Arepa-con-queso-2026")


@pytest.mark.django_db
def test_create_restaurant(bases_creadas_en_la_prueba, en_restaurante):
    bases_creadas_en_la_prueba.append("la-esquina")
    call_command("create_restaurant", "--name", "La Esquina", "--owner-email", "ana@example.com",
                 "--owner-name", "Ana Ruiz")
    t = Tenant.objects.get(slug="la-esquina")
    assert t.pedidos_qr and t.app_meseros
    assert TenantMembership.objects.get(tenant=t).role == TenantMembership.ROLE_OWNER
    assert "La Esquina" in mail.outbox[0].subject
    with en_restaurante(t):
        from apps.catalog.models import Menu

        assert Menu.objects.get().key == "carta"


@pytest.mark.django_db
def test_comando_import_menu_en_modo_revision(crear_restaurante, en_restaurante, capsys):
    t = crear_restaurante("restaurante-ejemplo")
    call_command("import_menu", str(EJEMPLO / "menu.seed.json"), "--assets", str(EJEMPLO), "--dry-run")
    salida = capsys.readouterr().out
    assert "REVISIÓN" in salida and "productos: 4 creados" in salida
    with en_restaurante(t):
        assert not Product.objects.exists()
