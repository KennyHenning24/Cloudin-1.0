/* Service worker de Cloudin Meseros.
 *
 * Objetivo modesto y concreto: que la app abra rápido en la tablet y que un
 * bajón de wifi no deje la pantalla en blanco.
 *
 *  - /static/          -> caché primero (logos, íconos: casi nunca cambian).
 *  - la página de app  -> red primero; sin red, la última copia guardada.
 *  - /api/             -> siempre red. Los pedidos nunca se sirven de caché:
 *                         un menú o un estado de mesa viejo es peor que un aviso
 *                         de «sin conexión».
 */
const VERSION = "cloudin-meseros-__VERSION__";

self.addEventListener("install", (evento) => {
  evento.waitUntil(
    caches.open(VERSION).then((cache) =>
      cache.addAll([
        "/static/img/cloudin-marca.png",
        "/static/img/cloudin-texto.png",
        "/static/img/favicon-512.png",
        "/static/img/apple-touch-icon.png",
      ]).catch(() => null)
    )
  );
  self.skipWaiting();
});

self.addEventListener("activate", (evento) => {
  evento.waitUntil(
    caches.keys().then((llaves) =>
      Promise.all(llaves.filter((l) => l !== VERSION).map((l) => caches.delete(l)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (evento) => {
  const peticion = evento.request;
  if (peticion.method !== "GET") return;
  const url = new URL(peticion.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.includes("/api/")) return;

  if (url.pathname.startsWith("/static/")) {
    evento.respondWith(
      caches.match(peticion).then((guardada) =>
        guardada ||
        fetch(peticion).then((respuesta) => {
          const copia = respuesta.clone();
          caches.open(VERSION).then((cache) => cache.put(peticion, copia));
          return respuesta;
        })
      )
    );
    return;
  }

  if (peticion.mode === "navigate") {
    evento.respondWith(
      fetch(peticion)
        .then((respuesta) => {
          if (respuesta.ok && !respuesta.redirected) {
            const copia = respuesta.clone();
            caches.open(VERSION).then((cache) => cache.put(peticion, copia));
          }
          return respuesta;
        })
        .catch(() => caches.match(peticion))
    );
  }
});
