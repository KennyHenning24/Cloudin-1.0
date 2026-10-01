"""Panel del dueño: pantallas, permisos por rol, asistente de la primera vez, cuenta y
equipo, mesas y QR, los interruptores de pedidos por QR y app de meseros, vista previa
y app instalable (PWA)."""

import io
import json
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.staticfiles import finders
from django.core import mail
from django.core.cache import cache
from django.urls import reverse
from django.utils.html import escapejs
from PIL import Image

from apps.business.models import OpeningHours, RestaurantSettings
from apps.catalog.models import Category, Product
from apps.dining.models import Table
from apps.tenants.crypto import hay_llave
from apps.tenants.models import TenantMembership

PANTALLAS_DEL_MENU = ("inicio", "mi-menu", "carta-producto-nuevo", "personalizar", "qr", "cuenta", "bienvenida")


@pytest.fixture
def menu_digital(crear_restaurante, crear_usuario, en_restaurante):
    tenant = crear_restaurante("birria-lucho", nombre="Birria Don Lucho")
    dueno = crear_usuario(tenant, "lucho", rol=TenantMembership.ROLE_OWNER, nombre="Lucho", correo="lucho@example.com")
    with en_restaurante(tenant):
        cat = Category.objects.create(name="Birria")
        taco = Product.objects.create(category=cat, name="Taco de birria", price=Decimal("9000"))
        consome = Product.objects.create(category=cat, name="Consomé", price=None)
        ajustes = RestaurantSettings.load()
        ajustes.onboarding_step = 1  # ya pasó por el asistente (lo saltó)
        ajustes.save()
    return SimpleNamespace(tenant=tenant, dueno=dueno, cat=cat, taco=taco, consome=consome)


def _foto_jpg():
    salida = io.BytesIO()
    Image.new("RGB", (900, 700), (200, 90, 40)).save(salida, "JPEG")
    salida.name = "foto.jpg"
    salida.seek(0)
    return salida


# --------------------------------------------------------------- pantallas


@pytest.mark.django_db
def test_las_pantallas_del_menu_abren(client, menu_digital):
    client.force_login(menu_digital.dueno)
    for nombre in PANTALLAS_DEL_MENU:
        r = client.get(reverse(f"panel:{nombre}"))
        assert r.status_code == 200, (nombre, r.status_code)
    assert client.get(reverse("panel:carta-producto", args=[menu_digital.taco.uuid])).status_code == 200


@pytest.mark.django_db
def test_todos_tienen_pedidos_mesas_cocina_y_meseros(client, menu_digital):
    """No hay planes: cualquier restaurante tiene el panel completo."""
    client.force_login(menu_digital.dueno)
    for nombre in ("tables", "kitchen", "mensajes", "meseros", "configuracion"):
        assert client.get(reverse(f"panel:{nombre}")).status_code == 200, nombre
    html = client.get(reverse("panel:inicio")).content.decode()
    for seccion in ("Personalizar", "Códigos QR", "Meseros", "Mesas", "Cocina"):
        assert seccion in html, seccion
    assert "Mi menú" not in html  # ahora es una pestaña de Personalizar
    assert "Pedidos y mesas" in html and 'id="campana"' in html and 'class="fab"' in html
    assert "barra-inferior" not in html


@pytest.mark.django_db
def test_inicio_con_estado_pendientes_y_qr(client, menu_digital):
    client.force_login(menu_digital.dueno)
    html = client.get(reverse("panel:inicio")).content.decode()
    assert "Sin publicar" in html  # todavía no tiene la página de su menú digital
    menu_digital.tenant.menu_page = "https://birria-lucho.pages.dev/"
    menu_digital.tenant.save()
    html = client.get(reverse("panel:inicio")).content.decode()
    assert "En línea" in html  # página publicada y un producto disponible con precio
    assert "Completa tu menú" in html and "Precio de 1 producto" in html
    assert "Logo y colores" not in html  # el diseño es de la página del menú
    assert reverse("api:qr-menu", args=["png"]) in html
    assert "https://birria-lucho.pages.dev/" in html  # «Ver mi menú» lleva a su página


@pytest.mark.django_db
def test_mi_menu_marca_sin_precio_y_agotado(client, menu_digital):
    client.force_login(menu_digital.dueno)
    html = client.get(reverse("panel:mi-menu")).content.decode()
    assert "Taco de birria" in html and "$ 9.000" in html
    assert "Poner precio" in html and "Sin precio" in html  # el consomé
    assert 'data-ordenable="categories"' in html and 'data-ordenable="products"' in html
    assert 'id="seleccionar"' in html and 'id="barra-masiva"' in html


@pytest.mark.django_db
def test_el_editor_se_abre_como_fragmento_para_la_tablet(client, menu_digital):
    client.force_login(menu_digital.dueno)
    r = client.get(reverse("panel:carta-producto", args=[menu_digital.taco.uuid]), {"fragmento": "1"})
    html = r.content.decode()
    assert r.status_code == 200 and "<html" not in html
    assert "data-editor-raiz" in html and 'id="editor-config"' in html
    config = json.loads(html.split('id="editor-config" type="application/json">')[1].split("</script>")[0])
    assert config["producto"]["name"] == "Taco de birria" and config["producto"]["price"] == 9000


# ------------------------------------------------------------------ roles


@pytest.mark.django_db
def test_el_equipo_solo_marca_agotados(client, menu_digital, crear_usuario):
    mesero = crear_usuario(menu_digital.tenant, "ana", rol=TenantMembership.ROLE_STAFF)
    client.force_login(mesero)
    html = client.get(reverse("panel:mi-menu")).content.decode()
    assert "data-disponible" in html
    assert "data-editar-precio" not in html and 'id="seleccionar"' not in html
    assert "pestanas-seccion" not in html  # los datos del negocio son solo del administrador
    for nombre in ("personalizar", "carta-producto-nuevo", "bienvenida"):
        assert client.get(reverse(f"panel:{nombre}")).status_code == 403, nombre
    url = f"/api/v1/staff/catalog/products/{menu_digital.taco.uuid}/"
    assert client.patch(url + "availability/", {"available": False}, content_type="application/json").status_code == 200
    assert client.patch(url, {"price": 1}, content_type="application/json").status_code == 403


# ------------------------------------------------------------- asistente


@pytest.mark.django_db
def test_la_primera_vez_empieza_por_el_asistente_y_se_puede_saltar(client, menu_digital, en_restaurante):
    with en_restaurante(menu_digital.tenant):
        RestaurantSettings.objects.filter(pk=1).update(onboarding_step=0)
    client.force_login(menu_digital.dueno)
    r = client.get(reverse("panel:inicio"))
    assert r.status_code == 302 and r.url == reverse("panel:bienvenida")
    assert client.post(reverse("panel:bienvenida"), {"accion": "saltar"}).status_code == 302
    html = client.get(reverse("panel:inicio")).content.decode()
    assert "Termina de configurar tu menú" in html


@pytest.mark.django_db
def test_el_asistente_completo_deja_el_menu_listo(client, menu_digital, en_restaurante):
    client.force_login(menu_digital.dueno)
    url = reverse("panel:bienvenida")
    # 3 pasos: el diseño (colores, logo, portada) es de la página del menú y no se pide.
    html = client.get(f"{url}?paso=1").content.decode()
    assert "Paso 1 de 3" in html and "Datos de tu negocio" in html and "color_primary" not in html
    r = client.post(url, {"paso": 1, "tagline": "Birria de verdad", "whatsapp": "300 123 4567", "city": "Cali",
                          "address": "Cra 1 # 2-3", "dias": ["0", "1", "2", "3", "4"], "abre": "12:00", "cierra": "21:00"})
    assert r.url == f"{url}?paso=2"
    r = client.post(url, {"paso": 2, "categoria": "Tacos"})
    assert r.url == f"{url}?paso=3"
    with en_restaurante(menu_digital.tenant):
        tacos = Category.objects.get(name="Tacos")
    html = client.get(f"{url}?paso=3").content.decode()
    assert f'value="{tacos.uuid}" selected' in html  # la categoría del paso 2 queda elegida
    assert "Terminar" in html
    r = client.post(url, {"paso": 3, "name": "Taco dorado", "price": "$ 8.000", "category": str(tacos.uuid),
                          "foto": _foto_jpg()})
    assert r.url == f"{url}?paso=4"
    # Sin página publicada no se promete un QR ni se muestra un teléfono en blanco.
    final = client.get(r.url).content.decode()
    assert "¡Tu carta está lista!" in final and "Tu menú todavía no está publicado" in final
    assert "<iframe" not in final
    menu_digital.tenant.menu_page = "https://birria-lucho.pages.dev/"
    menu_digital.tenant.save(update_fields=["menu_page"])
    final = client.get(r.url).content.decode()
    assert "¡Tu menú está listo!" in final
    assert 'src="https://birria-lucho.pages.dev/?cloudin-preview=1"' in final
    with en_restaurante(menu_digital.tenant):
        ajustes = RestaurantSettings.load()
        assert ajustes.onboarding_done_at is not None and ajustes.onboarding_step == 4
        assert ajustes.whatsapp == "+573001234567" and ajustes.tagline == "Birria de verdad"
        assert OpeningHours.objects.count() == 5
        taco = Product.objects.get(name="Taco dorado")
        assert taco.category == tacos and taco.price == Decimal("8000") and taco.is_available
        assert taco.imagen.name.endswith(".webp")


@pytest.mark.django_db
def test_el_asistente_explica_lo_que_falta(client, menu_digital):
    client.force_login(menu_digital.dueno)
    url = reverse("panel:bienvenida")
    r = client.post(url, {"paso": 1, "whatsapp": "123"}, follow=True)
    assert "celular de 10 dígitos" in r.content.decode()
    r = client.post(url, {"paso": 2, "categoria": ""}, follow=True)
    assert "primera categoría" in r.content.decode()


# ------------------------------------------------------------ Personalizar


@pytest.mark.django_db
def test_personalizar_tiene_los_platos_y_los_datos_del_negocio(client, menu_digital):
    """Una sola entrada «Personalizar» con dos pestañas; sin colores, logo ni portada."""
    client.force_login(menu_digital.dueno)
    assert reverse("panel:mi-menu") == "/panel/personalizar/"
    assert reverse("panel:personalizar") == "/panel/personalizar/datos/"
    platos = client.get(reverse("panel:mi-menu")).content.decode()
    assert "<h1>Personalizar</h1>" in platos and "Taco de birria" in platos
    assert f'<a href="{reverse("panel:mi-menu")}" aria-current="page">' in platos
    assert f'<a href="{reverse("panel:personalizar")}">' in platos
    datos = client.get(reverse("panel:personalizar")).content.decode()
    assert f'<a href="{reverse("panel:personalizar")}" aria-current="page">' in datos
    for campo in ("tagline", "whatsapp", "email", "instagram", "services", "payment_methods"):
        assert f'name="{campo}"' in datos, campo
    for diseno in ('id="marca"', 'id="portada"', "color_primary", "subir-foto", "colores.js"):
        assert diseno not in datos, diseno
    # En la barra lateral, «Personalizar» queda marcada en las dos pestañas y en el editor.
    editor = client.get(reverse("panel:carta-producto", args=[menu_digital.taco.uuid])).content.decode()
    for html in (platos, datos, editor):
        assert f'<a href="{reverse("panel:mi-menu")}" class="libre on">' in html
    assert "Volver a Personalizar" in editor


@pytest.mark.django_db
def test_las_direcciones_de_mi_menu_llevan_a_personalizar(client, menu_digital):
    client.force_login(menu_digital.dueno)
    r = client.get("/panel/mi-menu/?estado=sin_foto")
    assert r.status_code == 302 and r.url == "/panel/personalizar/?estado=sin_foto"
    r = client.get(f"/panel/mi-menu/producto/nuevo/?categoria={menu_digital.cat.uuid}")
    assert r.status_code == 302 and r.url == f"/panel/personalizar/producto/nuevo/?categoria={menu_digital.cat.uuid}"
    r = client.get(f"/panel/mi-menu/producto/{menu_digital.taco.uuid}/")
    assert r.status_code == 302 and r.url == f"/panel/personalizar/producto/{menu_digital.taco.uuid}/"
    assert client.get(r.url).status_code == 200


# ----------------------------------------------------------------- cuenta


@pytest.mark.django_db
def test_cambiar_la_clave_sigue_con_la_sesion_y_guarda_la_copia(client, menu_digital):
    client.force_login(menu_digital.dueno)
    r = client.post(reverse("panel:cuenta"), {"accion": "clave", "old_password": "clave-de-prueba-123",
                                              "new_password1": "Birria-2026-nueva", "new_password2": "Birria-2026-nueva"})
    assert r.status_code == 302
    assert client.get(reverse("panel:cuenta")).status_code == 200  # la sesión sigue viva
    dueno = type(menu_digital.dueno).objects.get(pk=menu_digital.dueno.pk)
    assert dueno.check_password("Birria-2026-nueva")
    if hay_llave():
        assert dueno.tenant_membership.password_visible == "Birria-2026-nueva"


@pytest.mark.django_db
def test_invitar_al_equipo_manda_el_correo(client, menu_digital):
    client.force_login(menu_digital.dueno)
    r = client.post(reverse("panel:cuenta"), {"accion": "invitar", "nombre": "Ana Gómez", "correo": "Ana@Example.com",
                                              "rol": "staff"})
    assert r.status_code == 302
    nueva = TenantMembership.objects.get(user__email="ana@example.com")
    assert nueva.tenant == menu_digital.tenant and nueva.role == TenantMembership.ROLE_STAFF
    assert nueva.user.username.startswith(f"{menu_digital.tenant.slug}.")
    assert len(mail.outbox) == 1 and "/panel/invitacion/" in mail.outbox[0].body
    # El mismo correo no se invita dos veces.
    client.post(reverse("panel:cuenta"), {"accion": "invitar", "nombre": "Otra", "correo": "ana@example.com"})
    assert TenantMembership.objects.filter(user__email__iexact="ana@example.com").count() == 1
    # Un rol que no existe (o «dueño») queda como equipo.
    client.post(reverse("panel:cuenta"), {"accion": "invitar", "nombre": "Leo", "correo": "leo@example.com", "rol": "owner"})
    assert TenantMembership.objects.get(user__email="leo@example.com").role == TenantMembership.ROLE_STAFF


@pytest.mark.django_db
def test_solo_el_dueno_saca_gente_del_equipo(client, menu_digital, crear_usuario):
    admin = crear_usuario(menu_digital.tenant, "admin", rol=TenantMembership.ROLE_ADMIN)
    mesero = crear_usuario(menu_digital.tenant, "mesero", rol=TenantMembership.ROLE_STAFF)
    client.force_login(admin)
    client.post(reverse("panel:cuenta"), {"accion": "quitar", "miembro": mesero.tenant_membership.pk})
    mesero.refresh_from_db()
    assert mesero.is_active
    client.force_login(menu_digital.dueno)
    client.post(reverse("panel:cuenta"), {"accion": "quitar", "miembro": mesero.tenant_membership.pk})
    mesero.refresh_from_db()
    assert not mesero.is_active
    # Al dueño no lo saca nadie.
    client.force_login(admin)
    client.post(reverse("panel:cuenta"), {"accion": "quitar", "miembro": menu_digital.dueno.tenant_membership.pk})
    assert type(admin).objects.get(pk=menu_digital.dueno.pk).is_active


# ------------------------------------------------------------ mesas y QR


@pytest.mark.django_db
def test_crear_mesas_y_ver_sus_qr(client, menu_digital, en_restaurante):
    client.force_login(menu_digital.dueno)
    r = client.post("/api/v1/staff/mesas/", {"count": 3}, content_type="application/json")
    assert r.status_code == 201 and r.json() == {"created": 3}
    html = client.get(reverse("panel:qr")).content.decode()
    # Sin la página del menú digital no hay a dónde llevar el QR: las mesas se ven, sus QR no.
    assert "Mesa 3" in html and reverse("api:qr-mesas-pdf") not in html
    assert "tu menú digital esté publicado" in html
    with en_restaurante(menu_digital.tenant):
        mesa = Table.objects.get(number=2)
    assert client.get(reverse("api:qr-mesa", args=[mesa.id, "png"])).status_code == 404
    menu_digital.tenant.menu_page = "https://birria-lucho.pages.dev/"
    menu_digital.tenant.save()
    html = client.get(reverse("panel:qr")).content.decode()
    assert reverse("api:qr-mesas-pdf") in html
    # Cada mesa deja copiar su enlace (con el token), para probar el menú sin escanear el QR.
    assert f"copiar('{escapejs(f'https://birria-lucho.pages.dev/?mesa={mesa.token}')}'" in html
    r = client.get(reverse("api:qr-mesa", args=[mesa.id, "png"]))
    assert r.status_code == 200 and r["Content-Type"] == "image/png"


# ------------------------------------------- cómo se toman los pedidos


@pytest.mark.django_db
def test_el_administrador_apaga_y_enciende_los_pedidos_por_qr(client, menu_digital, en_restaurante):
    with en_restaurante(menu_digital.tenant):
        mesa = Table.objects.create(number=1)
    llave = {"HTTP_X_API_KEY": menu_digital.tenant.api_key}
    estado = f"/api/v1/mesa/{mesa.token}/estado/"
    client.force_login(menu_digital.dueno)
    for pantalla in ("inicio", "qr", "meseros"):  # el interruptor está en las tres
        assert "data-pedidos-qr" in client.get(reverse(f"panel:{pantalla}")).content.decode(), pantalla
    assert client.get(estado, **llave).json()["recibe_pedidos"] is True

    r = client.post(reverse("panel:pedidos-qr"), {"activo": "0", "next": reverse("panel:qr")})
    assert r.status_code == 302 and r.url == reverse("panel:qr")
    menu_digital.tenant.refresh_from_db()
    assert not menu_digital.tenant.pedidos_qr
    assert "Pedidos por QR apagados" in client.get(reverse("panel:qr")).content.decode()
    assert client.get(estado, **llave).json()["recibe_pedidos"] is False
    r = client.post(f"/api/v1/mesa/{mesa.token}/enviar/", {"by": "Ana"}, content_type="application/json", **llave)
    assert r.status_code == 403 and r.json()["codigo"] == "sin_pedidos"

    # Una dirección de otro sitio no sirve para volver: se va al Inicio.
    r = client.post(reverse("panel:pedidos-qr"), {"activo": "1", "next": "https://otro.example/"})
    assert r.url == reverse("panel:inicio")
    menu_digital.tenant.refresh_from_db()
    assert menu_digital.tenant.pedidos_qr
    assert client.get(estado, **llave).json()["recibe_pedidos"] is True


@pytest.mark.django_db
def test_el_equipo_ve_si_hay_pedidos_por_qr_pero_no_los_cambia(client, menu_digital, crear_usuario):
    cajero = crear_usuario(menu_digital.tenant, "caja", rol=TenantMembership.ROLE_STAFF)
    client.force_login(cajero)
    html = client.get(reverse("panel:inicio")).content.decode()
    assert "Pedidos desde el QR de la mesa" in html and 'role="switch"' not in html.split("data-pedidos-qr")[1][:1500]
    assert client.post(reverse("panel:pedidos-qr"), {"activo": "0"}).status_code == 403
    menu_digital.tenant.refresh_from_db()
    assert menu_digital.tenant.pedidos_qr


@pytest.mark.django_db
def test_la_app_de_meseros_se_apaga_y_enciende_en_meseros(client, menu_digital):
    entrar = reverse("mesero:entrar", kwargs={"slug": menu_digital.tenant.slug})
    assert client.get(entrar).status_code == 200  # encendida al empezar
    client.force_login(menu_digital.dueno)
    r = client.post(reverse("panel:meseros"), {"accion": "app_meseros", "activo": "0"})
    assert r.status_code == 302
    menu_digital.tenant.refresh_from_db()
    assert not menu_digital.tenant.app_meseros and menu_digital.tenant.pedidos_qr  # el QR no cambia
    client.logout()
    apagada = client.get(entrar)
    assert apagada.status_code == 403 and "Meseros → App de meseros" in apagada.content.decode()
    client.force_login(menu_digital.dueno)
    client.post(reverse("panel:meseros"), {"accion": "app_meseros", "activo": "1"})
    client.logout()
    assert client.get(entrar).status_code == 200


# ---------------------------------------------------------- vista previa


@pytest.mark.django_db
def test_la_vista_previa_no_cuenta_como_visita(client, menu_digital):
    slug = menu_digital.tenant.slug
    cache.delete(f"menu_visto:{slug}")
    client.get(f"/api/public/{slug}/menu/", {"vista": "panel"})
    assert cache.get(f"menu_visto:{slug}") is None
    client.get(f"/api/public/{slug}/menu/")
    assert cache.get(f"menu_visto:{slug}") is not None


# ------------------------------------------------------------------- PWA


@pytest.mark.django_db
def test_el_panel_se_instala_como_app(client):
    manifiesto = client.get(reverse("panel:manifest"))
    datos = json.loads(manifiesto.content)
    assert manifiesto["Content-Type"] == "application/manifest+json"
    assert datos["scope"] == "/panel/" and datos["start_url"] == "/panel/" and datos["display"] == "standalone"
    assert any(i["purpose"] == "maskable" for i in datos["icons"])
    for icono in datos["icons"]:
        assert finders.find(icono["src"].replace("/static/", "", 1)), icono["src"]
    sw = client.get(reverse("panel:sw"))
    assert sw.status_code == 200 and sw["Service-Worker-Allowed"] == "/panel/"
    assert "cloudin-panel-" in sw.content.decode() and "__VERSION__" not in sw.content.decode()
    assert client.get(reverse("panel:sin-conexion")).status_code == 200


# ------------------------------------------------------ pedidos y mesas


@pytest.mark.django_db
def test_el_panel_tiene_mi_menu_y_pedidos_y_los_enlaces_viejos_llevan_al_editor(
        client, crear_restaurante, crear_usuario, en_restaurante):
    tenant = crear_restaurante("completo")
    admin = crear_usuario(tenant)
    with en_restaurante(tenant):
        p = Product.objects.create(category=Category.objects.create(name="Platos"), name="Bandeja", price=Decimal("25000"))
    client.force_login(admin)
    # La primera vez el administrador empieza por el asistente; se puede saltar.
    r = client.get(reverse("panel:inicio"))
    assert r.status_code == 302 and r.url == reverse("panel:bienvenida")
    client.post(reverse("panel:bienvenida"), {"accion": "saltar"})
    html = client.get(reverse("panel:inicio")).content.decode()
    assert f'href="{reverse("panel:mi-menu")}"' in html and f'href="{reverse("panel:personalizar")}"' in html
    # Pedidos, mesas, cocina y meseros (y ya no hay turno de caja).
    assert "Pedidos y mesas" in html and 'id="campana"' in html
    for nombre in ("tables", "mensajes", "kitchen", "meseros"):
        assert f'href="{reverse(f"panel:{nombre}")}"' in html, nombre
        assert client.get(reverse(f"panel:{nombre}")).status_code == 200, nombre
    for vieja in ("Turnos y caja", "Facturación", "Inventario", "Reservas", "Cloudin Control"):
        assert vieja not in html, vieja
    r = client.get(reverse("panel:producto-editar", args=[p.id]))
    assert r.status_code == 302 and r.url == reverse("panel:carta-producto", args=[p.uuid])
