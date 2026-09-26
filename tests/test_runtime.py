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
        "logo": None, "cover": None,
        "brand": {"primary": "#B3261E", "secondary": "#F2C14E", "background": "#1A1110", "text": "#FFF6EC"},
        "contact": {"whatsapp": "+573001234567", "phone": "+573001234567", "email": None,
                    "address": "Cra 00 # 00-00", "city": "Cali", "maps_url": None},
        "social": {"instagram": "https://instagram.com/restauranteejemplo", "facebook": None, "tiktok": None},
        "hours": [{"day": d, "open": "12:00", "close": "21:00"} for d in ("mon", "tue", "wed", "thu", "fri", "sat")]
        + [{"day": "sun", "closed": True}],
        "services": {"dine_in": True, "takeaway": True, "delivery": False},
        "payment_methods": ["efectivo"],
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


def pagina(menu="carta", **config):
    cfg = {"restaurant": "ejemplo", "api": API, "contract": 1, "locale": "es-CO", "currency": "COP",
           "hideSoldOut": False, "cacheTtl": 0, **config}
    return (f'<!doctype html><html lang="es"><head><meta charset="utf-8"></head><body>'
            f"{CUERPO.replace('{menu}', menu)}"
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


@pytest.fixture(scope="module")
def navegador():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="msedge", headless=True)
        except Exception as e:  # pragma: no cover - depende del equipo
            pytest.skip(f"No se pudo abrir Edge para las pruebas del runtime: {e}")
        yield browser
        browser.close()


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
        if config or "menu" in config:
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
    assert page.query_selector("#mesa") is None  # sin ?mesa= no hay mesa
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
    assert page.text_content("#mesa").strip() == "Mesa 5"


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


@pytest.mark.parametrize("cuando", ["2026-09-26T13:00:00-05:00", "2026-09-27T12:00:00-05:00"])
def test_horario_igual_que_en_python(entorno, cuando):
    abrir, api, page, errores = entorno
    momento = datetime.fromisoformat(cuando)
    page.add_init_script(f"Date.now = () => {int(momento.timestamp() * 1000)};")
    page = abrir()
    assert page.text_content("#hoy") == horario_de_hoy(DATOS["business"]["hours"], momento.astimezone(BOGOTA))
