/* Cloudin · Personalizar → Datos del negocio: frase, contacto, horario, redes, servicios y pagos.
 *
 * Todo se guarda de una vez con PATCH /api/v1/staff/settings/. La vista previa muestra los
 * cambios antes de guardar. El diseño del menú (colores, logo, portada) es de su página.
 */
(function () {
  "use strict";
  const C = window.Cloudin;
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const forma = $("#form-ajustes");
  if (!forma) return;
  const URL_AJUSTES = "/api/v1/staff/settings/";
  const estado = $("[data-estado-guardado]", forma);
  const botonGuardar = $("[data-guardar]", forma);
  const valor = (n) => (forma.elements[n] ? forma.elements[n].value.trim() : "");

  // En la tablet y el PC todas las secciones abiertas; en el celular, acordeón.
  if (matchMedia("(min-width: 640px)").matches) $$("details.seccion-ajustes", forma).forEach((d) => { d.open = true; });
  // Llegar con #horario (desde «Completa tu menú») abre esa sección.
  if (location.hash) { const d = $(location.hash); if (d && d.tagName === "DETAILS") { d.open = true; d.scrollIntoView({ block: "start" }); } }

  // ------------------------------------------------------------- horario
  const tramo = () => document.getElementById("t-tramo").content.firstElementChild.cloneNode(true);
  function pintarDia(dia) {
    const hay = $$(".tramo", dia).length > 0;
    $("[data-abierto]", dia).checked = hay;
    $(".cerrado", dia).hidden = hay;
    $("[data-agregar-tramo]", dia).hidden = !hay;
    textoCopiar();
  }
  function textoCopiar() {
    const primero = $$(".dia", forma).find((d) => $(".tramo", d));
    const t = $("[data-copiar-texto]", forma);
    if (t) t.textContent = primero ? `Copiar el ${primero.dataset.nombre.toLowerCase()} a todos los días` : "Copiar el primer día abierto a todos";
  }
  $$(".dia", forma).forEach((dia) => {
    $("[data-abierto]", dia).addEventListener("change", (ev) => {
      if (ev.target.checked) {
        const anterior = $$(".dia", forma).map((d) => $(".tramo", d)).find(Boolean);
        const nuevo = anterior ? anterior.cloneNode(true) : tramo();
        $("[data-agregar-tramo]", dia).before(nuevo);
      } else {
        $$(".tramo", dia).forEach((t) => t.remove());
      }
      pintarDia(dia);
      cambio();
    });
    $("[data-agregar-tramo]", dia).addEventListener("click", () => {
      const nuevo = tramo();
      $("[data-abre]", nuevo).value = "18:00";
      $("[data-cierra]", nuevo).value = "22:00";
      $("[data-agregar-tramo]", dia).before(nuevo);
      $("input", nuevo).focus();
      pintarDia(dia);
      cambio();
    });
    dia.addEventListener("click", (ev) => {
      if (!ev.target.closest("[data-quitar-tramo]")) return;
      ev.target.closest(".tramo").remove();
      pintarDia(dia);
      cambio();
    });
  });
  $("[data-copiar-horario]", forma).addEventListener("click", () => {
    const origen = $$(".dia", forma).find((d) => $(".tramo", d));
    if (!origen) return C.aviso("Primero abre un día y ponle su horario.");
    $$(".dia", forma).forEach((dia) => {
      if (dia === origen) return;
      $$(".tramo", dia).forEach((t) => t.remove());
      $$(".tramo", origen).forEach((t) => $("[data-agregar-tramo]", dia).before(t.cloneNode(true)));
      pintarDia(dia);
    });
    cambio();
    C.aviso("Horario copiado a toda la semana");
  });
  textoCopiar();
  const horario = () => $$(".dia", forma).flatMap((dia) => $$(".tramo", dia).map((t) => ({
    day: dia.dataset.dia, open: $("[data-abre]", t).value, close: $("[data-cierra]", t).value,
  })));

  // ----------------------------------------------------------- guardar
  function cambio() {
    forma.dataset.sucio = "1";
    estado.textContent = "Tienes cambios sin guardar";
    estado.classList.remove("listo");
    programarVista();
  }
  forma.addEventListener("input", cambio);
  forma.addEventListener("change", cambio);

  function datos() {
    const d = {};
    ["tagline", "description", "welcome_message", "whatsapp", "phone", "email", "address", "city", "maps_url",
      "instagram", "facebook", "tiktok"].forEach((n) => { d[n] = valor(n); });
    d.services = {};
    $$("input[name=services]", forma).forEach((i) => { d.services[i.value] = i.checked; });
    d.payment_methods = $$("input[name=payment_methods]:checked", forma).map((i) => i.value);
    d.hours = horario();
    return d;
  }
  function limpiarErrores() {
    $$(".campo.con-error", forma).forEach((c) => { c.classList.remove("con-error"); const e = $(".error.del-servidor", c); if (e) e.remove(); });
    $$("[aria-invalid=true]", forma).forEach((i) => i.removeAttribute("aria-invalid"));
  }
  function mostrarErrores(cuerpo) {
    if (!cuerpo || typeof cuerpo !== "object") return;
    let primero = null;
    Object.entries(cuerpo).forEach(([campo, mensajes]) => {
      const input = forma.elements[campo === "hours_input" ? "" : campo];
      if (!input || !input.closest) return;
      const caja = input.closest(".campo");
      input.setAttribute("aria-invalid", "true");
      if (caja) {
        caja.classList.add("con-error");
        const e = document.createElement("div");
        e.className = "error del-servidor";
        e.textContent = Array.isArray(mensajes) ? mensajes[0] : String(mensajes);
        caja.appendChild(e);
        const det = caja.closest("details");
        if (det) det.open = true;
      }
      primero = primero || input;
    });
    if (primero) primero.focus();
  }
  async function guardar() {
    const malo = horario().find((h) => !h.open || !h.close || h.open === h.close);
    if (malo) { $("#horario").open = true; return C.aviso("Revisa el horario: cada tramo necesita hora de abrir y de cerrar distintas.", { tipo: "error" }); }
    limpiarErrores();
    botonGuardar.setAttribute("aria-busy", "true");
    estado.textContent = "Guardando…";
    try {
      const r = await C.pedir(URL_AJUSTES, { metodo: "PATCH", datos: datos() });
      // El servidor lo guarda como +573001234567; se muestra como se escribe: 300 123 4567.
      const celular = (n) => { const d = String(n || "").replace(/\D/g, "").replace(/^57(?=\d{10}$)/, ""); return d.length === 10 ? `${d.slice(0, 3)} ${d.slice(3, 6)} ${d.slice(6)}` : n || ""; };
      if (forma.elements.whatsapp && r.whatsapp !== undefined) forma.elements.whatsapp.value = celular(r.whatsapp);
      if (forma.elements.phone && r.phone !== undefined) forma.elements.phone.value = celular(r.phone);
      delete forma.dataset.sucio;
      if (forma.limpiar) forma.limpiar();
      estado.textContent = "Guardado";
      estado.classList.add("listo");
      C.aviso("Cambios guardados: ya se ven en tu menú.");
    } catch (e) {
      estado.textContent = "No se guardó";
      mostrarErrores(e.cuerpo);
      C.aviso(e.detalle, { tipo: "error" });
    } finally { botonGuardar.removeAttribute("aria-busy"); }
  }
  forma.addEventListener("submit", (ev) => { ev.preventDefault(); guardar(); });
  document.addEventListener("keydown", (ev) => {
    if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "s") { ev.preventDefault(); guardar(); }
  });

  // ------------------------------------------------------ vista previa
  const vista = C.vistaPrevia($("iframe[data-vista-previa]"));
  let temporizador;
  function programarVista() { clearTimeout(temporizador); temporizador = setTimeout(enviarVista, 200); }
  // «300 123 4567» -> «+573001234567», como lo guarda el servidor (así sirve el enlace de WhatsApp).
  const internacional = (n) => { const x = String(n || "").replace(/\D/g, ""); return x.length === 10 ? "+57" + x : n || null; };
  function enviarVista() {
    const d = datos();
    vista.enviar({
      negocio: {
        tagline: d.tagline || null, description: d.description || null, welcome_message: d.welcome_message || null,
        contact: { whatsapp: internacional(d.whatsapp), phone: internacional(d.phone), email: d.email || null,
                   address: d.address || null, city: d.city || null, maps_url: d.maps_url || null },
        social: { instagram: d.instagram || null, facebook: d.facebook || null, tiktok: d.tiktok || null },
        hours: d.hours,
      },
    });
  }
  enviarVista();
})();
