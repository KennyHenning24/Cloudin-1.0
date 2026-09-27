/*! Cloudin · carrito y pedido a la mesa · implementación de referencia (sin dependencias) */
/*
 * Se suma a un menú digital que ya pinta la carta con cloudin-menu.v1.js. Solo se
 * activa si la página se abrió desde el QR de una mesa (?mesa=<token>) y hay
 * `apiKey` en CLOUDIN_CONFIG; sin eso el menú queda solo para mirar.
 *
 * Qué hace (ver GUIA-MENU-DIGITAL.md):
 *  1. A cada plato disponible le pone un botón «Agregar» (con tamaños y adiciones).
 *  2. El carrito vive en Cloudin (PUT /api/v1/mesa/<token>/borrador/): todos los que
 *     escanearon el QR de la mesa ven el mismo y lo pueden editar.
 *  3. «Enviar pedido» (POST …/enviar/) lo manda a la cocina. Si la mesa estaba libre,
 *     ese pedido la ocupa. El precio lo calcula siempre Cloudin, nunca esta página.
 *  4. Cada 5 s consulta el estado (GET …/estado/): carrito, pedidos y en qué van.
 *     Si Cloudin dice `recibe_pedidos: false` (plan solo menú o solo meseros), no hay
 *     botones: la carta queda para mirar.
 */
(() => {
  "use strict";
  const C = window.CLOUDIN_CONFIG || {};
  const Q = new URLSearchParams(location.search);
  const TOKEN = Q.get("mesa");
  if (!C.api || !C.apiKey || !TOKEN) return;

  const SERVIDOR = new URL(C.api, location.href).origin;
  const BASE = `${SERVIDOR}/api/v1/mesa/${encodeURIComponent(TOKEN)}/`;
  const LLAVE_NOMBRE = "cloudin:nombre";
  const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const pesos = (n) => "$ " + Math.round(Number(n) || 0).toLocaleString("es-CO");
  const nombre = () => { try { return localStorage.getItem(LLAVE_NOMBRE) || ""; } catch (e) { return ""; } };

  let estado = null;      // lo último que respondió Cloudin: mesa, cuenta, borrador
  let productos = {};     // key del plato -> producto de la carta pública (con sus id)

  async function api(ruta, metodo = "GET", datos) {
    const r = await fetch(BASE + ruta, {
      method: metodo,
      headers: { "X-API-Key": C.apiKey, ...(datos ? { "Content-Type": "application/json" } : {}) },
      body: datos ? JSON.stringify(datos) : undefined,
    });
    const cuerpo = await r.json().catch(() => ({}));
    if (!r.ok) throw Object.assign(new Error(cuerpo.detail || "No se pudo completar."), { status: r.status, datos: cuerpo });
    return cuerpo;
  }

  // ------------------------------------------------------------------ interfaz
  const css = document.createElement("style");
  css.textContent = `
    .cl-agregar{margin-top:8px;align-self:flex-start;min-height:40px;padding:0 16px;border-radius:12px;border:0;
      font:inherit;font-weight:700;cursor:pointer;background:var(--cloudin-primary,#B3261E);color:#fff}
    .cl-barra{position:fixed;left:50%;bottom:16px;transform:translateX(-50%);z-index:20;display:flex;gap:10px;
      align-items:center;min-height:52px;padding:0 20px;border-radius:999px;border:0;font:inherit;font-weight:700;
      cursor:pointer;background:var(--cloudin-primary,#B3261E);color:#fff;box-shadow:0 8px 30px rgba(0,0,0,.35)}
    .cl-barra[hidden]{display:none}
    .cl-dlg{width:min(460px,calc(100% - 24px));border:0;border-radius:18px;padding:18px;color:inherit;
      background:var(--fondo,#1A1110)}
    .cl-dlg::backdrop{background:rgba(0,0,0,.6)}
    .cl-dlg h3{margin:0 0 10px}.cl-dlg fieldset{border:0;padding:0;margin:0 0 12px}
    .cl-dlg label{display:flex;gap:10px;align-items:center;padding:6px 0}
    .cl-dlg input[type=radio],.cl-dlg input[type=checkbox]{width:20px;height:20px;flex:none;margin:0}
    .cl-fila{display:flex;gap:8px;align-items:center;padding:8px 0;border-bottom:1px solid rgba(255,255,255,.12)}
    .cl-fila span:first-child{flex:1}.cl-fila button{min-width:34px;min-height:34px}
    .cl-acciones{display:flex;gap:8px;justify-content:flex-end;margin-top:14px}
    .cl-acciones button,#cl-nombre{min-height:40px;border-radius:10px;font:inherit}
    #cl-nombre{flex:1;min-width:0;padding:0 10px;box-sizing:border-box}
    .cl-aviso{margin:10px 0;padding:8px 12px;border-radius:10px;background:rgba(255,255,255,.08)}`;
  document.head.appendChild(css);

  const barra = Object.assign(document.createElement("button"), { className: "cl-barra", type: "button", hidden: true });
  const dlgCarrito = Object.assign(document.createElement("dialog"), { className: "cl-dlg" });
  const dlgOpciones = Object.assign(document.createElement("dialog"), { className: "cl-dlg" });
  document.body.append(barra, dlgCarrito, dlgOpciones);
  barra.addEventListener("click", () => { pintarCarrito(); dlgCarrito.showModal(); });

  function pintarBarra() {
    const items = estado?.borrador?.items || [];
    const n = items.reduce((s, i) => s + i.quantity, 0);
    const pedidos = estado?.cuenta?.pedidos?.length || 0;
    barra.hidden = !n && !pedidos;
    barra.textContent = n ? `Ver pedido (${n}) · ${pesos(estado.borrador.total)}`
      : `Mesa ${estado.mesa} · ${pedidos} ${pedidos === 1 ? "pedido" : "pedidos"}`;
  }

  function pintarCarrito(aviso = "") {
    const items = estado?.borrador?.items || [];
    const pedidos = estado?.cuenta?.pedidos || [];
    dlgCarrito.innerHTML = `
      <h3>Mesa ${esc(estado?.mesa)}</h3>
      ${aviso ? `<p class="cl-aviso">${esc(aviso)}</p>` : ""}
      ${items.length ? items.map((i, k) => `
        <div class="cl-fila"><span>${esc(i.name)}${i.by ? ` <small>· ${esc(i.by)}</small>` : ""}</span>
          <button type="button" data-menos="${k}" aria-label="Quitar uno">−</button><b>${i.quantity}</b>
          <button type="button" data-mas="${k}" aria-label="Agregar uno">+</button>
          <span>${pesos(i.unit_price * i.quantity)}</span></div>`).join("")
        : "<p>Todavía no hay nada en el pedido de la mesa.</p>"}
      ${items.length ? `<p><b>Total del pedido: ${pesos(estado.borrador.total)}</b></p>
        <label>Tu nombre <input id="cl-nombre" value="${esc(nombre())}" maxlength="60" placeholder="Para saber de quién es"></label>` : ""}
      ${pedidos.length ? `<h3>Ya pedido</h3>${pedidos.map((p) => `<div class="cl-fila"><span>#${p.id} · ${esc(p.estado_texto)}</span>
        <span>${pesos(p.total)}</span></div>`).join("")}` : ""}
      <div class="cl-acciones">
        <button type="button" data-cerrar>Seguir mirando</button>
        ${items.length ? `<button type="button" data-enviar>Enviar pedido</button>` : ""}
      </div>`;
  }

  dlgCarrito.addEventListener("click", async (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    if (b.hasAttribute("data-cerrar")) return dlgCarrito.close();
    const items = [...(estado?.borrador?.items || [])];
    try {
      if (b.dataset.mas || b.dataset.menos) {
        const k = Number(b.dataset.mas ?? b.dataset.menos);
        items[k] = { ...items[k], quantity: items[k].quantity + (b.dataset.mas ? 1 : -1) };
        await guardar(items.filter((i) => i.quantity > 0));
        pintarCarrito();
      } else if (b.hasAttribute("data-enviar")) {
        const quien = (document.getElementById("cl-nombre")?.value || "").trim();
        try { localStorage.setItem(LLAVE_NOMBRE, quien); } catch (er) { /* sin almacenamiento, igual se envía */ }
        b.disabled = true;
        estado = await api("enviar/", "POST", { by: quien });
        pintarBarra();
        pintarCarrito("¡Pedido enviado! La cocina ya lo tiene.");
      }
    } catch (er) {
      pintarCarrito(er.message);
    }
  });

  // ---------------------------------------------------------------- el carrito
  const mismaLinea = (a, b) => a.product === b.product && (a.variant || null) === (b.variant || null)
    && [...(a.options || [])].sort().join() === [...(b.options || [])].sort().join();

  /** Guarda el carrito compartido. Si otro de la mesa lo cambió justo antes (409),
   *  Cloudin responde el carrito al día y se vuelve a aplicar el cambio una vez. */
  async function guardar(items, cambio) {
    if (!estado) estado = await api("estado/");
    try {
      estado = await api("borrador/", "PUT", { items, version: estado.borrador.version });
    } catch (e) {
      if (e.status !== 409 || !cambio || !e.datos.borrador) throw e;
      estado = e.datos;
      estado = await api("borrador/", "PUT", { items: cambio(estado.borrador.items), version: estado.borrador.version });
    }
    pintarBarra();
  }

  async function agregar(linea) {
    const juntar = (actuales) => {
      const items = [...actuales];
      const igual = items.findIndex((i) => mismaLinea(i, linea));
      if (igual >= 0) items[igual] = { ...items[igual], quantity: items[igual].quantity + linea.quantity };
      else items.push(linea);
      return items;
    };
    if (!estado) estado = await api("estado/");
    await guardar(juntar(estado.borrador.items), juntar);
  }

  // ------------------------------------------------ tamaños y adiciones del plato
  async function elegir(p) {
    const grupos = p.modifier_groups || [];
    if (!p.variants.length && !grupos.length) return agregar({ product: p.id, quantity: 1, by: nombre() });
    dlgOpciones.innerHTML = `<form method="dialog"><h3>${esc(p.name)}</h3>
      ${p.variants.length ? `<fieldset><legend>Presentación</legend>
        <label><input type="radio" name="variant" value="" checked> ${esc(p.name)} · ${pesos(p.price)}</label>
        ${p.variants.map((v) => `<label><input type="radio" name="variant" value="${esc(v.id)}"> ${esc(v.name)} · ${pesos(v.price)}</label>`).join("")}
      </fieldset>` : ""}
      ${grupos.map((g) => `<fieldset data-min="${g.min}" data-max="${g.max ?? ""}" data-nombre="${esc(g.name)}">
        <legend>${esc(g.name)}${g.min ? " (obligatorio)" : ""}${g.max > 1 ? ` · hasta ${g.max}` : ""}</legend>
        ${g.options.map((o) => `<label><input type="${g.max === 1 ? "radio" : "checkbox"}" name="g-${esc(g.id)}" value="${esc(o.id)}">
          ${esc(o.name)}${o.price ? ` · +${pesos(o.price)}` : ""}</label>`).join("")}
      </fieldset>`).join("")}
      <p class="cl-aviso" data-error hidden></p>
      <div class="cl-acciones"><button value="cancelar">Cancelar</button><button value="ok">Agregar al pedido</button></div></form>`;
    dlgOpciones.showModal();
    dlgOpciones.querySelector("form").onsubmit = async (e) => {
      if (e.submitter?.value !== "ok") return;
      e.preventDefault();
      const form = dlgOpciones.querySelector("form");
      const error = form.querySelector("[data-error]");
      const opciones = [];
      for (const fs of form.querySelectorAll("fieldset[data-nombre]")) {
        const marcadas = [...fs.querySelectorAll("input:checked")].map((i) => i.value);
        if (marcadas.length < Number(fs.dataset.min || 0)) {
          error.hidden = false;
          error.textContent = `Elige ${fs.dataset.nombre}.`;
          return;
        }
        opciones.push(...marcadas);
      }
      const variante = form.querySelector('input[name="variant"]:checked')?.value || null;
      try {
        await agregar({ product: p.id, variant: variante, options: opciones, quantity: 1, by: nombre() });
        dlgOpciones.close();
      } catch (er) {
        error.hidden = false;
        error.textContent = er.message;
      }
    };
  }

  // ------------------------------------------------ enganchar la carta pintada
  function conocerProductos() {
    productos = {};
    for (const m of window.Cloudin?.data?.menus || [])
      for (const c of m.categories) for (const p of c.products) productos[p.key] = p;
  }

  function botones(raiz = document) {
    if (!estado) return;  // primero hay que saber si el restaurante recibe pedidos por el QR
    if (estado.recibe_pedidos === false) {  // solo menú o solo meseros: la carta queda para mirar
      document.querySelectorAll(".cl-agregar").forEach((b) => b.remove());
      return;
    }
    conocerProductos();
    raiz.querySelectorAll("[data-cloudin-key]").forEach((tarjeta) => {
      const p = productos[tarjeta.dataset.cloudinKey];
      const cuerpo = tarjeta.querySelector(".dish__body") || tarjeta;
      if (!p || !p.available || p.price == null || cuerpo.querySelector(".cl-agregar")) return;
      const b = Object.assign(document.createElement("button"), { type: "button", className: "cl-agregar", textContent: "Agregar" });
      b.addEventListener("click", () => elegir(p).catch((er) => alert(er.message)));
      cuerpo.appendChild(b);
    });
  }

  async function refrescar() {
    if (document.visibilityState !== "visible" || dlgOpciones.open) return;
    try {
      estado = await api("estado/");
      pintarBarra();
      if (window.Cloudin?.data) botones();
      if (dlgCarrito.open && !dlgCarrito.contains(document.activeElement?.closest("input"))) pintarCarrito();
    } catch (e) { /* sin señal: se reintenta en el siguiente ciclo */ }
  }

  document.addEventListener("cloudin:rendered", (e) => botones(e.detail?.root || document));
  document.addEventListener("cloudin:ready", () => botones());
  refrescar();
  setInterval(refrescar, 5000);
})();
