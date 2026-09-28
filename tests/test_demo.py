"""seed_demo_menu: el restaurante de demostración (una birriería) listo para mostrar."""

from io import StringIO

import pytest
from django.core import mail
from django.core.management import call_command

from apps.business.models import RestaurantSettings
from apps.catalog.models import Menu, Product
from apps.dining.models import Table
from apps.tenants.models import Tenant, TenantMembership


@pytest.mark.django_db
def test_la_demo_queda_lista_y_reimportar_no_duplica(client, bases_creadas_en_la_prueba, en_restaurante):
    bases_creadas_en_la_prueba.append("demo-prueba")
    salida = StringIO()
    call_command("seed_demo_menu", "--slug", "demo-prueba", "--password", "Birria-Demo-2026", stdout=salida)
    assert "Restaurante de demostración listo" in salida.getvalue() and "Birria-Demo-2026" in salida.getvalue()
    assert mail.outbox == []  # la demo no le escribe a nadie

    t = Tenant.objects.get(slug="demo-prueba")
    assert t.pedidos_qr and t.name == "Birriería La Demo"
    dueno = TenantMembership.objects.get(tenant=t, role=TenantMembership.ROLE_OWNER).user
    assert dueno.email == "dueno@demo-prueba.test" and dueno.check_password("Birria-Demo-2026")
    with en_restaurante(t):
        assert list(Menu.objects.order_by("position").values_list("key", flat=True)) == ["carta", "desayunos"]
        productos = Product.objects.filter(eliminado=False)
        assert productos.count() == 14
        assert not productos.exclude(imagen="").exists() and not productos.exclude(image_url="").exists()  # sin fotos
        assert not Product.objects.get(key="michelada").is_available  # un agotado
        sin_precio = Product.objects.get(key="birria-por-libra")
        assert sin_precio.price is None and not sin_precio.is_available
        tacos = Product.objects.get(key="tacos-de-birria")
        assert tacos.variants.count() == 1 and tacos.modifier_links.count() == 2
        assert Table.objects.filter(is_active=True).count() == 8
        assert RestaurantSettings.load().onboarding_done_at is not None  # el panel abre directo en el Inicio

    # Otra vez: no duplica y respeta lo que se cambió en el panel.
    with en_restaurante(t):
        Product.objects.filter(key="horchata").update(price=8500)
    otra_vez = StringIO()
    call_command("seed_demo_menu", "--slug", "demo-prueba", stdout=otra_vez)
    assert "la misma de antes" in otra_vez.getvalue()
    dueno.refresh_from_db()
    assert dueno.check_password("Birria-Demo-2026")  # volver a correrlo no cambia la contraseña
    with en_restaurante(t):
        assert Product.objects.filter(eliminado=False).count() == 14
        assert Product.objects.get(key="horchata").price == 8500

    # El dueño entra y ve su menú.
    client.force_login(dueno)
    from django.conf import settings

    from apps.tenants.models import AceptacionLegal

    AceptacionLegal.objects.create(user=dueno, version=settings.LEGAL_VERSION)
    r = client.get("/panel/mi-menu/")
    assert r.status_code == 200, (r.status_code, r.get("Location"))
    html = r.content.decode()
    assert "Tacos de birria" in html and "Desayunos" in html
    assert client.get("/api/public/demo-prueba/menu/").json()["business"]["name"] == "Birriería La Demo"
