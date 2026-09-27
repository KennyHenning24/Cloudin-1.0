"""Carta v1: modelos, claves estables, compatibilidad con los pedidos de antes e historial."""

from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from apps.business.models import RestaurantSettings, normalizar_telefono
from apps.catalog.legacy import guardar_opciones_legacy
from apps.catalog.models import Category, Menu, ModifierGroup, ModifierOption, Product, ProductModifierGroup, Tag
from apps.catalog.opciones import aplicar
from apps.tenants.models import ApiToken, TenantMembership


@pytest.fixture
def restaurante(crear_restaurante):
    return crear_restaurante("carta-v1", phone="300 123 4567", city="Cali", address="Cra 1 # 2-3")


@pytest.mark.django_db
def test_las_etiquetas_del_contrato_vienen_sembradas(restaurante, en_restaurante):
    with en_restaurante(restaurante):
        assert set(Tag.objects.values_list("key", flat=True)) == {
            "vegetariano", "vegano", "picante", "sin-gluten", "nuevo", "recomendado", "para-compartir"}


@pytest.mark.django_db
def test_claves_estables_y_unicas(restaurante, en_restaurante):
    with en_restaurante(restaurante):
        cat = Category.objects.create(name="Sándwiches y Más")
        assert cat.menu.key == "carta"  # sin menú -> el menú principal, creado solo
        assert cat.key == "sandwiches-y-mas"
        a = Product.objects.create(category=cat, name="Hamburguesa Clásica", price=Decimal("24000"))
        b = Product.objects.create(category=cat, name="Hamburguesa clásica", price=Decimal("25000"))
        assert (a.key, b.key) == ("hamburguesa-clasica", "hamburguesa-clasica-2")
        a.name = "La Clásica de la casa"
        a.save()
        a.refresh_from_db()
        assert a.key == "hamburguesa-clasica"  # renombrar no cambia la clave
        assert a.uuid and a.uuid != b.uuid


@pytest.mark.django_db
def test_sin_precio_no_puede_estar_disponible(restaurante, en_restaurante):
    with en_restaurante(restaurante):
        cat = Category.objects.create(name="Bebidas")
        p = Product.objects.create(category=cat, name="Limonada de coco", price=None, is_available=True)
        assert p.is_available is False  # save() lo apaga
        with pytest.raises(IntegrityError), transaction.atomic(using=restaurante.db_alias):
            Product.objects.filter(pk=p.pk).update(is_available=True)  # la base tampoco lo deja


@pytest.mark.django_db
def test_opciones_viejas_ida_y_vuelta(restaurante, en_restaurante):
    grupos = [
        {"nombre": "Elige la carne", "tipo": "uno", "obligatorio": True,
         "valores": [{"nombre": "Brisket", "precio": 0}, {"nombre": "Pastrami", "precio": 0}]},
        {"nombre": "Adiciones", "tipo": "varios", "obligatorio": False, "maximo": 2,
         "valores": [{"nombre": "Tocineta", "precio": 4000}, {"nombre": "Queso", "precio": 3000}]},
    ]
    with en_restaurante(restaurante):
        cat = Category.objects.create(name="Sandwiches")
        p = Product.objects.create(category=cat, name="Dos quesos", price=Decimal("35000"))
        guardar_opciones_legacy(p, grupos)
        p = Product.objects.get(pk=p.pk)
        assert p.opciones == grupos
        nombre, precio, detalle, _ = aplicar(p, [{"grupo": 0, "valor": 1}, {"grupo": 1, "valor": 0}])
        assert precio == Decimal("39000")
        assert nombre == "Dos quesos · Pastrami, Tocineta (+$4.000)"
        # Reemplazar las opciones borra los grupos que quedan huérfanos.
        guardar_opciones_legacy(p, grupos[:1])
        assert ModifierGroup.objects.count() == 1


@pytest.mark.django_db
def test_tamanos_se_ven_como_primer_grupo_y_el_precio_sale_bien(restaurante, en_restaurante):
    with en_restaurante(restaurante):
        cat = Category.objects.create(name="Pizzas")
        p = Product.objects.create(category=cat, name="Hawaiana", price=Decimal("30000"), base_label="Mediana")
        p.variants.create(name="Personal", price=Decimal("18000"))
        p.variants.create(name="Familiar", price=Decimal("52000"))
        salsa = ModifierGroup.objects.create(name="Salsas", min_select=1, max_select=2)
        ModifierOption.objects.create(group=salsa, name="Ajo", price_delta=0)
        ModifierOption.objects.create(group=salsa, name="Piña extra", price_delta=Decimal("3000"))
        ProductModifierGroup.objects.create(product=p, group=salsa)
        p = Product.objects.get(pk=p.pk)

        assert p.precio_legacy == Decimal("18000")
        presentacion = p.opciones[0]
        assert presentacion["nombre"] == "Presentación" and presentacion["obligatorio"] is True
        assert [(v["nombre"], v["precio"]) for v in presentacion["valores"]] == [
            ("Mediana", 12000), ("Personal", 0), ("Familiar", 34000)]
        assert p.opciones[1]["minimo"] == 1 and p.opciones[1]["maximo"] == 2

        _, precio, _, _ = aplicar(p, [{"grupo": 0, "valor": 2}, {"grupo": 1, "valor": 1}])
        assert precio == Decimal("55000")  # familiar + piña extra
        with pytest.raises(Exception, match="Falta elegir"):
            aplicar(p, [{"grupo": 1, "valor": 0}])
        with pytest.raises(Exception, match="al menos 1"):
            aplicar(p, [{"grupo": 0, "valor": 0}])


@pytest.mark.django_db
def test_el_historial_guarda_quien_cambio_el_precio(client, restaurante, crear_usuario, en_restaurante):
    dueno = crear_usuario(restaurante, "ana", rol=TenantMembership.ROLE_OWNER, nombre="Ana Ruiz")
    with en_restaurante(restaurante):
        cat = Category.objects.create(name="Platos")
        p = Product.objects.create(category=cat, name="Bandeja", price=Decimal("25000"))
    client.force_login(dueno)
    # Así cambia el precio el editor del panel (sin turno abierto: la carta no lo exige).
    respuesta = client.patch(f"/api/v1/staff/catalog/products/{p.uuid}/", {"name": "Bandeja paisa", "price": 27000},
                             content_type="application/json")
    assert respuesta.status_code == 200, respuesta.content[:500]
    with en_restaurante(restaurante):
        ultimo = Product.history.filter(id=p.id).latest("history_date")
        assert ultimo.price == Decimal("27000") and ultimo.name == "Bandeja paisa"
        assert ultimo.history_user_id == dueno.id
        assert ultimo.history_user_name == "Ana Ruiz"
        assert ultimo.prev_record.price == Decimal("25000")


@pytest.mark.django_db
def test_el_dueno_es_administrador(restaurante, crear_usuario):
    dueno = crear_usuario(restaurante, "dueno", rol=TenantMembership.ROLE_OWNER)
    cajero = crear_usuario(restaurante, "caja", rol=TenantMembership.ROLE_STAFF)
    assert dueno.tenant_membership.es_admin and dueno.tenant_membership.es_dueno
    assert not cajero.tenant_membership.es_admin


@pytest.mark.django_db
def test_ajustes_del_negocio_nacen_con_lo_que_se_sabe(restaurante, en_restaurante):
    with en_restaurante(restaurante):
        ajustes = RestaurantSettings.load()
        assert (ajustes.phone, ajustes.city, ajustes.address) == ("+573001234567", "Cali", "Cra 1 # 2-3")
        assert RestaurantSettings.load().pk == ajustes.pk
    assert normalizar_telefono("(+57) 601 234 5678") == "+576012345678"
    assert normalizar_telefono("12345") == ""


@pytest.mark.django_db
def test_origenes_permitidos_y_plan(crear_restaurante):
    t = crear_restaurante("con-sitio", site_url="https://x.pages.dev/menu.html",
                          allowed_origins=["https://mi-restaurante.com/", "ftp://no.sirve"])
    assert t.origenes_permitidos == {"https://x.pages.dev", "https://mi-restaurante.com"}
    assert t.es_plan_menu


@pytest.mark.django_db
def test_token_de_superadmin(django_user_model):
    jefe = django_user_model.objects.create_superuser("jefe", "j@example.com", "clave-jefe-123")
    registro, token = ApiToken.crear(jefe, "Portátil")
    assert token.startswith("cld_") and registro.token_hash != token
    assert ApiToken.validar(token) == registro
    assert ApiToken.validar("cld_inventado") is None
    registro.revoked_at = registro.created_at
    registro.save()
    assert ApiToken.validar(token) is None
    # Un usuario que no es superusuario no puede tener un token válido.
    normal = django_user_model.objects.create_user("normal", "n@example.com", "clave-123456")
    _, otro = ApiToken.crear(normal, "No debería")
    assert ApiToken.validar(otro) is None


@pytest.mark.django_db
def test_menu_principal_crea_carta_una_sola_vez(restaurante, en_restaurante):
    with en_restaurante(restaurante):
        uno = Menu.principal()
        dos = Menu.principal()
        assert uno.pk == dos.pk and uno.key == "carta"
