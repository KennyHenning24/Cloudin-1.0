# Guía del menú digital: Cloudflare Pages + Cloudin

> **Para quién es:** para ti (o para Claude, o cualquier desarrollador) cuando armes el
> menú digital de un restaurante: la página que abre el cliente al escanear el QR de su
> mesa. Explica qué tecnologías usar, cómo publicarla en Cloudflare Pages y cómo habla
> con Cloudin para **leer la carta** (precios, fotos, datos del negocio) y **mandar
> pedidos a la mesa** con un carrito de compras.
>
> Todo lo que dice existe en el código y está probado (`tests/test_pedidos_menu_digital.py`
> y un recorrido real en el navegador). La implementación de referencia está en
> `client/example/`: `index.html` (la carta) y `carrito.js` (el carrito y el pedido).
>
> **¿Eres Claude Code creando un menú?** Lee **`CLAUDE-MENU-DIGITAL.md`**: es la versión
> completa y ordenada para ti (incluye cargar la carta con `menu.seed.json`).
>
> **¿Primera vez?** El paso a paso, con los nombres exactos de cada pantalla, desde
> registrar el restaurante hasta el pedido de prueba, y la plantilla mínima
> (`client/plantilla/index.html`) están en **`PASO-A-PASO-NUEVO-RESTAURANTE.md`**.

---

## 0. En 30 segundos

1. **Cloudin** (Django) es el backend: guarda la carta, las fotos, las mesas y los
   pedidos, y tiene el panel del restaurante y la app de meseros. Corre en un servidor
   con Docker: gratis en Render (`DESPLIEGUE-GRATIS.md`) o en Cloudflare Containers con
   el plan pago (`DESPLIEGUE-CLOUDFLARE.md`). En esta guía su dirección es
   `https://<servidor-cloudin>`.
2. **El menú digital** de cada cliente es un sitio **estático** (HTML, CSS y JavaScript)
   publicado en **Cloudflare Pages**. No tiene base de datos ni servidor propio: lee y
   escribe en Cloudin por HTTP.
3. La página carga tres cosas: tu diseño, `cloudin-menu.v1.js` (pinta la carta) y
   `carrito.js` (el botón «Agregar», el carrito y el envío).
4. El QR de cada mesa abre `https://<tu-menu>/?mesa=<token>`. Con ese token la página
   puede pedir; sin token, la carta queda solo para mirar.
5. **El precio lo calcula siempre Cloudin.** La página lo muestra, pero el que vale es el
   del servidor.
6. **La mesa se ocupa sola** con el primer pedido que se envía y queda **libre** cuando el
   restaurante cierra la cuenta en su panel. No hay reservas ni turno de caja: los pedidos
   entran a cualquier hora.

---

## 1. Cómo encaja todo

```
 Teléfono del cliente                              Internet
 ┌───────────────────────────┐   HTML, CSS, JS   ┌──────────────────────────────────┐
 │ Escanea el QR de la mesa ─┼──────────────────▶│ Cloudflare Pages: el menú de ESTE │
 │ menu.html?mesa=<token>    │                   │ cliente (estático, gratis)        │
 │                           │                   ├──────────────────────────────────┤
 │ cloudin-menu.v1.js ───────┼── carta (JSON) ──▶│ Servidor de Cloudin (Django):     │
 │ carrito.js ───────────────┼── carrito/pedido ▶│ Render gratis o Cloudflare        │
 └───────────────────────────┘                   │ Containers ── Postgres (Neon)     │
                                                  └──────────────────────────────────┘
 Panel del restaurante (/panel/) y app de meseros (/mesero/<slug>/) ──▶ el mismo Cloudin
```

| Quién | Qué hace | Dónde |
|---|---|---|
| El restaurante | Edita la carta: productos, precios, fotos, agotados, colores | Panel → **Mi menú** y **Personalizar** |
| El menú digital | Muestra la carta tal como está en el panel, sin volver a publicarlo | Cloudflare Pages |
| El cliente | Arma el pedido con los de su mesa y lo envía | Menú digital (QR) |
| El restaurante | Ve la mesa ocupada, el pedido en **Mensajes** y la comanda en **Cocina**; cierra la cuenta | Panel → **Mesas**, **Mensajes**, **Cocina** |
| Los meseros | Ven las mismas mesas y suman pedidos a la misma cuenta | Cloudin Meseros (`/mesero/<slug>/`) |

Cambiar un precio o marcar un plato agotado en el panel se ve en el menú al instante (a
lo sumo en 30 s por la caché): **no hay que volver a publicar la página**. Solo se vuelve
a publicar cuando cambias el diseño.

---

## 2. Tecnologías

### 2.1 Qué usar

| Pieza | Recomendación | Por qué |
|---|---|---|
| El menú | **HTML + CSS + JavaScript sin framework**, como `client/example/` | Carga rápido con datos móviles, Pages lo sirve tal cual y no hay nada que compilar. |
| Si quieres plantillas o componentes | **Astro** (u otro generador) con salida **estática** | Genera HTML puro. Pages lo construye con `npm run build`. Opcional. |
| Pintar la carta | **`cloudin-menu.v1.js`**, servido por Cloudin | Lee la carta, la guarda en caché, la pinta con tus plantillas y respeta agotados y horarios. |
| Carrito y pedido | **`client/example/carrito.js`** tal cual o adaptado | Ya resuelve el carrito compartido, tamaños y adiciones, conflictos entre teléfonos y el envío. |
| Backend | **Cloudin** (Django + Django REST Framework), el que ya existe | Ver 2.2. |
| Hosting del menú | **Cloudflare Pages** | Gratis para archivos estáticos, HTTPS y CDN incluidos, se publica solo con cada `git push`. |
| Hosting del backend | **Render** gratis (`render.yaml`) o **Cloudflare Containers** pago (`wrangler.jsonc`) | Pages no ejecuta Python. Los dos usan el mismo `Dockerfile`. |

### 2.2 ¿Django o FastAPI para la API?

**Quédate con Django.** La API que necesita el menú digital ya existe, está probada y
corre en Cloudflare:

- Cloudin no es solo la API: es el panel del restaurante, la app de meseros, el panel
  maestro, el admin, los usuarios, las migraciones y una base de datos por restaurante.
  Todo eso es Django. Pasar a FastAPI sería reescribirlo entero para llegar al mismo punto.
- Django REST Framework entrega el mismo JSON que entregaría FastAPI. Para el tráfico de
  un restaurante (decenas de mesas consultando cada pocos segundos) sobra.
- Para el menú digital da igual: habla HTTP + JSON. El contrato de esta guía es el mismo
  sea cual sea el backend, así que la decisión se puede revisar algún día sin tocar los
  menús.

### 2.3 Qué evitar

- **React, Next.js o una SPA con bundler:** un menú es una página; un framework pesado
  solo la vuelve lenta con datos móviles. Si igual lo usas, expórtalo estático.
- **Renderizar en el servidor o poner Pages Functions de «proxy» delante de Cloudin:**
  todos los clientes saldrían a Cloudin con la misma IP y los topes por IP (sección 8)
  bloquearían al restaurante entero. Llama a Cloudin directo desde el navegador.
- **Guardar el carrito solo en el teléfono** si quieres que los de la mesa pidan juntos:
  el carrito compartido vive en Cloudin (sección 6).

---

## 3. Lo que necesitas de cada cliente

| Dato | Dónde se ve | Ejemplo |
|---|---|---|
| Dirección del servidor Cloudin (`<servidor-cloudin>`) | Render: arriba en la página del servicio (`DESPLIEGUE-GRATIS.md`). Cloudflare: la del Worker (`DESPLIEGUE-CLOUDFLARE.md`) | `https://cloudin.onrender.com` o `https://cloudin-1-0.<tu-cuenta>.workers.dev` |
| Identificador (slug) | Panel maestro `/master/` | `culturabrisket` |
| Llave de conexión (`ck_…`) | Panel maestro → el restaurante → **API key** (o su panel → Configuración → Sitio web) | `ck_Xa3…` |
| Plan | Panel maestro | **Cloudin completo** para recibir pedidos |
| Cómo se toman los pedidos | Su panel → **Meseros** (o `/admin/` → Restaurantes → «Sitio web y menú») | Autoservicio, o Ambos |
| Mesas | Su panel → **Códigos QR** (crear mesas 1..N) | Mesas 1 a 12 |

¿El menú digital de este cliente recibe pedidos?

| Plan | Cómo se toman los pedidos | ¿Recibe pedidos por el QR? |
|---|---|---|
| Menú digital | cualquiera | **No.** La carta queda para mirar: su panel no tiene dónde ver pedidos. Cloudin responde `recibe_pedidos: false` y rechaza con `403 sin_pedidos`. |
| Cloudin completo | Autoservicio | **Sí.** |
| Cloudin completo | Ambos (QR y meseros) | **Sí**, y los meseros también piden desde su app. |
| Cloudin completo | Solo meseros | **No** (`403 solo_meseros`): el mesero toma el pedido en su app. |

`carrito.js` lee `recibe_pedidos` y no muestra el botón «Agregar» cuando es falso, así que
puedes usar la misma plantilla para todos los clientes.

---

## 4. Publicar el menú en Cloudflare Pages, paso a paso

### 4.1 La carpeta del menú

Empieza copiando `client/example/` a un repositorio nuevo (uno por cliente), o, más
simple, `client/plantilla/index.html` (la plantilla mínima, comentada) junto con
`client/example/carrito.js`:

```
menu-culturabrisket/
├── index.html      ← la carta: tu diseño + las plantillas data-cloudin (sección 5.4)
├── carrito.js      ← copia de client/example/carrito.js
├── assets/         ← logo, fuentes e imágenes del diseño
└── _headers        ← opcional (4.7)
```

Las fotos de los platos **no** van aquí: las sube el restaurante en su panel y llegan en la
carta como direcciones absolutas.

### 4.2 Conectar la página con Cloudin

Al final de `index.html`, en este orden:

```html
<script>
  window.CLOUDIN_CONFIG = {
    restaurant: "culturabrisket",                    // el slug
    api: "https://<servidor-cloudin>/api/public/culturabrisket/menu/",
    contract: 1,
    locale: "es-CO",
    currency: "COP",
    hideSoldOut: false,   // true = no mostrar lo agotado (false = se ve apagado)
    cacheTtl: 60,         // segundos que la carta guardada en el teléfono se da por buena
    apiKey: "ck_…"        // solo si el restaurante recibe pedidos por el QR (sección 3)
  };
</script>
<script src="https://<servidor-cloudin>/static/cloudin-menu.v1.js" defer></script>
<script src="carrito.js" defer></script>
```

- `api` apunta a **la carta pública** del restaurante; `carrito.js` saca de ahí también la
  dirección del servidor para los pedidos.
- Sin `apiKey`, o si la página se abre sin `?mesa=<token>`, `carrito.js` no hace nada y la
  carta queda para mirar (por ejemplo, desde Instagram).

### 4.3 Crear el proyecto en Pages

1. Sube la carpeta a un repositorio de GitHub (o GitLab).
2. En el panel de Cloudflare: **Workers & Pages** → **Create application** → pestaña
   **Pages** → **Import an existing Git repository** → elige el repositorio →
   **Begin setup**.
3. En **Set up builds and deployments**:

   | Opción | Valor sin framework | Valor con Astro |
   |---|---|---|
   | Production branch | `main` | `main` |
   | Framework preset | None | Astro |
   | Build command | *(vacío)* | `npm run build` |
   | Build output directory | `/` (la carpeta donde está `index.html`) | `dist` |

   El **Project name** será la dirección: `https://<project-name>.pages.dev`.
4. **Save and Deploy**. En menos de un minuto queda publicado.

Desde ahí, **cada `git push` a `main` publica** la versión nueva. Las otras ramas y los
pull requests generan una **vista previa** con su propia dirección
(`https://<rama>.<project-name>.pages.dev`), sin tocar la de producción. Pages sirve los
archivos con `ETag` y los revalida en cada visita, así que un cambio publicado se ve de
inmediato.

> **Pages o Workers.** La documentación de Cloudflare ahora sugiere Workers (con
> «static assets») para proyectos nuevos. Para un menú estático los dos son gratis y
> funcionan igual con Cloudin; esta guía usa Pages porque es lo más simple. Dos límites a
> tener en cuenta: Pages permite **100 proyectos por cuenta** (si pasas de ~100 clientes,
> usa Workers o un solo proyecto con una carpeta por cliente), y en Workers el dominio
> propio exige que el DNS del dominio esté en Cloudflare (Pages también acepta un CNAME
> desde otro proveedor).

### 4.4 Registrar la página en Cloudin

En el panel maestro (`https://<servidor-cloudin>/master/`) → el restaurante → tarjeta
**«Menú digital»**: «Página del menú (QR)» y «Otras direcciones autorizadas» (una por
línea). Esa tarjeta dice además si algún menú ya pidió la carta y trae el bloque
`CLOUDIN_CONFIG` listo para copiar. Lo mismo está en `https://<servidor-cloudin>/admin/` →
**Restaurantes** → el restaurante → sección **«Sitio web y menú»**:

| Campo | Qué poner | Para qué |
|---|---|---|
| **Página del menú (QR)** | La dirección exacta de la página: `https://culturabrisket.pages.dev/` | Con ella se generan los QR (`…?mesa=<token>`) y queda autorizada para pedir |
| **Otros sitios autorizados** | Lista JSON de orígenes extra: `["https://menu.culturabrisket.com"]` | Dominio propio, rama de pruebas, etc. |
| **Cómo se toman los pedidos** | Autoservicio o Ambos (el restaurante también lo cambia en su panel → **Meseros**) | Ver la tabla de la sección 3 |

Por qué importa: el navegador **solo deja pedir desde los orígenes registrados**
(esquema + dominio + puerto, sin ruta). Leer la carta funciona desde cualquier lado; los
pedidos no. Si ves un error de CORS en la consola, el origen de la página no coincide
exactamente con lo registrado (`http` vs `https`, `www`, puerto).

### 4.5 Imprimir los QR

En el panel del restaurante → **Códigos QR** (pantalla «Mesas y QR»): ahí se crean las
mesas («¿Cuántas mesas tienes?»), y cada una tiene su QR
(`https://culturabrisket.pages.dev/?mesa=<token>`) para descargar en PNG o SVG; hay además
un PDF con todas (4 por hoja). Mientras no haya «Página del menú», el panel avisa que el QR
aparece cuando el menú esté publicado. El **QR general del menú** (para la entrada o las
redes) abre la carta sin mesa: sirve para mirar, no para pedir.

**Imprime los QR cuando el dominio sea el definitivo.** Si luego cambias la «Página del
menú», los QR nuevos cambian; los viejos siguen funcionando mientras la dirección vieja
siga publicada y autorizada (déjala en «Otros sitios autorizados»).

El token de una mesa no cambia solo. Si hay que invalidar un QR (lo fotografiaron y están
haciendo bromas), hoy se hace desde la consola con `Table.rotate_token()` dentro del
restaurante, y se reimprime ese QR.

### 4.6 Dominio propio (opcional)

1. En Pages: el proyecto → **Custom domains** → **Set up a custom domain** →
   `menu.culturabrisket.com`. Si el DNS del dominio está en Cloudflare, el registro se crea
   solo; si no, crea un CNAME hacia `<project-name>.pages.dev` donde esté el DNS.
2. En Cloudin (4.4): pon la dirección nueva como **Página del menú** (si todavía no hay QR
   impresos) o agrégala a **Otros sitios autorizados** (si ya los hay con `pages.dev`).

### 4.7 Cabeceras (`_headers`, opcional)

Un archivo `_headers` en la raíz de lo que se publica:

```
/*
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
  Permissions-Policy: camera=(), microphone=(), geolocation=()
  Content-Security-Policy: frame-ancestors 'self' https://<servidor-cloudin>
```

- **No pongas `X-Frame-Options: DENY`**: el panel del restaurante (Personalizar) muestra
  el menú dentro de un marco para la vista previa. `frame-ancestors` con la dirección de
  Cloudin protege igual y deja la vista previa funcionando.
- Si agregas una política de contenido más estricta (`script-src`, `connect-src`,
  `img-src`), permite la dirección de Cloudin en las tres, y ten en cuenta que el ejemplo
  usa `<script>` en línea para `CLOUDIN_CONFIG`.

### 4.8 Vistas previas y CORS

La carta pública responde a cualquier origen, así que una vista previa de Pages
(`https://<rama>.<proyecto>.pages.dev`) muestra el menú completo. **Pedir** desde ahí
falla por CORS mientras ese origen no esté registrado. Para probar pedidos en una rama,
agrega su dirección estable a «Otros sitios autorizados» (nunca `*`) y quítala al
terminar.

---

## 5. Leer la carta: precios e información

### 5.1 La petición

```
GET https://<servidor-cloudin>/api/public/<slug>/menu/
GET https://<servidor-cloudin>/api/public/<slug>/menu/?table=<token>
```

| | |
|---|---|
| Autenticación | Ninguna: son datos públicos. |
| CORS | Abierto (`Access-Control-Allow-Origin: *`), sin cookies. |
| Caché | `Cache-Control: public, max-age=30` y `ETag`. Manda `If-None-Match` y recibes `304` si nada cambió. |
| Tope | 600 consultas cada 10 minutos por IP (un restaurante lleno comparte el wifi). |
| `?table=` | Con el token del QR (o el número de mesa), la respuesta trae `"table": {"number": 3}`. |
| Errores | `404` si el restaurante no existe o está inactivo; `429` si se pasa el tope. |

### 5.2 La respuesta

```json
{
  "schema": "cloudin.menu/v1",
  "business": {
    "slug": "la-casa",
    "name": "La Casa",
    "tagline": "Comida casera",
    "description": null,
    "logo": "https://<servidor-cloudin>/media/…/logo.webp",
    "cover": null,
    "brand": { "primary": "#B3261E", "secondary": "#F2C14E", "background": "#1A1110", "text": null },
    "contact": { "whatsapp": null, "phone": "+573001234567", "email": null,
                 "address": "Cra 1 # 2-3", "city": "Cali", "maps_url": null },
    "social": { "instagram": null, "facebook": null, "tiktok": null },
    "hours": [ { "day": "mon", "closed": true },
               { "day": "tue", "open": "12:00", "close": "21:00" } ],
    "services": { "dine_in": true, "takeaway": false, "delivery": false },
    "payment_methods": []
  },
  "menus": [
    {
      "id": "ec32812d-…", "key": "carta", "name": "Carta", "description": null,
      "availability": { "days": [], "from": null, "to": null },
      "categories": [
        {
          "id": "7eb185b8-…", "key": "hamburguesas", "name": "Hamburguesas",
          "description": null, "image": null,
          "products": [
            {
              "id": "6f1c2a90-…", "key": "hamburguesa", "name": "Hamburguesa",
              "description": "Carne de res, queso y papas.",
              "price": 24000,
              "image": "https://<servidor-cloudin>/media/…/hamburguesa.webp",
              "available": true, "featured": false, "tags": ["recomendado"], "tax": null,
              "variants": [
                { "id": "9a2e41c7-…", "key": "doble-carne", "name": "Doble carne", "price": 32000 }
              ],
              "modifier_groups": [
                { "id": "…", "key": "salsa", "name": "Salsa", "min": 1, "max": 1,
                  "options": [ { "id": "c1d0…", "key": "verde", "name": "Verde", "price": 0 },
                               { "id": "c2e7…", "key": "roja", "name": "Roja", "price": 1500 } ] },
                { "id": "…", "key": "adiciones", "name": "Adiciones", "min": 0, "max": 3,
                  "options": [ { "id": "d1a4…", "key": "queso", "name": "Queso", "price": 3000 },
                               { "id": "d2b9…", "key": "tocineta", "name": "Tocineta", "price": 4000 } ] }
              ]
            }
          ]
        }
      ]
    }
  ],
  "tags": [ { "key": "recomendado", "name": "Recomendado" } ],
  "meta": { "version": 4 },
  "table": { "number": 1 }
}
```

### 5.3 Qué significa cada campo (lo que importa para pedir)

| Campo | Qué es |
|---|---|
| `product.id` | **El id para pedir** (UUID). No cambia aunque el restaurante renombre el plato. |
| `product.key` | Clave legible y estable; es la que usa el HTML (`data-cloudin-key`). |
| `product.price` | Precio en pesos, entero. `null` = todavía sin precio: se muestra pero no se puede pedir. |
| `product.available` | `false` = agotado hoy: mostrarlo apagado y sin botón de pedir. |
| `variants[]` | Presentaciones (tamaño, peso). **`price` es el precio completo** de esa presentación, no una diferencia. Sin elegir ninguna, vale la del producto. |
| `modifier_groups[]` | Preguntas al cliente: `min` ≥ 1 = obligatorio; `max` = 1 se elige una (radio); `max` = `null` sin tope. Un grupo sin opciones se ignora. |
| `options[].price` | **Lo que suma** al precio (0 si no cambia). |
| `image` | Dirección absoluta, lista para `<img src>`. |
| `tags` | Claves; el nombre para mostrar está en `tags` de la raíz. |
| `business.*` | Datos del negocio para el encabezado, el pie, WhatsApp y el horario. |
| `meta.version` | Sube con cada cambio de la carta (es parte del `ETag`). |

El precio de una línea se calcula así, **igual que lo calcula Cloudin**:

```
precio unitario = (presentación elegida ? su precio : precio del producto) + suma de las opciones elegidas
```

Ejemplo: Hamburguesa · Doble carne (32.000) + Roja (1.500) + Tocineta (4.000) = **37.500**.
Muéstralo en pantalla, pero el que se cobra es el que devuelve Cloudin.

### 5.4 Con el runtime `cloudin-menu.v1.js` (recomendado)

El runtime pinta la carta dentro de tu diseño con plantillas HTML. Lo mínimo:

- Un contenedor `data-cloudin="menu"` con `data-cloudin="categories"` adentro, y las
  plantillas `<template data-cloudin-template="category">`, `"product"`, `"variant"` y
  `"tag"` (y `"category-link"` para la barra de categorías `data-cloudin="category-nav"`).
- Campos: `data-cloudin-field="product.name"`, `"product.price"`, `"category.name"`,
  `"business.name"`…; imágenes con `data-cloudin-src="product.image"`; enlaces con
  `data-cloudin-href="business.whatsapp_link"`; condiciones con
  `data-cloudin-if="product.description"` o `"!product.available"`.
- Cada tarjeta pintada lleva `data-cloudin-key` con la clave del plato (así `carrito.js`
  sabe dónde poner el botón).
- **HTML pre-renderizado:** deja la carta escrita en el HTML (como el ejemplo). Si Cloudin
  no responde, el cliente igual ve el menú; cuando responde, el runtime lo reemplaza.

Lo que expone para tu JavaScript:

| | |
|---|---|
| `window.Cloudin.data` | La carta completa (el JSON de 5.2). |
| `window.Cloudin.table` | `{ token, number }` si la página se abrió desde el QR de una mesa. |
| `window.Cloudin.state` | `static`, `cached`, `live` o `error` (también en `data-cloudin-state`). |
| `window.Cloudin.refresh()` | Vuelve a pedir la carta. |
| Evento `cloudin:ready` | La carta ya está pintada. |
| Evento `cloudin:rendered` | Se pintó una zona; `e.detail.root` es el nodo (para animaciones). |
| Evento `cloudin:error` | Cloudin no respondió; queda lo pre-renderizado o lo guardado. |

La referencia viva de plantillas, CSS mínimo y animaciones es `client/example/index.html`.
Todas las zonas, los atributos y los campos, en tablas: `PASO-A-PASO-NUEVO-RESTAURANTE.md`
§3.4 y §3.5.

### 5.5 Sin el runtime (tu propio JavaScript)

```js
const CARTA = "https://<servidor-cloudin>/api/public/culturabrisket/menu/";

async function cargarCarta() {
  let guardada = null;
  try { guardada = JSON.parse(localStorage.getItem("carta") || "null"); } catch (e) {}
  try {
    const r = await fetch(CARTA, {
      headers: guardada?.etag ? { "If-None-Match": guardada.etag } : {},
      credentials: "omit",
    });
    if (r.status === 304) return guardada.datos;          // no cambió nada
    if (!r.ok) throw new Error("HTTP " + r.status);
    const datos = await r.json();
    try { localStorage.setItem("carta", JSON.stringify({ etag: r.headers.get("ETag"), datos })); } catch (e) {}
    return datos;
  } catch (e) {
    if (guardada) return guardada.datos;                  // sin señal: la última carta buena
    throw e;
  }
}
```

Escapa **todo** texto que venga de la carta antes de meterlo con `innerHTML` (o usa
`textContent`): lo escribe el restaurante.

---

## 6. Pedir desde la mesa (autoservicio con carrito)

### 6.1 Cómo se identifica la mesa

- El QR lleva el **token** de la mesa: `?mesa=td8vIrnwaZPF` (12 caracteres al azar).
- Cada petición de pedido lleva la cabecera **`X-API-Key: ck_…`** (dice de qué restaurante
  es) y el token va en la ruta (dice qué mesa). El cliente no se registra.
- Todas las rutas de esta sección cuelgan de
  `https://<servidor-cloudin>/api/v1/mesa/<token>/`.

### 6.2 El recorrido

```
Abre el QR ──▶ GET  /api/public/<slug>/menu/?table=<token>   la carta y el número de mesa
           ──▶ GET  /api/v1/mesa/<token>/estado/              carrito y pedidos de la mesa
Agrega      ──▶ PUT  /api/v1/mesa/<token>/borrador/            {items, version}
               (otro teléfono de la misma mesa agrega lo suyo: todos ven el mismo carrito)
Envía       ──▶ POST /api/v1/mesa/<token>/enviar/              {by, note}
           ◀── 201: el pedido está en Mensajes y Cocina; la mesa quedó ocupada
Espera      ──▶ GET  /api/v1/mesa/<token>/estado/  cada 5 s:  Pendiente → En preparación → Servido
El restaurante cierra la cuenta en su panel ──▶ la mesa queda libre (ocupada: false)
```

### 6.3 Estado de la mesa — `GET …/estado/`

```json
{
  "mesa": 3,
  "recibe_pedidos": true,
  "ocupada": true,
  "cuenta": {
    "id": 46,
    "abierta_desde": "2026-09-26T22:39:30.635824Z",
    "total": 90000.0,
    "pedidos": [
      {
        "id": 48,
        "estado": "pending",
        "estado_texto": "Pendiente",
        "creado": "2026-09-26T22:39:30.636328Z",
        "por": "Ana",
        "total": 90000.0,
        "items": [
          { "nombre": "Sandwich 2 Quesos · Pastrami, Papas fritas y Coca-Cola (+$10.000)",
            "cantidad": 2, "nota": "sin pepinillos" }
        ]
      }
    ]
  },
  "borrador": { "items": [], "version": 14, "total": 0.0, "actualizado": "2026-09-26T22:39:19.531869Z" },
  "aviso": null,
  "servidor": "2026-09-26T22:39:30.645142Z"
}
```

| Campo | Qué es |
|---|---|
| `recibe_pedidos` | Si esta página puede pedir (sección 3). Si es `false`, no muestres el carrito. |
| `ocupada` | Si la mesa tiene una cuenta abierta. |
| `cuenta` | La cuenta abierta con sus pedidos (sin los anulados), o `null` si la mesa está libre. |
| `borrador` | El carrito compartido: lo que se está armando y todavía no se envía. |
| `aviso` | Nombre de quien dijo «voy a enviar» en los últimos 20 s, o `null` (6.5). |
| `servidor` | Hora del servidor. Las fechas vienen en ISO 8601: úsalas con `new Date(…)`. |

Los totales son números en pesos. Consulta esta ruta cada 5 s **solo mientras la página
está visible** (`document.visibilityState`).

### 6.4 Guardar el carrito — `PUT …/borrador/`

```http
PUT /api/v1/mesa/td8vIrnwaZPF/borrador/
X-API-Key: ck_…
Content-Type: application/json

{
  "version": 12,
  "items": [
    { "product": "35dfb1a7-2fc1-4ee0-b1de-ec5a5cb2d4d9",
      "variant": null,
      "options": ["c8211661-9891-44e1-b93c-54ca6d8eb54a", "0d1def6e-bcb8-40f2-80bb-02fb970b2afb"],
      "quantity": 2,
      "note": "sin pepinillos",
      "by": "Ana" }
  ]
}
```

Respuesta `200`: el estado completo (6.3), con cada línea ya calculada por Cloudin:

```json
"borrador": {
  "items": [
    { "quantity": 2, "by": "Ana", "key": "3", "product_id": 3,
      "opciones": [ { "grupo": 0, "valor": 1 }, { "grupo": 1, "valor": 0 } ],
      "name": "Sandwich 2 Quesos · Pastrami, Papas fritas y Coca-Cola (+$10.000)",
      "unit_price": 45000.0, "note": "sin pepinillos",
      "product": "35dfb1a7-2fc1-4ee0-b1de-ec5a5cb2d4d9", "variant": null,
      "options": ["c8211661-9891-44e1-b93c-54ca6d8eb54a", "0d1def6e-bcb8-40f2-80bb-02fb970b2afb"] }
  ],
  "version": 13,
  "total": 90000.0
}
```

Reglas:

- **Reemplaza el carrito entero.** Para agregar un plato: toma `borrador.items` del último
  estado, agrega (o suma cantidad si es la misma línea), y manda la lista completa. Manda
  las líneas que ya estaban **tal como llegaron** (con sus `product`, `variant` y
  `options`).
- **`version`** evita pisar lo que otro teléfono acaba de agregar. Si no es la actual,
  Cloudin responde **`409`** con el estado al día (mismo formato que 6.3, más `detail`):
  vuelve a aplicar tu cambio sobre ese carrito y reintenta una vez. `carrito.js` ya lo hace.
- Una línea que no se puede cobrar (plato agotado o eliminado, falta una opción obligatoria,
  una opción que ya no existe) **no entra** al carrito, sin error. Compara lo que mandaste con
  lo que volvió para avisarle al cliente.
- Topes: 60 líneas, cantidad de 1 a 99, `by` hasta 60 caracteres, `note` hasta 200. La nota
  de un plato solo se guarda si el producto la permite (se activa en el panel).
- Armar el carrito **no ocupa la mesa**.

### 6.5 «Voy a enviar» — `POST …/aviso/` (opcional)

```json
{ "by": "Ana" }
```

Durante 20 s el estado trae `"aviso": "Ana"`, para que los demás de la mesa vean que alguien
está por enviar y no agreguen a última hora.

### 6.6 Enviar a la cocina — `POST …/enviar/`

```json
{ "by": "Ana", "note": "Somos 3, una silla para bebé" }
```

Respuesta **`201`**: el estado (6.3) con el carrito vacío, la cuenta con el pedido nuevo y
`"pedido_enviado": 48`. En ese momento:

- Si la mesa estaba libre, **se ocupa**: se abre su cuenta, el panel la muestra ocupada, el
  pedido aparece en **Mensajes** (con el aviso de «Pedidos nuevos») y la comanda en **Cocina**.
- Los precios se recalculan al enviar (pudieron cambiar mientras el carrito esperaba).
- Si la mesa ya estaba ocupada (otro pedido, o un mesero), el pedido se suma a la misma cuenta.

| Respuesta | `codigo` | Qué pasó |
|---|---|---|
| `400` | — | El carrito está vacío. |
| `400` | `opciones` | Una línea quedó inválida (cambió una opción del plato). El `detail` dice cuál. |
| `409` | `agotado` | Un plato del carrito se agotó. Quitarlo y volver a enviar. |
| `403` | `sin_pedidos` | Plan «Menú digital»: el restaurante no recibe pedidos por el QR. |
| `403` | `solo_meseros` | El restaurante trabaja solo con meseros. |
| `429` | `demasiados` | Muchos envíos seguidos desde la misma IP (sección 8). |
| `404` | — | El token no corresponde a una mesa activa (QR viejo). |

### 6.7 Pedido directo, sin carrito compartido — `POST /api/v1/tables/<token>/orders/`

Para un menú donde cada teléfono arma su propio pedido (el carrito vive en el teléfono) y lo
manda de una vez:

```http
POST /api/v1/tables/td8vIrnwaZPF/orders/
X-API-Key: ck_…
Content-Type: application/json

{
  "customer_name": "Luis",
  "note": "",
  "guests": 2,
  "items": [
    { "product": "35dfb1a7-2fc1-4ee0-b1de-ec5a5cb2d4d9",
      "options": ["d3fe50e6-a5ea-4352-a23c-3b923eecbbcf"], "quantity": 1 }
  ]
}
```

Respuesta **`201`** (recortada):

```json
{
  "pedido": {
    "id": 49, "table_number": 3, "status": "pending", "source": "qr", "customer_name": "Luis",
    "items": [ { "product_name": "Sandwich 2 Quesos · Brisket", "unit_price": "35000.00", "quantity": 1,
                 "line_total": 35000.0,
                 "opciones": [ { "grupo": "Elige la carne", "nombre": "Brisket", "precio": 0 } ] } ],
    "total": 35000.0
  },
  "cuenta_id": 46
}
```

Ojo: aquí `unit_price` viene como texto (`"35000.00"`) y `total` como número. Los errores de
validación vienen por campo, por ejemplo
`{"items": ["Falta elegir «Elige la carne» para Sandwich 2 Quesos."]}` o
`{"items": {"0": {"non_field_errors": ["Un producto del pedido ya no está en el menú. Actualiza la página."]}}}`
(el helper de la sección 7 los convierte en una frase). Mismos `403`/`429`/`404` que 6.6.

Para seguirlo: `GET /api/v1/mesa/<token>/estado/` (6.3) sirve igual.

### 6.8 Estados del pedido y cierre de la mesa

| `estado` | `estado_texto` | Quién lo cambia |
|---|---|---|
| `pending` | Pendiente | Así llega. |
| `preparing` | En preparación | Cocina, en el panel. |
| `served` | Servido | Cocina o el mesero. |
| `cancelled` | Anulado | El restaurante (queda registrado con su motivo). No aparece en `estado`. |

- La mesa sigue ocupada, con todos sus pedidos, hasta que el restaurante **cierra la
  cuenta** en el panel (Mesas → la mesa → **Cerrar cuenta**, que además abre la precuenta
  para imprimir). Nada se cierra solo.
- Al cerrarla, la mesa queda libre y sus pedidos salen de Mensajes y Cocina. En la
  siguiente consulta el menú recibe `"ocupada": false` y `"cuenta": null`: es el momento de
  mostrar «¡Gracias por tu visita!» y dejar el carrito limpio.
- Los descuentos, cortesías y anulaciones los registra el restaurante con autorización de un
  administrador; el total de `cuenta` ya los refleja.

### 6.9 Formatos de una línea del pedido

| Forma | Ejemplo | Cuándo |
|---|---|---|
| **Con los id de la carta** (recomendada) | `{"product": "<uuid>", "variant": "<uuid>" \| null, "options": ["<uuid>"], "quantity": 2, "note": "…"}` | Todo menú nuevo. No se rompe si el restaurante reordena opciones. |
| Por posición (API vieja) | `{"product_id": 12, "opciones": [{"grupo": 0, "valor": 1}]}` | Sitios que leen `GET /api/v1/menu/`. Ver `CONECTAR-MENU-A-CLOUDIN.md`. |
| Armada en el sitio | `{"name": "Sandwich 2 Quesos · 250 g", "unit_price": 42000}` | Sitios con catálogo propio. El nombre tiene que ser un plato de la carta y nunca se cobra por debajo de su precio. |

En las dos primeras **no mandes precio ni nombre**: los pone Cloudin. En `carrito.js` cada
línea lleva además `by` (quién la agregó), que se ve en el carrito compartido.

---

## 7. Errores

Toda respuesta con error trae un `detail` legible, salvo los de validación del pedido
directo (6.7), que vienen por campo. Este helper saca siempre una frase para mostrar:

```js
function mensajeDeError(cuerpo) {
  if (cuerpo?.detail) return cuerpo.detail;
  const textos = [];
  (function recorrer(x) {
    if (typeof x === "string") textos.push(x);
    else if (x && typeof x === "object") Object.values(x).forEach(recorrer);
  })(cuerpo);
  return textos.join(" ") || "No se pudo completar. Intenta de nuevo.";
}
```

| Código | `codigo` | Qué pasó | Qué mostrar |
|---|---|---|---|
| `400` | — | Falta `X-API-Key` o está mala: «No se identificó el restaurante…» | Es un error de configuración: revisa `apiKey`. |
| `400` | — / `opciones` | Falta una opción obligatoria, se pasó un máximo, o la opción ya no existe | El mensaje tal cual; recargar la carta (`Cloudin.refresh()`). |
| `403` | `sin_pedidos` | El plan del restaurante no recibe pedidos por el QR | «Pídele tu pedido al mesero.» y ocultar el carrito |
| `403` | `solo_meseros` | Trabaja solo con meseros | «Llama al mesero, él toma tu pedido.» |
| `404` | — | Token de mesa inexistente (QR viejo) | «Este QR ya no es válido, pide ayuda al mesero.» |
| `409` | — | El carrito cambió en otro teléfono (`PUT borrador`) | Nada: reaplicar el cambio sobre el estado que vino y reintentar. |
| `409` | `agotado` | Un plato del carrito se agotó | Quitarlo del carrito y avisar. |
| `429` | `demasiados` | Muchos pedidos seguidos desde la misma IP | El mensaje tal cual; no borrar el carrito. |
| — | — | Sin señal (el `fetch` falla) | «Sin conexión, reintentando…»; no borrar el carrito. |

Un error de **CORS** no llega a tu código como respuesta: el `fetch` falla y la consola del
navegador dice «blocked by CORS policy». Casi siempre es el origen mal registrado (4.4).

---

## 8. Límites y cada cuánto consultar

| Qué | Tope por IP |
|---|---|
| Carta pública (`/api/public/…/menu/`) | 600 cada 10 min |
| Guardar el carrito (`PUT borrador`) | 240 cada 10 min |
| Enviar el carrito (`POST enviar`) | 20 cada 10 min |
| Pedido directo (`POST tables/<token>/orders`) | 20 cada 10 min |

- Los topes son por dirección IP y por restaurante. Los clientes con datos móviles tienen
  cada uno su IP; los que están en el wifi del restaurante la comparten. Si un restaurante
  grande con wifi abierto llega al tope de envíos, se sube en `apps/api/mesa_views.py` y
  `apps/api/views.py`.
- `estado/`: cada 5 s, solo con la página visible.
- La carta: al abrir la página y cuando el cliente vuelve a ella; el runtime ya usa `ETag` y
  su propia caché, no hace falta consultarla en bucle.

---

## 9. Seguridad: qué protege a quién

- **La llave `ck_…` es pública por diseño.** Va dentro del JavaScript de la página y
  cualquiera la puede leer. Solo dice de qué restaurante es la petición: no da acceso al
  panel, a las ventas ni a nada de los empleados (eso exige iniciar sesión).
- **Lo que protege la mesa es el token del QR.** Solo quien escaneó el QR (o tiene la foto)
  puede pedir a esa mesa. Por eso no conviene publicar las direcciones con `?mesa=`, y si
  usas analítica en la página, que no guarde la URL completa.
- **El precio lo pone Cloudin**, siempre. Una línea «armada en el sitio» se valida contra la
  carta y nunca se cobra por debajo de su precio: editar el JavaScript no sirve para pagar
  menos.
- **CORS** hace que un navegador solo pueda pedir desde los orígenes registrados. No frena a
  alguien con `curl`: para eso están los topes por IP.
- **No uses las rutas `/api/v1/site/…` en un menú público.** Piden por *número* de mesa, sin
  token: con la llave, cualquiera podría pedir a cualquier mesa. Son para un equipo del
  propio restaurante (la tablet del mostrador). Para los meseros está Cloudin Meseros.
- **Si la llave se filtra de forma dañina** (alguien la usa para molestar), se regenera en
  el panel maestro (**Regenerar API key**) y se actualiza `apiKey` en la página. Mientras
  tanto, el menú no puede pedir.

---

## 10. `carrito.js`: la implementación de referencia

`client/example/carrito.js` (~240 líneas, sin dependencias) hace todo lo de la sección 6:

1. Si hay `apiKey`, `?mesa=<token>` y `recibe_pedidos`, pone un botón **«Agregar»** en cada
   plato disponible con precio (dentro de `.dish__body`, o al final de la tarjeta).
2. Si el plato tiene presentaciones o adiciones, abre un selector (radio para «una sola»,
   casillas para varias) y valida lo obligatorio antes de agregar.
3. Guarda el carrito compartido con `PUT borrador/` y maneja el `409` reaplicando el cambio.
4. Muestra una barra flotante («Ver pedido (2) · $ 90.000» o «Mesa 3 · 1 pedido»), el
   carrito con − / +, el nombre de quien pide (se recuerda en el teléfono) y lo ya pedido con
   su estado.
5. «Enviar pedido» hace `POST enviar/` y confirma «¡Pedido enviado! La cocina ya lo tiene.».
6. Consulta `estado/` cada 5 s mientras la página está visible.

Para usarlo en otro diseño:

- Inclúyelo **después** del runtime, con `CLOUDIN_CONFIG.apiKey` puesto (4.2).
- Colores: toma `--cloudin-primary` (o `#B3261E`) para los botones y `--fondo` para los
  diálogos. Cambia el CSS del principio del archivo si el diseño lo pide.
- Textos: están en español dentro del archivo; cámbialos ahí.
- Todo texto que viene de Cloudin pasa por `esc()` antes de ir al HTML. Si lo modificas,
  mantenlo así.

---

## 11. Probarlo

### 11.1 En local

1. Arranca Cloudin: `python manage.py runserver` (ver `README.md`).
2. En `/admin/`, al restaurante de prueba ponle **Página del menú**
   `http://localhost:4431/index.html`, plan **Cloudin completo** y «Cómo se toman los
   pedidos» en **Autoservicio** o **Ambos**.
3. En `client/example/index.html` pon el `slug`, la `api` (`http://localhost:8000/api/public/<slug>/menu/`)
   y la `apiKey` del restaurante.
4. Sirve la carpeta: `python -m http.server 4431 --directory client/example`.
5. Saca el token de una mesa (en producción basta con escanear su QR con el teléfono):

   ```python
   # python manage.py shell
   from apps.dining.models import Table
   from apps.tenants.context import tenant_context
   from apps.tenants.models import Tenant

   with tenant_context(Tenant.objects.get(slug="restaurante-ejemplo")):
       print(list(Table.objects.values_list("number", "token")))
   ```

6. Abre `http://localhost:4431/index.html?mesa=<token>`, pide algo y mira **Mensajes**,
   **Cocina** y **Mesas** en el panel. Cierra la cuenta y comprueba que el menú se entera.

### 11.2 Con `curl` contra el servidor

```bash
S=https://<servidor-cloudin>
K=ck_...          # la llave del restaurante
T=td8vIrnwaZPF    # el token de una mesa (lo que va después de ?mesa= en su QR)

curl -s "$S/api/public/culturabrisket/menu/?table=$T" | head -c 400
curl -s -H "X-API-Key: $K" "$S/api/v1/mesa/$T/estado/"
curl -s -X PUT -H "X-API-Key: $K" -H "Content-Type: application/json" \
     -d '{"items":[{"product":"<id del plato>","quantity":1}]}' "$S/api/v1/mesa/$T/borrador/"
curl -s -X POST -H "X-API-Key: $K" -H "Content-Type: application/json" \
     -d '{"by":"Prueba"}' "$S/api/v1/mesa/$T/enviar/"
```

Después cierra la cuenta de prueba en el panel para dejar la mesa libre.

---

## 12. Checklist por cliente

- [ ] El restaurante existe en `/master/`, con el plan correcto (sección 3) y sus mesas creadas.
- [ ] La carta está completa en su panel (**Mi menú**): precios, fotos, opciones obligatorias.
- [ ] El proyecto de Pages publica y `CLOUDIN_CONFIG` apunta al servidor y al slug correctos.
- [ ] **Página del menú** registrada en `/admin/` (y el dominio propio en «Otros sitios autorizados»).
- [ ] **Cómo se toman los pedidos** = Autoservicio o Ambos (panel → Meseros), si va a pedir por QR.
- [ ] Abierto desde el QR de una mesa aparecen los botones «Agregar».
- [ ] Un plato con opción obligatoria no se puede agregar sin elegirla.
- [ ] Pedido de prueba: llega a **Mensajes** y **Cocina** con el nombre y el precio correctos, y la mesa queda ocupada.
- [ ] Cerrar la cuenta libera la mesa y el menú se entera.
- [ ] La vista previa del panel (**Personalizar**) muestra la página.
- [ ] Sin errores en la consola del navegador del teléfono.
- [ ] Los QR se imprimen con el dominio definitivo.

---

## 13. Qué NO hacer

- No cobres ni muestres como definitivo un precio calculado en la página: el que vale es el
  de Cloudin (`borrador.total`, `pedido.total`).
- No uses `/api/v1/site/…` desde el menú público (sección 9).
- No pongas un proxy (Pages Functions, otro Worker) entre el menú y Cloudin (sección 2.3).
- No guardes en caché `estado/` (ni en un Service Worker): tiene que estar siempre al día.
- No cambies la **Página del menú** después de imprimir los QR sin reimprimirlos o dejar la
  dirección vieja autorizada.
- No pintes texto de la carta con `innerHTML` sin escaparlo.
- No publiques cambios en el sitio de un cliente sin su permiso (el de Cultura Brisket está
  conectado a este panel).

---

## 14. Dónde está el código en Cloudin

| Qué | Archivo |
|---|---|
| Carta pública `cloudin.menu/v1` | `apps/public_menu/views.py`, `apps/public_menu/serializers.py` |
| Runtime `cloudin-menu.v1.js` | `static/cloudin-menu.v1.js` (se genera con `python manage.py build_runtime`) |
| Carrito compartido y envío (`/api/v1/mesa/…`) | `apps/api/mesa_views.py` |
| Pedido directo y rutas del sitio | `apps/api/views.py` |
| Líneas con los id de la carta → forma interna | `apps/catalog/legacy.py` (`linea_desde_v1`) |
| Validación y precio de las opciones | `apps/catalog/opciones.py` (`aplicar`) |
| Topes por IP y precio mínimo | `apps/api/limites.py` |
| Orígenes autorizados (CORS) | `apps/tenants/cors.py`, `Tenant.origenes_permitidos` |
| Enlace del QR de cada mesa | `apps/dining/qr.py` (`enlace_de_mesa`) |
| Plan y modo de servicio | `apps/tenants/models.py` (`recibe_pedidos_del_menu`) |
| Ejemplo completo | `client/example/index.html`, `client/example/carrito.js` |
| Pruebas | `tests/test_pedidos_menu_digital.py` |
