/* Cloudin · editor de producto.
 *
 * Cloudin.editorProducto(raiz, {alGuardar, alEliminar}) engancha el formulario de
 * templates/panel/duenio/_producto_form.html (en su página o en el cajón de la tablet).
 * Guardar = crear o actualizar el producto, luego sus tamaños, sus grupos de adiciones
 * y la foto, todo con la API /api/v1/staff/catalog/. Mientras se escribe, la vista previa
 * muestra el producto tal como saldrá en el menú.
 */
(function () {
  "use strict";
  const C = (window.Cloudin = window.Cloudin || {});
  const API = "/api/v1/staff/catalog/";
  const CERO = "00000000-0000-0000-0000-000000000000";
  const $ = (s, r) => r.querySelector(s);
  const $$ = (s, r) => [...r.querySelectorAll(s)];
  const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const regla = (g) => {
    const cuantas = g.max === 1 ? "elige 1" : g.max ? `hasta ${g.max}` : "las que quiera";
    return (g.min >= 1 ? "Obligatoria · " : "Opcional · ") + cuantas;
  };

  C.editorProducto = function (raiz, { alGuardar = null, alEliminar = null } = {}) {
    const forma = raiz && $("form[data-editor-producto]", raiz);
    if (!forma || forma.dataset.listo) return;
    forma.dataset.listo = "1";
    const cfg = JSON.parse($("#editor-config", raiz).textContent);
    const enCajon = raiz.dataset.cajon === "1";
    let producto = cfg.producto; // null mientras es nuevo
    let fotoNueva = null, urlFotoNueva = null, quitarFoto = false, guardando = false;
    const grupos = new Map(cfg.grupos.map((g) => [g.id, g]));
    let elegidos = producto ? producto.modifier_groups.map((g) => g.id) : [];
    const estado = $("[data-estado-guardado]", raiz);
    const botonGuardar = $("[data-guardar]", raiz);
    const f = forma.elements;

    C.enganchar(raiz);
    if (C.engancharFotos) C.engancharFotos(raiz);

    // ------------------------------------------------------ cambios sin guardar
    function marcar(texto = "Cambios sin guardar") {
      forma.dataset.sucio = "1";
      estado.textContent = texto;
      estado.classList.remove("listo");
      programarVista();
    }
    function limpio(texto) {
      delete forma.dataset.sucio;
      estado.innerHTML = texto;
      estado.classList.add("listo");
    }
    forma.addEventListener("input", (ev) => { if (!ev.target.closest("[data-ver-agotado]")) marcar(); });
    forma.addEventListener("change", (ev) => { if (!ev.target.closest("[data-ver-agotado]")) marcar(); else programarVista(); });
    if (!enCajon) {
      window.addEventListener("beforeunload", (ev) => { if (forma.dataset.sucio) { ev.preventDefault(); ev.returnValue = ""; } });
    }

    // -------------------------------------------------------------- foto
    const cajaFoto = $("[data-subir-foto]", raiz);
    const quitar = $("[data-quitar-foto]", raiz);
    raiz.addEventListener("foto-lista", (ev) => {
      fotoNueva = ev.detail.foto;
      quitarFoto = false;
      if (quitar) quitar.hidden = false;
      // La vista previa es el sitio del restaurante (otro dominio): la foto viaja como data: URL.
      const lector = new FileReader();
      lector.onload = () => { urlFotoNueva = lector.result; programarVista(); };
      lector.readAsDataURL(fotoNueva);
      marcar();
    });
    quitar && quitar.addEventListener("click", () => {
      fotoNueva = null;
      quitarFoto = !!(producto && producto.image);
      const vista = $("img.vista", cajaFoto);
      if (vista) { vista.hidden = true; vista.removeAttribute("src"); }
      cajaFoto.classList.remove("con-foto");
      quitar.hidden = true;
      marcar();
    });

    // ---------------------------------------------------------- tamaños
    const listaVar = $("[data-variantes]", raiz);
    function filaVariante(v = {}) {
      const fila = document.createElement("div");
      fila.className = "fila-variante";
      if (v.id) fila.dataset.id = v.id;
      fila.innerHTML = `<input type="text" name="variante_nombre" maxlength="60" placeholder="Ej. Doble carne" value="${esc(v.name || "")}" aria-label="Nombre del tamaño">
        <input type="text" data-precio placeholder="$ 0" value="${v.price ?? ""}" aria-label="Precio del tamaño">
        <button type="button" class="btn fantasma icono sm" data-quitar-variante aria-label="Quitar este tamaño">
          <svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg></button>`;
      return fila;
    }
    (producto ? producto.variants : []).forEach((v) => listaVar.appendChild(filaVariante(v)));
    C.enganchar(listaVar);
    $("[data-agregar-variante]", raiz).addEventListener("click", () => {
      const fila = filaVariante();
      listaVar.appendChild(fila);
      C.enganchar(fila);
      $("input", fila).focus();
      marcar();
    });
    listaVar.addEventListener("click", (ev) => {
      if (!ev.target.closest("[data-quitar-variante]")) return;
      ev.target.closest(".fila-variante").remove();
      marcar();
    });
    const variantes = () => $$(".fila-variante", listaVar).map((fila) => ({
      id: fila.dataset.id || undefined,
      name: $("[name=variante_nombre]", fila).value.trim(),
      price: C.valorPrecio($("[data-precio]", fila)),
    })).filter((v) => v.name || v.price !== null);

    // ------------------------------------------------ grupos de adiciones
    const listaGrupos = $("[data-grupos]", raiz);
    const elegir = $("[data-elegir-grupo]", raiz);
    function pintarGrupos() {
      listaGrupos.innerHTML = elegidos.map((id) => {
        const g = grupos.get(id);
        if (!g) return "";
        const opciones = g.options.map((o) => esc(o.name) + (o.price ? " (+" + C.pesos(o.price) + ")" : "")).join(" · ");
        return `<li class="grupo-elegido" data-id="${esc(id)}"><div><strong>${esc(g.name)}</strong>
          <span class="chip">${regla(g)}</span><p class="dim small">${opciones || "Sin opciones todavía"}</p></div>
          <button type="button" class="btn fantasma icono sm" data-quitar-grupo aria-label="Quitar el grupo ${esc(g.name)}">
          <svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg></button></li>`;
      }).join("");
      elegir.innerHTML = '<option value="">Usar un grupo existente…</option>' +
        [...grupos.values()].filter((g) => !elegidos.includes(g.id))
          .map((g) => `<option value="${esc(g.id)}">${esc(g.name)} · ${regla(g)}</option>`).join("");
      elegir.disabled = elegir.options.length <= 1;
    }
    pintarGrupos();
    elegir.addEventListener("change", () => {
      if (!elegir.value) return;
      elegidos.push(elegir.value);
      pintarGrupos();
      marcar();
    });
    listaGrupos.addEventListener("click", (ev) => {
      if (!ev.target.closest("[data-quitar-grupo]")) return;
      const id = ev.target.closest("[data-id]").dataset.id;
      elegidos = elegidos.filter((x) => x !== id);
      pintarGrupos();
      marcar();
    });

    // Crear un grupo nuevo (queda disponible para otros productos).
    const dialogo = $("[data-dialogo-grupo]", raiz);
    const formaGrupo = $("[data-formulario-grupo]", raiz);
    const listaOpciones = $("[data-opciones]", raiz);
    function filaOpcion() {
      const fila = document.createElement("div");
      fila.className = "fila-variante";
      fila.innerHTML = `<input type="text" name="opcion_nombre" maxlength="60" placeholder="Ej. Salsa de ajo" aria-label="Nombre de la opción">
        <input type="text" data-precio placeholder="+ $ 0" aria-label="Precio extra (0 si no cambia)">
        <button type="button" class="btn fantasma icono sm" data-quitar-opcion aria-label="Quitar esta opción">
          <svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg></button>`;
      listaOpciones.appendChild(fila);
      C.enganchar(fila);
      return fila;
    }
    $("[data-crear-grupo]", raiz).addEventListener("click", () => {
      formaGrupo.reset();
      listaOpciones.innerHTML = "";
      filaOpcion(); filaOpcion();
      C.abrir(dialogo);
    });
    $("[data-agregar-opcion]", raiz).addEventListener("click", () => $("input", filaOpcion()).focus());
    listaOpciones.addEventListener("click", (ev) => { if (ev.target.closest("[data-quitar-opcion]")) ev.target.closest(".fila-variante").remove(); });
    formaGrupo.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const nombre = formaGrupo.elements.nombre.value.trim();
      const opciones = $$(".fila-variante", listaOpciones).map((fila) => ({
        name: $("[name=opcion_nombre]", fila).value.trim(), price: C.valorPrecio($("[data-precio]", fila)) || 0,
      })).filter((o) => o.name);
      if (!nombre) return C.aviso("Escribe el nombre del grupo.", { tipo: "error" });
      if (!opciones.length) return C.aviso("Agrega al menos una opción.", { tipo: "error" });
      const maximo = formaGrupo.elements.maximo.value ? Number(formaGrupo.elements.maximo.value) : null;
      const obligatorio = formaGrupo.elements.obligatorio.checked;
      try {
        const g = await C.pedir(`${API}modifier-groups/`, { metodo: "POST", datos: {
          name: nombre, min: obligatorio ? 1 : 0, max: maximo, options: opciones } });
        grupos.set(g.id, { id: g.id, name: g.name, min: g.min, max: g.max,
          options: g.options.map((o) => ({ id: o.id, name: o.name, price: Number(o.price) })) });
        elegidos.push(g.id);
        pintarGrupos();
        C.cerrar(dialogo);
        marcar();
        C.aviso(`Grupo «${g.name}» creado`);
      } catch (e) { C.aviso(e.detalle, { tipo: "error" }); }
    });

    // --------------------------------------------------------- etiquetas
    raiz.addEventListener("click", (ev) => {
      const b = ev.target.closest("[data-etiqueta]");
      if (!b) return;
      b.setAttribute("aria-pressed", String(b.getAttribute("aria-pressed") !== "true"));
      marcar();
    });
    // Una etiqueta nueva se crea al vuelo, queda marcada en este plato y en la lista de todos.
    const entradaEtiqueta = $("[data-etiqueta-nueva]", raiz);
    async function crearEtiqueta() {
      const nombre = entradaEtiqueta.value.replace(/\s+/g, " ").trim();
      if (!nombre) return entradaEtiqueta.focus();
      const existente = $$("[data-etiqueta]", raiz).find((b) => b.textContent.trim().toLowerCase() === nombre.toLowerCase());
      if (existente) {
        existente.setAttribute("aria-pressed", "true");
        entradaEtiqueta.value = "";
        return marcar();
      }
      try {
        const t = await C.pedir(`${API}tags/`, { metodo: "POST", datos: { name: nombre } });
        const b = document.createElement("button");
        b.type = "button";
        b.className = "chip";
        b.dataset.etiqueta = t.key;
        b.setAttribute("aria-pressed", "true");
        b.textContent = t.name;
        const vacio = $("[data-sin-etiquetas]", raiz);
        if (vacio) vacio.remove();
        $("[data-etiquetas]", raiz).appendChild(b);
        entradaEtiqueta.value = "";
        marcar();
        C.aviso(`Etiqueta «${t.name}» creada: ya está en la lista para todos tus platos.`);
      } catch (e) { C.aviso(e.detalle, { tipo: "error" }); }
    }
    if (entradaEtiqueta) {
      $("[data-crear-etiqueta]", raiz).addEventListener("click", crearEtiqueta);
      entradaEtiqueta.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter") { ev.preventDefault(); crearEtiqueta(); }  // Enter no guarda el plato
      });
    }

    // ------------------------------------------------------------ datos
    function datos() {
      const impuesto = $("input[name=tax_type]:checked", forma);
      const prep = f.prep_minutes.value.trim();
      return {
        name: f.name.value.trim(),
        price: C.valorPrecio(f.price),
        category: f.category.value,
        description: f.description.value.trim(),
        is_available: f.is_available.checked,
        is_featured: f.is_featured.checked,
        base_label: f.base_label.value.trim(),
        sku: f.sku.value.trim(),
        prep_minutes: prep === "" ? null : Math.max(0, Math.round(Number(prep)) || 0),
        tax_type: impuesto ? impuesto.value : "",
        permite_observacion: f.permite_observacion.checked,
        tags: $$("[data-etiqueta][aria-pressed=true]", raiz).map((b) => b.dataset.etiqueta),
      };
    }
    function errorNombre(mostrar) {
      const e = $("#e-nombre-error", raiz);
      if (e) e.hidden = !mostrar;
      f.name.setAttribute("aria-invalid", String(mostrar));
      f.name.closest(".campo").classList.toggle("con-error", mostrar);
    }
    f.name.addEventListener("input", () => { if (f.name.value.trim()) errorNombre(false); });

    // ----------------------------------------------------------- guardar
    async function guardar() {
      if (guardando) return;
      if (C.fotoEnCamino && C.fotoEnCamino(raiz)) {
        // La foto elegida todavía se está preparando: se guarda con ella, no sin ella.
        guardando = true;
        botonGuardar.setAttribute("aria-busy", "true");
        estado.textContent = "Preparando la foto…";
        try { await C.fotosPendientes(raiz); } finally { guardando = false; botonGuardar.removeAttribute("aria-busy"); }
      }
      const d = datos();
      if (!d.name) { errorNombre(true); f.name.focus(); return C.aviso("Falta el nombre del producto.", { tipo: "error" }); }
      if (d.price === null && d.is_available) {
        d.is_available = false;
        f.is_available.checked = false;
      }
      const vs = variantes();
      if (vs.some((v) => !v.name || v.price === null)) return C.aviso("Cada tamaño necesita nombre y precio.", { tipo: "error" });
      guardando = true;
      botonGuardar.setAttribute("aria-busy", "true");
      estado.textContent = "Guardando…";
      const nuevo = !producto;
      try {
        let r = await C.pedir(nuevo ? `${API}products/` : `${API}products/${producto.id}/`, { metodo: nuevo ? "POST" : "PATCH", datos: d });
        producto = r;
        r = await C.pedir(`${API}products/${r.id}/variants/`, { metodo: "PUT", datos: vs });
        r = await C.pedir(`${API}products/${r.id}/modifier-groups/`, { metodo: "PUT", datos: elegidos });
        if (fotoNueva) {
          r = await C.pedir(`${API}products/${r.id}/image/`, { metodo: "POST", archivo: fotoNueva });
          fotoNueva = null;
        } else if (quitarFoto) {
          await C.pedir(`${API}products/${r.id}/image/`, { metodo: "DELETE" });
          r.image = null;
          quitarFoto = false;
        }
        producto = { ...r, variants: r.variants.map((v) => ({ ...v, price: Number(v.price) })) };
        // Los tamaños nuevos ya tienen id: la próxima vez se actualizan, no se duplican.
        $$(".fila-variante", listaVar).filter((fila) => $("[name=variante_nombre]", fila).value.trim())
          .forEach((fila, i) => { if (producto.variants[i]) fila.dataset.id = producto.variants[i].id; });
        limpio('Guardado <svg class="ico sm" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg>');
        const eliminar = $("[data-eliminar]", raiz);
        if (eliminar) eliminar.hidden = false;
        if (nuevo && !enCajon) {
          history.replaceState(null, "", cfg.editar.replace(CERO, producto.id));
          document.title = `${producto.name} · Cloudin`;
        }
        if (alGuardar) return alGuardar(producto, nuevo);
        C.aviso(nuevo ? `«${producto.name}» quedó en tu menú` : "Cambios guardados");
      } catch (e) {
        estado.textContent = "No se guardó";
        if (e.cuerpo && e.cuerpo.name) errorNombre(true);
        C.aviso(e.detalle, { tipo: "error" });
      } finally {
        guardando = false;
        botonGuardar.removeAttribute("aria-busy");
      }
    }
    forma.addEventListener("submit", (ev) => { ev.preventDefault(); guardar(); });
    raiz.addEventListener("keydown", (ev) => {
      if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "s") { ev.preventDefault(); guardar(); }
    });
    if (!enCajon) {
      document.addEventListener("keydown", (ev) => {
        if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "s" && !raiz.contains(ev.target)) { ev.preventDefault(); guardar(); }
      });
    }

    // ---------------------------------------------------------- eliminar
    const botonEliminar = $("[data-eliminar]", raiz);
    botonEliminar && botonEliminar.addEventListener("click", async () => {
      if (!producto) return;
      const seguro = await C.confirmar(
        `«${producto.name}» sale de tu menú y tus clientes dejan de verlo. Justo después puedes deshacerlo.`,
        { titulo: "¿Eliminar este producto?", boton: "Sí, eliminar" });
      if (!seguro) return;
      try {
        await C.pedir(`${API}products/${producto.id}/`, { metodo: "DELETE" });
        delete forma.dataset.sucio;
        C.avisoPendiente(`«${producto.name}» salió de tu menú`, { deshacer: { url: `${API}products/${producto.id}/restore/`, metodo: "POST" } });
        if (alEliminar) return alEliminar(producto);
        location.href = cfg.volver;
      } catch (e) { C.aviso(e.detalle, { tipo: "error" }); }
    });

    // ---------------------------------------------------- vista previa
    const vista = C.vistaPrevia ? C.vistaPrevia($("iframe[data-vista-previa]", raiz)) : null;
    const verAgotado = $("[data-ver-agotado]", raiz);
    let temporizador;
    function programarVista() { clearTimeout(temporizador); temporizador = setTimeout(enviarVista, 200); }
    function enviarVista() {
      if (!vista) return;
      const d = datos();
      const cat = cfg.categorias[d.category] || {};
      const foto = fotoNueva ? urlFotoNueva : quitarFoto ? null : (producto && producto.image) || null;
      vista.enviar({
        producto: {
          id: producto ? producto.id : "nuevo", key: producto ? producto.key : "producto-nuevo",
          name: d.name || "Tu producto", description: d.description || null, price: d.price, image: foto,
          available: d.is_available && d.price !== null && !(verAgotado && verAgotado.checked),
          featured: d.is_featured, tags: d.tags, tax: d.tax_type || null,
          variants: variantes().filter((v) => v.name && v.price !== null).map((v, i) => ({ key: "tamano-" + i, name: v.name, price: v.price })),
          modifier_groups: [],
        },
        categoria: { id: d.category, key: cat.key, name: cat.name },
        menu: cat.menu,
      });
    }
    enviarVista();
  };

  document.addEventListener("DOMContentLoaded", () => {
    const raiz = document.querySelector("[data-editor-raiz]");
    if (raiz && !raiz.closest("dialog")) C.editorProducto(raiz);
  });
})();
