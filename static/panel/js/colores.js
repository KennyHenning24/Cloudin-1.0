/* Cloudin · colores sugeridos a partir del logo del restaurante.
 *
 * Cloudin.coloresDeImagen(img) → [{primary, secondary, background, text}, …] (hasta 3 combinaciones)
 * Lee la imagen en un lienzo pequeño, agrupa los colores parecidos y elige los más
 * presentes con buena saturación. Cada combinación ya trae un texto que se lee bien
 * sobre su fondo (contraste AA, 4,5:1).
 */
(function () {
  "use strict";
  const C = (window.Cloudin = window.Cloudin || {});

  const hex = (r, g, b) => "#" + [r, g, b].map((v) => Math.round(v).toString(16).padStart(2, "0")).join("").toUpperCase();
  function hsl(r, g, b) {
    r /= 255; g /= 255; b /= 255;
    const max = Math.max(r, g, b), min = Math.min(r, g, b), l = (max + min) / 2;
    const s = max === min ? 0 : (max - min) / (1 - Math.abs(2 * l - 1));
    return { s, l };
  }
  const contraste = (a, b) => (C.contraste ? C.contraste(a, b) : 21);

  C.coloresDeImagen = function (img) {
    const lado = 64;
    const lienzo = document.createElement("canvas");
    lienzo.width = lienzo.height = lado;
    const ctx = lienzo.getContext("2d", { willReadFrequently: true });
    try { ctx.drawImage(img, 0, 0, lado, lado); } catch (e) { return []; }
    let px;
    try { px = ctx.getImageData(0, 0, lado, lado).data; } catch (e) { return []; }
    const cubetas = new Map();
    for (let i = 0; i < px.length; i += 4) {
      if (px[i + 3] < 200) continue; // transparente
      const [r, g, b] = [px[i], px[i + 1], px[i + 2]];
      const llave = (r >> 4) + "," + (g >> 4) + "," + (b >> 4);
      const c = cubetas.get(llave) || { n: 0, r: 0, g: 0, b: 0 };
      c.n++; c.r += r; c.g += g; c.b += b;
      cubetas.set(llave, c);
    }
    const colores = [...cubetas.values()].map((c) => {
      const r = c.r / c.n, g = c.g / c.n, b = c.b / c.n;
      return { hex: hex(r, g, b), n: c.n, ...hsl(r, g, b) };
    });
    // Los «de marca»: saturados y ni casi blancos ni casi negros, del más presente al menos.
    const vivos = colores.filter((c) => c.s > 0.35 && c.l > 0.18 && c.l < 0.82).sort((a, b) => b.n - a.n);
    const distintos = [];
    for (const c of vivos) {
      if (distintos.every((d) => contraste(d.hex, c.hex) > 1.35)) distintos.push(c);
      if (distintos.length === 3) break;
    }
    if (!distintos.length) return [];
    const oscuro = colores.filter((c) => c.l < 0.16).sort((a, b) => b.n - a.n)[0];
    const fondos = [["#FFFFFF", "#1D2029"], [oscuro ? oscuro.hex : "#151515", "#FFF8F0"], ["#FFF8F0", "#2A1D14"]];
    const salida = [];
    fondos.forEach(([fondo, texto], i) => {
      const primario = distintos[i % distintos.length].hex;
      const secundario = (distintos[(i + 1) % distintos.length] || distintos[0]).hex;
      // El principal va en botones con el color de fondo como texto: si no se lee, se prueba otro fondo.
      if (contraste(primario, fondo) >= 3) salida.push({ primary: primario, secondary: secundario, background: fondo, text: texto });
    });
    return salida;
  };
})();
