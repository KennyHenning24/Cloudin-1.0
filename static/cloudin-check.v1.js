/*! Cloudin · revisor del menú digital · cloudin-check.v1.js */
/*
 * ¿Este menú muestra lo que el restaurante cambia en su panel? Se abre con ?cloudin-check=1
 * en la dirección del menú (https://<menú>/?cloudin-check=1): el runtime cloudin-menu.v1.js
 * carga este archivo desde Cloudin.
 *
 * Sin guardar nada, le pasa al runtime cartas de prueba (Cloudin.render) y mira si la página
 * cambia: un plato y una categoría nuevos; un plato con otro nombre, precio, descripción y
 * foto; uno eliminado; uno agotado; todos los platos quitados (lo que siga en la página está
 * escrito a mano); otro nombre, frase, logo, WhatsApp, teléfono, dirección, horario y colores
 * del negocio. Al final vuelve a pintar la carta real y muestra el informe:
 * ✅ bien · ❌ hay que arreglarlo · ⚠️ revisar.
 *
 * Pruebas automáticas (Playwright): espera window.CloudinCheck.terminado y lee .aprobado (sin
 * ❌), .resultados ([{id, estado: "ok" | "falla" | "aviso", texto}]) y .texto (el informe).
 * Guía: CLAUDE-MENU-DIGITAL.md, sección 0.
 */
(() => {
  "use strict";
  const w = window, d = document;
  if (w.CloudinCheck) return;
  const resultados = [];
  const CK = (w.CloudinCheck = { version: 1, terminado: false, aprobado: false, resultados, texto: "" });
  let origen = "";
  try {
    origen = new URL(d.currentScript.src).origin;
  } catch (e) { /* cargado a mano sin src */ }
  const sello = Math.random().toString(36).slice(2, 7);
  const foto = (n) => `${origen}/static/img/cloudin-marca.png?cloudin-check=${n}-${sello}`;
  const copia = (x) => JSON.parse(JSON.stringify(x));
  const anotar = (id, estado, texto) => resultados.push({ id, estado, texto });
  const lista = (xs) => xs.slice(0, 8).map((x) => `«${x}»`).join(", ") + (xs.length > 8 ? ` y ${xs.length - 8} más` : "");

  // ------------------------------------------------------------ leer la página
  const norm = (t) => String(t ?? "").replace(/\s+/g, " ").trim().toLowerCase();
  const SALTAR = new Set(["SCRIPT", "STYLE", "NOSCRIPT", "TEMPLATE"]);
  // Elementos cuyo texto es exactamente `t` (el más interno): así «Sandwich 2 Quesos» no se
  // confunde con «Sandwich». El texto escondido con CSS (pestañas, acordeones) también cuenta.
  const conTexto = (t) => {
    const b = norm(t);
    if (!b) return [];
    return [...d.body.querySelectorAll("*")].filter((el) => {
      if (SALTAR.has(el.tagName)) return false;
      const tc = el.textContent;
      if (tc.length < b.length || tc.length > b.length * 3 + 40 || norm(tc) !== b) return false;
      return ![...el.children].some((h) => norm(h.textContent) === b);
    });
  };
  const hay = (t) => conTexto(t).length > 0;
  const textoPagina = () => {
    const partes = [], it = d.createTreeWalker(d.body, NodeFilter.SHOW_TEXT);
    for (let n = it.nextNode(); n; n = it.nextNode()) if (!SALTAR.has(n.parentElement?.tagName)) partes.push(n.data);
    return norm(partes.join(" "));
  };
  const contiene = (t) => textoPagina().includes(norm(t));
  const imagen = (url) => !!url && [...d.querySelectorAll("img")].some((i) => i.getAttribute("src") === url);
  const enlace = (url) => [...d.querySelectorAll("a[href]")].some((a) => a.getAttribute("href") === url);
  const enlaceA = (patron) => [...d.querySelectorAll("a[href]")].some((a) => patron.test(a.getAttribute("href")));

  const esperar = (cond, ms) => new Promise((listo) => {
    const inicio = Date.now();
    const mirar = () => {
      let v;
      try { v = cond(); } catch (e) { /* todavía no */ }
      if (v || Date.now() - inicio > ms) return listo(v);
      setTimeout(mirar, 200);
    };
    mirar();
  });

  // ------------------------------------------------------------ el informe en pantalla
  let sombra = null;
  function panel() {
    const host = d.createElement("div");
    host.id = "cloudin-check";
    sombra = host.attachShadow({ mode: "open" });
    sombra.innerHTML = `<style>
      .caja{position:fixed;left:12px;right:12px;bottom:12px;margin:0 auto;max-width:560px;max-height:78vh;overflow:auto;
        z-index:2147483647;background:#fff;color:#16181d;border-radius:16px;box-shadow:0 12px 40px rgba(0,0,0,.35);
        font:15px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;padding:16px 18px;text-align:left}
      .cab{display:flex;align-items:center;gap:8px;margin-bottom:6px}
      .cab strong{font-size:17px;flex:1}
      button{font:inherit;border:0;border-radius:10px;padding:8px 12px;cursor:pointer;background:#eef0f4;color:#16181d}
      button.fuerte{background:#16181d;color:#fff}
      .resumen{font-weight:600;margin:4px 0 10px}
      ul{list-style:none;margin:0;padding:0;display:grid;gap:6px}
      li{display:flex;gap:8px;padding:8px 10px;border-radius:10px;background:#f6f7f9}
      li.falla{background:#fdecec}li.aviso{background:#fff6e0}
      .pie{display:flex;gap:8px;justify-content:flex-end;margin-top:12px}
    </style>
    <section class="caja" role="dialog" aria-label="Revisión de Cloudin">
      <div class="cab"><strong>Revisión de Cloudin</strong><button type="button" data-cerrar aria-label="Cerrar">✕</button></div>
      <p class="resumen">Revisando tu menú…</p><ul></ul>
      <div class="pie"><button type="button" class="fuerte" data-copiar hidden>Copiar informe</button></div>
    </section>`;
    sombra.querySelector("[data-cerrar]").onclick = () => host.remove();
    sombra.querySelector("[data-copiar]").onclick = (ev) => {
      const boton = ev.currentTarget;
      const avisar = () => { boton.textContent = "Copiado"; setTimeout(() => { boton.textContent = "Copiar informe"; }, 1500); };
      if (navigator.clipboard) navigator.clipboard.writeText(CK.texto).then(avisar, () => prompt("Copia el informe:", CK.texto));
      else prompt("Copia el informe:", CK.texto);
    };
    // Fuera del <body>: el informe no cuenta como texto del menú en las pruebas.
    d.documentElement.appendChild(host);
  }
  const avance = (t) => { if (sombra) sombra.querySelector(".resumen").textContent = t; };

  // --------------------------------------------------------------------- pruebas
  async function revisar() {
    const C = w.CLOUDIN_CONFIG || {};
    if (!C.api) {
      anotar("conexion", "falla", "Falta el bloque de conexión (window.CLOUDIN_CONFIG con api). Pégalo desde el panel maestro → el restaurante → «Menú digital» → Copiar código.");
    }
    const R = await esperar(() => w.Cloudin, 5000);
    if (!R || typeof R.render !== "function") {
      anotar("runtime", "falla", "No carga cloudin-menu.v1.js desde el servidor Cloudin: la carta no puede salir del panel. Carga el runtime con el bloque de conexión (guía, sección 3.2).");
      return;
    }
    avance("Leyendo la carta de Cloudin (si el servidor estaba dormido, tarda cerca de un minuto)…");
    await esperar(() => R.state !== "static", 90000);
    if (!R.data) {
      anotar("carta", "falla", "No se pudo leer la carta de Cloudin. Abre la dirección de «api» (CLOUDIN_CONFIG) en el navegador: debe mostrar la carta en JSON.");
      return;
    }
    anotar("carta", "ok", R.state === "cached" ? "Lee la carta de Cloudin (la guardada en este teléfono)." : "Lee la carta de Cloudin.");
    if (!C.apiKey) anotar("apikey", "aviso", "Sin apiKey en CLOUDIN_CONFIG la carta queda solo para mirar: no se puede pedir desde la mesa.");
    const carrito = [...d.scripts].some((s) => /carrito\.js(\?|$)/.test(s.src));
    anotar("carrito", carrito ? "ok" : "aviso",
      carrito ? "Carga carrito.js: se puede pedir desde la mesa." : "No carga carrito.js: sin él no se puede pedir desde la mesa.");

    avance("Probando la carta con cambios de mentira (no se guarda nada)…");
    // El HTML tal como se publicó: data-cloudin-if borra el elemento de un dato vacío (p. ej.
    // el logo si no hay), y sin esto un logo bien conectado parecería escrito a mano.
    const fuente = await fetch(location.href, { cache: "no-store" }).then((r) => (r.ok ? r.text() : ""), () => "");
    const real = copia(R.data);
    const errores = [];
    const alFallar = (ev) => errores.push(ev.message || String(ev.reason || ev));
    w.addEventListener("error", alFallar);
    w.addEventListener("unhandledrejection", alFallar);
    try {
      pruebas(R, real, C, fuente);
    } finally {
      try { R.render(real); } catch (e) { /* la carta real ya se pintó una vez */ }
      w.removeEventListener("error", alFallar);
      w.removeEventListener("unhandledrejection", alFallar);
    }
    if (errores.length) {
      anotar("errores-js", "aviso", `El JavaScript de la página falló con la carta de prueba: ${lista([...new Set(errores)])}.`);
    }
  }

  function pruebas(R, real, C, fuente) {
    const pintar = (x) => R.render(x);
    // ¿La página muestra este dato desde Cloudin? (en el HTML publicado o en la página ahora)
    const enlazado = (ruta) => new RegExp(`data-cloudin-(field|src|href)=["']${ruta.replace(".", "\\.")}["']`).test(fuente)
      || !!d.querySelector(`[data-cloudin-field="${ruta}"],[data-cloudin-src="${ruta}"],[data-cloudin-href="${ruta}"]`);
    const raiz = d.querySelector('[data-cloudin="menu"]');
    const menuDe = (x) => (raiz && x.menus.find((m) => m.key == raiz.getAttribute("data-cloudin-menu"))) || x.menus[0];
    const plantilla = (n) => d.querySelector(`template[data-cloudin-template="${n}"]`);
    const falta = !raiz ? 'no hay ninguna zona data-cloudin="menu"'
      : !raiz.querySelector('[data-cloudin="categories"]') ? 'falta la zona data-cloudin="categories" dentro de la raíz'
      : !plantilla("category") ? 'falta <template data-cloudin-template="category">'
      : !plantilla("product") ? 'falta <template data-cloudin-template="product">'
      : !plantilla("category").content.querySelector('[data-cloudin="products"]') ? 'la plantilla category no tiene data-cloudin="products"'
      : "";
    const porque = falta ? ` (${falta}; guía, sección 4)` : "";

    const menu = menuDe(real);
    const visibles = (c) => (c.products || []).filter((p) => !(C.hideSoldOut && p.available === false));
    const disponibles = menu ? menu.categories.flatMap((c) => visibles(c).filter((q) => q.available !== false)
      .map((q) => ({ c, q }))) : [];
    if (!disponibles.length) {
      anotar("sin-platos", "aviso", "La carta no tiene platos disponibles para probar: agrega uno en el panel (Mi menú) y repite.");
      return;
    }
    const todos = real.menus.flatMap((m) => m.categories.flatMap((c) => c.products || []));
    const b0 = real.business || {};
    const otros = [...real.menus.flatMap((m) => m.categories.map((c) => c.name)), b0.name, b0.tagline, b0.description]
      .filter(Boolean).map(norm);
    // Un nombre «único» no está dentro de otro (así un plato quitado no se confunde con otro).
    const unico = (p) => {
      const n = norm(p.name);
      return n.length >= 3 && !todos.some((q) => q !== p && norm(q.name).includes(n)) && !otros.some((o) => o.includes(n));
    };
    const elegido = disponibles.find(({ q }) => unico(q) && hay(q.name)) || disponibles.find(({ q }) => unico(q))
      || disponibles[0];
    const cat = elegido.c, p = elegido.q;
    const buscar = (x) => {
      const c = menuDe(x).categories.find((k) => k.id === cat.id);
      return { c, q: c.products.find((q) => q.id === p.id) };
    };
    const estabaP = hay(p.name);
    const muestraFotos = todos.some((q) => imagen(q.image)) || d.querySelectorAll("main img, section img, article img").length >= 3;
    const muestraDescripciones = todos.some((q) => q.description && contiene(q.description));

    // 1. Un plato nuevo en una categoría que ya existe.
    const nuevo = {
      id: `cloudin-check-${sello}`, key: `cloudin-check-${sello}`, name: `Plato nuevo ${sello}`,
      description: `Descripción nueva ${sello}`, price: 12345, image: foto("nuevo"), available: true, featured: false,
      tags: [], tax: null, variants: [], modifier_groups: [],
    };
    let x = copia(real);
    buscar(x).c.products.push(nuevo);
    pintar(x);
    const aparecio = hay(nuevo.name);
    anotar("plato-nuevo", aparecio ? "ok" : "falla", aparecio ? "Un plato nuevo del panel aparece en el menú."
      : `Un plato nuevo del panel NO aparece: los platos están escritos a mano. Cada categoría debe pintar sus platos con <template data-cloudin-template="product"> dentro de data-cloudin="products"${porque}.`);

    // 2. Una categoría nueva, con su plato (y su enlace en la barra de categorías).
    const catNueva = {
      id: `cloudin-check-cat-${sello}`, key: `cloudin-check-${sello}`, name: `Categoría nueva ${sello}`,
      description: null, image: null,
      products: [{ ...nuevo, id: `${nuevo.id}-b`, key: `${nuevo.key}-b`, name: `Plato de la categoría nueva ${sello}`, image: null }],
    };
    x = copia(real);
    menuDe(x).categories.push(catNueva);
    pintar(x);
    const catOk = hay(catNueva.name) && hay(catNueva.products[0].name);
    anotar("categoria-nueva", catOk ? "ok" : "falla", catOk ? "Una categoría nueva del panel aparece con sus platos."
      : `Una categoría nueva del panel NO aparece: las categorías están escritas a mano. Usa <template data-cloudin-template="category"> dentro de data-cloudin="categories"${porque}.`);
    const barra = d.querySelector('[data-cloudin="category-nav"]');
    const nombresCat = real.menus.flatMap((m) => m.categories.map((c) => norm(c.name)));
    const barraAMano = [...d.querySelectorAll('a[href^="#"]')].filter((a) => !a.closest('[data-cloudin="category-nav"]')
      && nombresCat.includes(norm(a.textContent))).length >= 2;
    if (barra) {
      const ok = enlace(`#cat-${catNueva.key}`);
      anotar("barra", ok ? "ok" : "falla", ok ? "La barra de categorías sale de Cloudin."
        : 'La barra de categorías no muestra la categoría nueva: usa <template data-cloudin-template="category-link"> con data-cloudin-href="category.anchor".');
    } else if (barraAMano) {
      anotar("barra", "falla", 'La barra de categorías está escrita a mano: una categoría nueva no sale en ella. Usa data-cloudin="category-nav" con <template data-cloudin-template="category-link">.');
    }

    // 3. Cambiar nombre, precio, descripción y foto de un plato.
    x = copia(real);
    const cambiado = buscar(x).q;
    Object.assign(cambiado, {
      name: `Nombre cambiado ${sello}`, price: 54321, description: `Descripción cambiada ${sello}`,
      image: foto("cambio"), variants: [],
    });
    pintar(x);
    const sigueViejo = estabaP && hay(p.name);
    const nombreOk = hay(cambiado.name) && !sigueViejo;
    anotar("cambiar-nombre", nombreOk ? "ok" : "falla", nombreOk ? "Cambiar el nombre de un plato en el panel se ve en el menú."
      : sigueViejo ? `Cambiar el nombre de un plato NO se ve: «${p.name}» sigue escrito a mano en la página.`
      : 'Cambiar el nombre de un plato NO se ve: usa data-cloudin-field="product.name".');
    const precioOk = contiene("54.321");
    anotar("cambiar-precio", precioOk ? "ok" : "falla", precioOk ? "Cambiar el precio en el panel se ve en el menú."
      : 'Cambiar el precio en el panel NO se ve: usa data-cloudin-field="product.price" (ya viene escrito: «$ 24.000»).');
    const descOk = contiene(cambiado.description);
    anotar("cambiar-descripcion", descOk ? "ok" : muestraDescripciones ? "falla" : "aviso",
      descOk ? "Cambiar la descripción en el panel se ve en el menú."
      : muestraDescripciones ? 'Cambiar la descripción de un plato en el panel NO se ve: usa data-cloudin-field="product.description" (con data-cloudin-if).'
      : 'La descripción del plato no se muestra: si la quieres, usa data-cloudin-field="product.description" (con data-cloudin-if).');
    const fotoOk = imagen(cambiado.image);
    anotar("cambiar-foto", fotoOk ? "ok" : muestraFotos ? "falla" : "aviso", fotoOk ? "Cambiar la foto en el panel se ve en el menú."
      : muestraFotos ? 'Cambiar la foto de un plato en el panel NO se ve: las fotos están escritas a mano. Usa <img data-cloudin-if="product.image" data-cloudin-src="product.image">.'
      : 'El menú no muestra fotos de los platos: si las quieres, usa <img data-cloudin-if="product.image" data-cloudin-src="product.image">.');

    // 4. Eliminar un plato.
    x = copia(real);
    const lugar = buscar(x);
    lugar.c.products = lugar.c.products.filter((q) => q.id !== p.id);
    pintar(x);
    if (!estabaP) {
      anotar("eliminar", "aviso", `No se pudo probar eliminar: «${p.name}» no se ve en la página.`);
    } else {
      const sigue = hay(p.name);
      anotar("eliminar", sigue ? "falla" : "ok", sigue ? `Eliminar un plato en el panel NO se ve: «${p.name}» sigue escrito a mano en la página.`
        : "Un plato eliminado en el panel desaparece del menú.");
    }

    // 5. Agotar un plato.
    x = copia(real);
    buscar(x).q.available = false;
    pintar(x);
    let agotadoOk;
    if (C.hideSoldOut) {
      agotadoOk = !hay(p.name);
    } else {
      const porClave = [...d.querySelectorAll("[data-cloudin-key]")].find((el) => el.getAttribute("data-cloudin-key") === p.key);
      let tarjeta = porClave;
      if (!tarjeta) {
        tarjeta = conTexto(p.name)[0];
        for (let i = 0; tarjeta && i < 4; i++) tarjeta = tarjeta.parentElement;
      }
      agotadoOk = !!tarjeta && (tarjeta.getAttribute("data-available") === "false" || norm(tarjeta.textContent).includes("agotad"));
    }
    anotar("agotado", agotadoOk ? "ok" : "falla", agotadoOk ? "Marcar un plato agotado en el panel se ve en el menú."
      : 'Marcar agotado en el panel NO se ve: el runtime pone data-available="false" en la copia de la plantilla; muestra el aviso con data-cloudin-if="!product.available".');

    // 6. Todos los platos quitados: lo que siga en la página está escrito a mano.
    x = copia(real);
    x.menus.forEach((m) => m.categories.forEach((c) => { c.products = []; }));
    pintar(x);
    const aMano = [...new Set(todos.filter(unico).filter((q) => hay(q.name)).map((q) => q.name))];
    anotar("a-mano", aMano.length ? "falla" : "ok", aMano.length
      ? `${aMano.length === 1 ? "1 plato está escrito" : `${aMano.length} platos están escritos`} a mano en el HTML y no cambian desde el panel: ${lista(aMano)}. Bórralos: los pinta la plantilla.`
      : "Ningún plato está escrito a mano: todos salen de Cloudin.");

    // 7. Datos del negocio y colores (Personalizar).
    x = copia(real);
    const b = (x.business = x.business || {});
    b.contact = { ...(b.contact || {}) };
    b.social = { ...(b.social || {}) };
    Object.assign(b, { name: `Negocio ${sello}`, tagline: `Frase del panel ${sello}`, logo: foto("logo"), cover: foto("portada") });
    Object.assign(b.contact, { whatsapp: "+573009998877", phone: "+573009998877", address: `Calle del panel ${sello}` });
    b.social.instagram = `https://instagram.com/cloudincheck${sello}`;
    b.hours = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"].map((day) => ({ day, open: "01:23", close: "23:45" }));
    b.brand = { primary: "#0A7C66", secondary: "#7B2D8E", background: "#FBF7E4", text: "#20243A" };
    pintar(x);
    const c0 = b0.contact || {};
    // ✅ si se ve el dato de prueba o el HTML lo toma de Cloudin (vacío en el panel, su elemento
    // se quitó); ❌ si se ve el dato viejo escrito a mano; ⚠️ si el menú no lo muestra.
    const dato = (id, rutas, nuevoVisible, viejoVisible, que, arreglo) => {
      const unido = rutas.some(enlazado);
      const f = /^la /i.test(que), o = f ? "a" : "o", lo = f ? "la" : "lo";
      if (nuevoVisible) anotar(id, "ok", `${que} sale de Cloudin.`);
      else if (unido) anotar(id, "ok", `${que} sale de Cloudin (está vací${o} en el panel: llén${lo === "la" ? "ala" : "alo"} en Personalizar para que se vea).`);
      else if (viejoVisible) anotar(id, "falla", `${que} está escrit${o} a mano: cambiar${lo} en el panel NO cambia el menú. ${arreglo}`);
      else anotar(id, "aviso", `${que} no se muestra en el menú. Para mostrar${lo}: ${arreglo[0].toLowerCase()}${arreglo.slice(1)}`);
    };
    dato("negocio-nombre", ["business.name"], hay(b.name), !!b0.name && hay(b0.name),
      "El nombre del restaurante", 'Usa data-cloudin-field="business.name".');
    dato("negocio-frase", ["business.tagline"], hay(b.tagline), !!b0.tagline && hay(b0.tagline),
      "La frase corta", 'Usa data-cloudin-field="business.tagline" (con data-cloudin-if).');
    const logoAMano = !!d.querySelector("header img")
      || [...d.querySelectorAll("img")].some((i) => /logo/i.test(`${i.getAttribute("src")} ${i.alt} ${i.className}`));
    dato("negocio-logo", ["business.logo"], imagen(b.logo), logoAMano,
      "El logo", 'Usa <img data-cloudin-if="business.logo" data-cloudin-src="business.logo">.');
    dato("negocio-whatsapp", ["business.whatsapp_link", "business.whatsapp"], enlace("https://wa.me/573009998877"),
      enlaceA(/wa\.me|whatsapp/i), "El botón de WhatsApp",
      'Usa <a data-cloudin-if="business.whatsapp_link" data-cloudin-href="business.whatsapp_link">.');
    dato("negocio-telefono", ["business.phone_link", "business.phone"], enlace("tel:+573009998877") || hay("+573009998877"),
      enlaceA(/^tel:/i), "El teléfono", 'Usa data-cloudin-href="business.phone_link" y data-cloudin-field="business.phone".');
    dato("negocio-direccion", ["business.address"], contiene(b.contact.address), !!c0.address && contiene(c0.address),
      "La dirección", 'Usa data-cloudin-field="business.address" y data-cloudin-field="business.city".');
    dato("negocio-horario", ["business.hours_today"], contiene("01:23"), false,
      "El horario de hoy", 'Usa data-cloudin-field="business.hours_today" (con data-cloudin-if).');
    if (enlace(b.social.instagram) || enlaceA(/instagram\.com/i) || enlazado("business.instagram")) {
      dato("negocio-redes", ["business.instagram"], enlace(b.social.instagram), true,
        "El enlace de Instagram", 'Usa data-cloudin-href="business.instagram" (y facebook, tiktok) con data-cloudin-if.');
    }
    const buscados = { principal: "rgb(10, 124, 102)", secundario: "rgb(123, 45, 142)", fondo: "rgb(251, 247, 228)", texto: "rgb(32, 36, 58)" };
    const usados = new Set();
    for (const el of [d.documentElement, d.body, ...d.body.querySelectorAll("*")].slice(0, 5000)) {
      const s = getComputedStyle(el);
      const valores = [s.color, s.backgroundColor, s.borderTopColor, s.borderBottomColor, s.borderLeftColor, s.outlineColor,
        s.fill, s.stroke, s.backgroundImage, s.boxShadow, s.textDecorationColor];
      for (const [k, v] of Object.entries(buscados)) if (valores.some((y) => y && y.includes(v))) usados.add(k);
      if (usados.size === 4) break;
    }
    anotar("colores", usados.has("principal") ? "ok" : usados.size ? "aviso" : "falla",
      usados.has("principal") ? `Los colores de Personalizar se usan (${[...usados].join(", ")}).`
      : usados.size ? `Solo se usa el color ${[...usados].join(", ")} de Personalizar: usa también var(--cloudin-primary, …) en botones y precios.`
      : "Los colores de Personalizar NO se usan: el CSS tiene colores fijos. Escribe var(--cloudin-primary, #tu-color) (y --cloudin-secondary, --cloudin-background, --cloudin-text) donde van los colores de la marca.");
  }

  function terminar() {
    const orden = { falla: 0, aviso: 1, ok: 2 };
    resultados.sort((a, b) => orden[a.estado] - orden[b.estado]);
    const fallas = resultados.filter((r) => r.estado === "falla").length;
    CK.aprobado = fallas === 0;
    const icono = { ok: "✅", falla: "❌", aviso: "⚠️" };
    const resumen = CK.aprobado
      ? "✅ Tu menú está conectado: lo que cambies en el panel se verá aquí sin volver a publicarlo."
      : `❌ ${fallas === 1 ? "Hay 1 cosa" : `Hay ${fallas} cosas`} del panel que el menú no muestra. Copia este informe y pégaselo a Claude Code.`;
    CK.texto = [`Revisión de Cloudin · ${location.origin}${location.pathname} · ${new Date().toLocaleString("es-CO")}`, resumen,
      ...resultados.map((r) => `${icono[r.estado]} ${r.texto}`)].join("\n");
    CK.terminado = true;
    if (sombra) {
      sombra.querySelector(".resumen").textContent = resumen;
      const ul = sombra.querySelector("ul");
      for (const r of resultados) {
        const li = d.createElement("li");
        li.className = r.estado;
        li.textContent = `${icono[r.estado]} ${r.texto}`;
        ul.appendChild(li);
      }
      sombra.querySelector("[data-copiar]").hidden = false;
    }
    (CK.aprobado ? console.info : console.warn)(CK.texto);
    d.dispatchEvent(new CustomEvent("cloudin:check", { detail: CK }));
  }

  const iniciar = () => {
    panel();
    revisar().catch((e) => anotar("error", "falla", `La revisión no pudo terminar: ${e && e.message}`)).finally(terminar);
  };
  d.readyState === "loading" ? d.addEventListener("DOMContentLoaded", iniciar) : iniciar();
})();
