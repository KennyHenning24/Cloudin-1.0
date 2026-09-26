/* Cloudin · vista previa en vivo del menú.
 *
 * <iframe data-vista-previa src="/m/<slug>/?vista=panel"> carga el menú de respaldo del
 * restaurante (con su runtime y sus colores). El panel le manda por postMessage lo que se
 * está editando y el menú se vuelve a pintar con Cloudin.render(), sin guardar nada:
 *   Cloudin.vistaPrevia(iframe).enviar({ producto, categoria, menu })   ← editor de producto
 *   Cloudin.vistaPrevia(iframe).enviar({ colores, negocio })            ← Personalizar
 * Solo se aceptan mensajes del mismo origen.
 */
(function () {
  "use strict";
  const C = (window.Cloudin = window.Cloudin || {});

  C.vistaPrevia = function (iframe) {
    if (!iframe) return { enviar() {} };
    if (iframe._vista) return iframe._vista;
    let lista = false, pendiente = null;
    const mandar = () => {
      if (lista && pendiente && iframe.contentWindow) {
        iframe.contentWindow.postMessage({ tipo: "cloudin:vista", ...pendiente }, location.origin);
      }
    };
    window.addEventListener("message", (ev) => {
      if (ev.origin !== location.origin || ev.source !== iframe.contentWindow) return;
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
