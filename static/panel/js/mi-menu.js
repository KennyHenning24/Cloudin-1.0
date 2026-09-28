/* Cloudin · Mi menú.
 *
 * - Disponible / agotado en un toque, optimista, con «Deshacer» (también en el Inicio).
 * - Precio en línea con teclado numérico; Enter guarda, Esc cancela.
 * - Eliminar y mover con «Deshacer».
 * - Buscar y filtrar al instante (en el navegador), selección múltiple y acciones masivas.
 * - Categorías y menús: crear, renombrar y archivar. Ordenar lo hace ordenar.js.
 * - En la tablet, el editor de producto se abre en un cajón lateral sin salir de la lista.
 * Todo guarda con la API /api/v1/staff/catalog/. Sin internet, agotar y precio quedan en cola.
 */
(function () {
  "use strict";
  const C = window.Cloudin;
  const API = "/api/v1/staff/catalog/";
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const raiz = $("#mi-menu");
  const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const normal = (t) => String(t || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const nombreDe = (fila) => fila.dataset.nombreProducto || "El producto";
  const filaDe = (id) => $(`.producto[data-id="${CSS.escape(id)}"]`);
  const plural = (n, uno, varios) => `${n} ${n === 1 ? uno : varios}`;
  const plantilla = (id) => (document.getElementById(id) || {}).innerHTML || "";

  // ------------------------------------------------------------ pintar una fila
  function pintarEstado(fila) {
    const disponible = fila.dataset.available === "true";
    const sinPrecio = fila.dataset.precioActual === "";
    const sw = $("[data-disponible]", fila);
    if (sw) { sw.checked = disponible; sw.disabled = sinPrecio; }
    const texto = $(".switch .estado", fila);
    if (texto) texto.textContent = disponible ? "Disponible" : "Agotado";
    const chips = $(".chips-estado", fila);
    if (chips) chips.innerHTML = sinPrecio ? plantilla("t-chip-sin-precio") : disponible ? "" : plantilla("t-chip-agotado");
  }
  function ponerDisponible(fila, disponible) {
    fila.dataset.available = String(disponible && fila.dataset.precioActual !== "");
    pintarEstado(fila);
    contar();
  }
  function ponerPrecioEnFila(fila, precio) {
    fila.dataset.precioActual = precio === null || precio === undefined ? "" : String(Math.round(precio));
    const boton = $("[data-editar-precio]", fila);
    if (boton) {
      const desde = boton.dataset.desde === "1" ? "Desde " : "";
      $("span", boton).textContent = precio === null ? "Poner precio" : desde + C.pesos(precio);
      boton.classList.toggle("sin-precio", precio === null);
      boton.setAttribute("aria-label", `Cambiar el precio de ${nombreDe(fila)}${precio === null ? "" : ": " + C.pesos(precio)}`);
    }
    if (precio === null) fila.dataset.available = "false";
    pintarEstado(fila);
    contar();
  }

  // ---------------------------------------------------- disponible / agotado
  async function cambiarDisponible(fila, disponible, conDeshacer = true) {
    const url = `${API}products/${fila.dataset.id}/availability/`;
    const opciones = { metodo: "PATCH", datos: { available: disponible } };
    ponerDisponible(fila, disponible); // se ve al instante
    try {
      await C.pedir(url, opciones);
      if (conDeshacer) {
        C.aviso(`${nombreDe(fila)} quedó ${disponible ? "disponible" : "agotado"}`, {
          accion: "Deshacer", alHacer: () => cambiarDisponible(fila, !disponible, false),
        });
      }
    } catch (e) {
      if (e.sinConexion) {
        C.enCola(url, opciones);
        C.aviso("Sin internet: lo guardamos cuando vuelva la conexión.");
        return;
      }
      ponerDisponible(fila, !disponible);
      C.aviso(e.detalle, { tipo: "error" });
    }
  }
  document.addEventListener("change", (ev) => {
    const sw = ev.target.closest("[data-disponible]");
    const fila = sw && sw.closest(".producto");
    if (fila) cambiarDisponible(fila, sw.checked);
  });

  // ------------------------------------------------------------ precio en línea
  async function guardarPrecio(fila, nuevo, anterior, conDeshacer = true) {
    const url = `${API}products/${fila.dataset.id}/`;
    const datos = { price: nuevo };
    // Si vuelve a tener precio con «Deshacer», también vuelve a estar como estaba.
    if (anterior.disponible !== undefined && nuevo !== null) datos.is_available = anterior.disponible;
    const antes = { precio: fila.dataset.precioActual === "" ? null : Number(fila.dataset.precioActual),
                    disponible: fila.dataset.available === "true" };
    ponerPrecioEnFila(fila, nuevo);
    try {
      const r = await C.pedir(url, { metodo: "PATCH", datos });
      ponerPrecioEnFila(fila, r.price === null ? null : Number(r.price));
      ponerDisponible(fila, r.is_available);
      if (conDeshacer) {
        C.aviso(`${nombreDe(fila)}: ${nuevo === null ? "sin precio" : C.pesos(nuevo)}`, {
          accion: "Deshacer", alHacer: () => guardarPrecio(fila, antes.precio, antes, false),
        });
      }
    } catch (e) {
      if (e.sinConexion) {
        C.enCola(url, { metodo: "PATCH", datos });
        C.aviso("Sin internet: el precio se guarda cuando vuelva la conexión.");
        return;
      }
      ponerPrecioEnFila(fila, antes.precio);
      ponerDisponible(fila, antes.disponible);
      C.aviso(e.detalle, { tipo: "error" });
    }
  }
  function editarPrecio(boton) {
    const fila = boton.closest(".producto");
    const actual = fila.dataset.precioActual;
    const caja = document.createElement("span");
    caja.className = "precio-edicion";
    caja.innerHTML = `<input type="text" data-precio value="${esc(actual)}" aria-label="Nuevo precio de ${esc(nombreDe(fila))}">
      <button type="button" class="btn sm icono" aria-label="Guardar el precio">${plantilla("t-guardar") || "OK"}</button>`;
    boton.hidden = true;
    boton.after(caja);
    C.enganchar(caja);
    const input = $("input", caja);
    input.focus();
    input.select();
    let terminado = false;
    const cerrar = () => { caja.remove(); boton.hidden = false; };
    const guardar = () => {
      if (terminado) return;
      terminado = true;
      const nuevo = C.valorPrecio(input);
      const previo = actual === "" ? null : Number(actual);
      cerrar();
      if (nuevo !== previo) guardarPrecio(fila, nuevo, {});
    };
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") { e.preventDefault(); guardar(); boton.focus(); }
      if (e.key === "Escape") { e.preventDefault(); terminado = true; cerrar(); boton.focus(); }
    });
    const ok = $("button", caja);
    ok.addEventListener("mousedown", (e) => e.preventDefault()); // el campo no pierde el foco antes del clic
    ok.addEventListener("click", guardar);
    input.addEventListener("blur", () => setTimeout(() => { if (!terminado && document.contains(caja)) guardar(); }, 150));
  }
  document.addEventListener("click", (ev) => {
    const boton = ev.target.closest("[data-editar-precio]");
    if (boton && !(raiz && raiz.classList.contains("seleccionando"))) editarPrecio(boton);
  });

  if (!raiz) return; // en el Inicio solo hacen falta el switch y el precio

  const admin = raiz.dataset.admin === "1";
  const buscar = $("#buscar");
  const filtroCategoria = $("#filtro-categoria");
  const sinResultados = $("#sin-resultados");
  let estado = ($(".filtros .segmento .on") || {}).dataset?.estado || "";

  // ---------------------------------------------------------- contadores y vacíos
  function contar() {
    if (!raiz) return; // en el Inicio no hay contadores
    const filas = $$(".producto", raiz);
    const n = {
      "": filas.length,
      disponibles: filas.filter((f) => f.dataset.available === "true").length,
      agotados: filas.filter((f) => f.dataset.available === "false" && f.dataset.precioActual !== "").length,
      sin_precio: filas.filter((f) => f.dataset.precioActual === "").length,
      sin_foto: filas.filter((f) => f.dataset.foto === "0").length,
    };
    $$(".filtros [data-estado]").forEach((b) => { const c = $(".cuenta", b); if (c) c.textContent = n[b.dataset.estado]; });
    $$(".categoria", raiz).forEach((cat) => {
      const total = $$(".producto", cat).length;
      const c = $(".cuenta-categoria", cat);
      if (c) c.textContent = "· " + total;
      const vacio = $(".vacio-categoria", cat);
      if (vacio) vacio.hidden = total > 0 || hayFiltros();
    });
  }

  // ------------------------------------------------------------- buscar y filtrar
  const hayFiltros = () => !!((buscar && buscar.value.trim()) || estado || (filtroCategoria && filtroCategoria.value));
  function coincide(f) {
    if (estado === "disponibles") return f.dataset.available === "true";
    if (estado === "agotados") return f.dataset.available === "false" && f.dataset.precioActual !== "";
    if (estado === "sin_precio") return f.dataset.precioActual === "";
    if (estado === "sin_foto") return f.dataset.foto === "0";
    return true;
  }
  function filtrar() {
    const q = normal(buscar ? buscar.value.trim() : "");
    const soloCategoria = filtroCategoria ? filtroCategoria.value : "";
    let visibles = 0;
    $$(".categoria", raiz).forEach((cat) => {
      const verCategoria = !soloCategoria || cat.dataset.id === soloCategoria;
      let aqui = 0;
      $$(".producto", cat).forEach((f) => {
        const ver = verCategoria && (!q || normal(f.dataset.buscar).includes(q)) && coincide(f);
        f.hidden = !ver;
        if (ver) aqui++;
      });
      cat.hidden = !verCategoria || ((q || estado) && aqui === 0);
      visibles += aqui;
    });
    if (sinResultados) sinResultados.hidden = !hayFiltros() || visibles > 0;
    contar();
    // La dirección recuerda el filtro (sirve para volver del editor al mismo lugar).
    const url = new URL(location.href);
    [["q", q ? buscar.value.trim() : ""], ["estado", estado], ["categoria", soloCategoria]].forEach(([k, v]) =>
      v ? url.searchParams.set(k, v) : url.searchParams.delete(k));
    history.replaceState(null, "", url);
  }
  let espera;
  buscar && buscar.addEventListener("input", () => { clearTimeout(espera); espera = setTimeout(filtrar, 120); });
  filtroCategoria && filtroCategoria.addEventListener("change", filtrar);
  $$(".filtros [data-estado]").forEach((b) => b.addEventListener("click", () => {
    estado = b.dataset.estado;
    $$(".filtros [data-estado]").forEach((x) => { x.classList.toggle("on", x === b); x.setAttribute("aria-pressed", String(x === b)); });
    filtrar();
  }));
  function limpiarFiltros() {
    if (buscar) buscar.value = "";
    if (filtroCategoria) filtroCategoria.value = "";
    estado = "";
    $$(".filtros [data-estado]").forEach((x) => { const si = x.dataset.estado === ""; x.classList.toggle("on", si); x.setAttribute("aria-pressed", String(si)); });
    filtrar();
  }

  // -------------------------------------------------------- selección múltiple
  const barra = $("#barra-masiva");
  const botonSeleccionar = $("#seleccionar");
  const seleccionadas = () => $$(".producto .seleccion:checked", raiz).map((c) => c.closest(".producto"));
  function contarSeleccion() {
    const n = seleccionadas().length;
    const t = $("#cuantos-seleccionados");
    if (t) t.textContent = plural(n, "seleccionado", "seleccionados");
  }
  function modoSeleccion(activo) {
    if (!barra) return;
    raiz.classList.toggle("seleccionando", activo);
    barra.hidden = !activo;
    if (botonSeleccionar) botonSeleccionar.setAttribute("aria-pressed", String(activo));
    if (!activo) { $$(".seleccion", raiz).forEach((c) => { c.checked = false; }); const t = $("#seleccionar-todos"); if (t) t.checked = false; }
    contarSeleccion();
  }
  botonSeleccionar && botonSeleccionar.addEventListener("click", () => modoSeleccion(!raiz.classList.contains("seleccionando")));
  raiz.addEventListener("change", (ev) => { if (ev.target.matches(".seleccion")) contarSeleccion(); });
  const todos = $("#seleccionar-todos");
  todos && todos.addEventListener("change", () => {
    $$(".producto:not([hidden]) .seleccion", raiz).forEach((c) => { if (!c.closest(".categoria[hidden]")) c.checked = todos.checked; });
    contarSeleccion();
  });
  // En selección, tocar la fila la marca (y el nombre no abre el editor).
  raiz.addEventListener("click", (ev) => {
    if (!raiz.classList.contains("seleccionando")) return;
    const fila = ev.target.closest(".producto");
    if (!fila || ev.target.closest("input, button, label, summary, details")) return;
    ev.preventDefault();
    const c = $(".seleccion", fila);
    if (c) { c.checked = !c.checked; contarSeleccion(); }
  }, true);
  // Mantener presionado un producto (celular) entra en modo selección.
  let presion;
  raiz.addEventListener("pointerdown", (ev) => {
    const fila = ev.target.closest(".producto");
    if (!admin || !fila || ev.pointerType !== "touch" || ev.target.closest("button, input, label, summary, .asa")) return;
    presion = setTimeout(() => {
      modoSeleccion(true);
      const c = $(".seleccion", fila);
      if (c) c.checked = true;
      contarSeleccion();
      if (navigator.vibrate) navigator.vibrate(15);
    }, 550);
  });
  ["pointerup", "pointercancel", "pointerleave"].forEach((t) => raiz.addEventListener(t, () => clearTimeout(presion)));
  window.addEventListener("scroll", () => clearTimeout(presion), { passive: true });

  // En el celular, «Ordenar» muestra las flechas ↑↓ (y esconde lo demás para que quepan).
  const botonOrdenar = $("#ordenar");
  botonOrdenar && botonOrdenar.addEventListener("click", () => {
    const activo = raiz.classList.toggle("ordenando");
    botonOrdenar.setAttribute("aria-pressed", String(activo));
    if (activo) modoSeleccion(false);
  });

  // ------------------------------------------------------------ eliminar
  function devolver(lugares) {
    lugares.forEach(({ fila, padre, siguiente }) => {
      padre.insertBefore(fila, siguiente && siguiente.parentElement === padre ? siguiente : null);
      ponerDisponible(fila, fila.dataset.precioActual !== ""); // al restaurar queda disponible si tiene precio
    });
    contar();
  }
  async function eliminar(filas) {
    const uno = filas.length === 1;
    const seguro = await C.confirmar(uno
      ? `«${nombreDe(filas[0])}» sale de tu menú y tus clientes dejan de verlo. Justo después puedes deshacerlo.`
      : `Salen de tu menú y tus clientes dejan de verlos. Justo después puedes deshacerlo.`,
    { titulo: uno ? "¿Eliminar este producto?" : `¿Eliminar ${filas.length} productos?`, boton: "Sí, eliminar" });
    if (!seguro) return;
    const ids = filas.map((f) => f.dataset.id);
    const lugares = filas.map((fila) => ({ fila, padre: fila.parentElement, siguiente: fila.nextElementSibling }));
    filas.forEach((f) => f.remove());
    contar();
    try {
      if (ids.length === 1) await C.pedir(`${API}products/${ids[0]}/`, { metodo: "DELETE" });
      else await C.pedir(`${API}bulk/`, { metodo: "POST", datos: { action: "delete", ids } });
      C.aviso(ids.length === 1 ? `${nombreDe(filas[0])} salió de tu menú` : `${ids.length} productos salieron de tu menú`, {
        accion: "Deshacer", ms: 8000, alHacer: async () => {
          try {
            await C.pedir(`${API}bulk/`, { metodo: "POST", datos: { action: "restore", ids } });
            devolver(lugares);
            C.aviso(ids.length === 1 ? "Listo, volvió a tu menú." : "Listo, volvieron a tu menú.");
          } catch (e) { C.aviso(e.detalle, { tipo: "error" }); }
        },
      });
    } catch (e) {
      devolver(lugares);
      C.aviso(e.detalle, { tipo: "error" });
    }
  }

  // --------------------------------------------------------------- mover
  let aMover = [];
  const nombreCategoria = (id) => { const o = $(`#c-mover option[value="${CSS.escape(id)}"]`); return o ? o.textContent : "otra categoría"; };
  function pedirMover(filas) {
    aMover = filas;
    const select = $("#c-mover");
    const actual = filas[0].dataset.categoria;
    const otra = $$("option", select).find((o) => o.value !== actual);
    if (otra) select.value = otra.value;
    C.abrir("dialogo-mover");
  }
  function colocar(filas, categoria) {
    const lista = $(`.categoria[data-id="${CSS.escape(categoria)}"] .productos`, raiz);
    filas.forEach((f) => { f.dataset.categoria = categoria; if (lista) lista.appendChild(f); else f.remove(); });
    contar();
  }
  async function mover(filas, destino) {
    try {
      const r = await C.pedir(`${API}bulk/`, { metodo: "POST", datos: { action: "move", ids: filas.map((f) => f.dataset.id), value: destino } });
      colocar(filas, destino);
      C.aviso(`${filas.length === 1 ? nombreDe(filas[0]) + " pasó" : filas.length + " productos pasaron"} a ${nombreCategoria(destino)}`, {
        accion: r.undo.length ? "Deshacer" : "", alHacer: async () => {
          const grupos = {};
          r.undo.forEach((u) => { (grupos[u.category] = grupos[u.category] || []).push(u.id); });
          try {
            for (const [categoria, ids] of Object.entries(grupos)) {
              await C.pedir(`${API}bulk/`, { metodo: "POST", datos: { action: "move", ids, value: categoria } });
              colocar(filas.filter((f) => ids.includes(f.dataset.id)), categoria);
            }
          } catch (e) { C.aviso(e.detalle, { tipo: "error" }); }
        },
      });
    } catch (e) { C.aviso(e.detalle, { tipo: "error" }); }
  }

  // ------------------------------------------------------- acciones masivas
  async function refrescarPrecios() {
    try {
      const r = await C.pedir(`${API}products/?menu=${raiz.dataset.menu}`);
      (Array.isArray(r) ? r : r.results || []).forEach((p) => {
        const f = filaDe(p.id);
        if (f) { ponerPrecioEnFila(f, p.price === null ? null : Number(p.price)); ponerDisponible(f, p.is_available); }
      });
    } catch (e) { location.reload(); }
  }
  async function disponibles(accion, filas) {
    const quiere = accion === "available";
    const antes = filas.map((f) => [f, f.dataset.available === "true"]);
    filas.forEach((f) => ponerDisponible(f, quiere));
    try {
      const r = await C.pedir(`${API}bulk/`, { metodo: "POST", datos: { action: accion, ids: filas.map((f) => f.dataset.id) } });
      C.aviso(`${plural(r.changed, "producto", "productos")} ${quiere ? "disponible" : "agotado"}${r.changed === 1 ? "" : "s"}`, {
        accion: r.undo.length ? "Deshacer" : "", alHacer: async () => {
          const por = { available: [], soldout: [] };
          r.undo.forEach((u) => por[u.available ? "available" : "soldout"].push(u.id));
          for (const [a, ids] of Object.entries(por)) {
            if (!ids.length) continue;
            await C.pedir(`${API}bulk/`, { metodo: "POST", datos: { action: a, ids } }).catch((e) => C.aviso(e.detalle, { tipo: "error" }));
            ids.forEach((id) => { const f = filaDe(id); if (f) ponerDisponible(f, a === "available"); });
          }
        },
      });
    } catch (e) {
      antes.forEach(([f, d]) => ponerDisponible(f, d));
      C.aviso(e.detalle, { tipo: "error" });
    }
  }
  let aCambiar = [];
  function ejemploPorcentaje() {
    const p = Number($("#c-porcentaje").value);
    const f = aCambiar.find((x) => x.dataset.precioActual !== "");
    const ej = $("#porcentaje-ejemplo");
    if (!ej) return;
    if (!f || !isFinite(p)) { ej.textContent = ""; return; }
    const antes = Number(f.dataset.precioActual);
    ej.textContent = `Ejemplo: ${nombreDe(f)} pasa de ${C.pesos(antes)} a ${C.pesos(Math.round(antes * (1 + p / 100) / 100) * 100)}.`;
  }
  $("#c-porcentaje") && $("#c-porcentaje").addEventListener("input", ejemploPorcentaje);
  async function porcentaje(filas, valor) {
    try {
      const r = await C.pedir(`${API}bulk/`, { metodo: "POST", datos: { action: "price_percent", ids: filas.map((f) => f.dataset.id), value: valor } });
      await refrescarPrecios();
      C.aviso(`Precios actualizados en ${plural(r.changed, "producto", "productos")}`, {
        accion: r.undo.length ? "Deshacer" : "", ms: 8000, alHacer: async () => {
          try {
            await C.pedir(`${API}bulk/`, { metodo: "POST", datos: { action: "set_prices", ids: r.undo.map((u) => u.id), value: r.undo } });
            await refrescarPrecios();
            C.aviso("Listo, volvieron los precios de antes.");
          } catch (e) { C.aviso(e.detalle, { tipo: "error" }); }
        },
      });
    } catch (e) { C.aviso(e.detalle, { tipo: "error" }); }
  }
  barra && barra.addEventListener("click", (ev) => {
    const b = ev.target.closest("[data-masivo]");
    if (!b) return;
    const accion = b.dataset.masivo;
    if (accion === "cancelar") return modoSeleccion(false);
    const filas = seleccionadas();
    if (!filas.length) return C.aviso("Primero elige uno o más productos.");
    if (accion === "move") return pedirMover(filas);
    if (accion === "delete") return eliminar(filas);
    if (accion === "price_percent") { aCambiar = filas; ejemploPorcentaje(); return C.abrir("dialogo-porcentaje"); }
    disponibles(accion, filas);
  });

  // ------------------------------------------------------ confirmar (diálogo)
  const confirmar = (texto, boton) => C.confirmar(texto, { boton });

  // ------------------------------------------------ categorías y menús
  let renombrando = null;
  function pedirNombre(tipo, id, actual) {
    renombrando = { tipo, id };
    const d = $("#dialogo-renombrar");
    $("#c-renombrar").value = actual;
    $("#t-dialogo-renombrar").textContent = tipo === "menu" ? "Nombre del menú" : "Nombre de la categoría";
    C.abrir(d);
  }
  async function archivarCategoria(cat, confirmado = false) {
    const id = cat.dataset.id;
    try {
      await C.pedir(`${API}categories/${id}/${confirmado ? "?confirm=1" : ""}`, { metodo: "DELETE" });
      cat.remove();
      contar();
      C.aviso(`Categoría «${cat.dataset.nombre}» archivada`, {
        accion: "Deshacer", ms: 8000, alHacer: () => C.pedir(`${API}categories/${id}/restore/`, { metodo: "POST" })
          .then(() => { C.avisoPendiente("Listo, la categoría volvió."); location.reload(); })
          .catch((e) => C.aviso(e.detalle, { tipo: "error" })),
      });
    } catch (e) {
      if (e.codigo === "confirm" && await confirmar(e.detalle, "Sí, archivar")) return archivarCategoria(cat, true);
      if (e.codigo !== "confirm") C.aviso(e.detalle, { tipo: "error" });
    }
  }
  document.addEventListener("click", async (ev) => {
    const b = ev.target.closest("[data-accion]");
    if (!b || !raiz.contains(b) && !b.closest("dialog")) return;
    const accion = b.dataset.accion;
    const det = b.closest("details");
    if (det) det.open = false;
    const fila = b.closest(".producto");
    const cat = b.closest(".categoria");
    if (accion === "eliminar" && fila) return eliminar([fila]);
    if (accion === "mover" && fila) return pedirMover([fila]);
    if (accion === "limpiar-filtros") return limpiarFiltros();
    if (accion === "renombrar-categoria" && cat) return pedirNombre("categoria", cat.dataset.id, cat.dataset.nombre);
    if (accion === "archivar-categoria" && cat) return archivarCategoria(cat);
    const tab = $(`[data-menu-tab="${CSS.escape(raiz.dataset.menu)}"]`);
    if (accion === "renombrar-menu") return pedirNombre("menu", raiz.dataset.menu, tab ? $(".nombre-menu", tab).textContent : "");
    if (accion === "archivar-menu") {
      if (!await confirmar("El menú deja de salir para tus clientes, con sus categorías. Tus productos no se borran.", "Sí, archivar")) return;
      try {
        await C.pedir(`${API}menus/${raiz.dataset.menu}/`, { metodo: "DELETE" });
        C.avisoPendiente("Menú archivado.");
        location.href = location.pathname;
      } catch (e) { C.aviso(e.detalle, { tipo: "error" }); }
    }
  });

  // Formularios de los diálogos (method=dialog: el diálogo se cierra solo al enviar).
  document.addEventListener("submit", async (ev) => {
    const forma = ev.target.closest("form[data-formulario]");
    if (!forma) return;
    const tipo = forma.dataset.formulario;
    const nombre = forma.elements.name ? forma.elements.name.value.trim() : "";
    try {
      if (tipo === "categoria" && nombre) {
        await C.pedir(`${API}categories/`, { metodo: "POST", datos: { name: nombre, menu: raiz.dataset.menu } });
        C.avisoPendiente(`Categoría «${nombre}» creada. Ahora agrégale productos.`);
        location.reload();
      } else if (tipo === "menu" && nombre) {
        const r = await C.pedir(`${API}menus/`, { metodo: "POST", datos: { name: nombre } });
        C.avisoPendiente(`Menú «${nombre}» creado.`);
        location.href = `${location.pathname}?menu=${r.id}`;
      } else if (tipo === "renombrar" && nombre && renombrando) {
        const { tipo: t, id } = renombrando;
        await C.pedir(`${API}${t === "menu" ? "menus" : "categories"}/${id}/`, { metodo: "PATCH", datos: { name: nombre } });
        if (t === "menu") {
          const tab = $(`[data-menu-tab="${CSS.escape(id)}"] .nombre-menu`);
          if (tab) tab.textContent = nombre;
        } else {
          const cat = $(`.categoria[data-id="${CSS.escape(id)}"]`);
          cat.dataset.nombre = nombre;
          $(".nombre-categoria", cat).textContent = nombre;
          $$(`option[value="${CSS.escape(id)}"]`).forEach((o) => { o.textContent = nombre; });
        }
        C.aviso("Nombre cambiado");
      } else if (tipo === "mover") {
        await mover(aMover, forma.elements.categoria.value);
        modoSeleccion(false);
      } else if (tipo === "porcentaje") {
        const valor = Number(forma.elements.porcentaje.value);
        if (!isFinite(valor) || valor === 0) return C.aviso("Escribe el porcentaje, por ejemplo 5 o -10.", { tipo: "error" });
        await porcentaje(aCambiar, valor);
        modoSeleccion(false);
      }
    } catch (e) { C.aviso(e.detalle, { tipo: "error" }); }
  });

  // ------------------------------------------- editor en el cajón (tablet)
  const cajon = $("#cajon-editor");
  const esTablet = () => matchMedia("(min-width: 640px) and (max-width: 1023px)").matches;
  document.addEventListener("click", async (ev) => {
    const a = ev.target.closest("a[data-editor]");
    if (!a || !cajon || !esTablet() || ev.ctrlKey || ev.metaKey || ev.shiftKey || !C.editorProducto) return;
    if (raiz.classList.contains("seleccionando") && a.closest(".producto")) return;
    ev.preventDefault();
    const det = a.closest("details");
    if (det) det.open = false;
    try {
      const r = await fetch(a.href + (a.href.includes("?") ? "&" : "?") + "fragmento=1", { credentials: "same-origin" });
      if (!r.ok || r.redirected) throw new Error("sin fragmento");
      cajon.innerHTML = await r.text();
      C.abrir(cajon);
      C.editorProducto($(".editor-raiz", cajon), {
        alGuardar: (p, nuevo) => { C.avisoPendiente(nuevo ? `«${p.name}» quedó en tu menú` : "Cambios guardados"); location.reload(); },
        alEliminar: () => location.reload(),
      });
    } catch (e) { location.href = a.href; }
  });
  cajon && cajon.addEventListener("cancel", (ev) => {
    const forma = $("form[data-editor-producto]", cajon);
    if (forma && forma.dataset.sucio && !confirm("Tienes cambios sin guardar. ¿Cerrar igual?")) ev.preventDefault();
  });

  // ------------------------------------------------------------- arranque
  const params = new URLSearchParams(location.search);
  if (params.get("categoria") && filtroCategoria) filtroCategoria.value = params.get("categoria");
  if (hayFiltros()) filtrar(); else contar();
  if (params.get("seleccionar") === "1") modoSeleccion(true);
  if (params.get("nueva") === "categoria" && $("#dialogo-categoria")) C.abrir("dialogo-categoria");
  document.addEventListener("keydown", (ev) => { if (ev.key === "Escape" && raiz.classList.contains("seleccionando") && !$("dialog[open]")) modoSeleccion(false); });
})();
