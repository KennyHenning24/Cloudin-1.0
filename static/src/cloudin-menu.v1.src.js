/*! Cloudin · runtime de menús v1 · cloudin.menu/v1 */
/*
 * Pinta un menú digital con los datos vivos de Cloudin sobre el HTML del sitio.
 * Este es el archivo LEGIBLE; el que se publica es static/cloudin-menu.v1.js
 * (minificado con `python manage.py build_runtime`; debe pesar menos de 8 KB).
 *
 * Qué hace (sección 5 del contrato):
 *  1. Pinta al instante desde la caché local (localStorage, clave cloudin:{slug}).
 *  2. Pide la API. El navegador revalida con el ETag (sin preflight CORS) y, si
 *     algo cambió, re-pinta los contenedores data-cloudin con las <template>.
 *  3. Si la API falla y no hay caché, no toca nada: queda el HTML pre-renderizado.
 *  4. Lee ?mesa= y lo expone en window.Cloudin.table.
 *  5. Pone data-cloudin-state = static | cached | live | error.
 *  6. Dispara cloudin:ready, cloudin:rendered (detail.root) y cloudin:error.
 *  7. Pone los colores del restaurante (business.brand) como variables CSS en <html>:
 *     --cloudin-primary, --cloudin-secondary, --cloudin-background, --cloudin-text.
 *     El sitio los usa así: color: var(--cloudin-primary, #B3261E).
 *  8. Vista previa del panel: con ?cloudin-preview=1 y dentro de un iframe, acepta
 *     (solo del origen de la API) los datos que el dueño está editando y los pinta.
 *  9. Con ?cloudin-check=1 carga el revisor de Cloudin (cloudin-check.v1.js): prueba con
 *     cartas de mentira si el menú muestra todo lo que cambia en el panel.
 * 10. Carta en vivo: mientras la página se ve, pregunta cada `live` segundos (15; 0 = nunca)
 *     y al volver a ella si la carta cambió. Sin cambios Cloudin responde 304 (sin datos) y
 *     no se repinta; con cambios (un agotado, un plato nuevo, otro precio) se repinta sola.
 */
((w, d) => {
  "use strict";
  const C = w.CLOUDIN_CONFIG || {};
  if (!C.api || w.Cloudin) return;

  const LLAVE = "cloudin:" + (C.restaurant || ""),
    TTL = (C.cacheTtl ?? 60) * 1e3,
    Q = new URLSearchParams(location.search),
    MESA = Q.get("mesa"),
    PREVIA = Q.has("cloudin-preview") && w.parent != w,
    ORIGEN = new URL(C.api, location.href).origin,
    DIAS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
    zona = (n) => '[data-cloudin="' + n + '"]',
    todos = (s, r = d) => [...r.querySelectorAll(s)],
    evento = (n, detail) => d.dispatchEvent(new CustomEvent("cloudin:" + n, { detail }));

  let etiquetas = {}, pintado = 0, avisado = 0, ultimo; // ultimo: ETag de lo último pintado

  const Cloudin = (w.Cloudin = {
    version: 1,
    table: MESA ? { token: MESA, number: /^\d+$/.test(MESA) ? +MESA : null } : null,
    data: null,
    state: "static",
    preview: PREVIA,
    render: (x) => pintar(x, "live"),
    refresh: () => cargar(1),
  });

  // ---------------------------------------------------------------- formatos
  // «$ 12.000»: símbolo, espacio, punto de miles, sin decimales (igual que en Python).
  const pesos = (n) => (n == null || n === "" ? "" : "$ " + String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, "."));

  // Hora de Colombia: siempre UTC−5 (no hay horario de verano).
  const ahora = () => {
    const t = new Date(Date.now() - 18e6);
    return [(t.getUTCDay() + 6) % 7, t.getUTCHours() * 60 + t.getUTCMinutes()];
  };
  const mins = (h) => h.split(":").reduce((a, b) => a * 60 + +b, 0);
  const tramos = (hs, dia) => (hs || []).filter((h) => h.day == DIAS[dia] && !h.closed && h.open);
  const hoy = (hs) => {
    if (!hs?.length) return "";
    const t = tramos(hs, ahora()[0]);
    return "Hoy: " + (t.length ? t.map((h) => h.open + " – " + h.close).join(" y ") : "cerrado");
  };
  const abierto = (hs) => {
    const [dia, m] = ahora();
    return (
      tramos(hs, dia).some(({ open, close }) => {
        const a = mins(open), c = mins(close);
        return m >= a && (a >= c || m < c);
      }) ||
      // un tramo de anoche que pasó la medianoche
      tramos(hs, (dia + 6) % 7).some(({ open, close }) => mins(close) <= mins(open) && m < mins(close))
    );
  };

  // ------------------------------------------------------- lo que ve el HTML
  const vNegocio = (n) => {
    const c = n.contact || {}, s = n.social || {}, wa = String(c.whatsapp || "").replace(/\D/g, "");
    return {
      ...s,
      name: n.name, tagline: n.tagline, description: n.description, logo: n.logo, cover: n.cover,
      address: c.address, city: c.city, email: c.email, maps_url: c.maps_url, phone: c.phone,
      phone_link: c.phone ? "tel:" + c.phone : "", whatsapp: c.whatsapp, whatsapp_link: wa ? "https://wa.me/" + wa : "",
      hours_today: hoy(n.hours), open_now: abierto(n.hours),
    };
  };
  const vCategoria = (c) => ({ ...c, products: 0, anchor: "#cat-" + c.key });
  const vProducto = (p) => {
    const vs = p.variants || [], ps = [p.price, ...vs.map((v) => v.price)].filter((x) => x != null);
    return {
      ...p,
      price: vs.length && ps.length ? "Desde " + pesos(Math.min(...ps)) : pesos(p.price),
      available: p.available !== false, featured: !!p.featured,
    };
  };
  const vMesa = () => ({ number: Cloudin.table?.number || "" });

  // -------------------------------------------------------------- plantillas
  // La <template data-cloudin-template="…"> más cercana: en el contenedor y luego hacia arriba.
  const molde = (nombres, el, tope) => {
    for (const n of nombres) {
      const s = 'template[data-cloudin-template="' + n + '"]';
      for (let e = el; e; e = e == tope ? 0 : e.parentElement) {
        const t = e.querySelector(s);
        if (t) return t;
      }
      const t = d.querySelector(s);
      if (t) return t;
    }
  };

  const valor = (ctx, ruta) => {
    const [r, c] = ruta.split(".");
    return ctx[r]?.[c];
  };
  const aplica = (ctx, ruta) => ruta.replace("!", "").split(".")[0] in ctx;
  const lleno = (v) => !(v == null || v === "" || v === false || v?.length === 0);
  const cada = (sel, raiz, fn) => {
    for (const el of [...(raiz.matches?.(sel) ? [raiz] : []), ...todos(sel, raiz)]) {
      const r = el.getAttribute(sel.slice(1, -1));
      if (aplica(fn.ctx, r)) fn(el, r, valor(fn.ctx, r.replace("!", "")));
    }
  };

  // Llena un nodo: primero quita lo que no aplica (data-cloudin-if), luego textos, src y href.
  // Solo toca rutas cuya raíz está en el contexto (el paso del negocio no toca productos).
  const llenar = (raiz, ctx) => {
    const f = (fn) => ((fn.ctx = ctx), fn);
    cada("[data-cloudin-if]", raiz, f((el, r, v) => (r[0] == "!" ? lleno(v) : !lleno(v)) && el.remove()));
    cada("[data-cloudin-field]", raiz, f((el, r, v) => (el.textContent = v ?? "")));
    cada("[data-cloudin-href]", raiz, f((el, r, v) => (v ? el.setAttribute("href", v) : el.removeAttribute("href"))));
    cada("[data-cloudin-src]", raiz, f((el, r, v) => {
      if (!v) return el.removeAttribute("src");
      el.setAttribute("src", v);
      if (!el.getAttribute("alt")) el.setAttribute("alt", valor(ctx, r.split(".")[0] + ".name") || "");
    }));
  };

  // Vacía el contenedor (menos sus <template>) y lo llena con un clon por ítem.
  const lista = (cont, nombres, items, armar, tope) => {
    if (!cont) return;
    const t = molde(nombres, cont, tope)?.content.firstElementChild;
    for (const n of [...cont.childNodes]) n.nodeName != "TEMPLATE" && n.remove();
    if (t)
      for (const item of items) {
        const [ctx, antes, despues] = armar(item), n = t.cloneNode(true);
        n.setAttribute("data-cloudin-key", item.key);
        antes?.(n);
        cont.appendChild(n);
        llenar(n, ctx);
        despues?.(n);
      }
  };

  const productos = (cont, ps, base, tope, nombres = ["product"]) =>
    lista(cont, nombres, ps, (p) => {
      const vp = vProducto(p), ctx = { ...base, product: vp };
      return [
        ctx,
        (n) => {
          n.setAttribute("data-available", vp.available);
          n.setAttribute("data-featured", vp.featured);
        },
        (n) => {
          lista(n.querySelector(zona("variants")), ["variant"], p.variants || [],
            (v) => [{ ...ctx, variant: { ...v, price: pesos(v.price) } }], n);
          lista(n.querySelector(zona("tags")), ["tag"], (p.tags || []).map((key) => ({ key, name: etiquetas[key] || key })),
            (tag) => [{ ...ctx, tag }], n);
        },
      ];
    }, tope);

  const visibles = (ps) => (ps || []).filter((p) => !(C.hideSoldOut && p.available === false));

  const pintarMenu = (raiz, x, base) => {
    const m = x.menus.find((m) => m.key == raiz.getAttribute("data-cloudin-menu")) || x.menus[0];
    if (!m) return;
    const cats = (m.categories || []).map((c) => ({ ...c, products: visibles(c.products) })).filter((c) => c.products.length),
      ctxDe = (c) => ({ ...base, category: vCategoria(c) });
    lista(raiz.querySelector(zona("category-nav")), ["category-link"], cats, (c) => [ctxDe(c)], raiz);
    lista(raiz.querySelector(zona("categories")), ["category"], cats, (c) => [
      ctxDe(c),
      (n) => (n.id = "cat-" + c.key),
      (n) => productos(n.querySelector(zona("products")), c.products, ctxDe(c), raiz),
    ], raiz);
  };

  const estado = (e) => {
    Cloudin.state = e;
    for (const el of [d.documentElement, ...todos(zona("menu"))]) el.setAttribute("data-cloudin-state", e);
  };

  const valido = (x) => x?.schema == "cloudin.menu/v1" && Array.isArray(x.menus);

  function pintar(x, origen) {
    if (!valido(x)) throw Error("menú inválido");
    etiquetas = {};
    for (const t of x.tags || []) etiquetas[t.key] = t.name;
    Cloudin.data = x;
    if (x.table) Cloudin.table = { token: MESA, ...Cloudin.table, number: x.table.number };
    const base = { business: vNegocio(x.business || {}), table: vMesa() };
    for (const raiz of todos(zona("menu"))) {
      pintarMenu(raiz, x, base);
      evento("rendered", { root: raiz });
    }
    for (const cont of todos(zona("featured"))) {
      const ps = x.menus.flatMap((m) => (m.categories || []).flatMap((c) => visibles(c.products))).filter((p) => p.featured);
      productos(cont, ps, base, cont, ["featured", "product"]);
      evento("rendered", { root: cont });
    }
    llenar(d.body, base); // datos del negocio en todo el sitio: header, footer, WhatsApp…
    // Colores del panel (Personalizar) como variables CSS: el sitio decide dónde usarlos.
    const marca = x.business?.brand || {}, raiz = d.documentElement.style;
    for (const k of ["primary", "secondary", "background", "text"])
      /^#[\da-f]{6}$/i.test(marca[k]) ? raiz.setProperty("--cloudin-" + k, marca[k]) : raiz.removeProperty("--cloudin-" + k);
    pintado = 1;
    estado(origen);
  }

  // ----------------------------------------------------------------- caché
  const leer = () => {
    try {
      const x = JSON.parse(localStorage.getItem(LLAVE));
      return valido(x?.d) ? x : null;
    } catch (e) {}
  };
  const guardar = (e, x) => {
    try {
      const { table, ...sinMesa } = x; // la mesa es de esta visita, no del menú
      localStorage.setItem(LLAVE, JSON.stringify({ e, t: Date.now(), d: sinMesa }));
    } catch (e) {}
  };
  const listo = () => avisado || ((avisado = 1), evento("ready", { state: Cloudin.state }));

  function cargar(forzar) {
    const c = leer();
    if (c && !pintado)
      try {
        pintar(c.d, "cached");
      } catch (e) {}
    if (c && !forzar && !MESA && Date.now() - c.t < TTL) return Promise.resolve(listo());
    // La vista previa del panel no cuenta como una visita al menú.
    const extra = [MESA && "table=" + encodeURIComponent(MESA), PREVIA && "vista=panel"].filter(Boolean).join("&");
    return fetch(C.api + (extra ? (C.api.includes("?") ? "&" : "?") + extra : ""),
      { cache: "no-cache", credentials: "omit" })
      .then((r) => {
        if (!r.ok) throw Error("HTTP " + r.status);
        const e = r.headers.get("ETag");
        if (e && e == ultimo) return estado("live"); // sin cambios desde lo último pintado
        if (c && e && e == c.e && pintado && !MESA) return (ultimo = e), guardar(e, c.d), estado("live");
        return r.json().then((x) => (pintar(x, "live"), (ultimo = e), guardar(e, x)));
      })
      .catch((error) => {
        pintado || estado("error"); // sin caché: queda el HTML pre-renderizado, intacto
        evento("error", { error });
      })
      .then(listo);
  }

  // --------------------------------------------------- vista previa del panel
  // El panel de Cloudin carga este sitio en un iframe (?cloudin-preview=1) y le manda
  // lo que el dueño está editando. Solo se acepta lo que llega del origen de la API.
  if (PREVIA) {
    w.addEventListener("message", (e) => {
      const m = e.data;
      if (e.origin != ORIGEN || m?.tipo != "cloudin:vista") return;
      try {
        pintar(m.data, "live");
      } catch (er) {}
      m.foco && d.querySelector('[data-cloudin="products"] [data-cloudin-key="' + CSS.escape(m.foco) + '"]')?.scrollIntoView({ block: "center" });
    });
    d.addEventListener("cloudin:ready", () => w.parent.postMessage({ tipo: "cloudin:vista-lista" }, ORIGEN));
  }

  // Revisión de la conexión (?cloudin-check=1): el revisor vive en Cloudin, junto al runtime.
  Q.has("cloudin-check") && d.head.append(Object.assign(d.createElement("script"), { src: ORIGEN + "/static/cloudin-check.v1.js" }));

  // Carta en vivo (no en la vista previa: ahí manda el panel). Solo con la página a la vista.
  const EN_VIVO = (C.live ?? 15) * 1e3,
    revisar = () => d.visibilityState == "visible" && cargar(1);
  if (EN_VIVO && !PREVIA) setInterval(revisar, EN_VIVO), d.addEventListener("visibilitychange", revisar);

  estado("static");
  d.readyState == "loading" ? d.addEventListener("DOMContentLoaded", () => cargar()) : cargar();
})(window, document);
