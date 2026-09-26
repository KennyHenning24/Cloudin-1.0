/* Cloudin · reordenar con arrastrar y soltar (SortableJS) o con flechas ↑ ↓.
 *
 * <ul data-ordenable="products"> <li data-id="<uuid>"> <span class="asa">…</span> … </li> </ul>
 * - El asa (.asa) se arrastra con el dedo o el mouse (SortableJS, static/vendor).
 * - En el celular también hay botones [data-mover="arriba"|"abajo"].
 * - Al soltar se guarda el orden en POST /api/v1/staff/catalog/reorder/; si falla, vuelve atrás.
 */
(function () {
  "use strict";
  const C = (window.Cloudin = window.Cloudin || {});
  const URL_ORDEN = "/api/v1/staff/catalog/reorder/";

  const ids = (lista) => [...lista.children].filter((el) => el.dataset.id).map((el) => el.dataset.id);

  async function guardar(lista, antes) {
    try {
      await C.pedir(URL_ORDEN, { metodo: "POST", datos: { kind: lista.dataset.ordenable, ids: ids(lista) } });
      lista.dispatchEvent(new CustomEvent("orden-guardado", { bubbles: true }));
    } catch (e) {
      // Vuelve al orden anterior: la pantalla nunca muestra algo que no quedó guardado.
      antes.forEach((id) => { const el = lista.querySelector(`[data-id="${CSS.escape(id)}"]`); if (el) lista.appendChild(el); });
      C.aviso(e.detalle || "No se pudo guardar el orden.", { tipo: "error" });
    }
  }

  function mover(item, direccion) {
    const lista = item.parentElement;
    const antes = ids(lista);
    const vecino = direccion === "arriba" ? item.previousElementSibling : item.nextElementSibling;
    if (!vecino || !vecino.dataset.id) return;
    if (direccion === "arriba") lista.insertBefore(item, vecino); else lista.insertBefore(vecino, item);
    item.querySelector(`[data-mover="${direccion}"]`)?.focus();
    guardar(lista, antes);
  }

  C.engancharOrden = function (raiz = document) {
    raiz.querySelectorAll("[data-ordenable]").forEach((lista) => {
      if (lista.dataset.ordenListo) return;
      lista.dataset.ordenListo = "1";
      let antes = [];
      // Listas anidadas (categorías con sus productos): cada una con su asa (data-asa).
      const asa = lista.dataset.asa || ".asa";
      if (window.Sortable) {
        window.Sortable.create(lista, {
          handle: asa, animation: 150, delay: 0, touchStartThreshold: 4,
          draggable: "[data-id]", chosenClass: "arrastrando",
          onStart: () => { antes = ids(lista); },
          onEnd: (ev) => { if (ev.oldIndex !== ev.newIndex) guardar(lista, antes); },
        });
      }
      lista.addEventListener("click", (ev) => {
        const boton = ev.target.closest("[data-mover]");
        if (!boton) return;
        const item = boton.closest("[data-id]");
        // Solo las flechas de los hijos directos de ESTA lista (no las de una lista de adentro).
        if (item && item.parentElement === lista) mover(item, boton.dataset.mover);
      });
    });
  };
  document.addEventListener("DOMContentLoaded", () => C.engancharOrden());
})();
