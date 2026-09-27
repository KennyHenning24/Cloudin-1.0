"""Panel maestro: registrar la página del menú digital de un restaurante y darle el
código que conecta ese menú con Cloudin (PASO-A-PASO-NUEVO-RESTAURANTE.md)."""

import pytest
from django.urls import reverse

from apps.dining.models import Table
from apps.dining.qr import enlace_de_mesa


@pytest.fixture
def jefe(client, django_user_model):
    usuario = django_user_model.objects.create_superuser("jefe", "jefe@example.com", "clave-jefe-123")
    client.force_login(usuario)
    return usuario


@pytest.mark.django_db
def test_nuevo_restaurante_con_la_pagina_de_su_menu(client, jefe, bases_creadas_en_la_prueba):
    from apps.tenants.models import Tenant

    bases_creadas_en_la_prueba.append("la-casa")
    r = client.post(reverse("master:restaurante-nuevo"), {
        "name": "La Casa", "slug": "la-casa", "plan": "completo",
        "menu_page": "https://la-casa.pages.dev/",
        "admin_usuario": "admin", "admin_correo": "ana@example.com",
    })
    assert r.status_code == 302 and r.url == reverse("master:restaurante", args=["la-casa"])
    tenant = Tenant.objects.get(slug="la-casa")
    assert tenant.menu_page == "https://la-casa.pages.dev/" and tenant.site_url == ""
    assert "https://la-casa.pages.dev" in tenant.origenes_permitidos  # ya puede pedir


@pytest.mark.django_db
def test_la_ficha_registra_la_pagina_y_da_el_codigo_del_menu(client, jefe, crear_restaurante, en_restaurante):
    tenant = crear_restaurante("cultura", plan="completo")
    ficha = reverse("master:restaurante", args=["cultura"])
    html = client.get(ficha).content.decode()
    assert "Sin página registrada" in html and "Sin conexión todavía" in html
    # El código que va en el menú, con este servidor, este restaurante y su llave.
    assert 'restaurant: "cultura"' in html
    assert 'api: "http://testserver/api/public/cultura/menu/"' in html
    assert f'apiKey: "{tenant.api_key}"' in html
    assert "http://testserver/static/cloudin-menu.v1.js" in html

    r = client.post(reverse("master:restaurante-menu", args=["cultura"]), {
        "pagina": "https://culturabrisket.pages.dev/",
        "otros": "https://menu.culturabrisket.com/carta\n\nhttps://menu.culturabrisket.com",
    })
    assert r.status_code == 302
    tenant.refresh_from_db()
    assert tenant.menu_page == "https://culturabrisket.pages.dev/"
    assert tenant.allowed_origins == ["https://menu.culturabrisket.com"]
    assert tenant.origenes_permitidos == {"https://culturabrisket.pages.dev", "https://menu.culturabrisket.com"}
    with en_restaurante(tenant):
        mesa = Table.objects.create(number=1)
        assert enlace_de_mesa(tenant, mesa) == f"https://culturabrisket.pages.dev/?mesa={mesa.token}"

    # Cuando el menú pide la carta, la ficha lo muestra conectado.
    assert client.get("/api/public/cultura/menu/").status_code == 200
    html = client.get(ficha).content.decode()
    assert "Menú de Cultura registrado" in html and "Conectado" in html and "Sin página registrada" not in html


@pytest.mark.django_db
def test_la_ficha_rechaza_direcciones_que_no_son_web(client, jefe, crear_restaurante):
    tenant = crear_restaurante("cultura", plan="completo", menu_page="https://culturabrisket.pages.dev/")
    r = client.post(reverse("master:restaurante-menu", args=["cultura"]),
                    {"pagina": "https://otra.pages.dev/", "otros": "menu.culturabrisket.com"}, follow=True)
    assert "no es una dirección" in r.content.decode()
    tenant.refresh_from_db()
    assert tenant.menu_page == "https://culturabrisket.pages.dev/" and tenant.allowed_origins == []


@pytest.mark.django_db
def test_con_el_plan_menu_el_codigo_no_lleva_llave(client, jefe, crear_restaurante):
    crear_restaurante("solo-carta")  # plan «Menú digital»: la carta es solo para mirar
    html = client.get(reverse("master:restaurante", args=["solo-carta"])).content.decode()
    assert 'apiKey: ""' in html
