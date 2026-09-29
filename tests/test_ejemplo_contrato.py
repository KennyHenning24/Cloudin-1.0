"""El ejemplo del contrato de punta a punta: semilla → Cloudin → API → runtime → página.

Se importa client/example/menu.seed.json, se pide la API pública y se carga
client/example/index.html en Edge. Lo pre-renderizado (sin Cloudin) y lo que
pinta el runtime con los datos vivos deben verse IGUAL: sin salto visual.
"""

import json
import mimetypes
import os
from pathlib import Path

import pytest

from apps.importer.assets import Carpeta
from apps.importer.services import importar_semilla

# Playwright (sync) deja un bucle de asyncio en el hilo; las consultas a la base de
# estas pruebas ocurren antes de abrir el navegador, así que es seguro permitirlo.
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")

EJEMPLO = Path(__file__).resolve().parent.parent / "client" / "example"
RUNTIME = Path(__file__).resolve().parent.parent / "static" / "cloudin-menu.v1.js"
API = "http://localhost:8000/api/public/restaurante-ejemplo/menu/"

# Lo que ve el cliente de cada plato, en orden.
FOTO = """() => ({
  estado: document.documentElement.dataset.cloudinState || null,
  menus: [...document.querySelectorAll('[data-cloudin=menus] > section')].map(s => [s.id, s.querySelector('h2').textContent.trim()]),
  barraMenus: [...document.querySelectorAll('.menus-nav a')].map(a => [a.getAttribute('href'), a.textContent.trim()]),
  // Lo de Personalizar: qué se ve, con qué texto y a dónde lleva.
  negocio: [...document.querySelectorAll('[data-cloudin-if^="business."]')].map(e => [e.getAttribute('data-cloudin-if'),
    getComputedStyle(e).display !== 'none', e.textContent.replace(/\\s+/g, ' ').trim(), e.getAttribute('href')]),
  portada: getComputedStyle(document.querySelector('.portada')).backgroundImage,
  colores: ['.cta-whatsapp', 'body', '.menu-cat h3'].map(s => [getComputedStyle(document.querySelector(s)).color,
    getComputedStyle(document.querySelector(s)).backgroundColor]),
  nav: [...document.querySelectorAll('.menu-nav a')].map(a => [a.getAttribute('href'), a.textContent.trim()]),
  categorias: [...document.querySelectorAll('[data-cloudin=categories] > section')].map(s => ({
    id: s.id, titulo: s.querySelector('h3').textContent.trim(),
    desc: s.querySelector(':scope > p') ? s.querySelector(':scope > p').textContent.trim() : null,
    platos: [...s.querySelectorAll('.dish')].map(d => ({
      key: d.dataset.cloudinKey, disponible: d.dataset.available, destacado: d.dataset.featured,
      nombre: d.querySelector('h4').textContent.trim(),
      desc: d.querySelector('.dish__body > p') ? d.querySelector('.dish__body > p').textContent.trim() : null,
      etiquetas: [...d.querySelectorAll('.dish__tags li')].map(x => x.textContent.trim()),
      tamanos: [...d.querySelectorAll('.dish__variants li')].map(x => x.textContent.replace(/\\s+/g, ' ').trim()),
      precio: d.querySelector('.dish__price').textContent.trim(),
      agotado: !!d.querySelector('.dish__soldout'),
      foto: !!d.querySelector('img'),
    })),
  })),
  whatsapp: document.querySelector('.cta-whatsapp').getAttribute('href'),
})"""


@pytest.fixture
def datos_vivos(client, crear_restaurante, settings):
    settings.CLOUDIN_PUBLIC_URL = "http://localhost:8000"
    crear_restaurante("restaurante-ejemplo", nombre="Restaurante Ejemplo")
    importar_semilla(json.loads((EJEMPLO / "menu.seed.json").read_text(encoding="utf-8")), Carpeta(EJEMPLO),
                     invitar=False)
    r = client.get("/api/public/restaurante-ejemplo/menu/")
    return r.content, r["ETag"]


def _abrir(navegador, cuerpo_api, estado_api=200, con_runtime=True):
    contexto = navegador.new_context()
    errores = []

    def sitio(route):
        ruta = route.request.url.split("localhost:4431/", 1)[1].split("?")[0] or "index.html"
        archivo = EJEMPLO / ruta
        if not archivo.is_file():
            return route.fulfill(status=404, body="")
        route.fulfill(status=200, body=archivo.read_bytes(),
                      content_type=mimetypes.guess_type(archivo.name)[0] or "application/octet-stream")

    contexto.route("http://localhost:4431/**", sitio)
    if con_runtime:
        contexto.route("http://localhost:8000/static/cloudin-menu.v1.js",
                       lambda r: r.fulfill(status=200, body=RUNTIME.read_text(encoding="utf-8"),
                                           content_type="application/javascript"))
    else:
        contexto.route("http://localhost:8000/static/cloudin-menu.v1.js", lambda r: r.abort())
    contexto.route(API + "**", lambda r: r.fulfill(
        status=estado_api, body=cuerpo_api[0] if estado_api == 200 else b"caido", content_type="application/json",
        headers={"ETag": cuerpo_api[1], "Access-Control-Allow-Origin": "*", "Access-Control-Expose-Headers": "ETag"}))
    page = contexto.new_page()
    page.on("pageerror", lambda e: errores.append(str(e)))
    page.goto("http://localhost:4431/index.html")
    return contexto, page, errores


@pytest.mark.django_db
def test_sin_salto_visual_entre_lo_pre_renderizado_y_lo_vivo(navegador, datos_vivos):
    # 1) Sin Cloudin (el script ni siquiera carga): lo que trae el HTML.
    contexto, page, errores = _abrir(navegador, datos_vivos, con_runtime=False)
    page.wait_for_load_state("load")
    estatico = page.evaluate(FOTO)
    contexto.close()
    # 2) Con Cloudin respondiendo: lo que pinta el runtime con los datos vivos.
    contexto, page, errores = _abrir(navegador, datos_vivos)
    page.wait_for_function("() => document.documentElement.dataset.cloudinState === 'live'")
    vivo = page.evaluate(FOTO)
    contexto.close()
    assert errores == []
    estatico.pop("estado"), vivo.pop("estado")
    assert vivo == estatico
    # Y lo que se ve es lo de la semilla.
    platos = [p["key"] for c in vivo["categorias"] for p in c["platos"]]
    assert platos == ["hamburguesa-clasica", "hamburguesa-vegetariana", "limonada-de-coco", "jugo-natural"]
    assert vivo["categorias"][0]["platos"][0]["precio"] == "Desde $ 24.000"
    assert vivo["menus"] == [["menu-carta", "Carta"]]
    visibles = {ruta: texto for ruta, se_ve, texto, _ in vivo["negocio"] if se_ve}
    assert visibles["business.takeaway"] == "Pide y recoge" and "business.delivery" not in visibles
    assert visibles["business.payment_methods_text"] == "Pagos: Efectivo, Nequi y Tarjeta"
    assert "business.email_link" not in visibles and "business.facebook" not in visibles


@pytest.mark.django_db
def test_con_cloudin_caido_el_menu_se_ve_completo_y_sin_errores(navegador, datos_vivos):
    contexto, page, errores = _abrir(navegador, datos_vivos, estado_api=503)
    page.wait_for_function("() => document.documentElement.dataset.cloudinState === 'error'")
    platos = page.eval_on_selector_all(".dish", "ds => ds.map(d => d.dataset.cloudinKey)")
    contexto.close()
    assert errores == []
    assert platos == ["hamburguesa-clasica", "hamburguesa-vegetariana", "limonada-de-coco", "jugo-natural"]
