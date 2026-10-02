/* Cloudin · asistente de la primera vez (panel/duenio/bienvenida.html).
 * Paso 2: ideas de categoría. Paso 3: la foto recortada en el navegador viaja con el formulario.
 */
(function () {
  "use strict";
  const C = window.Cloudin;
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const forma = $("#form-paso");
  if (!forma) return;
  const campo = (n) => forma.elements[n];

  // ------------------------------------------------ paso 2: ideas de nombre
  $$("[data-sugerencia]").forEach((b) => b.addEventListener("click", () => {
    const i = campo("categoria");
    i.value = b.dataset.sugerencia;
    i.focus();
  }));

  // -------------------------------------- paso 3: la foto va con el formulario
  const archivo = $("#foto-archivo");
  if (archivo) {
    document.addEventListener("foto-lista", (ev) => {
      try {
        const dt = new DataTransfer();
        dt.items.add(ev.detail.foto);
        archivo.files = dt.files;
      } catch (e) { C.aviso("Este navegador no pudo adjuntar la foto. Súbela después desde Personalizar.", { tipo: "error" }); }
    });
  }

  // Sin nombre no se sigue (el servidor también lo revisa).
  forma.addEventListener("submit", async (ev) => {
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
    // La foto del plato que se prepara viaja con este paso: se espera a que esté y se
    // vuelve a enviar (sin esperar se perdía en un celular lento).
    if (C.fotoEnCamino && C.fotoEnCamino(document)) {
      ev.preventDefault();
      await C.fotosPendientes(document);
      forma.requestSubmit ? forma.requestSubmit(ev.submitter || undefined) : forma.submit();
    }
  });
})();
