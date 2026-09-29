"""El panel del dueño en Edge, contra un servidor de verdad (live_server).

Lo que solo se puede probar con el navegador: agotar con «Deshacer», el precio en
línea, el editor con su vista previa en vivo y que ninguna pantalla se salga de lo
ancho en un celular de 375 px. Sin Edge se usa Chromium; sin ninguno, se saltan.
"""

import os
import time
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.conf import settings

from apps.business.models import RestaurantSettings
from apps.catalog.models import Category, Product
from apps.tenants.models import TenantMembership

# Playwright (sync) deja un bucle de asyncio en este hilo; las consultas de la prueba
# a la base son cortas y no compiten con el servidor.
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")

PANTALLAS = ["/panel/", "/panel/mi-menu/", "/panel/mi-menu/producto/nuevo/", "/panel/personalizar/",
             "/panel/mesas-y-qr/", "/panel/cuenta/", "/panel/bienvenida/?paso=1", "/panel/bienvenida/?paso=4"]


@pytest.fixture
def panel(live_server, transactional_db, crear_restaurante, crear_usuario, en_restaurante, client):
    tenant = crear_restaurante("birria-e2e", nombre="Birria E2E")
    dueno = crear_usuario(tenant, "lucho", rol=TenantMembership.ROLE_OWNER, nombre="Lucho")
    with en_restaurante(tenant):
        cat = Category.objects.create(name="Birria")
        taco = Product.objects.create(category=cat, name="Taco de birria", price=Decimal("9000"),
                                      description="Tortilla de maíz, birria de res y consomé.")
        Product.objects.create(category=cat, name="Quesabirria con doble queso y cebolla asada", price=Decimal("14000"))
        Product.objects.create(category=Category.objects.create(name="Bebidas"), name="Horchata", price=None)
        ajustes = RestaurantSettings.load()
        ajustes.onboarding_step = 1
        ajustes.save()
    client.force_login(dueno)
    return SimpleNamespace(url=live_server.url, sesion=client.cookies["sessionid"].value, tenant=tenant,
                           taco=taco, cat=cat, en=lambda: en_restaurante(tenant))


def _abrir(navegador, panel, ruta, ancho=375, alto=812):
    movil = ancho < 640
    contexto = navegador.new_context(viewport={"width": ancho, "height": alto}, is_mobile=movil, has_touch=movil)
    contexto.add_cookies([{"name": "sessionid", "value": panel.sesion, "url": panel.url}])
    page = contexto.new_page()
    errores = []
    page.on("pageerror", lambda e: errores.append(str(e)))
    page.on("console", lambda m: errores.append(m.text) if m.type == "error" else None)
    page.goto(panel.url + ruta)
    return contexto, page, errores


def _esperar(condicion, segundos=5):
    fin = time.time() + segundos
    while time.time() < fin:
        if condicion():
            return True
        time.sleep(0.1)
    return condicion()


def _producto(panel, **filtro):
    with panel.en():
        return Product.objects.get(**filtro)


@pytest.mark.django_db(transaction=True)
def test_agotar_con_deshacer_en_el_celular(navegador, panel):
    contexto, page, errores = _abrir(navegador, panel, "/panel/mi-menu/")
    fila = page.locator(f'li.producto[data-id="{panel.taco.uuid}"]')
    fila.locator(".switch").click()
    page.get_by_text("Taco de birria quedó agotado").wait_for()
    assert fila.get_attribute("data-available") == "false"
    assert _esperar(lambda: not _producto(panel, pk=panel.taco.pk).is_available)
    page.get_by_role("button", name="Deshacer").click()
    assert _esperar(lambda: _producto(panel, pk=panel.taco.pk).is_available)
    assert fila.get_attribute("data-available") == "true"
    contexto.close()
    assert errores == []


@pytest.mark.django_db(transaction=True)
def test_precio_en_linea_con_teclado_numerico(navegador, panel):
    contexto, page, errores = _abrir(navegador, panel, "/panel/mi-menu/", ancho=1440, alto=900)
    fila = page.locator(f'li.producto[data-id="{panel.taco.uuid}"]')
    fila.locator("[data-editar-precio]").click()
    campo = fila.locator(".precio-edicion input")
    assert campo.get_attribute("inputmode") == "numeric"
    campo.fill("12500")
    assert campo.input_value() == "$ 12.500"  # se formatea mientras se escribe
    campo.press("Enter")
    page.get_by_text("Taco de birria: $ 12.500").wait_for()
    assert _esperar(lambda: _producto(panel, pk=panel.taco.pk).price == Decimal("12500"))
    assert fila.locator("[data-editar-precio]").inner_text() == "$ 12.500"
    contexto.close()
    assert errores == []


@pytest.mark.django_db(transaction=True)
def test_buscar_filtra_al_instante(navegador, panel):
    contexto, page, errores = _abrir(navegador, panel, "/panel/mi-menu/", ancho=1440, alto=900)
    page.locator("#buscar").fill("quesa")
    page.wait_for_function("() => document.querySelectorAll('.producto:not([hidden])').length === 1")
    page.locator("#buscar").fill("")
    page.locator('.filtros [data-estado="sin_precio"]').click()
    visibles = page.eval_on_selector_all(".producto:not([hidden])", "fs => fs.map(f => f.dataset.nombreProducto)")
    assert visibles == ["Horchata"]
    contexto.close()
    assert errores == []


@pytest.fixture
def menu_externo(panel, tmp_path):
    """La página del menú digital del restaurante vive en otro origen (en producción,
    su sitio en Cloudflare Pages). Aquí es el ejemplo del contrato (client/example),
    servido por un servidor estático aparte, con la API y el runtime de este servidor."""
    import shutil
    import threading
    from functools import partial
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

    ejemplo = Path(settings.BASE_DIR) / "client" / "example"
    shutil.copytree(ejemplo, tmp_path, dirs_exist_ok=True)
    html = (ejemplo / "index.html").read_text(encoding="utf-8")
    html = html.replace("http://localhost:8000", panel.url).replace("restaurante-ejemplo", panel.tenant.slug)
    (tmp_path / "menu.html").write_text(html, encoding="utf-8")

    class Silencioso(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    servidor = ThreadingHTTPServer(("127.0.0.1", 0), partial(Silencioso, directory=str(tmp_path)))
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    panel.tenant.menu_page = f"http://127.0.0.1:{servidor.server_port}/menu.html"
    panel.tenant.save()
    yield panel.tenant.menu_page
    servidor.shutdown()


@pytest.mark.django_db(transaction=True)
def test_el_editor_crea_el_producto_y_la_vista_previa_lo_muestra(navegador, panel, menu_externo):
    ruta = f"/panel/mi-menu/producto/nuevo/?categoria={panel.cat.uuid}"
    contexto, page, errores = _abrir(navegador, panel, ruta, ancho=1440, alto=900)
    page.locator("#e-nombre").fill("Consomé grande")
    page.locator("#e-precio").fill("6000")
    vista = page.frame_locator("iframe[data-vista-previa]")
    vista.get_by_text("Consomé grande").wait_for(timeout=10000)
    page.locator("[data-guardar]").click()
    page.get_by_text("«Consomé grande» quedó en tu menú").wait_for()
    nuevo = _producto(panel, name="Consomé grande")
    assert nuevo.price == Decimal("6000") and nuevo.category_id == panel.cat.pk and nuevo.is_available
    assert page.url.endswith(f"/panel/mi-menu/producto/{nuevo.uuid}/")
    contexto.close()
    assert errores == []


@pytest.mark.django_db(transaction=True)
def test_en_la_tablet_el_editor_se_abre_en_el_cajon(navegador, panel):
    contexto, page, errores = _abrir(navegador, panel, "/panel/mi-menu/", ancho=768, alto=1024)
    page.locator(f'li.producto[data-id="{panel.taco.uuid}"] a.nombre').click()
    cajon = page.locator("#cajon-editor")
    cajon.locator("#e-nombre").wait_for()
    assert page.url.endswith("/panel/mi-menu/")  # no salió de la lista
    cajon.locator("#e-nombre").fill("Taco de birria especial")
    with page.expect_navigation():
        cajon.locator("[data-guardar]").click()
    page.get_by_text("Cambios guardados").wait_for()
    assert _producto(panel, pk=panel.taco.pk).name == "Taco de birria especial"
    contexto.close()
    assert errores == []


@pytest.mark.django_db(transaction=True)
def test_subir_precios_en_porcentaje_y_deshacer(navegador, panel):
    contexto, page, errores = _abrir(navegador, panel, "/panel/mi-menu/", ancho=1440, alto=900)
    page.locator("#seleccionar").click()
    filas = page.locator(f'.categoria[data-id="{panel.cat.uuid}"] li.producto')
    for i in range(2):
        filas.nth(i).locator(".seleccion").check()
    page.get_by_text("2 seleccionados").wait_for()
    page.locator('[data-masivo="price_percent"]').click()
    page.locator("#c-porcentaje").fill("10")
    page.locator('#dialogo-porcentaje button[type="submit"]').click()
    page.get_by_text("Precios actualizados en 2 productos").wait_for()
    assert _esperar(lambda: _producto(panel, pk=panel.taco.pk).price == Decimal("9900"))
    assert _producto(panel, name__startswith="Quesabirria").price == Decimal("15400")
    assert "$ 9.900" in page.locator(f'li.producto[data-id="{panel.taco.uuid}"]').inner_text()
    page.get_by_role("button", name="Deshacer").click()
    assert _esperar(lambda: _producto(panel, pk=panel.taco.pk).price == Decimal("9000"))
    assert _producto(panel, name__startswith="Quesabirria").price == Decimal("14000")
    contexto.close()
    assert errores == []


@pytest.mark.django_db(transaction=True)
def test_ordenar_con_flechas_en_el_celular(navegador, panel):
    contexto, page, errores = _abrir(navegador, panel, "/panel/mi-menu/")
    page.locator("#ordenar").click()
    fila = page.locator(f'li.producto[data-id="{panel.taco.uuid}"]')
    # Sin orden guardado van por nombre: Quesabirria y luego el taco. Se sube el taco.
    fila.locator('[data-mover="arriba"]').click()
    assert _esperar(lambda: _producto(panel, name__startswith="Quesabirria").position == 1)
    assert _producto(panel, pk=panel.taco.pk).position == 0
    assert page.locator(f'.categoria[data-id="{panel.cat.uuid}"] li.producto').first.get_attribute("data-id") == str(panel.taco.uuid)
    contexto.close()
    assert errores == []


@pytest.mark.django_db(transaction=True)
def test_personalizar_guarda_datos_y_horario(navegador, panel):
    contexto, page, errores = _abrir(navegador, panel, "/panel/personalizar/", ancho=1440, alto=900)
    page.locator("#c-tagline").fill("La birria más jugosa de Cali")
    page.locator("#c-whatsapp").fill("310 555 1234")
    page.locator('.dia[data-dia="mon"] .switch').click()  # abre el lunes con un horario
    page.locator('[data-copiar-horario]').click()          # y lo copia a toda la semana
    page.locator("[data-guardar]").click()
    page.get_by_text("Cambios guardados: ya se ven en tu menú.").wait_for()
    assert page.locator("#c-whatsapp").input_value() == "310 555 1234"
    with panel.en():
        from apps.business.models import OpeningHours

        ajustes = RestaurantSettings.load()
        assert ajustes.tagline == "La birria más jugosa de Cali" and ajustes.whatsapp == "+573105551234"
        assert sorted(OpeningHours.objects.values_list("day", flat=True)) == list(range(7))
    contexto.close()
    assert errores == []


@pytest.mark.django_db(transaction=True)
def test_eliminar_desde_mi_menu_pregunta_antes(navegador, panel):
    contexto, page, errores = _abrir(navegador, panel, "/panel/mi-menu/", ancho=1440, alto=900)
    fila = page.locator(f'li.producto[data-id="{panel.taco.uuid}"]')

    def pedir_eliminar():
        fila.locator("details.desplegable > summary").click()
        fila.locator('[data-accion="eliminar"]').click()
        dialogo = page.locator("#dialogo-confirmar[open]")
        dialogo.get_by_text("«Taco de birria» sale de tu menú").wait_for()
        return dialogo

    pedir_eliminar().get_by_role("button", name="Cancelar").click()
    assert fila.count() == 1 and not _producto(panel, pk=panel.taco.pk).eliminado
    pedir_eliminar().get_by_role("button", name="Sí, eliminar").click()
    page.get_by_text("Taco de birria salió de tu menú").wait_for()
    assert _esperar(lambda: _producto(panel, pk=panel.taco.pk).eliminado)
    contexto.close()
    assert errores == []


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("ancho,alto", [(375, 812), (1440, 900)])
def test_el_menu_del_ultimo_plato_se_ve_entero(navegador, panel, ancho, alto):
    # El «⋯» del último plato, con la fila pegada al borde de abajo: la caja no queda cortada por
    # la tarjeta de la categoría ni tapada por la barra del celular o el botón «+ Producto».
    contexto, page, errores = _abrir(navegador, panel, "/panel/mi-menu/", ancho=ancho, alto=alto)
    fila = page.locator("li.categoria").last.locator("li.producto").last
    nombre = fila.get_attribute("data-nombre-producto")
    fila.scroll_into_view_if_needed()
    page.evaluate("(f) => scrollBy(0, f.getBoundingClientRect().bottom - innerHeight + 60)", fila.element_handle())
    fila.locator("details.desplegable > summary").click()
    eliminar = fila.locator('.opciones [data-accion="eliminar"]')
    eliminar.wait_for()
    tocable = page.evaluate("""(b) => { const r = b.getBoundingClientRect();
        const p = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
        return r.bottom <= innerHeight && !!p && b.contains(p); }""", eliminar.element_handle())
    assert tocable, "«Eliminar» queda cortado o tapado"
    eliminar.click()
    page.locator("#dialogo-confirmar[open]").get_by_text(f"«{nombre}» sale de tu menú").wait_for()
    page.locator("#dialogo-confirmar[open]").get_by_role("button", name="Cancelar").click()
    contexto.close()
    assert errores == []


@pytest.mark.django_db(transaction=True)
def test_etiqueta_nueva_desde_el_editor_del_plato(navegador, panel):
    contexto, page, errores = _abrir(navegador, panel, f"/panel/mi-menu/producto/{panel.taco.uuid}/",
                                     ancho=1440, alto=900)
    page.locator("details.avanzadas > summary").click()
    page.locator("#e-etiqueta-nueva").fill("Ahumado")
    page.locator("[data-crear-etiqueta]").click()
    chip = page.locator("button.chip[data-etiqueta]", has_text="Ahumado")
    chip.wait_for()
    assert chip.get_attribute("aria-pressed") == "true"
    page.locator("#e-etiqueta-nueva").fill("Picante suave")
    page.locator("#e-etiqueta-nueva").press("Enter")  # Enter la crea; no guarda el plato
    page.locator("button.chip[data-etiqueta]", has_text="Picante suave").wait_for()
    page.locator("#e-etiqueta-nueva").fill("vegano")  # ya existe: solo la marca
    page.locator("[data-crear-etiqueta]").click()
    assert _esperar(lambda: page.locator('button.chip[data-etiqueta="vegano"]').get_attribute("aria-pressed") == "true")
    assert page.locator("button.chip[data-etiqueta]", has_text="vegano").count() == 1
    page.locator("[data-guardar]").click()
    page.get_by_text("Cambios guardados").wait_for()
    with panel.en():
        taco = Product.objects.get(pk=panel.taco.pk)
        assert sorted(taco.tags.values_list("key", flat=True)) == ["ahumado", "picante-suave", "vegano"]
    contexto.close()
    assert errores == []


@pytest.mark.django_db(transaction=True)
def test_el_editor_pregunta_antes_de_eliminar(navegador, panel):
    contexto, page, errores = _abrir(navegador, panel, f"/panel/mi-menu/producto/{panel.taco.uuid}/",
                                     ancho=1440, alto=900)
    page.locator("[data-eliminar]").click()
    page.locator("#dialogo-confirmar[open]").get_by_role("button", name="Cancelar").click()
    assert not _producto(panel, pk=panel.taco.pk).eliminado and "/producto/" in page.url
    page.locator("[data-eliminar]").click()
    with page.expect_navigation():
        page.locator("#dialogo-confirmar[open]").get_by_role("button", name="Sí, eliminar").click()
    page.get_by_text("«Taco de birria» salió de tu menú").wait_for()
    assert "/panel/mi-menu/" in page.url and _producto(panel, pk=panel.taco.pk).eliminado
    page.wait_for_load_state("networkidle")  # nada en camino cuando se borra la base de la prueba
    contexto.close()
    assert errores == []


def _celular_lento(navegador, panel, tmp_path):
    """Un contexto donde preparar la foto (canvas → WebP) tarda 1,5 s, como en un celular
    lento, y una foto de prueba para elegir."""
    from PIL import Image

    foto = tmp_path / "plato.jpg"
    Image.new("RGB", (1600, 1200), (180, 90, 40)).save(foto)
    contexto = navegador.new_context(viewport={"width": 1440, "height": 900})
    contexto.add_cookies([{"name": "sessionid", "value": panel.sesion, "url": panel.url}])
    contexto.add_init_script("""(() => {
      const original = HTMLCanvasElement.prototype.toBlob;
      HTMLCanvasElement.prototype.toBlob = function (...args) { setTimeout(() => original.apply(this, args), 1500); };
    })();""")
    page = contexto.new_page()
    errores = []
    page.on("pageerror", lambda e: errores.append(str(e)))
    page.on("console", lambda m: errores.append(m.text) if m.type == "error" else None)
    return contexto, page, errores, str(foto)


@pytest.mark.django_db(transaction=True)
def test_guardar_espera_la_foto_que_se_esta_preparando(navegador, panel, tmp_path):
    contexto, page, errores, foto = _celular_lento(navegador, panel, tmp_path)
    page.goto(panel.url + f"/panel/mi-menu/producto/{panel.taco.uuid}/")
    page.locator("[data-subir-foto] input[type=file]:not([capture])").set_input_files(foto)
    page.locator("#dialogo-recorte [data-usar]").click()
    page.locator("[data-guardar]").click()  # enseguida: la foto todavía se está preparando
    page.get_by_text("Cambios guardados").wait_for(timeout=10000)
    assert _producto(panel, pk=panel.taco.pk).imagen
    contexto.close()
    assert errores == []


@pytest.mark.django_db(transaction=True)
def test_el_asistente_espera_la_foto_del_plato(navegador, panel, tmp_path):
    contexto, page, errores, foto = _celular_lento(navegador, panel, tmp_path)
    page.goto(panel.url + "/panel/bienvenida/?paso=4")
    page.locator("#foto-plato input[type=file]:not([capture])").set_input_files(foto)
    page.locator("#dialogo-recorte [data-usar]").click()
    page.locator('input[name="name"]').fill("Birria con foto")
    page.locator('input[name="price"]').fill("15000")
    with page.expect_navigation():
        page.get_by_role("button", name="Terminar").click()
    assert _producto(panel, name="Birria con foto").imagen
    page.wait_for_load_state("networkidle")
    contexto.close()
    assert errores == []


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("ancho", [375, 768])
def test_ninguna_pantalla_se_sale_de_lo_ancho(navegador, panel, ancho):
    for ruta in PANTALLAS:
        contexto, page, errores = _abrir(navegador, panel, ruta, ancho=ancho)
        page.wait_for_load_state("networkidle")
        sobra = page.evaluate("() => document.documentElement.scrollWidth - innerWidth")
        contexto.close()
        assert sobra <= 0, (ruta, sobra)
        assert errores == [], (ruta, errores)
