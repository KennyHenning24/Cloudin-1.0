"""Pruebas de humo: cada pantalla abre sin errores del servidor.

No revisan el contenido en detalle; su trabajo es avisar si una actualización
(de Django, de un modelo o de una plantilla) rompe alguna pantalla.
"""

from decimal import Decimal

import pytest
from django.urls import get_resolver, reverse

from apps.catalog.models import Category, Product
from apps.dining.models import Table

# Rutas del panel que solo aceptan POST o que no son pantallas.
SOLO_POST = {
    "logout", "soporte-salir", "entrar-como", "turno-abrir", "turno-cerrar", "control-analizar",
    "empleado-marcar",
}
# Solo existen con DEBUG=True (tienen su propia prueba en test_diseno.py).
SOLO_DEBUG = {"design-system"}
# Pantallas principales: deben responder 200, no una redirección. («Nueva compra»
# redirige a crear el proveedor mientras no haya uno: es lo esperado.)
PRINCIPALES = {
    "inicio", "tables", "kitchen", "mensajes", "configuracion", "mesas-qr", "mi-menu", "carta-producto-nuevo",
    "menu-importar", "ventas", "turnos", "reservas", "reserva-nueva", "clientes", "reservas-config",
    "control", "control-ajustes", "propinas", "empleados", "empleado-nuevo", "meseros", "mesero-nuevo",
    "inventario", "insumos", "insumo-nuevo", "compras", "proveedores",
    "proveedor-nuevo", "recetas", "subreceta-nueva", "conteos", "inventario-reportes",
    "inventario-maestros", "facturacion", "personalizar", "qr", "cuenta", "bienvenida", "manifest", "sw",
    "sin-conexion",
}


def _rutas_sin_parametros(espacio):
    resolver = get_resolver()
    _, sub = resolver.namespace_dict[espacio]
    nombres = []
    for patron in sub.url_patterns:
        nombre = getattr(patron, "name", None)
        if nombre and not patron.pattern.regex.groupindex:
            nombres.append(nombre)
    return sorted(set(nombres))


@pytest.fixture
def restaurante_listo(crear_restaurante, crear_usuario, abrir_turno, en_restaurante):
    tenant = crear_restaurante("humo", modo_servicio="mixto", plan="completo")
    user = crear_usuario(tenant)
    abrir_turno(tenant)
    with en_restaurante(tenant):
        mesa = Table.objects.create(number=1)
        cat = Category.objects.create(name="Platos")
        producto = Product.objects.create(category=cat, name="Bandeja", price=Decimal("25000"))
    return tenant, user, mesa, producto


@pytest.mark.django_db
def test_todas_las_pantallas_del_panel_abren(client, restaurante_listo):
    tenant, user, mesa, producto = restaurante_listo
    client.force_login(user)
    fallas = {}
    for nombre in _rutas_sin_parametros("panel"):
        if nombre in SOLO_POST | SOLO_DEBUG:
            continue
        respuesta = client.get(reverse(f"panel:{nombre}"))
        esperado = (200,) if nombre in PRINCIPALES else (200, 302)
        if respuesta.status_code not in esperado:
            fallas[nombre] = respuesta.status_code
    # Pantallas con parámetros que se pueden armar con datos sencillos.
    for url in (
        reverse("panel:table-detail", args=[mesa.id]),
        reverse("panel:carta-producto", args=[producto.uuid]),
        reverse("panel:carta-producto", args=[producto.uuid]) + "?fragmento=1",
        reverse("panel:receta-producto", args=[producto.id]),
    ):
        respuesta = client.get(url)
        if respuesta.status_code != 200:
            fallas[url] = respuesta.status_code
    assert fallas == {}


@pytest.mark.django_db
def test_rutas_solo_post_no_revientan_con_get(client, restaurante_listo):
    _, user, _, _ = restaurante_listo
    client.force_login(user)
    for nombre in SOLO_POST:
        respuesta = client.get(reverse(f"panel:{nombre}"))
        assert respuesta.status_code < 500, nombre


@pytest.mark.django_db
def test_salir_cierra_la_sesion(client, restaurante_listo):
    _, user, _, _ = restaurante_listo
    client.force_login(user)
    respuesta = client.post(reverse("panel:logout"))
    assert respuesta.status_code == 302
    assert client.get(reverse("panel:inicio")).status_code == 302  # de vuelta al login


@pytest.mark.django_db
def test_login_y_recuperar_abren_sin_sesion(client):
    for nombre in ("login", "recuperar", "recuperar-enviado", "recuperar-listo"):
        assert client.get(reverse(f"panel:{nombre}")).status_code == 200, nombre


@pytest.mark.django_db
def test_panel_maestro_abre_para_el_superusuario(client, django_user_model, restaurante_listo):
    tenant, *_ = restaurante_listo
    jefe = django_user_model.objects.create_superuser("jefe", "jefe@example.com", "clave-jefe-123")
    client.force_login(jefe)
    for url in (reverse("master:home"), reverse("master:restaurante-nuevo"), reverse("master:tokens"),
                reverse("master:restaurante", args=[tenant.slug]), "/admin/", "/api/docs/", "/api/schema/"):
        assert client.get(url).status_code == 200, url


@pytest.mark.django_db
def test_documentacion_de_la_api_solo_para_el_superusuario(client, restaurante_listo):
    _, user, _, _ = restaurante_listo
    assert client.get("/api/docs/").status_code == 404
    client.force_login(user)
    assert client.get("/api/schema/").status_code == 404


@pytest.mark.django_db
def test_salir_del_admin_es_por_post(client, django_user_model):
    """Desde Django 5 cerrar sesión por GET ya no existe; el maestro usa un formulario."""
    jefe = django_user_model.objects.create_superuser("jefe", "jefe@example.com", "clave-jefe-123")
    client.force_login(jefe)
    html = client.get(reverse("master:home")).content.decode()
    assert 'href="/admin/logout/"' not in html
    assert client.post("/admin/logout/").status_code in (200, 302)


@pytest.mark.django_db
def test_api_del_sitio_y_app_de_meseros(client, restaurante_listo):
    tenant, *_ = restaurante_listo
    llave = {"HTTP_X_API_KEY": tenant.api_key}
    for url in ("/api/v1/ping/", "/api/v1/menu/", "/api/v1/menu/?formato=cloudin", "/api/v1/site/info/",
                "/api/v1/site/tables/", "/api/v1/reservas/"):
        assert client.get(url, **llave).status_code == 200, url
    assert client.get(f"/mesero/{tenant.slug}/entrar/").status_code == 200


@pytest.mark.django_db
def test_app_de_meseros_apagada_en_autoservicio(client, crear_restaurante):
    tenant = crear_restaurante("solo-qr")
    assert client.get(f"/mesero/{tenant.slug}/entrar/").status_code == 403
