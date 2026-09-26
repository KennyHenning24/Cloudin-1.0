/* Cloudin · ayudas comunes del panel (api, dinero, escHTML, tema, avisos, impresión).
   CSRF lo deja la plantilla base en window.CSRF. */
async function api(url, opts = {}) {
  const res = await fetch(url, {
    headers: {"Content-Type": "application/json", "X-CSRFToken": CSRF, ...(opts.headers||{})},
    credentials: "same-origin", ...opts
  });
  if (!res.ok) throw new Error(await res.text());
  return res.status === 204 ? null : res.json();
}
const money = n => "$" + Number(n).toLocaleString("es-CO", {maximumFractionDigits: 0});
/* Todo texto que venga de afuera (nombres de clientes, platos, notas) pasa por
   aquí antes de ir a innerHTML: así nadie puede meter código en el panel
   escribiendo HTML en un pedido. */
function escHTML(t) {
  return String(t ?? "").replace(/[&<>"']/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
}
function copiar(texto, boton) {
  navigator.clipboard.writeText(texto).then(() => {
    const antes = boton.textContent;
    boton.textContent = "Copiado";
    setTimeout(() => { boton.textContent = antes; }, 1500);
  });
}

/* ---------- tema claro / oscuro ---------- */
function ponerTema(t) {
  // "sistema" olvida la elección: el panel vuelve a seguir el tema del teléfono o del PC.
  const aplicar = () => {
    let tema = t;
    try {
      if (t === "sistema") localStorage.removeItem("cloudin-tema");
      else localStorage.setItem("cloudin-tema", t);
    } catch (e) {}
    if (t === "sistema") tema = window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches ? "oscuro" : "claro";
    document.documentElement.dataset.theme = tema;
    document.querySelectorAll("[data-tema]").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.tema === tema)));
    window.dispatchEvent(new CustomEvent("cambio-tema", {detail: tema}));
  };
  // Con View Transitions el cambio de tema se funde suavemente.
  if (document.startViewTransition && !matchMedia("(prefers-reduced-motion: reduce)").matches) {
    document.startViewTransition(aplicar);
  } else aplicar();
}
function temaActual() { return document.documentElement.dataset.theme || "claro"; }
/* Colores del tema para las gráficas (Chart.js no lee variables CSS). */
function colorTema(nombre) {
  return getComputedStyle(document.documentElement).getPropertyValue("--" + nombre).trim();
}

/* ---------- mensaje flotante ---------- */
let _toastT;
function avisar(texto, ms = 2600) {
  const t = document.getElementById("toast");
  if (!t) return;
  t.textContent = texto;
  t.classList.add("on");
  clearTimeout(_toastT);
  _toastT = setTimeout(() => t.classList.remove("on"), ms);
}

/* ---------- números que cuentan hasta su valor ---------- */
function contar(el, valor, formato = money, ms = 900) {
  const fin = Number(valor) || 0;
  if (matchMedia("(prefers-reduced-motion: reduce)").matches || !fin) { el.textContent = formato(fin); return; }
  const inicio = performance.now();
  const paso = ahora => {
    const p = Math.min(1, (ahora - inicio) / ms);
    const e = 1 - Math.pow(1 - p, 3);
    el.textContent = formato(Math.round(fin * e));
    if (p < 1) requestAnimationFrame(paso);
  };
  requestAnimationFrame(paso);
}
document.addEventListener("DOMContentLoaded", () => {
  // Montos: se escriben con puntos de miles mientras se teclea (10.000, 150.000).
  document.querySelectorAll("[data-plata]").forEach(inp => {
    inp.addEventListener("input", () => {
      const n = inp.value.replace(/\D/g, "");
      inp.value = n ? Number(n).toLocaleString("es-CO") : "";
    });
    const form = inp.form;
    if (form) form.addEventListener("submit", (e) => {
      const n = Number(inp.value.replace(/\D/g, "")) || 0;
      if (n < 10000) {
        e.preventDefault();
        avisar("La base de caja debe ser de mínimo $10.000.");
        inp.focus();
      }
    });
  });
  document.querySelectorAll("[data-contar]").forEach(el => {
    const f = el.dataset.formato === "numero" ? (n => Number(n).toLocaleString("es-CO")) : money;
    contar(el, el.dataset.contar, f);
  });
  document.querySelectorAll("[data-tema]").forEach(b => {
    b.setAttribute("aria-pressed", String(b.dataset.tema === temaActual()));
    b.addEventListener("click", () => ponerTema(b.dataset.tema));
  });
});

/* Impresión de comandas.
   Se hace en un iframe escondido para no abrir pestañas ni chocar con el
   bloqueador de pop-ups. Detalles que importan: el iframe no puede medir 0
   (Chrome no imprime marcos de tamaño cero) y la URL lleva un parámetro
   distinto cada vez, porque recargar la misma dirección no vuelve a
   disparar 'load'. */
/* El botón de imprimir recuerda cuántas veces salió la comanda:
   «Imprimir» → «Imprimido» → «Imprimido (1)» → «Imprimido (2)»…
   Se guarda en el servidor, así se ve igual en cualquier pantalla. */
function textoImpresion(n) {
  n = Number(n) || 0;
  return n === 0 ? "Imprimir" : n === 1 ? "Imprimido" : `Imprimido (${n - 1})`;
}
function botonImprimir(o, clases = "quiet sm") {
  const n = o.impresiones || 0;
  return `<button class="btn ${n ? "impreso" : ""} ${clases}" data-imprimir="${o.id}"
    onclick="event.stopPropagation(); imprimir(${o.id})"
    title="${n ? "Ya se imprimió; toca para imprimir otra vez" : "Imprimir la comanda"}">
    <svg class="ico" viewBox="0 0 24 24" style="width:15px;height:15px">${n
      ? '<path d="M5 12.5l4.5 4.5L19 7.5"/>'
      : '<path d="M6 9V3h12v6M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="7"/>'}</svg>
    ${textoImpresion(n)}</button>`;
}
function marcarImpreso(id, n) {
  document.querySelectorAll(`[data-imprimir="${id}"]`).forEach((b) => {
    const tmp = document.createElement("div");
    tmp.innerHTML = botonImprimir({id, impresiones: n}, [...b.classList]
      .filter((c) => !["btn", "impreso"].includes(c)).join(" "));
    b.replaceWith(tmp.firstElementChild);
  });
}
async function registrarImpresion(id) {
  try {
    const r = await api(`/api/v1/staff/orders/${id}/impreso/`, {method: "POST"});
    marcarImpreso(id, r.impresiones);
  } catch (e) { /* si falla el conteo, la comanda igual se imprimió */ }
}

function imprimirComanda(id) {
  let marco = document.getElementById("impresora-cloudin");
  if (!marco) {
    marco = document.createElement("iframe");
    marco.id = "impresora-cloudin";
    marco.title = "Impresión de comandas";
    marco.setAttribute("aria-hidden", "true");
    marco.style.cssText =
      "position:fixed;right:0;bottom:0;width:1px;height:1px;opacity:0;border:0;pointer-events:none";
    document.body.appendChild(marco);
  }
  const url = `/panel/comanda/${id}/imprimir/?t=${Date.now()}`;
  marco.onload = () => {
    let contado = false;
    const contar = () => { if (!contado) { contado = true; registrarImpresion(id); } };
    try {
      marco.contentWindow.addEventListener("afterprint", contar, {once: true});
      marco.contentWindow.focus();
      marco.contentWindow.print();
      setTimeout(contar, 300);
    } catch (e) {
      window.open(url, "_blank", "width=420,height=620");
      contar();
    }
  };
  marco.src = url;
}
const imprimir = imprimirComanda;

// Repinta solo si los datos cambiaron: evita que el sondeo haga parpadear
// la pantalla o robe el foco mientras alguien escribe.
function pintarSiCambia(el, html) {
  if (el.dataset.firma === html) return false;
  el.dataset.firma = html;
  el.innerHTML = html;
  return true;
}
