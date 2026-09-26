/* Cloudin · vista previa en vivo, sobre el menú REAL del restaurante.
 *
 * Cloudin no tiene un menú propio: cada restaurante tiene su página (Tenant.menu_page)
 * con el runtime cloudin-menu.v1.js adentro. El panel la carga en un iframe con
 * ?cloudin-preview=1; el runtime avisa «cloudin:vista-lista» y desde ahí acepta (solo
 * del origen de Cloudin) los datos que el dueño está editando, sin guardar nada.
 *
 *   <iframe data-vista-previa src="https://x.pages.dev/menu.html?cloudin-preview=1"
 *           data-api="/api/public/<slug>/menu/?vista=panel">
 *   Cloudin.vistaPrevia(iframe).enviar({ producto, categoria, menu })   ← editor de producto
 *   Cloudin.vistaPrevia(iframe).enviar({ colores, negocio })            ← Personalizar
 *
 * El panel toma los datos guardados de la API, les aplica lo que se está editando y le
 * manda al sitio el menú completo (cloudin.menu/v1) para que lo pinte con sus plantillas.
 */
(function () {
  "use strict";
  const C = (window.Cloudin = window.Cloudin || {});
  const copia = (x) => JSON.parse(JSON.stringify(x));
  const COLOR = /^#[0-9a-f]{6}$/i;

  /* Los datos guardados + lo que se está editando = lo que el sitio debe pintar. */
  function combinar(base, m) {
    const d = copia(base);
    let foco = null;
    if (m.colores) {
      const c = m.colores;
      d.business.brand = {
        primary: COLOR.test(c.primario || "") ? c.primario : null,
        secondary: COLOR.test(c.secundario || "") ? c.secundario : null,
        background: COLOR.test(c.fondo || "") ? c.fondo : null,
        text: COLOR.test(c.texto || "") ? c.texto : null,
      };
    }
    if (m.negocio) {
      const n = m.negocio, b = d.business;
      ["tagline", "description", "logo", "cover"].forEach((k) => { if (k in n) b[k] = n[k]; });
      if (n.contact) Object.assign(b.contact, n.contact);
      if (n.social) Object.assign(b.social, n.social);
      if (n.hours) b.hours = n.hours;
    }
    if (m.producto) {
      let donde = null;
      d.menus.forEach((menu) => menu.categories.forEach((c) => {
        const i = c.products.findIndex((p) => p.id === m.producto.id);
        if (i >= 0) { donde = { categoria: c.id, i }; c.products.splice(i, 1); }
      }));
      let menu = d.menus.find((x) => x.key === m.menu) || d.menus[0];
      if (!menu) { menu = { id: "vista", key: m.menu || "carta", name: "Carta", description: null, categories: [] }; d.menus.push(menu); }
      let cat = menu.categories.find((c) => c.id === m.categoria.id);
      if (!cat) {
        cat = { id: m.categoria.id, key: m.categoria.key || "categoria", name: m.categoria.name || "Categoría",
                description: null, image: null, products: [] };
        menu.categories.unshift(cat);
      }
      cat.products.splice(donde && donde.categoria === cat.id ? donde.i : 0, 0, m.producto);
      foco = m.producto.key;
    }
    return { data: d, foco };
  }

  C.vistaPrevia = function (iframe) {
    if (!iframe || !iframe.getAttribute("src")) return { enviar() {} };
    if (iframe._vista) return iframe._vista;
    const destino = new URL(iframe.src, location.href).origin;
    let lista = false, base = null, pendiente = null;
    const mandar = () => {
      if (!lista || !base || !pendiente || !iframe.contentWindow) return;
      const { data, foco } = combinar(base, pendiente);
      iframe.contentWindow.postMessage({ tipo: "cloudin:vista", data, foco }, destino);
    };
    fetch(iframe.dataset.api, { credentials: "same-origin", cache: "no-cache" })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { base = d; mandar(); })
      .catch(() => {});
    window.addEventListener("message", (ev) => {
      if (ev.source !== iframe.contentWindow || ev.origin !== destino) return;
      if (ev.data && ev.data.tipo === "cloudin:vista-lista") { lista = true; mandar(); }
    });
    iframe._vista = { enviar(datos) { pendiente = datos; mandar(); } };
    return iframe._vista;
  };

  /* En el celular y la tablet la vista previa es una hoja que se abre con [data-abrir-vista]. */
  document.addEventListener("click", (ev) => {
    const abrir = ev.target.closest("[data-abrir-vista]");
    const cerrar = ev.target.closest("[data-cerrar-vista]");
    if (!abrir && !cerrar) return;
    const raiz = (abrir || cerrar).closest("dialog") || document;
    const vista = raiz.querySelector("[data-vista]") || document.querySelector("[data-vista]");
    if (!vista) return;
    const abierta = !!abrir;
    vista.classList.toggle("abierta", abierta);
    document.body.classList.toggle("vista-abierta", abierta);
    if (abierta) { const b = vista.querySelector("[data-cerrar-vista]"); if (b) b.focus(); }
  });
  document.addEventListener("keydown", (ev) => {
    if (ev.key !== "Escape") return;
    document.querySelectorAll("[data-vista].abierta").forEach((v) => v.classList.remove("abierta"));
    document.body.classList.remove("vista-abierta");
  });
})();
