/* Service worker del panel de Cloudin (se sirve desde /panel/sw.js, alcance /panel/).
 *
 * Que el panel se instale como app y que un bajón de wifi no lo deje en blanco:
 *  - /static/        -> caché primero (CSS, JS, fuentes e íconos; cambian con la versión).
 *  - pantallas       -> siempre red; sin red, la página «Sin conexión» (guardada al instalar).
 *                       Las pantallas con datos del restaurante NO se guardan: después de
 *                       cerrar sesión nadie las puede ver desde la caché.
 *  - /api/           -> siempre red. Los cambios sin conexión los guarda el panel en su
 *                       cola (ui.js) y los reenvía al volver internet.
 */
const VERSION = "cloudin-panel-__VERSION__";
const SIN_CONEXION = "/panel/sin-conexion/";
const BASICOS = [
  SIN_CONEXION,
  "/static/css/cloudin.css",
  "/static/panel/js/base.js",
  "/static/panel/js/ui.js",
  "/static/fonts/plus-jakarta-sans-latin.woff2",
  "/static/img/cloudin-marca.png",
];

self.addEventListener("install", (evento) => {
  evento.waitUntil(caches.open(VERSION).then((cache) => cache.addAll(BASICOS)).catch(() => null));
  self.skipWaiting();
});

self.addEventListener("activate", (evento) => {
  evento.waitUntil(
    caches.keys().then((llaves) => Promise.all(
      llaves.filter((l) => l.startsWith("cloudin-panel-") && l !== VERSION).map((l) => caches.delete(l)),
    )),
  );
  self.clients.claim();
});

self.addEventListener("fetch", (evento) => {
  const peticion = evento.request;
  if (peticion.method !== "GET") return;
  const url = new URL(peticion.url);
  if (url.origin !== self.location.origin || url.pathname.startsWith("/api/")) return;

  if (url.pathname.startsWith("/static/")) {
    evento.respondWith(
      caches.match(peticion).then((guardada) => guardada || fetch(peticion).then((respuesta) => {
        if (respuesta.ok) {
          const copia = respuesta.clone();
          caches.open(VERSION).then((cache) => cache.put(peticion, copia));
        }
        return respuesta;
      })),
    );
    return;
  }

  if (peticion.mode === "navigate" && url.pathname.startsWith("/panel/")) {
    evento.respondWith(fetch(peticion).catch(() => caches.match(SIN_CONEXION)));
  }
});
