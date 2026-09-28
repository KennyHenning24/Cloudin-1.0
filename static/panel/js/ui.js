/* Cloudin · componentes del panel (docs/DISENO.md, guía viva en /panel/design-system/).
 *
 * JavaScript sin dependencias. Todo cuelga de window.Cloudin:
 *   Cloudin.pedir(url, {metodo, datos, archivo, alProgreso})  → JSON o Error con .detalle humano
 *   Cloudin.aviso(texto, {accion, alHacer, tipo, ms})         → toast («Deshacer»)
 *   Cloudin.pesos(12000)                                     → "$ 12.000"
 *   Cloudin.abrir(dialogo) / Cloudin.cerrar(dialogo)          → modal, bottom sheet o drawer
 *   Cloudin.confirmar(texto, {titulo, boton})                 → «¿Seguro?»: promesa true/false
 *   Cloudin.enCola(url, opciones)                             → reintenta al volver la conexión
 * Y se enganchan solos por atributos: [data-abrir], [data-cerrar], [role=tablist],
 * details.desplegable, [data-precio], .color, form[data-avisar-cambios].
 */
(function () {
  "use strict";
  const C = (window.Cloudin = window.Cloudin || {});
  const $$ = (sel, raiz = document) => [...raiz.querySelectorAll(sel)];

  // ------------------------------------------------------------------ dinero
  C.pesos = (n) => (n === null || n === undefined || n === "" ? "" :
    "$ " + String(Math.round(Number(n))).replace(/\B(?=(\d{3})+(?!\d))/g, "."));
  C.digitos = (texto) => String(texto ?? "").replace(/\D/g, "");

  // ---------------------------------------------------------------- pedidos
  /* Errores en lenguaje humano: el servidor responde {"detail": "..."} o
     {"campo": ["..."]}; nunca se muestran trazas ni códigos. */
  function mensajeDe(cuerpo, estado) {
    if (cuerpo && typeof cuerpo === "object") {
      if (cuerpo.detail) return String(cuerpo.detail);
      const primero = Object.values(cuerpo)[0];
      if (Array.isArray(primero) && primero.length) return String(primero[0]);
      if (typeof primero === "string") return primero;
    }
    if (estado === 403) return "No tienes permiso para hacer esto. Pídeselo al dueño del restaurante.";
    if (estado >= 500) return "Algo falló de nuestro lado. Intenta de nuevo en un momento.";
    return "No se pudo guardar. Revisa los datos e intenta de nuevo.";
  }

  C.pedir = function (url, { metodo = "GET", datos, archivo, campoArchivo = "file", alProgreso } = {}) {
    if (!navigator.onLine && metodo !== "GET") {
      const e = new Error("Sin conexión");
      e.detalle = "No hay internet. Guardaremos el cambio cuando vuelva la conexión.";
      e.sinConexion = true;
      return Promise.reject(e);
    }
    if (archivo) {
      // Con archivo se usa XMLHttpRequest para poder mostrar el avance.
      return new Promise((resolver, rechazar) => {
        const xhr = new XMLHttpRequest();
        const forma = new FormData();
        forma.append(campoArchivo, archivo, archivo.name || "foto.webp");
        xhr.open(metodo === "GET" ? "POST" : metodo, url);
        xhr.setRequestHeader("X-CSRFToken", window.CSRF || "");
        xhr.upload.onprogress = (ev) => alProgreso && ev.lengthComputable && alProgreso(ev.loaded / ev.total);
        xhr.onload = () => {
          let cuerpo = null;
          try { cuerpo = JSON.parse(xhr.responseText); } catch (e) { /* sin cuerpo */ }
          if (xhr.status >= 200 && xhr.status < 300) return resolver(cuerpo);
          const e = new Error("HTTP " + xhr.status);
          e.estado = xhr.status;
          e.detalle = mensajeDe(cuerpo, xhr.status);
          rechazar(e);
        };
        xhr.onerror = () => { const e = new Error("red"); e.detalle = "Se cortó la conexión. Intenta de nuevo."; rechazar(e); };
        xhr.send(forma);
      });
    }
    return fetch(url, {
      method: metodo,
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": window.CSRF || "" },
      body: datos === undefined ? undefined : JSON.stringify(datos),
    }).then(async (r) => {
      const cuerpo = r.status === 204 ? null : await r.json().catch(() => null);
      if (r.ok) return cuerpo;
      const e = new Error("HTTP " + r.status);
      e.estado = r.status;
      e.cuerpo = cuerpo;
      e.codigo = cuerpo && cuerpo.code;
      e.detalle = mensajeDe(cuerpo, r.status);
      throw e;
    }, () => {
      const e = new Error("red");
      e.detalle = "Se cortó la conexión. Intenta de nuevo.";
      e.sinConexion = !navigator.onLine;
      throw e;
    });
  };

  // ------------------------------------------------ avisos (toast con acción)
  C.aviso = function (texto, { accion = "", alHacer = null, tipo = "", ms = 5000 } = {}) {
    const zona = document.getElementById("avisos");
    if (!zona) return;
    const el = document.createElement("div");
    el.className = "aviso-flotante" + (tipo ? " " + tipo : "");
    el.setAttribute("role", tipo === "error" ? "alert" : "status");
    const t = document.createElement("span");
    t.className = "texto";
    t.textContent = texto;
    el.appendChild(t);
    let cerrado = false;
    const cerrar = () => { if (!cerrado) { cerrado = true; el.remove(); } };
    if (accion && alHacer) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "accion";
      b.textContent = accion;
      b.addEventListener("click", () => { cerrar(); alHacer(); });
      el.appendChild(b);
    }
    zona.appendChild(el);
    while (zona.children.length > 3) zona.firstElementChild.remove();
    setTimeout(cerrar, ms);
    return cerrar;
  };

  /* Un aviso para la PRÓXIMA pantalla (después de guardar y volver a la lista).
     Con `deshacer: {url, metodo, datos}` el aviso ofrece «Deshacer». */
  const PENDIENTE = "cloudin:aviso";
  C.avisoPendiente = function (texto, { deshacer = null, tipo = "" } = {}) {
    try { sessionStorage.setItem(PENDIENTE, JSON.stringify({ texto, deshacer, tipo })); } catch (e) { /* privado */ }
  };
  function mostrarPendiente() {
    let a = null;
    try { a = JSON.parse(sessionStorage.getItem(PENDIENTE)); sessionStorage.removeItem(PENDIENTE); } catch (e) { return; }
    if (!a || !a.texto) return;
    if (!a.deshacer) return C.aviso(a.texto, { tipo: a.tipo, ms: 6000 });
    C.aviso(a.texto, {
      accion: "Deshacer", ms: 8000,
      alHacer: () => C.pedir(a.deshacer.url, { metodo: a.deshacer.metodo || "POST", datos: a.deshacer.datos })
        .then(() => { C.avisoPendiente("Listo, lo devolvimos."); location.reload(); })
        .catch((e) => C.aviso(e.detalle, { tipo: "error" })),
    });
  }

  // --------------------------------------------- modal, hoja y cajón lateral
  let ultimoFoco = null;
  C.abrir = function (dialogo) {
    if (typeof dialogo === "string") dialogo = document.getElementById(dialogo);
    if (!dialogo || dialogo.open) return;
    ultimoFoco = document.activeElement;
    dialogo.showModal();
    const primero = dialogo.querySelector("[autofocus], input:not([type=hidden]), select, textarea, button:not(.cierre)");
    if (primero) primero.focus();
  };
  C.cerrar = function (dialogo) {
    if (typeof dialogo === "string") dialogo = document.getElementById(dialogo);
    if (dialogo && dialogo.open) dialogo.close();
  };

  /* «¿Seguro?» antes de algo que el cliente nota (eliminar, archivar). Resuelve true solo si
     se toca el botón de confirmar; Cancelar, Escape o tocar afuera resuelven false. Usa el
     <dialog id="dialogo-confirmar"> de la página o lo crea (el editor de producto no lo trae). */
  C.confirmar = function (texto, { titulo = "¿Seguro?", boton = "Sí, continuar" } = {}) {
    let d = document.getElementById("dialogo-confirmar");
    if (!d) {
      d = document.createElement("dialog");
      d.id = "dialogo-confirmar";
      d.setAttribute("aria-labelledby", "t-dialogo-confirmar");
      d.innerHTML = `<form method="dialog">
        <h2 id="t-dialogo-confirmar"></h2>
        <p id="confirmar-texto"></p>
        <div class="acciones-dialogo"><button type="button" class="btn fantasma" data-cerrar>Cancelar</button>
          <button class="btn peligro" type="submit"></button></div></form>`;
      document.body.appendChild(d);
    }
    d.querySelector("#t-dialogo-confirmar").textContent = titulo;
    d.querySelector("#confirmar-texto").textContent = texto;
    d.querySelector("button[type=submit]").textContent = boton;
    return new Promise((resolver) => {
      let si = false;
      d.querySelector("form").onsubmit = () => { si = true; };
      d.addEventListener("close", () => resolver(si), { once: true });
      C.abrir(d);
    });
  };
  document.addEventListener("click", (ev) => {
    const abrir = ev.target.closest("[data-abrir]");
    if (abrir) { ev.preventDefault(); C.abrir(abrir.dataset.abrir); return; }
    const cerrar = ev.target.closest("[data-cerrar]");
    if (cerrar) { C.cerrar(cerrar.closest("dialog")); return; }
    // Clic en el fondo oscuro (fuera del cuadro) cierra.
    if (ev.target.tagName === "DIALOG" && ev.target.open) {
      const r = ev.target.getBoundingClientRect();
      if (ev.clientX < r.left || ev.clientX > r.right || ev.clientY < r.top || ev.clientY > r.bottom) ev.target.close();
    }
    // Los menús desplegables se cierran al tocar afuera.
    $$("details.desplegable[open]").forEach((d) => { if (!d.contains(ev.target)) d.open = false; });
  });
  document.addEventListener("close", (ev) => {
    if (ev.target.tagName === "DIALOG" && ultimoFoco && document.contains(ultimoFoco)) ultimoFoco.focus();
  }, true);
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") $$("details.desplegable[open]").forEach((d) => { d.open = false; d.querySelector("summary").focus(); });
  });

  // ------------------------------------------------------------- pestañas
  function engancharPestanas(lista) {
    const tabs = $$('[role="tab"]', lista);
    const elegir = (tab, enfocar) => {
      tabs.forEach((t) => {
        const si = t === tab;
        t.setAttribute("aria-selected", String(si));
        t.tabIndex = si ? 0 : -1;
        const panel = t.getAttribute("aria-controls") && document.getElementById(t.getAttribute("aria-controls"));
        if (panel) panel.hidden = !si;
      });
      if (enfocar) tab.focus();
      lista.dispatchEvent(new CustomEvent("cambio-pestana", { detail: { tab }, bubbles: true }));
    };
    tabs.forEach((t, i) => {
      t.tabIndex = t.getAttribute("aria-selected") === "true" ? 0 : -1;
      t.addEventListener("click", () => elegir(t));
      t.addEventListener("keydown", (ev) => {
        const pasos = { ArrowRight: 1, ArrowLeft: -1, Home: -i, End: tabs.length - 1 - i };
        if (ev.key in pasos) { ev.preventDefault(); elegir(tabs[(i + pasos[ev.key] + tabs.length) % tabs.length], true); }
      });
    });
  }

  // ------------------------------------------ PriceInput: «$ 25.000» al teclear
  function engancharPrecio(input) {
    input.setAttribute("inputmode", "numeric");
    input.setAttribute("autocomplete", "off");
    const pintar = () => {
      const n = C.digitos(input.value).replace(/^0+(?=\d)/, "").slice(0, 9);
      input.dataset.valor = n;
      input.value = n ? C.pesos(n) : "";
    };
    input.addEventListener("input", pintar);
    pintar();
    const forma = input.form;
    if (forma && input.name) {
      // Al enviar un formulario normal viaja el número limpio (25000).
      forma.addEventListener("submit", () => { input.value = input.dataset.valor || ""; });
    }
  }
  C.valorPrecio = (input) => (input.dataset.valor === "" || input.dataset.valor === undefined ? null : Number(input.dataset.valor));

  // --------------------------------------- ColorPicker con aviso de contraste
  function luminancia(hex) {
    const c = hex.replace("#", "").match(/../g).map((x) => parseInt(x, 16) / 255)
      .map((v) => (v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4)));
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
  }
  C.contraste = function (a, b) {
    const [l1, l2] = [luminancia(a), luminancia(b)].sort((x, y) => y - x);
    return (l1 + 0.05) / (l2 + 0.05);
  };
  function engancharColor(caja) {
    const rueda = caja.querySelector("input[type=color]");
    const texto = caja.querySelector("input[type=text]");
    if (!rueda || !texto) return;
    const valido = (v) => /^#[0-9a-f]{6}$/i.test(v);
    rueda.addEventListener("input", () => { texto.value = rueda.value.toUpperCase(); caja.dispatchEvent(new Event("cambio-color", { bubbles: true })); });
    texto.addEventListener("input", () => {
      let v = texto.value.trim();
      if (v && v[0] !== "#") v = "#" + v;
      if (valido(v)) { rueda.value = v; caja.dispatchEvent(new Event("cambio-color", { bubbles: true })); }
      texto.setAttribute("aria-invalid", String(!!v && !valido(v)));
    });
  }
  /* Revisa si el texto se lee sobre el fondo: pinta el aviso en [data-contraste]. */
  C.revisarContraste = function (aviso, colorTexto, colorFondo) {
    if (!aviso || !/^#[0-9a-f]{6}$/i.test(colorTexto) || !/^#[0-9a-f]{6}$/i.test(colorFondo)) return;
    const r = C.contraste(colorTexto, colorFondo);
    const bien = r >= 4.5;
    aviso.className = "contraste " + (bien ? "bien" : "mal");
    aviso.textContent = bien ? "El texto se lee bien sobre el fondo" :
      "El texto casi no se lee sobre ese fondo: prueba un color más " + (luminancia(colorFondo) > 0.4 ? "oscuro" : "claro");
  };

  // ------------------------------------------------ cambios sin guardar
  function engancharAvisoDeCambios(forma) {
    let sucio = false;
    forma.addEventListener("input", () => { sucio = true; forma.dataset.sucio = "1"; });
    forma.addEventListener("submit", () => { sucio = false; });
    forma.limpiar = () => { sucio = false; delete forma.dataset.sucio; };
    window.addEventListener("beforeunload", (ev) => { if (sucio) { ev.preventDefault(); ev.returnValue = ""; } });
  }

  // --------------------------------- sin conexión: aviso y cola de cambios
  const COLA = "cloudin:cola";
  const leerCola = () => { try { return JSON.parse(localStorage.getItem(COLA)) || []; } catch (e) { return []; } };
  const guardarCola = (c) => { try { localStorage.setItem(COLA, JSON.stringify(c.slice(-50))); } catch (e) { /* lleno */ } };
  /* Cambios rápidos (agotado, precio) que no se pudieron enviar: se reintentan al volver
     la conexión, en orden. Solo para acciones idempotentes. */
  C.enCola = function (url, opciones) {
    const cola = leerCola();
    cola.push({ url, opciones, t: Date.now() });
    guardarCola(cola);
  };
  async function vaciarCola() {
    const cola = leerCola();
    if (!cola.length || !navigator.onLine) return;
    guardarCola([]);
    let fallidos = 0;
    for (const item of cola) {
      try { await C.pedir(item.url, item.opciones); } catch (e) { fallidos++; }
    }
    C.aviso(fallidos ? `Volvió la conexión. ${fallidos} cambio(s) no se pudieron guardar: revísalos.` :
      "Volvió la conexión: tus cambios ya están guardados.", { tipo: fallidos ? "error" : "" });
    document.dispatchEvent(new CustomEvent("cloudin:sincronizado"));
  }
  function estadoConexion() {
    document.documentElement.classList.toggle("desconectado", !navigator.onLine);
    if (navigator.onLine) vaciarCola();
  }
  window.addEventListener("online", estadoConexion);
  window.addEventListener("offline", estadoConexion);

  // --------------------------------------------------------- tema claro / oscuro
  /* Si la persona no eligió tema, el panel sigue al de su sistema en vivo. */
  if (window.matchMedia) {
    matchMedia("(prefers-color-scheme: dark)").addEventListener("change", (ev) => {
      let elegido = null;
      try { elegido = localStorage.getItem("cloudin-tema"); } catch (e) { /* privado */ }
      if (!elegido) document.documentElement.dataset.theme = ev.matches ? "oscuro" : "claro";
    });
  }

  // --------------------------------------------- contador de caracteres
  function engancharContador(marca) {
    const campo = document.getElementById(marca.dataset.contadorDe);
    if (!campo) return;
    const tope = Number(campo.getAttribute("maxlength")) || 0;
    const pintar = () => { marca.textContent = campo.value.length + (tope ? "/" + tope : ""); };
    campo.addEventListener("input", pintar);
    pintar();
  }

  // ------------------------------------- riel de la tablet: se despliega completo
  document.addEventListener("click", (ev) => {
    if (!ev.target.closest("[data-riel]")) return;
    const abierto = document.body.classList.toggle("riel-abierto");
    $$("button[data-riel]").forEach((b) => b.setAttribute("aria-expanded", String(abierto)));
  });

  // ------------------------------------------------ atajos de teclado (PC)
  /* «/» busca y «N» crea un producto. Nunca mientras se escribe en un campo. */
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") document.body.classList.remove("riel-abierto");
    if (ev.ctrlKey || ev.metaKey || ev.altKey || ev.defaultPrevented) return;
    const t = ev.target;
    if (t.closest("input, textarea, select, [contenteditable=true], dialog[open]")) return;
    if (ev.key === "/") {
      const buscar = document.getElementById("buscar");
      if (buscar) { ev.preventDefault(); buscar.focus(); buscar.select(); }
      return;
    }
    const atajo = document.querySelector(`[data-atajo="${CSS.escape(ev.key.toLowerCase())}"]`);
    if (atajo && atajo.offsetParent !== null) { ev.preventDefault(); atajo.click(); }
  });

  // ------------------------------------------------------------- arranque
  C.enganchar = function (raiz = document) {
    $$('[role="tablist"]', raiz).forEach((l) => { if (!l.dataset.listo && !l.matches("nav")) { l.dataset.listo = 1; engancharPestanas(l); } });
    $$("[data-precio]", raiz).forEach((i) => { if (!i.dataset.listo) { i.dataset.listo = 1; engancharPrecio(i); } });
    $$(".color", raiz).forEach((c) => { if (!c.dataset.listo) { c.dataset.listo = 1; engancharColor(c); } });
    $$("form[data-avisar-cambios]", raiz).forEach((f) => { if (!f.dataset.listo) { f.dataset.listo = 1; engancharAvisoDeCambios(f); } });
    $$("[data-contador-de]", raiz).forEach((m) => { if (!m.dataset.listo) { m.dataset.listo = 1; engancharContador(m); } });
  };
  document.addEventListener("DOMContentLoaded", () => { C.enganchar(); estadoConexion(); mostrarPendiente(); });
})();
