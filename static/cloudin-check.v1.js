/*! Cloudin · revisor del menú digital · cloudin-check.v1.js */
/*
 * ¿Este menú muestra lo que el restaurante cambia en su panel? Se abre con ?cloudin-check=1
 * en la dirección del menú (https://<menú>/?cloudin-check=1): el runtime cloudin-menu.v1.js
 * carga este archivo desde Cloudin.
 *
 * Sin guardar nada, le pasa al runtime cartas de prueba (Cloudin.render) y mira si la página
 * cambia. De Mi menú: un menú, una categoría y un plato nuevos; un plato con otro nombre,
 * precio, descripción y foto; uno eliminado; uno agotado; todos los platos quitados (lo que siga
 * en la página está escrito a mano). De Personalizar: nombre, frase, descripción, bienvenida,
 * logo, portada, WhatsApp, teléfono, correo, dirección, ciudad, mapa, horario, Instagram,
 * Facebook, TikTok, medios de pago, Recoger y Domicilio (encendidos y apagados) y los 4 colores.
 * Al final vuelve a pintar la carta real y muestra el informe:
 * ✅ bien · ❌ hay que arreglarlo · ⚠️ revisar.
 *
 * Pruebas automáticas (Playwright): espera window.CloudinCheck.terminado y lee .aprobado (sin
 * ❌), .resultados ([{id, estado: "ok" | "falla" | "aviso", texto}]) y .texto (el informe).
 * Guía: CLAUDE-MENU-DIGITAL.md, secciones 0 y 4.
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
  // Lo que el runtime escondió porque el dato está vacío o apagado (data-cloudin-if fuera de las
  // listas queda con display:none) no se ve. El resto del texto escondido con CSS (pestañas,
  // acordeones, ventanas) sí cuenta: el cliente lo ve al abrirlo.
  const oculto = (el) => !!el?.closest('[data-cloudin-if][style*="display: none"]');
  // Elementos cuyo texto es exactamente `t` (el más interno): así «Sandwich 2 Quesos» no se
  // confunde con «Sandwich».
  const conTexto = (t) => {
    const b = norm(t);
    if (!b) return [];
    return [...d.body.querySelectorAll("*")].filter((el) => {
      if (SALTAR.has(el.tagName)) return false;
      const tc = el.textContent;
      if (tc.length < b.length || tc.length > b.length * 3 + 40 || norm(tc) !== b) return false;
      return !oculto(el) && ![...el.children].some((h) => norm(h.textContent) === b);
    });
  };
  const hay = (t) => conTexto(t).length > 0;
  const textoPagina = () => {
    const partes = [], it = d.createTreeWalker(d.body, NodeFilter.SHOW_TEXT);
    for (let n = it.nextNode(); n; n = it.nextNode()) {
      const p = n.parentElement;
      if (p && !SALTAR.has(p.tagName) && !oculto(p)) partes.push(n.data);
    }
    return norm(partes.join(" "));
  };
  const contiene = (t) => textoPagina().includes(norm(t));
  const enlaces = () => [...d.querySelectorAll("a[href]")].filter((a) => !oculto(a));
  const enlace = (url) => enlaces().some((a) => a.getAttribute("href") === url);
  const enlaceA = (patron) => enlaces().some((a) => patron.test(a.getAttribute("href")));
  // Una foto se ve si su <img> tiene ese src y nada la tapa: con srcset o un <source> de
  // <picture> escritos a mano, el navegador muestra esos y no la de Cloudin.
  const tapada = (i) => i.hasAttribute("srcset") || !!i.closest("picture")?.querySelector("source[srcset]");
  const imgs = (url) => (url ? [...d.querySelectorAll("img")].filter((i) => i.getAttribute("src") === url && !oculto(i)) : []);
  const imagen = (url) => imgs(url).some((i) => !tapada(i));
  const imagenTapada = (url) => imgs(url).some(tapada);
  // …o como fondo (background-image: var(--cloudin-cover, …)), también en ::before y ::after.
  const fondo = (url) => !!url && [...d.body.querySelectorAll("*")].slice(0, 4000).some((el) =>
    [null, "::before", "::after"].some((p) => getComputedStyle(el, p).backgroundImage.includes(url)));

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
    const real = copia(R.data);
    const errores = [];
    const alFallar = (ev) => errores.push(ev.message || String(ev.reason || ev));
    w.addEventListener("error", alFallar);
    w.addEventListener("unhandledrejection", alFallar);
    try {
      pruebas(R, real, C);
    } finally {
      try { R.render(real); } catch (e) { /* la carta real ya se pintó una vez */ }
      w.removeEventListener("error", alFallar);
      w.removeEventListener("unhandledrejection", alFallar);
    }
    if (errores.length) {
      anotar("errores-js", "aviso", `El JavaScript de la página falló con la carta de prueba: ${lista([...new Set(errores)])}.`);
    }
  }

  function pruebas(R, real, C) {
    const pintar = (x) => R.render(x);
    real.menus = real.menus || [];
    // La carta vive en data-cloudin="menus" (todos los menús, con <template menu>) o, a la
    // antigua, en una raíz data-cloudin="menu" (un solo menú: uno nuevo no sale).
    const zonaMenus = d.querySelector('[data-cloudin="menus"]');
    const raiz = d.querySelector('[data-cloudin="menu"]');
    const visibles = (c) => (c.products || []).filter((p) => !(C.hideSoldOut && p.available === false));
    const conPlatos = (m) => (m.categories || []).some((c) => visibles(c).length);
    const menuDe = (x) => (raiz ? x.menus.find((m) => m.key == raiz.getAttribute("data-cloudin-menu")) || x.menus[0]
      : x.menus.find(conPlatos) || x.menus[0]);
    // También busca dentro de otras plantillas (la de category puede ir dentro de la de menu).
    const plantilla = (n, r = d) => {
      const t = r.querySelector(`template[data-cloudin-template="${n}"]`);
      if (t) return t;
      for (const o of r.querySelectorAll("template")) {
        const u = plantilla(n, o.content);
        if (u) return u;
      }
      return null;
    };
    const falta = !zonaMenus && !raiz ? 'no hay zona data-cloudin="menus"'
      : zonaMenus && !plantilla("menu") ? 'falta <template data-cloudin-template="menu"> dentro de data-cloudin="menus"'
      : zonaMenus && !plantilla("menu").content.querySelector('[data-cloudin="categories"]') ? 'la plantilla menu no tiene data-cloudin="categories"'
      : !zonaMenus && !raiz.querySelector('[data-cloudin="categories"]') ? 'falta la zona data-cloudin="categories" dentro de la raíz'
      : !plantilla("category") ? 'falta <template data-cloudin-template="category">'
      : !plantilla("product") ? 'falta <template data-cloudin-template="product">'
      : !plantilla("category").content.querySelector('[data-cloudin="products"]') ? 'la plantilla category no tiene data-cloudin="products"'
      : "";
    const porque = falta ? ` (${falta}; guía, sección 4)` : "";

    const todos = real.menus.flatMap((m) => (m.categories || []).flatMap((c) => c.products || []));
    const b0 = real.business || {};
    const otros = [...real.menus.flatMap((m) => [m.name, ...(m.categories || []).map((c) => c.name)]), b0.name, b0.tagline,
      b0.description].filter(Boolean).map(norm);
    // Un nombre «único» no está dentro de otro (así un plato quitado no se confunde con otro).
    const unico = (p) => {
      const n = norm(p.name);
      return n.length >= 3 && !todos.some((q) => q !== p && norm(q.name).includes(n)) && !otros.some((o) => o.includes(n));
    };
    const nuevo = {
      id: `cloudin-check-${sello}`, key: `cloudin-check-${sello}`, name: `Plato nuevo ${sello}`,
      description: `Descripción nueva ${sello}`, price: 12345, image: foto("nuevo"), available: true, featured: false,
      tags: [], tax: null, variants: [], modifier_groups: [],
    };
    let x;

    // 1. Un menú nuevo (Mi menú → Nuevo menú), con su categoría y su plato.
    const menuNuevo = {
      id: `cloudin-check-menu-${sello}`, key: `cloudin-check-${sello}`, name: `Menú nuevo ${sello}`, description: null,
      categories: [{
        id: `cloudin-check-cat-m-${sello}`, key: `cloudin-check-m-${sello}`, name: `Categoría del menú nuevo ${sello}`,
        description: null, image: null,
        products: [{ ...nuevo, id: `${nuevo.id}-m`, key: `${nuevo.key}-m`, name: `Plato del menú nuevo ${sello}`, image: null }],
      }],
    };
    x = copia(real);
    x.menus.push(menuNuevo);
    pintar(x);
    const menuSale = hay(menuNuevo.categories[0].products[0].name) && hay(menuNuevo.categories[0].name);
    const menuConNombre = hay(menuNuevo.name);
    anotar("menu-nuevo", menuSale && menuConNombre ? "ok" : "falla", menuSale && menuConNombre
      ? "Un menú nuevo del panel aparece con su nombre, sus categorías y sus platos."
      : menuSale ? 'Un menú nuevo del panel sale sin su nombre: ponle data-cloudin-field="menu.name" en <template data-cloudin-template="menu"> (y, si hay barra de menús, data-cloudin="menu-nav").'
      : `Un menú nuevo del panel (Mi menú → Nuevo menú) NO aparece: la carta muestra un solo menú fijo. Usa data-cloudin="menus" con <template data-cloudin-template="menu">, y dentro data-cloudin="categories"${porque}.`);

    // 2. Una categoría nueva, con su plato (y su enlace en la barra de categorías).
    const menu = menuDe(real);
    if (menu) {
      const catNueva = {
        id: `cloudin-check-cat-${sello}`, key: `cloudin-check-${sello}`, name: `Categoría nueva ${sello}`,
        description: null, image: null,
        products: [{ ...nuevo, id: `${nuevo.id}-b`, key: `${nuevo.key}-b`, name: `Plato de la categoría nueva ${sello}`, image: null }],
      };
      x = copia(real);
      menuDe(x).categories = [...(menuDe(x).categories || []), catNueva];
      pintar(x);
      const catOk = hay(catNueva.name) && hay(catNueva.products[0].name);
      anotar("categoria-nueva", catOk ? "ok" : "falla", catOk ? "Una categoría nueva del panel aparece con sus platos."
        : `Una categoría nueva del panel NO aparece: las categorías están escritas a mano. Usa <template data-cloudin-template="category"> dentro de data-cloudin="categories"${porque}.`);
      const barra = d.querySelector('[data-cloudin="category-nav"]');
      const nombresCat = real.menus.flatMap((m) => (m.categories || []).map((c) => norm(c.name)));
      const barraAMano = [...d.querySelectorAll('a[href^="#"]')].filter((a) => !a.closest('[data-cloudin="category-nav"]')
        && nombresCat.includes(norm(a.textContent))).length >= 2;
      if (barra) {
        const ok = enlace(`#cat-${catNueva.key}`);
        anotar("barra", ok ? "ok" : "falla", ok ? "La barra de categorías sale de Cloudin."
          : 'La barra de categorías no muestra la categoría nueva: usa <template data-cloudin-template="category-link"> con data-cloudin-href="category.anchor".');
      } else if (barraAMano) {
        anotar("barra", "falla", 'La barra de categorías está escrita a mano: una categoría nueva no sale en ella. Usa data-cloudin="category-nav" con <template data-cloudin-template="category-link">.');
      }
    }

    // 3 a 6: los platos. Hace falta uno disponible en la carta para probar.
    const disponibles = menu ? (menu.categories || []).flatMap((c) => visibles(c).filter((q) => q.available !== false)
      .map((q) => ({ c, q }))) : [];
    if (!disponibles.length) {
      anotar("sin-platos", "aviso", "La carta no tiene platos disponibles para probar cambios en los platos: agrega uno en el panel (Mi menú) y repite.");
    } else {
      platos(disponibles);
    }
    negocio();

    function platos(disponibles) {
      const elegido = disponibles.find(({ q }) => unico(q) && hay(q.name)) || disponibles.find(({ q }) => unico(q))
        || disponibles[0];
      const cat = elegido.c, p = elegido.q;
      const buscar = (y) => {
        const c = menuDe(y).categories.find((k) => k.id === cat.id);
        return { c, q: c.products.find((q) => q.id === p.id) };
      };
      const estabaP = hay(p.name);
      const muestraFotos = todos.some((q) => imagen(q.image)) || d.querySelectorAll("main img, section img, article img").length >= 3;
      const muestraDescripciones = todos.some((q) => q.description && contiene(q.description));

      // 3. Un plato nuevo en una categoría que ya existe.
      x = copia(real);
      buscar(x).c.products.push(nuevo);
      pintar(x);
      const aparecio = hay(nuevo.name);
      anotar("plato-nuevo", aparecio ? "ok" : "falla", aparecio ? "Un plato nuevo del panel aparece en el menú."
        : `Un plato nuevo del panel NO aparece: los platos están escritos a mano. Cada categoría debe pintar sus platos con <template data-cloudin-template="product"> dentro de data-cloudin="products"${porque}.`);

      // 4. Cambiar nombre, precio, descripción y foto de un plato.
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
      anotar("cambiar-foto", fotoOk ? "ok" : muestraFotos || imagenTapada(cambiado.image) ? "falla" : "aviso",
        fotoOk ? "Cambiar la foto en el panel se ve en el menú."
        : imagenTapada(cambiado.image) ? 'La foto de Cloudin queda tapada: el <img> de la plantilla tiene srcset o está en un <picture> con <source>. Quítalos: deja solo data-cloudin-src="product.image".'
        : muestraFotos ? 'Cambiar la foto de un plato en el panel NO se ve: las fotos están escritas a mano. Usa <img data-cloudin-if="product.image" data-cloudin-src="product.image">.'
        : 'El menú no muestra fotos de los platos: si las quieres, usa <img data-cloudin-if="product.image" data-cloudin-src="product.image">.');

      // 5. Eliminar un plato.
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

      // 6. Agotar un plato.
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

      // 7. Todos los platos quitados: lo que siga en la página está escrito a mano.
      x = copia(real);
      x.menus.forEach((m) => (m.categories || []).forEach((c) => { c.products = []; }));
      pintar(x);
      const aMano = [...new Set(todos.filter(unico).filter((q) => hay(q.name)).map((q) => q.name))];
      anotar("a-mano", aMano.length ? "falla" : "ok", aMano.length
        ? `${aMano.length === 1 ? "1 plato está escrito" : `${aMano.length} platos están escritos`} a mano en el HTML y no cambian desde el panel: ${lista(aMano)}. Bórralos: los pinta la plantilla.`
        : "Ningún plato está escrito a mano: todos salen de Cloudin.");
    }

    // 8. Personalizar: todo lo que el dueño cambia ahí tiene que verse en el menú. Si un dato
    //    queda vacío en el panel, su elemento se esconde solo (data-cloudin-if).
    function negocio() {
      x = copia(real);
      const b = (x.business = x.business || {});
      b.contact = { ...(b.contact || {}) };
      b.social = { ...(b.social || {}) };
      Object.assign(b, {
        name: `Negocio ${sello}`, tagline: `Frase del panel ${sello}`, description: `Descripción del negocio ${sello}`,
        welcome_message: `Bienvenida del panel ${sello}`, logo: foto("logo"), cover: foto("portada"),
        payment_methods: ["efectivo", "nequi"], payment_methods_text: `Medios de pago ${sello}`,
        services: { dine_in: true, takeaway: true, delivery: true },
      });
      Object.assign(b.contact, {
        whatsapp: "+573009998877", phone: "+573009998877", email: `hola${sello}@cloudin-check.co`,
        address: `Calle del panel ${sello}`, city: `Ciudad ${sello}`, maps_url: `https://maps.app.goo.gl/cloudin${sello}`,
      });
      Object.assign(b.social, {
        instagram: `https://instagram.com/cloudincheck${sello}`, facebook: `https://facebook.com/cloudincheck${sello}`,
        tiktok: `https://tiktok.com/@cloudincheck${sello}`,
      });
      b.hours = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"].map((day) => ({ day, open: "01:23", close: "23:45" }));
      b.brand = { primary: "#0A7C66", secondary: "#7B2D8E", background: "#FBF7E4", text: "#20243A" };
      pintar(x);
      const c0 = b0.contact || {};
      // ✅ si se ve el dato de prueba; ❌ si sigue el viejo escrito a mano o si no se muestra.
      const dato = (id, seVe, viejoVisible, que, arreglo) => {
        const f = /^las? /i.test(que), pl = /^l[oa]s /i.test(que);
        const o = (f ? "a" : "o") + (pl ? "s" : ""), lo = (f ? "la" : "lo") + (pl ? "s" : ""), esta = pl ? "están" : "está";
        if (seVe) anotar(id, "ok", `${que} sale${pl ? "n" : ""} de Cloudin.`);
        else if (viejoVisible) anotar(id, "falla", `${que} ${esta} escrit${o} a mano: cambiar${lo} en Personalizar NO cambia el menú. ${arreglo}`);
        else anotar(id, "falla", `${que} no se ve${pl ? "n" : ""} en el menú: si el restaurante ${lo} cambia en Personalizar, no pasa nada. ${arreglo}`);
      };
      dato("negocio-nombre", hay(b.name), !!b0.name && hay(b0.name),
        "El nombre del restaurante", 'Usa data-cloudin-field="business.name".');
      dato("negocio-frase", contiene(b.tagline), !!b0.tagline && contiene(b0.tagline),
        "La frase corta", 'Usa data-cloudin-field="business.tagline" (con data-cloudin-if).');
      dato("negocio-descripcion", contiene(b.description), !!b0.description && contiene(b0.description),
        "La descripción del negocio", 'Usa data-cloudin-field="business.description" (con data-cloudin-if), p. ej. en «Nosotros».');
      dato("negocio-bienvenida", contiene(b.welcome_message), !!b0.welcome_message && contiene(b0.welcome_message),
        "El mensaje de bienvenida", 'Usa data-cloudin-field="business.welcome_message" (con data-cloudin-if), p. ej. arriba de la carta.');
      const logoAMano = !!d.querySelector("header img")
        || [...d.querySelectorAll("img")].some((i) => /logo/i.test(`${i.getAttribute("src")} ${i.alt} ${i.className}`));
      if (imagenTapada(b.logo) && !imagen(b.logo)) {
        anotar("negocio-logo", "falla", 'El logo de Cloudin queda tapado: su <img> tiene srcset o está en un <picture> con <source>. Quítalos: deja solo data-cloudin-src="business.logo".');
      } else {
        dato("negocio-logo", imagen(b.logo), logoAMano, "El logo", 'Usa <img data-cloudin-if="business.logo" data-cloudin-src="business.logo">.');
      }
      if (imagenTapada(b.cover) && !imagen(b.cover) && !fondo(b.cover)) {
        anotar("negocio-portada", "falla", 'La portada de Cloudin queda tapada: su <img> tiene srcset o está en un <picture> con <source>. Quítalos: deja solo data-cloudin-src="business.cover".');
      } else {
        dato("negocio-portada", imagen(b.cover) || fondo(b.cover), false, "La portada",
          'Usa <img data-cloudin-if="business.cover" data-cloudin-src="business.cover"> o, si es un fondo, background-image: var(--cloudin-cover, url(tu-portada.jpg)).');
      }
      dato("negocio-whatsapp", enlace("https://wa.me/573009998877"), enlaceA(/wa\.me|whatsapp/i), "El botón de WhatsApp",
        'Usa <a data-cloudin-if="business.whatsapp_link" data-cloudin-href="business.whatsapp_link">.');
      dato("negocio-telefono", enlace("tel:+573009998877") || hay("+573009998877"), enlaceA(/^tel:/i), "El teléfono",
        'Usa data-cloudin-href="business.phone_link" y data-cloudin-field="business.phone" (con data-cloudin-if).');
      dato("negocio-correo", enlace(`mailto:${b.contact.email}`) || contiene(b.contact.email),
        enlaceA(/^mailto:/i) || (!!c0.email && contiene(c0.email)), "El correo",
        'Usa <a data-cloudin-if="business.email_link" data-cloudin-href="business.email_link"><span data-cloudin-field="business.email"></span></a>.');
      dato("negocio-direccion", contiene(b.contact.address), !!c0.address && contiene(c0.address),
        "La dirección", 'Usa data-cloudin-field="business.address" (con data-cloudin-if).');
      dato("negocio-ciudad", contiene(b.contact.city), !!c0.city && contiene(c0.city),
        "La ciudad", 'Usa data-cloudin-field="business.city" (con data-cloudin-if), junto a la dirección.');
      dato("negocio-mapa", enlace(b.contact.maps_url), enlaceA(/maps\.app\.goo\.gl|goo\.gl\/maps|google\.[a-z.]+\/maps|maps\.google\./i),
        "El enlace de Google Maps", 'Usa <a data-cloudin-if="business.maps_url" data-cloudin-href="business.maps_url">Cómo llegar</a>.');
      dato("negocio-horario", contiene("01:23"), false,
        "El horario de hoy", 'Usa data-cloudin-field="business.hours_today" (con data-cloudin-if).');
      for (const [k, nombre, patron] of [["instagram", "Instagram", /instagram\.com/i], ["facebook", "Facebook", /facebook\.com|fb\.com/i],
        ["tiktok", "TikTok", /tiktok\.com/i]]) {
        dato(`negocio-${k}`, enlace(b.social[k]), enlaceA(patron), `El enlace de ${nombre}`,
          `Usa <a data-cloudin-if="business.${k}" data-cloudin-href="business.${k}">${nombre}</a>.`);
      }
      dato("negocio-pagos", contiene(b.payment_methods_text), /\bnequi\b|\bdaviplata\b|\befectivo\b|\btransferencia\b/i.test(textoPagina()),
        "Los medios de pago", 'Usa data-cloudin-field="business.payment_methods_text" (con data-cloudin-if): viene escrito, «Efectivo, Nequi y Tarjeta».');

      // Los 4 colores: en el estilo calculado de la página o en su CSS (p. ej. solo en :hover).
      const buscados = { principal: "rgb(10, 124, 102)", secundario: "rgb(123, 45, 142)", fondo: "rgb(251, 247, 228)", texto: "rgb(32, 36, 58)" };
      const variables = { principal: "primary", secundario: "secondary", fondo: "background", texto: "text" };
      const usados = new Set();
      for (const el of [d.documentElement, d.body, ...d.body.querySelectorAll("*")].slice(0, 5000)) {
        const s = getComputedStyle(el);
        const valores = [s.color, s.backgroundColor, s.borderTopColor, s.borderBottomColor, s.borderLeftColor, s.outlineColor,
          s.fill, s.stroke, s.backgroundImage, s.boxShadow, s.textDecorationColor];
        for (const [k, v] of Object.entries(buscados)) if (valores.some((y) => y && y.includes(v))) usados.add(k);
        if (usados.size === 4) break;
      }
      let css = [...d.body.querySelectorAll("[style]")].map((e) => e.getAttribute("style")).join("\n");
      for (const hoja of d.styleSheets) {
        try { css += [...hoja.cssRules].map((r) => r.cssText).join("\n"); } catch (e) { /* hoja de otro dominio */ }
      }
      for (const [k, v] of Object.entries(variables)) if (css.includes(`var(--cloudin-${v}`)) usados.add(k);
      const faltan = Object.keys(buscados).filter((k) => !usados.has(k));
      const ayuda = "Escribe var(--cloudin-primary, #tu-color) en botones y precios, var(--cloudin-secondary, …) en detalles y títulos, var(--cloudin-background, …) en el fondo y var(--cloudin-text, …) en el texto.";
      anotar("colores", faltan.length ? "falla" : "ok", !faltan.length
        ? "Los 4 colores de Personalizar se usan (principal, secundario, fondo y texto)."
        : usados.size ? `Solo se usa${usados.size > 1 ? "n" : ""} el color ${[...usados].join(", ")} de Personalizar; cambiar ${faltan.join(", ")} no hace nada. ${ayuda}`
        : `Los colores de Personalizar NO se usan: el CSS tiene colores fijos. ${ayuda}`);

      // Recoger y Domicilio: encendidos se ofrecen; apagados en Personalizar, desaparecen. Se
      // prueba sin platos: lo que diga «domicilio» sin data-cloudin-if está escrito a mano.
      const SERVICIOS = [["takeaway", "Recoger", /recog|para llevar/], ["delivery", "Domicilio", /domicilio/]];
      x = copia(real);
      x.menus.forEach((m) => (m.categories || []).forEach((c) => { c.products = []; }));
      x.business = { ...b, services: { dine_in: true, takeaway: false, delivery: false } };
      pintar(x);
      const apagados = textoPagina();
      x.business.services = { dine_in: true, takeaway: true, delivery: true };
      pintar(x);
      const encendidos = textoPagina();
      for (const [k, nombre, patron] of SERVICIOS) {
        const ruta = `business.${k}`;
        const unido = [...d.querySelectorAll(`[data-cloudin-if="${ruta}"]`)].some((el) => !oculto(el));
        if (patron.test(apagados)) {
          anotar(`servicio-${k}`, "falla", `«${nombre}» sigue en el menú aunque el restaurante lo apague en Personalizar: está escrito a mano. Ponlo dentro de un elemento con data-cloudin-if="${ruta}".`);
        } else if (unido || patron.test(encendidos)) {
          anotar(`servicio-${k}`, "ok", `«${nombre}» se ofrece si está encendido en Personalizar y desaparece si lo apagan.`);
        } else {
          anotar(`servicio-${k}`, "falla", `El menú no dice si hay «${nombre}»: agrega un aviso o botón con data-cloudin-if="${ruta}" (se ve si está encendido en Personalizar y se esconde si lo apagan).`);
        }
      }
    }
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
