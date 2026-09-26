/* Cloudin · asistente de la primera vez (panel/duenio/bienvenida.html).
 * Paso 1: colores sugeridos del logo y muestra de la cabecera. Paso 3: ideas de categoría.
 * Paso 4: la foto recortada en el navegador viaja con el formulario.
 */
(function () {
  "use strict";
  const C = window.Cloudin;
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const forma = $("#form-paso");
  if (!forma) return;
  const campo = (n) => forma.elements[n];

  // ---------------------------------------------- paso 1: marca y colores
  const muestra = $("[data-muestra]");
  function pintarMuestra() {
    if (!muestra) return;
    const v = (n, defecto) => (/^#[0-9a-f]{6}$/i.test((campo(n) || {}).value || "") ? campo(n).value : defecto);
    muestra.style.setProperty("--m-fondo", v("color_background", "#FFFFFF"));
    muestra.style.setProperty("--m-texto", v("color_text", "#1D2029"));
    muestra.style.setProperty("--m-primario", v("color_primary", "#C2410C"));
    C.revisarContraste($("[data-contraste=texto]"), v("color_text", "#1D2029"), v("color_background", "#FFFFFF"));
  }
  forma.addEventListener("input", pintarMuestra);
  forma.addEventListener("cambio-color", pintarMuestra);
  pintarMuestra();

  function usarPaleta(p) {
    const campos = { color_primary: p.primary, color_secondary: p.secondary, color_background: p.background, color_text: p.text };
    Object.entries(campos).forEach(([n, v]) => {
      const i = campo(n);
      if (!i) return;
      i.value = v;
      i.dispatchEvent(new Event("input", { bubbles: true }));
    });
    pintarMuestra();
  }
  function sugerir(img, aplicar = true) {
    const caja = $("[data-sugeridos]");
    if (!caja || !C.coloresDeImagen) return;
    const paletas = C.coloresDeImagen(img);
    if (!paletas.length) return;
    const lista = $("[data-paletas]", caja);
    lista.innerHTML = "";
    paletas.forEach((p, i) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "paleta";
      b.setAttribute("aria-pressed", String(aplicar && i === 0));
      b.setAttribute("aria-label", `Combinación ${i + 1}: principal ${p.primary}, fondo ${p.background}`);
      b.innerHTML = [p.primary, p.secondary, p.background, p.text].map((c) => `<i style="background:${c}"></i>`).join("");
      b.addEventListener("click", () => {
        $$(".paleta", lista).forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
        usarPaleta(p);
      });
      lista.appendChild(b);
    });
    caja.hidden = false;
    if (aplicar) usarPaleta(paletas[0]);
  }
  const logo = $("#subir-logo");
  if (logo) {
    // Si ya había logo, se muestran las sugerencias sin cambiar los colores que tiene.
    const actual = $("img.vista", logo);
    if (actual && !actual.hidden && actual.getAttribute("src")) {
      if (actual.complete) sugerir(actual, false); else actual.addEventListener("load", () => sugerir(actual, false), { once: true });
    }
    logo.addEventListener("foto-subida", () => {
      const img = $("img.vista", logo);
      const logoMuestra = $(".muestra-logo", muestra);
      if (logoMuestra && img.src) logoMuestra.innerHTML = `<img src="${img.src}" alt="">`;
      if (img.complete) sugerir(img); else img.addEventListener("load", () => sugerir(img), { once: true });
    });
  }

  // ------------------------------------------------ paso 3: ideas de nombre
  $$("[data-sugerencia]").forEach((b) => b.addEventListener("click", () => {
    const i = campo("categoria");
    i.value = b.dataset.sugerencia;
    i.focus();
  }));

  // -------------------------------------- paso 4: la foto va con el formulario
  const archivo = $("#foto-archivo");
  if (archivo) {
    document.addEventListener("foto-lista", (ev) => {
      try {
        const dt = new DataTransfer();
        dt.items.add(ev.detail.foto);
        archivo.files = dt.files;
      } catch (e) { C.aviso("Este navegador no pudo adjuntar la foto. Súbela después desde Mi menú.", { tipo: "error" }); }
    });
  }

  // Sin nombre no se sigue (el servidor también lo revisa).
  forma.addEventListener("submit", (ev) => {
    const requerido = $$("[required]", forma).find((i) => !i.value.trim());
    if (requerido) {
      ev.preventDefault();
      requerido.setAttribute("aria-invalid", "true");
      requerido.focus();
      C.aviso("Completa este dato para seguir, o toca «Saltar por ahora».", { tipo: "error" });
      return;
    }
    const boton = $("button[type=submit]", forma);
    if (boton) boton.setAttribute("aria-busy", "true");
  });
})();
