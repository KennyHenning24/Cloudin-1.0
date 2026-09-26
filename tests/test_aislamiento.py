"""Aislamiento entre restaurantes: nadie ve ni toca los datos de otro.

Cada restaurante tiene su propia base; estas pruebas verifican que ninguna
puerta (panel, API del panel, API del sitio, subdominio) cruce de una a otra.
"""

from decimal import Decimal

import pytest

from apps.catalog.models import Category, Product


@pytest.fixture
def dos_restaurantes(crear_restaurante, crear_usuario, abrir_turno, en_restaurante):
    a = crear_restaurante("casa-a")
    b = crear_restaurante("casa-b")
    for tenant, plato in ((a, "Solo de A"), (b, "Solo de B")):
        abrir_turno(tenant)
        with en_restaurante(tenant):
            cat = Category.objects.create(name="Carta")
            Product.objects.create(category=cat, name=plato, price=Decimal("10000"))
    return a, b, crear_usuario(a, "admin"), crear_usuario(b, "admin")


def _nombres(respuesta):
    return respuesta.content.decode()


@pytest.mark.django_db
def test_cada_base_guarda_solo_lo_suyo(dos_restaurantes, en_restaurante):
    a, b, *_ = dos_restaurantes
    with en_restaurante(a):
        assert list(Product.objects.values_list("name", flat=True)) == ["Solo de A"]
    with en_restaurante(b):
        assert list(Product.objects.values_list("name", flat=True)) == ["Solo de B"]


@pytest.mark.django_db
def test_la_api_del_panel_devuelve_solo_su_restaurante(client, dos_restaurantes):
    _, _, admin_a, _ = dos_restaurantes
    client.force_login(admin_a)
    cuerpo = _nombres(client.get("/api/v1/staff/menu/"))
    assert "Solo de A" in cuerpo and "Solo de B" not in cuerpo


@pytest.mark.django_db
def test_usuario_de_a_no_entra_por_el_subdominio_de_b(client, dos_restaurantes):
    _, b, admin_a, _ = dos_restaurantes
    client.force_login(admin_a)
    host_b = {"HTTP_HOST": f"{b.slug}.localhost"}
    assert client.get("/panel/", **host_b).status_code == 403
    assert client.get("/api/v1/staff/menu/", **host_b).status_code == 403


@pytest.mark.django_db
def test_usuario_de_a_no_escribe_en_b(client, dos_restaurantes, en_restaurante):
    _, b, admin_a, _ = dos_restaurantes
    client.force_login(admin_a)
    with en_restaurante(b):
        cat_b = Category.objects.get()
    respuesta = client.post(
        "/api/v1/staff/menu/products/",
        {"category": cat_b.id, "name": "Intruso", "price": "1000"},
        content_type="application/json",
        HTTP_HOST=f"{b.slug}.localhost",
    )
    assert respuesta.status_code == 403
    with en_restaurante(b):
        assert not Product.objects.filter(name="Intruso").exists()


@pytest.mark.django_db
def test_la_llave_de_a_solo_abre_la_carta_de_a(client, dos_restaurantes):
    a, b, *_ = dos_restaurantes
    cuerpo = _nombres(client.get("/api/v1/menu/", HTTP_X_API_KEY=a.api_key))
    assert "Solo de A" in cuerpo and "Solo de B" not in cuerpo
    # Aunque se pida por el subdominio de B, manda la llave (es de A).
    cuerpo = _nombres(client.get("/api/v1/menu/", HTTP_X_API_KEY=a.api_key, HTTP_HOST=f"{b.slug}.localhost"))
    assert "Solo de B" not in cuerpo


@pytest.mark.django_db
def test_sin_llave_ni_subdominio_la_api_no_responde_datos(client, dos_restaurantes):
    assert client.get("/api/v1/menu/").status_code == 400


@pytest.mark.django_db
def test_superusuario_necesita_modo_soporte(client, django_user_model, dos_restaurantes):
    a, *_ = dos_restaurantes
    jefe = django_user_model.objects.create_superuser("jefe", "jefe@example.com", "clave-jefe-123")
    client.force_login(jefe)
    respuesta = client.get("/panel/", HTTP_HOST=f"{a.slug}.localhost")
    assert respuesta.status_code == 302 and "/panel/soporte/" in respuesta["Location"]
    assert client.get("/api/v1/staff/menu/", HTTP_HOST=f"{a.slug}.localhost").status_code == 403


@pytest.mark.django_db
def test_restaurante_inactivo_no_se_resuelve(client, dos_restaurantes):
    a, *_ = dos_restaurantes
    a.is_active = False
    a.save(update_fields=["is_active"])
    assert client.get("/api/v1/menu/", HTTP_X_API_KEY=a.api_key).status_code == 400
