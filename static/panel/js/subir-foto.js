/* Cloudin · ImageUploader: cámara o galería → recorte → compresión en el navegador → subida.
 *
 * <div class="subir-foto" data-subir-foto data-url="/api/…/image/" data-proporcion="1" data-lado="1200">
 *   … <input type="file" accept="image/*" capture="environment"> (cámara) y otro sin capture (galería)
 * </div>
 * Sin data-url, la foto queda en el elemento (el.foto, un Blob) y se avisa con el evento
 * «foto-lista». Con data-url, se sube (con barra de avance) y se avisa con «foto-subida».
 * El servidor la vuelve a validar y la guarda en WebP (apps/catalog/images.py).
 */
(function () {
  "use strict";
  const C = (window.Cloudin = window.Cloudin || {});
  const MAX_MB = 25;

  function dialogoRecorte() {
    let d = document.getElementById("dialogo-recorte");
    if (d) return d;
    d = document.createElement("dialog");
    d.id = "dialogo-recorte";
    d.setAttribute("aria-labelledby", "titulo-recorte");
    d.innerHTML = `
      <h2 id="titulo-recorte">Ajusta la foto</h2>
      <p class="dim small" style="margin-bottom:12px">Arrástrala con el dedo para encuadrar el plato.</p>
      <div class="recorte" tabindex="0" aria-label="Encuadre de la foto: arrastra o usa las flechas"><canvas></canvas></div>
      <label class="recorte-zoom"><span class="small">Acercar</span>
        <input type="range" min="1" max="3" step="0.01" value="1" aria-label="Acercar la foto"></label>
      <div class="acciones-dialogo">
        <button type="button" class="btn fantasma" data-cerrar>Cancelar</button>
        <button type="button" class="btn" data-usar>Usar foto</button>
      </div>`;
    document.body.appendChild(d);
    return d;
  }

  function recortar(bitmap, proporcion) {
    return new Promise((resolver) => {
      const d = dialogoRecorte();
      const lienzo = d.querySelector("canvas");
      const marco = d.querySelector(".recorte");
      const zoom = d.querySelector("input[type=range]");
      marco.style.aspectRatio = String(proporcion);
      const W = 900, H = Math.round(900 / proporcion);
      lienzo.width = W;
      lienzo.height = H;
      const ctx = lienzo.getContext("2d");
      const base = Math.max(W / bitmap.width, H / bitmap.height);
      let escala = 1, x = 0, y = 0;
      const limitar = () => {
        const w = bitmap.width * base * escala, h = bitmap.height * base * escala;
        x = Math.min(0, Math.max(W - w, x));
        y = Math.min(0, Math.max(H - h, y));
      };
      const pintar = () => {
        limitar();
        ctx.fillStyle = "#000";
        ctx.fillRect(0, 0, W, H);
        ctx.drawImage(bitmap, x, y, bitmap.width * base * escala, bitmap.height * base * escala);
      };
      x = (W - bitmap.width * base) / 2;
      y = (H - bitmap.height * base) / 2;
      zoom.value = 1;
      pintar();

      let arrastre = null;
      const factor = () => W / marco.getBoundingClientRect().width;
      marco.onpointerdown = (ev) => { arrastre = { x: ev.clientX, y: ev.clientY }; marco.setPointerCapture(ev.pointerId); };
      marco.onpointermove = (ev) => {
        if (!arrastre) return;
        x += (ev.clientX - arrastre.x) * factor();
        y += (ev.clientY - arrastre.y) * factor();
        arrastre = { x: ev.clientX, y: ev.clientY };
        pintar();
      };
      marco.onpointerup = marco.onpointercancel = () => { arrastre = null; };
      marco.onkeydown = (ev) => {
        const pasos = { ArrowLeft: [20, 0], ArrowRight: [-20, 0], ArrowUp: [0, 20], ArrowDown: [0, -20] };
        if (pasos[ev.key]) { ev.preventDefault(); x += pasos[ev.key][0]; y += pasos[ev.key][1]; pintar(); }
      };
      zoom.oninput = () => {
        const antes = escala;
        escala = Number(zoom.value);
        x = W / 2 - (W / 2 - x) * (escala / antes);
        y = H / 2 - (H / 2 - y) * (escala / antes);
        pintar();
      };
      marco.onwheel = (ev) => {
        ev.preventDefault();
        zoom.value = Math.min(3, Math.max(1, Number(zoom.value) - ev.deltaY / 500));
        zoom.oninput();
      };
      let listo = false;
      d.querySelector("[data-usar]").onclick = () => { listo = true; d.close(); resolver({ x, y, escala, base, W, H }); };
      d.addEventListener("close", () => { if (!listo) resolver(null); }, { once: true });
      C.abrir(d);
    });
  }

  function exportar(bitmap, corte, ladoMayor, proporcion) {
    const w = proporcion >= 1 ? ladoMayor : Math.round(ladoMayor * proporcion);
    const h = Math.round(w / proporcion);
    const lienzo = document.createElement("canvas");
    lienzo.width = w;
    lienzo.height = h;
    const f = w / corte.W;
    const ctx = lienzo.getContext("2d");
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(bitmap, corte.x * f, corte.y * f, bitmap.width * corte.base * corte.escala * f,
      bitmap.height * corte.base * corte.escala * f);
    return new Promise((resolver) => lienzo.toBlob((blob) => {
      if (blob && blob.type === "image/webp") return resolver(new File([blob], "foto.webp", { type: "image/webp" }));
      lienzo.toBlob((jpg) => resolver(new File([jpg], "foto.jpg", { type: "image/jpeg" })), "image/jpeg", 0.85);
    }, "image/webp", 0.85));
  }

  async function procesar(caja, archivo) {
    if (!archivo) return;
    if (!/^image\//.test(archivo.type)) return C.aviso("Ese archivo no es una foto. Elige una imagen.", { tipo: "error" });
    if (archivo.size > MAX_MB * 1024 * 1024) return C.aviso(`La foto pesa más de ${MAX_MB} MB.`, { tipo: "error" });
    let bitmap;
    try {
      bitmap = await createImageBitmap(archivo, { imageOrientation: "from-image" });
    } catch (e) {
      return C.aviso("No pudimos abrir esa foto. Prueba con otra (JPG o PNG).", { tipo: "error" });
    }
    const proporcion = Number(caja.dataset.proporcion || 1);
    const corte = await recortar(bitmap, proporcion);
    if (!corte) return;
    const foto = await exportar(bitmap, corte, Number(caja.dataset.lado || 1200), proporcion);
    const vista = caja.querySelector("img.vista");
    if (vista) {
      vista.src = URL.createObjectURL(foto);
      vista.hidden = false;
      vista.alt = "Vista previa de la foto";
    }
    caja.classList.add("con-foto");
    const texto = caja.querySelector(".texto-galeria");
    if (texto) texto.textContent = "Cambiar";
    caja.foto = foto;
    if (!caja.dataset.url) {
      caja.dispatchEvent(new CustomEvent("foto-lista", { detail: { foto }, bubbles: true }));
      return;
    }
    const barra = caja.querySelector(".progreso");
    if (barra) barra.hidden = false;
    try {
      const respuesta = await C.pedir(caja.dataset.url, {
        metodo: "POST", archivo: foto,
        alProgreso: (p) => { if (barra) barra.firstElementChild.style.width = Math.round(p * 100) + "%"; },
      });
      C.aviso("Foto guardada");
      caja.dispatchEvent(new CustomEvent("foto-subida", { detail: respuesta, bubbles: true }));
    } catch (e) {
      C.aviso(e.detalle || "No se pudo subir la foto.", { tipo: "error" });
    } finally {
      if (barra) { barra.hidden = true; barra.firstElementChild.style.width = "0"; }
    }
  }

  C.engancharFotos = function (raiz = document) {
    raiz.querySelectorAll("[data-subir-foto]").forEach((caja) => {
      if (caja.dataset.fotoLista) return;
      caja.dataset.fotoLista = "1";
      caja.querySelectorAll("input[type=file]").forEach((input) => input.addEventListener("change", () => {
        procesar(caja, input.files[0]);
        input.value = "";
      }));
      // En el computador también se puede soltar una foto encima.
      caja.addEventListener("dragover", (ev) => { ev.preventDefault(); caja.classList.add("arrastrando"); });
      caja.addEventListener("dragleave", () => caja.classList.remove("arrastrando"));
      caja.addEventListener("drop", (ev) => {
        ev.preventDefault();
        caja.classList.remove("arrastrando");
        procesar(caja, ev.dataTransfer.files[0]);
      });
    });
  };
  document.addEventListener("DOMContentLoaded", () => C.engancharFotos());
})();
