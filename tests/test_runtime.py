"""Pruebas del runtime `cloudin-menu.v1.js` en un navegador real (Edge, con Playwright).

No levantan el servidor: el sitio, el runtime y la API se simulan con rutas de
Playwright (`https://sitio.test`, `https://cloudin.test`). Cubren la sección 5
del contrato y la lista de verificación de la skill (sección 9).

Si este equipo no tiene Edge, las pruebas se saltan.
"""

import copy
import json
from datetime import datetime
from pathlib import Path

import pytest

from apps.public_menu.horario import BOGOTA, horario_de_hoy

RUNTIME = (Path(__file__).resolve().parent.parent / "static" / "cloudin-menu.v1.js").read_text(encoding="utf-8")
API = "https://cloudin.test/api/public/ejemplo/menu/"

DATOS = {
    "schema": "cloudin.menu/v1",
    "business": {
        "slug": "ejemplo", "name": "Restaurante Ejemplo", "tagline": "Comida casera, en Cali",
        "description": None, "welcome_message": None, "logo": None, "cover": None,
        "brand": {"primary": "#B3261E", "secondary": "#F2C14E", "background": "#1A1110", "text": "#FFF6EC"},
        "contact": {"whatsapp": "+573001234567", "phone": "+573001234567", "email": None,
                    "address": "Cra 00 # 00-00", "city": "Cali", "maps_url": None},
        "social": {"instagram": "https://instagram.com/restauranteejemplo", "facebook": None, "tiktok": None},
        "hours": [{"day": d, "open": "12:00", "close": "21:00"} for d in ("mon", "tue", "wed", "thu", "fri", "sat")]
        + [{"day": "sun", "closed": True}],
        "services": {"dine_in": True, "takeaway": True, "delivery": False},
        "payment_methods": ["efectivo"], "payment_methods_text": "Efectivo",
    },
    "menus": [
        {"id": "m1", "key": "carta", "name": "Carta", "description": None, "categories": [
            {"id": "c1", "key": "hamburguesas", "name": "Hamburguesas", "description": "Con papas a la francesa.",
             "image": None, "products": [
                 {"id": "p1", "key": "hamburguesa-clasica", "name": "Hamburguesa clásica",
                  "description": "Carne de res, queso, lechuga, tomate y papas a la francesa.", "price": 24000,
                  "image": "https://cloudin.test/media/hamburguesa.webp", "available": True, "featured": True,
                  "tags": ["recomendado"], "tax": None,
                  "variants": [{"id": "v1", "key": "doble", "name": "Doble carne", "price": 32000}],
                  "modifier_groups": []},
                 {"id": "p2", "key": "vegetariana", "name": "Hamburguesa vegetariana", "description": None,
                  "price": 26000, "image": None, "available": False, "featured": False, "tags": [], "tax": None,
                  "variants": [], "modifier_groups": []},
             ]},
            {"id": "c2", "key": "bebidas", "name": "Bebidas", "description": None, "image": None, "products": [
                {"id": "p3", "key": "limonada-de-coco", "name": "Limonada de coco", "description": None,
                 "price": 8500, "image": None, "available": True, "featured": False, "tags": ["nuevo"],
                 "tax": None, "variants": [], "modifier_groups": []},
            ]},
        ]},
        {"id": "m2", "key": "desayunos", "name": "Desayunos", "description": None, "categories": [
            {"id": "c3", "key": "calentados", "name": "Calentados", "description": None, "image": None, "products": [
                {"id": "p4", "key": "calentado-paisa", "name": "Calentado paisa", "description": None,
                 "price": 18000, "image": None, "available": True, "featured": False, "tags": [], "tax": None,
                 "variants": [], "modifier_groups": []},
            ]},
        ]},
    ],
    "tags": [{"key": "recomendado", "name": "Recomendado"}, {"key": "nuevo", "name": "Nuevo"}],
    "meta": {"version": 1},
}

# Anota los eventos del runtime en window.__eventos (y re-engancha los reveals).
EVENTOS = """
<script>
  window.__eventos = [];
  ["ready", "rendered", "error"].forEach(function (n) {
    document.addEventListener("cloudin:" + n, function (e) {
      window.__eventos.push({ tipo: n, raiz: e.detail && e.detail.root ? (e.detail.root.id || e.detail.root.tagName) : null });
      // Como en 10k-websites: los reveals se re-enganchan en los nodos nuevos.
      if (n === "rendered") e.detail.root.querySelectorAll("[data-reveal]").forEach(function (el) { el.classList.add("is-visible"); });
    });
  });
</script>
"""

# El marcado del ejemplo de la sección 5.4 del contrato, con un producto pre-renderizado.
CUERPO = """
<header><h1 data-cloudin-field="business.name">Restaurante Ejemplo</h1>
<p id="hoy" data-cloudin-field="business.hours_today">Hoy: 12:00 – 21:00</p>
<p id="mesa" data-cloudin-if="table.number">Mesa <span data-cloudin-field="table.number"></span></p></header>
<section id="menu" data-cloudin="menu" data-cloudin-menu="{menu}">
  <nav class="menu-nav" data-cloudin="category-nav">
    <a href="#cat-hamburguesas" data-cloudin-key="hamburguesas">Hamburguesas</a>
    <template data-cloudin-template="category-link">
      <a data-cloudin-href="category.anchor" data-cloudin-field="category.name"></a>
    </template>
  </nav>
  <div data-cloudin="categories">
    <section class="menu-cat" id="cat-hamburguesas" data-cloudin-key="hamburguesas">
      <h3>Hamburguesas</h3>
      <div class="menu-grid" data-cloudin="products">
        <article class="dish" data-cloudin-key="hamburguesa-clasica" data-available="true" data-featured="true">
          <div class="dish__body"><h4>Hamburguesa clásica</h4><strong class="dish__price">$ 24.000</strong></div>
        </article>
      </div>
    </section>
    <template data-cloudin-template="category">
      <section class="menu-cat" data-reveal>
        <h3 data-cloudin-field="category.name"></h3>
        <p class="cat-desc" data-cloudin-if="category.description" data-cloudin-field="category.description"></p>
        <div class="menu-grid" data-cloudin="products"></div>
      </section>
    </template>
    <template data-cloudin-template="product">
      <article class="dish" data-reveal>
        <img data-cloudin-if="product.image" data-cloudin-src="product.image" loading="lazy" width="800" height="800">
        <div class="dish__body">
          <h4 data-cloudin-field="product.name"></h4>
          <p class="desc" data-cloudin-if="product.description" data-cloudin-field="product.description"></p>
          <ul class="dish__tags" data-cloudin="tags">
            <template data-cloudin-template="tag"><li data-cloudin-field="tag.name"></li></template>
          </ul>
          <ul class="dish__variants" data-cloudin="variants">
            <template data-cloudin-template="variant">
              <li><span data-cloudin-field="variant.name"></span> <span data-cloudin-field="variant.price"></span></li>
            </template>
          </ul>
          <strong class="dish__price" data-cloudin-field="product.price"></strong>
          <span class="dish__soldout" data-cloudin-if="!product.available">Agotado</span>
        </div>
      </article>
    </template>
  </div>
</section>
<div id="destacados" data-cloudin="featured"></div>
<a class="cta-whatsapp" href="https://wa.me/570000000000" data-cloudin-href="business.whatsapp_link">Pide por WhatsApp</a>
""" + EVENTOS

# Todos los menús (data-cloudin="menus") y lo de Personalizar que va fuera de la carta.
MENUS = """
<p id="bienvenida" data-cloudin-if="business.welcome_message" data-cloudin-field="business.welcome_message"></p>
<nav id="menus-nav" data-cloudin="menu-nav">
  <a href="#menu-carta" data-cloudin-key="carta">Carta</a>
  <template data-cloudin-template="menu-link"><a data-cloudin-href="menu.anchor" data-cloudin-field="menu.name"></a></template>
</nav>
<div id="menus" data-cloudin="menus">
  <section class="menu" id="menu-carta" data-cloudin-key="carta"><h2>Carta</h2>
    <div data-cloudin="categories"><section class="menu-cat" id="cat-hamburguesas"><h3>Hamburguesas</h3></section></div>
  </section>
  <template data-cloudin-template="menu">
    <section class="menu">
      <h2 data-cloudin-field="menu.name"></h2>
      <p class="menu-desc" data-cloudin-if="menu.description" data-cloudin-field="menu.description"></p>
      <nav class="menu-nav" data-cloudin="category-nav">
        <template data-cloudin-template="category-link"><a data-cloudin-href="category.anchor" data-cloudin-field="category.name"></a></template>
      </nav>
      <div data-cloudin="categories"></div>
    </section>
  </template>
  <template data-cloudin-template="category">
    <section class="menu-cat"><h3 data-cloudin-field="category.name"></h3><div data-cloudin="products"></div></section>
  </template>
  <template data-cloudin-template="product">
    <article class="dish"><h4 data-cloudin-field="product.name"></h4>
      <strong class="dish__price" data-cloudin-field="product.price"></strong>
      <small class="del-menu" data-cloudin-field="menu.name"></small></article>
  </template>
</div>
<footer>
  <a id="correo" data-cloudin-if="business.email_link" data-cloudin-href="business.email_link"><span data-cloudin-field="business.email"></span></a>
  <a id="facebook" data-cloudin-if="business.facebook" data-cloudin-href="business.facebook">Facebook</a>
  <a id="tiktok" data-cloudin-if="business.tiktok" data-cloudin-href="business.tiktok">TikTok</a>
  <a id="mapa" data-cloudin-if="business.maps_url" data-cloudin-href="business.maps_url">Cómo llegar</a>
  <p id="pagos" data-cloudin-if="business.payment_methods_text">Pagos: <span data-cloudin-field="business.payment_methods_text"></span></p>
  <p id="recoger" data-cloudin-if="business.takeaway">Pide y recoge en el local</p>
  <p id="domicilio" data-cloudin-if="business.delivery">Te lo llevamos a domicilio</p>
</footer>
<div id="portada" style="height:40px;background-image:var(--cloudin-cover, url(https://sitio.test/assets/portada.jpg))"></div>
""" + EVENTOS


def pagina(menu="carta", cuerpo=None, **config):
    cfg = {"restaurant": "ejemplo", "api": API, "contract": 1, "locale": "es-CO", "currency": "COP",
           "hideSoldOut": False, "cacheTtl": 0, **config}
    return (f'<!doctype html><html lang="es"><head><meta charset="utf-8"></head><body>'
            f"{(cuerpo or CUERPO).replace('{menu}', menu)}"
            f"<script>window.CLOUDIN_CONFIG = {json.dumps(cfg)};</script>"
            f'<script src="https://cloudin.test/static/cloudin-menu.v1.js" defer></script></body></html>')


class ApiFalsa:
    """Responde como la API de Cloudin y cuenta lo que le piden."""

    def __init__(self):
        self.datos, self.etag, self.estado, self.urls = copy.deepcopy(DATOS), 'W/"ejemplo-1"', 200, []

    def __call__(self, route):
        self.urls.append(route.request.url)
        if self.estado != 200:
            return route.fulfill(status=self.estado, body="caída")
        route.fulfill(status=200, body=json.dumps(self.datos), content_type="application/json",
                      headers={"ETag": self.etag, "Access-Control-Allow-Origin": "*",
                               "Access-Control-Expose-Headers": "ETag"})


@pytest.fixture
def entorno(navegador):
    contexto = navegador.new_context()
    api = ApiFalsa()
    html = {"actual": pagina()}
    errores = []
    contexto.route("https://sitio.test/**", lambda r: r.fulfill(status=200, body=html["actual"],
                                                              content_type="text/html; charset=utf-8"))
    contexto.route("https://cloudin.test/static/cloudin-menu.v1.js",
                   lambda r: r.fulfill(status=200, body=RUNTIME, content_type="application/javascript"))
    contexto.route("https://cloudin.test/media/**", lambda r: r.fulfill(status=200, body=b"", content_type="image/webp"))
    contexto.route(API + "**", api)
    page = contexto.new_page()
    page.on("pageerror", lambda e: errores.append(str(e)))

    def abrir(ruta="/", esperar="live", **config):
        if config:
            html["actual"] = pagina(**config)
        page.goto("https://sitio.test" + ruta)
        page.wait_for_function("() => window.__eventos && window.__eventos.some(e => e.tipo === 'ready')")
        assert page.evaluate("document.documentElement.dataset.cloudinState") == esperar
        return page

    yield abrir, api, page, errores
    contexto.close()


def textos(page, selector):
    return page.eval_on_selector_all(selector, "els => els.map(e => e.textContent.trim())")


def test_api_caida_sin_cache_no_toca_el_html(entorno):
    abrir, api, page, errores = entorno
    api.estado = 500
    antes = None
    page.route("**/nada", lambda r: r.abort())
    page = abrir(esperar="error")
    antes = textos(page, "[data-cloudin=categories] .dish h4")
    assert antes == ["Hamburguesa clásica"]  # lo pre-renderizado sigue intacto
    assert page.evaluate("document.querySelector('#menu').dataset.cloudinState") == "error"
    assert [e["tipo"] for e in page.evaluate("window.__eventos")] == ["error", "ready"]
    assert errores == []


def test_en_vivo_pinta_con_las_plantillas(entorno):
    abrir, api, page, errores = entorno
    page = abrir()
    assert page.eval_on_selector_all("[data-cloudin=categories] > section", "s => s.map(x => x.id)") == [
        "cat-hamburguesas", "cat-bebidas"]
    assert textos(page, ".menu-nav a") == ["Hamburguesas", "Bebidas"]
    assert page.eval_on_selector_all(".menu-nav a", "a => a.map(x => x.getAttribute('href'))") == [
        "#cat-hamburguesas", "#cat-bebidas"]
    platos = page.eval_on_selector_all("#cat-hamburguesas .dish", """ds => ds.map(d => ({
        key: d.dataset.cloudinKey, disp: d.dataset.available, dest: d.dataset.featured,
        precio: d.querySelector('.dish__price').textContent, agotado: !!d.querySelector('.dish__soldout'),
        img: d.querySelector('img') && [d.querySelector('img').getAttribute('src'), d.querySelector('img').alt],
        desc: !!d.querySelector('.desc'), tags: [...d.querySelectorAll('.dish__tags li')].map(l => l.textContent),
        variantes: [...d.querySelectorAll('.dish__variants li')].map(l => l.textContent.replace(/\\s+/g, ' ').trim())}))""")
    assert platos[0] == {"key": "hamburguesa-clasica", "disp": "true", "dest": "true", "precio": "Desde $ 24.000",
                         "agotado": False, "img": ["https://cloudin.test/media/hamburguesa.webp", "Hamburguesa clásica"],
                         "desc": True, "tags": ["Recomendado"], "variantes": ["Doble carne $ 32.000"]}
    assert platos[1]["disp"] == "false" and platos[1]["agotado"] and platos[1]["img"] is None
    assert platos[1]["precio"] == "$ 26.000" and platos[1]["desc"] is False
    assert page.get_attribute(".cta-whatsapp", "href") == "https://wa.me/573001234567"
    assert page.text_content("#hoy").startswith("Hoy: ")
    assert page.is_hidden("#mesa")  # sin ?mesa= no hay mesa (lo fijo se oculta, no se borra)
    assert page.eval_on_selector_all(".dish.is-visible", "d => d.length") >= 3  # reveals re-enganchados
    eventos = page.evaluate("window.__eventos")
    assert {"tipo": "rendered", "raiz": "menu"} in eventos and eventos[-1]["tipo"] == "ready"
    assert errores == []


def test_cache_cuando_la_api_se_cae(entorno):
    abrir, api, page, errores = entorno
    abrir()
    api.estado = 503
    page = abrir(esperar="cached")
    assert textos(page, "#cat-bebidas .dish h4") == ["Limonada de coco"]
    assert any(e["tipo"] == "error" for e in page.evaluate("window.__eventos"))


def test_mismo_etag_no_repinta_y_un_cambio_si(entorno):
    abrir, api, page, errores = entorno
    page = abrir()
    page.evaluate("document.querySelector('[data-cloudin-key=limonada-de-coco]').dataset.marca = 'x'")
    page.evaluate("Cloudin.refresh()")
    page.wait_for_timeout(300)
    assert page.get_attribute("[data-cloudin-key=limonada-de-coco]", "data-marca") == "x"
    # El dueño cambia un precio, agota un plato y agrega uno nuevo.
    api.etag = 'W/"ejemplo-2"'
    bebidas = api.datos["menus"][0]["categories"][1]["products"]
    bebidas[0]["price"] = 9000
    bebidas.append({**bebidas[0], "id": "p9", "key": "jugo-de-mango", "name": "Jugo de mango", "price": 7000,
                    "tags": [], "available": False})
    page.evaluate("Cloudin.refresh()")
    page.wait_for_function("() => document.querySelector('[data-cloudin-key=jugo-de-mango]')")
    assert textos(page, "#cat-bebidas .dish__price") == ["$ 9.000", "$ 7.000"]
    assert page.get_attribute("[data-cloudin-key=limonada-de-coco]", "data-marca") is None
    assert page.get_attribute("[data-cloudin-key=jugo-de-mango]", "data-available") == "false"
    assert "is-visible" in page.get_attribute("[data-cloudin-key=jugo-de-mango]", "class")


def test_mesa_desde_el_qr(entorno):
    abrir, api, page, errores = entorno
    api.datos["table"] = {"number": 5}
    page = abrir("/menu.html?mesa=tok123")
    assert "table=tok123" in api.urls[-1]
    assert page.evaluate("Cloudin.table") == {"token": "tok123", "number": 5}
    assert page.text_content("#mesa").strip() == "Mesa 5" and page.is_visible("#mesa")


def test_ocultar_agotados(entorno):
    abrir, api, page, errores = entorno
    page = abrir(hideSoldOut=True)
    assert page.query_selector("[data-cloudin-key=vegetariana]") is None


def test_elige_el_menu_por_clave_y_destacados(entorno):
    abrir, api, page, errores = entorno
    page = abrir(menu="desayunos")
    assert textos(page, "[data-cloudin=categories] .dish h4") == ["Calentado paisa"]
    assert textos(page, "#destacados .dish h4") == ["Hamburguesa clásica"]


def test_nombres_largos_y_ocho_variantes(entorno):
    abrir, api, page, errores = entorno
    p = api.datos["menus"][0]["categories"][0]["products"][0]
    p["name"] = "Hamburguesa triple con tocineta ahumada, cebolla caramelizada y salsa de la casa"
    p["variants"] = [{"id": f"v{i}", "key": f"t{i}", "name": f"Tamaño {i}", "price": 20000 + i * 1000}
                     for i in range(8)]
    page = abrir()
    assert len(page.query_selector_all("#menu [data-cloudin-key=hamburguesa-clasica] .dish__variants li")) == 8
    assert page.text_content("#menu [data-cloudin-key=hamburguesa-clasica] .dish__price") == "Desde $ 20.000"
    assert page.text_content("#menu [data-cloudin-key=hamburguesa-clasica] h4").startswith("Hamburguesa triple")


def test_el_runtime_no_toca_los_colores_ni_la_portada_del_sitio(entorno):
    """El diseño es del sitio: aunque una carta (de antes) traiga colores o portada, el runtime
    no pone variables --cloudin-…, y un CSS viejo con var(--cloudin-…, X) se queda con X."""
    abrir, api, page, errores = entorno
    api.datos["business"].update(cover="https://cloudin.test/media/portada.webp", brand={
        "primary": "#C2410C", "secondary": "#F59E0B", "background": "#FFFFFF", "text": "#1D2029"})
    page = abrir(cuerpo=MENUS)  # con el #portada de un sitio viejo: var(--cloudin-cover, url(portada.jpg))
    variables = page.evaluate("""() => ['primary', 'secondary', 'background', 'text', 'cover'].map(k =>
        getComputedStyle(document.documentElement).getPropertyValue('--cloudin-' + k).trim())""")
    assert variables == ["", "", "", "", ""]
    assert "--cloudin" not in (page.get_attribute("html", "style") or "")
    fondo = "getComputedStyle(document.querySelector('#portada')).backgroundImage"
    assert "sitio.test/assets/portada.jpg" in page.evaluate(fondo)
    # Otra versión de la carta tampoco los pone.
    api.etag = 'W/"ejemplo-2"'
    api.datos["business"]["brand"]["primary"] = "#0B6E4F"
    pintadas = _pintadas(page)
    page.evaluate("Cloudin.refresh()")
    page.wait_for_function(f"() => window.__eventos.filter(e => e.tipo === 'rendered').length > {pintadas}")
    assert "--cloudin" not in (page.get_attribute("html", "style") or "")
    assert errores == []


def _visibles(page, *selectores):
    return [s for s in selectores if page.is_visible(s)]


def test_todos_los_menus_y_un_menu_nuevo_aparece_sin_recargar(entorno):
    abrir, api, page, errores = entorno
    # Un menú sin platos todavía no sale (el dueño lo acaba de crear en Personalizar).
    api.datos["menus"].append({"id": "m3", "key": "postres", "name": "Postres", "description": None, "categories": []})
    page = abrir(cuerpo=MENUS, live=1)
    assert page.eval_on_selector_all("#menus > section", "s => s.map(x => x.id)") == ["menu-carta", "menu-desayunos"]
    assert textos(page, "#menus-nav a") == ["Carta", "Desayunos"]
    assert page.eval_on_selector_all("#menus-nav a", "a => a.map(x => x.getAttribute('href'))") == [
        "#menu-carta", "#menu-desayunos"]
    assert textos(page, "#menu-carta .menu-nav a") == ["Hamburguesas", "Bebidas"]
    assert textos(page, "#menu-desayunos h4") == ["Calentado paisa"]
    assert textos(page, "#menu-desayunos .del-menu") == ["Desayunos"]  # el plato sabe de qué menú es
    assert page.query_selector("#menu-desayunos .menu-desc") is None  # sin descripción: no se pone
    assert {"tipo": "rendered", "raiz": "menus"} in page.evaluate("window.__eventos")
    # En el panel: Personalizar → Nuevo menú «Almuerzos», con su categoría y su plato.
    api.etag = 'W/"ejemplo-2"'
    plato = {**DATOS["menus"][1]["categories"][0]["products"][0], "id": "p9", "key": "bandeja-paisa",
             "name": "Bandeja paisa", "price": 25000}
    api.datos["menus"].append({"id": "m4", "key": "almuerzos", "name": "Almuerzos", "description": "De 12 a 3",
                               "categories": [{"id": "c9", "key": "ejecutivos", "name": "Ejecutivos",
                                               "description": None, "image": None, "products": [plato]}]})
    page.locator("#menu-almuerzos h4", has_text="Bandeja paisa").wait_for(timeout=5000)
    assert textos(page, "#menus-nav a") == ["Carta", "Desayunos", "Almuerzos"]
    assert textos(page, "#menu-almuerzos .menu-desc") == ["De 12 a 3"]
    assert textos(page, "#menu-almuerzos .menu-nav a") == ["Ejecutivos"]
    assert page.evaluate("performance.getEntriesByType('navigation').length") == 1  # nunca recargó
    assert errores == []


def test_lo_de_personalizar_se_esconde_y_vuelve_sin_recargar(entorno):
    abrir, api, page, errores = entorno
    page = abrir(cuerpo=MENUS, live=1)
    todo = ("#bienvenida", "#correo", "#facebook", "#tiktok", "#mapa", "#pagos", "#recoger", "#domicilio")
    assert _visibles(page, *todo) == ["#pagos", "#recoger"]  # Domicilio apagado; sin correo ni redes
    assert page.text_content("#pagos").strip() == "Pagos: Efectivo"
    fondo = "getComputedStyle(document.querySelector('#portada')).backgroundImage"
    assert "portada.jpg" in page.evaluate(fondo)  # la portada es del sitio
    # En Personalizar: correo, Facebook, TikTok, mapa y bienvenida; enciende Domicilio y apaga
    # Recoger. (Una portada en la carta, de antes, no cambia la del sitio.)
    api.etag = 'W/"ejemplo-2"'
    b = api.datos["business"]
    b["contact"].update(email="hola@ejemplo.co", maps_url="https://maps.app.goo.gl/abc")
    b["social"].update(facebook="https://facebook.com/ejemplo", tiktok="https://tiktok.com/@ejemplo")
    b.update(welcome_message="¡Bienvenido! Pide desde tu mesa.", cover="https://cloudin.test/media/portada.webp",
             services={"dine_in": True, "takeaway": False, "delivery": True})
    page.wait_for_function("() => document.querySelector('#domicilio').offsetParent !== null", timeout=5000)
    assert _visibles(page, *todo) == ["#bienvenida", "#correo", "#facebook", "#tiktok", "#mapa", "#pagos", "#domicilio"]
    assert page.get_attribute("#correo", "href") == "mailto:hola@ejemplo.co"
    assert page.text_content("#correo").strip() == "hola@ejemplo.co"
    assert page.get_attribute("#facebook", "href") == "https://facebook.com/ejemplo"
    assert page.text_content("#bienvenida") == "¡Bienvenido! Pide desde tu mesa."
    assert "portada.jpg" in page.evaluate(fondo)
    # Lo vuelve a apagar: se esconde otra vez.
    api.etag = 'W/"ejemplo-3"'
    b["contact"]["email"] = None
    b["social"].update(facebook=None, tiktok=None)
    b.update(services={"dine_in": True, "takeaway": True, "delivery": False})
    page.wait_for_function("() => document.querySelector('#domicilio').offsetParent === null", timeout=5000)
    assert _visibles(page, *todo) == ["#bienvenida", "#mapa", "#pagos", "#recoger"]
    assert "portada.jpg" in page.evaluate(fondo)
    assert page.evaluate("performance.getEntriesByType('navigation').length") == 1
    assert errores == []


def _panel_con_vista_previa(navegador, origen_panel):
    """Un «panel» en `origen_panel` con el sitio en un iframe (?cloudin-preview=1)."""
    contexto = navegador.new_context()
    contexto.route("https://sitio.test/**", lambda r: r.fulfill(status=200, body=pagina(), content_type="text/html"))
    contexto.route("https://cloudin.test/static/cloudin-menu.v1.js",
                   lambda r: r.fulfill(status=200, body=RUNTIME, content_type="application/javascript"))
    api = ApiFalsa()
    contexto.route(API + "**", api)
    panel = """<!doctype html><html><body><iframe id="vista" src="https://sitio.test/menu.html?cloudin-preview=1"
      style="width:400px;height:700px"></iframe><script>
      window.listo = false;
      addEventListener("message", (e) => { if (e.data && e.data.tipo === "cloudin:vista-lista") window.listo = true; });
      window.mandar = (data, foco) => document.getElementById("vista").contentWindow.postMessage(
        {tipo: "cloudin:vista", data, foco}, "https://sitio.test");
    </script></body></html>"""
    contexto.route(origen_panel + "/panel/**", lambda r: r.fulfill(status=200, body=panel, content_type="text/html"))
    page = contexto.new_page()
    page.goto(origen_panel + "/panel/")
    return contexto, page, api


def test_vista_previa_del_panel_pinta_lo_que_se_edita(navegador):
    contexto, page, api = _panel_con_vista_previa(navegador, "https://cloudin.test")
    page.wait_for_function("() => window.listo")  # el sitio avisó que está listo
    assert "vista=panel" in api.urls[-1]  # la vista previa no cuenta como visita
    borrador = copy.deepcopy(DATOS)
    borrador["menus"][0]["categories"][1]["products"][0].update(name="Limonada de coco helada", price=9500)
    page.evaluate("([d, foco]) => mandar(d, foco)", [borrador, "limonada-de-coco"])
    sitio = page.frame_locator("#vista")
    sitio.locator("[data-cloudin-key=limonada-de-coco] h4").filter(has_text="Limonada de coco helada").wait_for()
    assert sitio.locator("[data-cloudin-key=limonada-de-coco] .dish__price").inner_text() == "$ 9.500"
    contexto.close()


def test_la_vista_previa_no_acepta_mensajes_de_otro_sitio(navegador):
    contexto, page, api = _panel_con_vista_previa(navegador, "https://intruso.test")
    borrador = copy.deepcopy(DATOS)
    borrador["menus"][0]["categories"][1]["products"][0]["name"] = "Hackeado"
    page.wait_for_timeout(800)
    assert page.evaluate("window.listo") is False  # el aviso solo va al origen de la API
    page.evaluate("([d]) => mandar(d)", [borrador])
    page.wait_for_timeout(300)
    assert page.frame_locator("#vista").locator("text=Hackeado").count() == 0
    contexto.close()


@pytest.mark.parametrize("cuando", ["2026-09-26T13:00:00-05:00", "2026-09-27T12:00:00-05:00"])
def test_horario_igual_que_en_python(entorno, cuando):
    abrir, api, page, errores = entorno
    momento = datetime.fromisoformat(cuando)
    page.add_init_script(f"Date.now = () => {int(momento.timestamp() * 1000)};")
    page = abrir()
    assert page.text_content("#hoy") == horario_de_hoy(DATOS["business"]["hours"], momento.astimezone(BOGOTA))


# ------------------------------------------------ revisor del menú (?cloudin-check=1)

REVISOR = (Path(__file__).resolve().parent.parent / "static" / "cloudin-check.v1.js").read_text(encoding="utf-8")

# Todo lo de Personalizar conectado (con data-cloudin-if: si queda vacío, no se ve). El diseño
# (colores, logo) es del sitio.
NEGOCIO = """
<header class="marca">
  <img class="logo" src="/assets/logo.png" alt="Restaurante Ejemplo">
  <p data-cloudin-if="business.tagline" data-cloudin-field="business.tagline"></p>
  <p data-cloudin-if="business.welcome_message" data-cloudin-field="business.welcome_message"></p>
</header>
<footer>
  <p data-cloudin-if="business.description" data-cloudin-field="business.description"></p>
  <span data-cloudin-field="business.address"></span> · <span data-cloudin-field="business.city"></span>
  <a data-cloudin-if="business.maps_url" data-cloudin-href="business.maps_url">Cómo llegar</a>
  <a data-cloudin-if="business.phone_link" data-cloudin-href="business.phone_link"><span data-cloudin-field="business.phone"></span></a>
  <a data-cloudin-if="business.email_link" data-cloudin-href="business.email_link"><span data-cloudin-field="business.email"></span></a>
  <a data-cloudin-if="business.instagram" data-cloudin-href="business.instagram">Instagram</a>
  <a data-cloudin-if="business.facebook" data-cloudin-href="business.facebook">Facebook</a>
  <a data-cloudin-if="business.tiktok" data-cloudin-href="business.tiktok">TikTok</a>
  <p data-cloudin-if="business.payment_methods_text">Pagos: <span data-cloudin-field="business.payment_methods_text"></span></p>
  <p data-cloudin-if="business.takeaway">Pide y recoge en el local</p>
  <p data-cloudin-if="business.delivery">Te lo llevamos a domicilio</p>
</footer>
<style>
  :root { --fondo: #fff; --cloudin-primary: #B3261E; }
  body { background: var(--fondo); color: #111; }
  .dish__price { color: #B3261E; }
  h3 { color: #F2C14E; }
</style>
"""

# Un menú bien conectado: todos los menús (data-cloudin="menus") y todo lo de Personalizar.
CONECTADO = """
<header><h1 data-cloudin-field="business.name">Restaurante Ejemplo</h1>
<p id="hoy" data-cloudin-if="business.hours_today" data-cloudin-field="business.hours_today">Hoy: 12:00 – 21:00</p></header>
<nav data-cloudin="menu-nav"><template data-cloudin-template="menu-link">
  <a data-cloudin-href="menu.anchor" data-cloudin-field="menu.name"></a></template></nav>
<main data-cloudin="menus">
  <template data-cloudin-template="menu">
    <section class="menu"><h2 data-cloudin-field="menu.name"></h2>
      <nav class="menu-nav" data-cloudin="category-nav"><template data-cloudin-template="category-link">
        <a data-cloudin-href="category.anchor" data-cloudin-field="category.name"></a></template></nav>
      <div data-cloudin="categories"></div>
    </section>
  </template>
  <template data-cloudin-template="category">
    <section class="menu-cat"><h3 data-cloudin-field="category.name"></h3><div data-cloudin="products"></div></section>
  </template>
  <template data-cloudin-template="product">
    <article class="dish">
      <img data-cloudin-if="product.image" data-cloudin-src="product.image" width="80" height="80">
      <div class="dish__body"><h4 data-cloudin-field="product.name"></h4>
        <p class="desc" data-cloudin-if="product.description" data-cloudin-field="product.description"></p>
        <strong class="dish__price" data-cloudin-field="product.price"></strong>
        <span class="dish__soldout" data-cloudin-if="!product.available">Agotado</span></div>
    </article>
  </template>
</main>
<a class="cta-whatsapp" href="https://wa.me/570000000000" data-cloudin-if="business.whatsapp_link"
   data-cloudin-href="business.whatsapp_link">Pide por WhatsApp</a>
""" + NEGOCIO

# Lo mismo con la carta a la antigua (una raíz data-cloudin="menu" fija): un menú nuevo no sale.
UN_MENU_FIJO = CUERPO + NEGOCIO

NEGOCIO_IDS = ("negocio-nombre", "negocio-frase", "negocio-descripcion", "negocio-bienvenida",
               "negocio-whatsapp", "negocio-telefono", "negocio-correo", "negocio-direccion",
               "negocio-ciudad", "negocio-mapa", "negocio-horario", "negocio-instagram", "negocio-facebook",
               "negocio-tiktok", "negocio-pagos", "servicio-takeaway", "servicio-delivery")

# Un menú «conectado» a medias: carga el runtime, pero la carta y el negocio están escritos a mano.
A_MANO = """
<header><img src="/assets/logo.png" alt="Logo"><h1>Restaurante Ejemplo</h1><p>Comida casera, en Cali</p></header>
<nav><a href="#hamburguesas">Hamburguesas</a> <a href="#bebidas">Bebidas</a></nav>
<main>
  <section id="hamburguesas"><h2>Hamburguesas</h2>
    <article data-cloudin-key="hamburguesa-clasica"><img src="/assets/clasica.jpg" alt="">
      <div class="dish__body"><h3>Hamburguesa clásica</h3>
        <p>Carne de res, queso, lechuga, tomate y papas a la francesa.</p><strong>$ 24.000</strong></div></article>
    <article data-cloudin-key="vegetariana"><img src="/assets/vegetariana.jpg" alt="">
      <div class="dish__body"><h3>Hamburguesa vegetariana</h3><strong>$ 26.000</strong></div></article>
  </section>
  <section id="bebidas"><h2>Bebidas</h2>
    <article data-cloudin-key="limonada-de-coco"><img src="/assets/limonada.jpg" alt="">
      <div class="dish__body"><h3>Limonada de coco</h3><strong>$ 8.500</strong></div></article>
  </section>
</main>
<footer><a href="https://wa.me/573001234567">WhatsApp</a> <a href="tel:+573001234567">Llamar</a> Cra 00 # 00-00, Cali
  <a href="mailto:hola@ejemplo.co">hola@ejemplo.co</a> <a href="https://facebook.com/restauranteejemplo">Facebook</a>
  <p>Domicilios al 300 123 4567</p></footer>
<style>strong { color: #B3261E; }</style>
"""


def _revisar(navegador, cuerpo, con_runtime=True, html=None, **config):
    """Abre el menú con ?cloudin-check=1 y devuelve lo que dejó el revisor (`html`: la página entera)."""
    cfg = {"restaurant": "ejemplo", "api": API, "apiKey": "ck_prueba", "hideSoldOut": False, "cacheTtl": 0, **config}
    html = html or ('<!doctype html><html lang="es"><head><meta charset="utf-8"></head><body>' + cuerpo
                    + (f"<script>window.CLOUDIN_CONFIG = {json.dumps(cfg)};</script>"
                       '<script src="https://cloudin.test/static/cloudin-menu.v1.js" defer></script>'
                       '<script src="/carrito.js" defer></script>' if con_runtime else "") + "</body></html>")
    contexto = navegador.new_context()
    contexto.route("https://sitio.test/carrito.js", lambda r: r.fulfill(status=200, body="", content_type="application/javascript"))
    contexto.route("https://sitio.test/assets/**", lambda r: r.fulfill(status=200, body=b"", content_type="image/png"))
    contexto.route("https://sitio.test/", lambda r: r.fulfill(status=200, body=html, content_type="text/html; charset=utf-8"))
    contexto.route("https://sitio.test/?**", lambda r: r.fulfill(status=200, body=html, content_type="text/html; charset=utf-8"))
    contexto.route("https://cloudin.test/static/cloudin-menu.v1.js",
                   lambda r: r.fulfill(status=200, body=RUNTIME, content_type="application/javascript"))
    contexto.route("https://cloudin.test/static/cloudin-check.v1.js",
                   lambda r: r.fulfill(status=200, body=REVISOR, content_type="application/javascript"))
    contexto.route("https://cloudin.test/static/img/**", lambda r: r.fulfill(status=200, body=b"", content_type="image/png"))
    contexto.route("https://cloudin.test/media/**", lambda r: r.fulfill(status=200, body=b"", content_type="image/webp"))
    contexto.route(API + "**", ApiFalsa())
    page = contexto.new_page()
    errores = []
    page.on("pageerror", lambda e: errores.append(str(e)))
    page.goto("https://sitio.test/?cloudin-check=1")
    if not con_runtime:
        page.add_script_tag(url="https://cloudin.test/static/cloudin-check.v1.js")
    page.wait_for_function("() => window.CloudinCheck && window.CloudinCheck.terminado", timeout=30000)
    informe = page.evaluate("window.CloudinCheck")
    return contexto, page, informe, {r["id"]: r for r in informe["resultados"]}, errores


def test_el_revisor_aprueba_un_menu_conectado(navegador):
    contexto, page, informe, r, errores = _revisar(navegador, CONECTADO)
    assert informe["aprobado"], informe["texto"]
    for id_ in ("carta", "carrito", "menu-nuevo", "plato-nuevo", "categoria-nueva", "barra", "cambiar-nombre",
                "cambiar-precio", "cambiar-descripcion", "cambiar-foto", "eliminar", "agotado", "a-mano", *NEGOCIO_IDS):
        assert r[id_]["estado"] == "ok", r[id_]
    assert not {"negocio-logo", "negocio-portada", "colores"} & set(r)  # el diseño es del sitio: no se revisa
    # Al terminar queda la carta real (los dos menús), y el informe está a la vista.
    assert textos(page, "[data-cloudin=menus] .dish h4") == [
        "Hamburguesa clásica", "Hamburguesa vegetariana", "Limonada de coco", "Calentado paisa"]
    assert textos(page, "[data-cloudin=menu-nav] a") == ["Carta", "Desayunos"]
    assert "Plato nuevo" not in page.inner_text("body")  # el informe va fuera del <body>
    assert "Tu menú está conectado" in page.locator("#cloudin-check .resumen").inner_text()
    contexto.close()
    assert errores == []


@pytest.mark.parametrize("archivo", ["plantilla/index.html", "example/index.html"])
def test_la_plantilla_y_el_ejemplo_pasan_la_revision(navegador, archivo):
    html = (Path(__file__).resolve().parent.parent / "client" / archivo).read_text(encoding="utf-8")
    html = (html.replace("<servidor-cloudin>", "cloudin.test").replace("<slug>", "ejemplo")
            .replace("http://localhost:8000", "https://cloudin.test").replace("restaurante-ejemplo/menu/", "ejemplo/menu/"))
    contexto, page, informe, r, errores = _revisar(navegador, "", html=html)
    assert informe["aprobado"], informe["texto"]
    contexto.close()
    assert errores == []


def test_el_revisor_pide_todos_los_menus(navegador):
    contexto, page, informe, r, errores = _revisar(navegador, UN_MENU_FIJO)
    assert not informe["aprobado"]
    assert [k for k, v in r.items() if v["estado"] == "falla"] == ["menu-nuevo"], informe["texto"]
    assert 'data-cloudin="menus"' in r["menu-nuevo"]["texto"]
    contexto.close()
    assert errores == []


def test_el_revisor_encuentra_lo_escrito_a_mano(navegador):
    contexto, page, informe, r, errores = _revisar(navegador, A_MANO)
    assert not informe["aprobado"]
    for id_ in ("menu-nuevo", "plato-nuevo", "categoria-nueva", "barra", "cambiar-nombre", "cambiar-precio",
                "cambiar-descripcion", "cambiar-foto", "eliminar", "agotado", "a-mano", *NEGOCIO_IDS):
        assert r[id_]["estado"] == "falla", r[id_]
    assert r["a-mano"]["texto"].startswith("3 platos están escritos a mano")
    for plato in ("«Hamburguesa clásica»", "«Hamburguesa vegetariana»", "«Limonada de coco»"):
        assert plato in r["a-mano"]["texto"]
    assert "«Hamburguesa clásica» sigue escrito a mano" in r["eliminar"]["texto"]
    # Lo escrito a mano se distingue de lo que no se muestra.
    for id_ in ("negocio-correo", "negocio-facebook", "negocio-whatsapp", "negocio-direccion", "servicio-delivery"):
        assert "escrit" in r[id_]["texto"] and "a mano" in r[id_]["texto"], r[id_]
    for id_ in ("negocio-tiktok", "negocio-pagos"):
        assert "no se ve" in r[id_]["texto"], r[id_]
    assert 'data-cloudin-if="business.takeaway"' in r["servicio-takeaway"]["texto"]
    assert informe["texto"].splitlines()[1].startswith("❌ Hay ")  # el resumen, listo para pegarle a Claude Code
    contexto.close()
    assert errores == []


def test_el_revisor_sin_runtime(navegador):
    contexto, page, informe, r, errores = _revisar(navegador, A_MANO, con_runtime=False)
    assert not informe["aprobado"]
    assert r["conexion"]["estado"] == "falla" and r["runtime"]["estado"] == "falla"
    contexto.close()


def test_el_revisor_con_agotados_ocultos(navegador):
    contexto, page, informe, r, errores = _revisar(navegador, CONECTADO, hideSoldOut=True)
    assert r["agotado"]["estado"] == "ok" and informe["aprobado"], informe["texto"]
    contexto.close()


# ------------------------------------------------------- carta en vivo (sin recargar)

def _pintadas(page):
    return len([e for e in page.evaluate("window.__eventos") if e["tipo"] == "rendered"])


def test_un_agotado_del_panel_se_ve_sin_recargar(entorno):
    abrir, api, page, errores = entorno
    page = abrir(live=1)
    pintadas = _pintadas(page)
    preguntas = len(api.urls)
    page.wait_for_timeout(2500)
    assert len(api.urls) >= preguntas + 2  # sigue preguntando si la carta cambió…
    assert _pintadas(page) == pintadas     # …y si no cambió, no repinta
    # El dueño agota la limonada en su panel: la carta sube de versión.
    api.etag = 'W/"ejemplo-2"'
    api.datos["menus"][0]["categories"][1]["products"][0]["available"] = False
    page.wait_for_function("""() => document.querySelector('#menu [data-cloudin-key="limonada-de-coco"]')
        .dataset.available === 'false'""", timeout=5000)
    assert page.locator('#menu [data-cloudin-key="limonada-de-coco"] .dish__soldout').inner_text() == "Agotado"
    # Y un plato nuevo aparece solo.
    api.etag = 'W/"ejemplo-3"'
    api.datos["menus"][0]["categories"][1]["products"].append(
        {**api.datos["menus"][0]["categories"][1]["products"][0], "id": "p9", "key": "jugo-de-mango",
         "name": "Jugo de mango", "available": True})
    page.locator("#menu h4", has_text="Jugo de mango").wait_for(timeout=5000)
    assert page.evaluate("performance.getEntriesByType('navigation').length") == 1  # nunca recargó
    assert errores == []


def test_en_segundo_plano_no_pregunta_y_al_volver_si(entorno):
    abrir, api, page, errores = entorno
    page = abrir(live=1)
    page.evaluate("Object.defineProperty(document, 'visibilityState', {configurable: true, get: () => 'hidden'})")
    preguntas = len(api.urls)
    page.wait_for_timeout(2200)
    assert len(api.urls) == preguntas  # el teléfono guardado en el bolsillo no gasta datos
    api.etag = 'W/"ejemplo-2"'
    api.datos["menus"][0]["categories"][1]["products"][0]["name"] = "Limonada de coco helada"
    page.evaluate("""() => { Object.defineProperty(document, 'visibilityState', {configurable: true, get: () => 'visible'});
                             document.dispatchEvent(new Event('visibilitychange')); }""")
    page.locator("#menu h4", has_text="Limonada de coco helada").wait_for(timeout=3000)
    assert errores == []


def test_live_cero_no_pregunta(entorno):
    abrir, api, page, errores = entorno
    page = abrir(live=0)
    preguntas = len(api.urls)
    page.wait_for_timeout(1500)
    assert len(api.urls) == preguntas
