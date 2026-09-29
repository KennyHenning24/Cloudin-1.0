# Menú digital conectado a Cloudin — instrucciones para Claude Code

> **Para ti, Claude Code.** Te van a pedir crear (o arreglar) el menú digital de un
> restaurante: la página que el cliente abre al escanear el QR de su mesa. Este archivo
> dice **todo** lo que ese menú necesita para funcionar con Cloudin: pintar la carta,
> recibir pedidos de la mesa, dejar que el restaurante cambie platos, precios y fotos sin
> tocar el código, publicarlo y probarlo. Léelo completo antes de escribir código y
> síguelo al pie de la letra: cada ruta, campo y atributo de aquí existe en Cloudin y
> está probado.
>
> **Para la persona:** copia este archivo a la raíz del repositorio del menú con el
> nombre `CLAUDE.md` (Claude Code lo lee solo al empezar), o dile a Claude Code «lee
> `CLAUDE-MENU-DIGITAL.md` antes de empezar». Si el menú ya existe con los platos escritos
> a mano, pídele: «Convierte este menú siguiendo la sección 0 de CLAUDE.md, sin cambiar el
> diseño, hasta que `?cloudin-check=1` salga sin ❌».
>
> El código de Cloudin está en `https://github.com/KennyHenning24/Cloudin-1.0`. Si
> trabajas dentro de ese repositorio, las piezas están en `client/plantilla/index.html`,
> `client/example/carrito.js` y `static/src/cloudin-menu.v1.src.js`.

> **Lo más importante, antes que nada.** El menú es una **plantilla**: ningún menú,
> categoría, plato, precio, foto, etiqueta ni dato del negocio (nombre, logo, portada,
> colores, frase, descripción, bienvenida, WhatsApp, teléfono, correo, dirección, mapa,
> horario, redes, medios de pago, Recoger y Domicilio) va escrito a mano en el HTML. Todo
> sale de Cloudin, y **todo lo que el restaurante puede cambiar en su panel tiene que verse
> en el menú** (la lista completa, con el código de cada cosa, está en la **sección 4.8**).
> Lo que cambie (un menú nuevo, un plato nuevo, uno eliminado, un **agotado**, otra foto,
> otro precio, otro color, otra portada, Domicilio apagado) aparece **solo** en el menú,
> también en el que el cliente ya tiene abierto: en máximo 15 segundos, sin volver a
> publicar y **sin recargar la página**. Se comprueba con la **prueba de fuego**:
> `https://<menú>/?cloudin-check=1` debe salir sin ❌ (sección 10.4). No digas «listo»
> antes. Si el menú ya existe y tiene la carta escrita a mano, empieza por la **sección 0**.

---

## 0. Si el menú ya existe con la carta escrita a mano (convertirlo)

**Síntoma:** en el panel el restaurante crea un plato o un menú, cambia una foto, un
precio, un color, la portada o el logo, agrega su correo o su Facebook, apaga Domicilio, y
el menú no cambia (a lo sumo se notan los agotados o los eliminados). El menú tiene la carta
y los datos **escritos en el HTML** y Cloudin no los puede tocar. Se convierte **sin cambiar
el diseño**, en este orden:

1. **Diagnóstico.** Sirve el sitio en local (sección 10.1). Si todavía no tiene el bloque de
   conexión, agrégalo primero (sección 3.2). Abre `http://localhost:8080/?cloudin-check=1`:
   el informe dice qué está escrito a mano y qué no cambia desde el panel. Guárdalo.
2. **Trabaja en una rama** (`git switch -c conectar-cloudin`). Nada de push a `main` sin
   permiso del usuario (sección 9).
3. **La carta ya está en Cloudin.** Abre `https://<servidor>/api/public/<slug>/menu/`: si
   ahí están los platos, **no los vuelvas a escribir en ningún lado**. Si falta alguno, se
   agrega en el panel (o por importación, sección 7.2), nunca en el HTML.
4. **Fotos.** Si en esa carta las fotos apuntan al sitio (`"image":
   "https://<menú>/assets/…"`), **no borres esos archivos del sitio**: son las fotos que el
   menú muestra hasta que el restaurante suba otra en el panel (la del panel reemplaza a la
   del sitio).
5. **Convierte, conservando clases, estructura y CSS:**
   - Toma **una** tarjeta de plato y hazla `<template data-cloudin-template="product">`:
     el nombre con `data-cloudin-field="product.name"`, el precio con
     `data-cloudin-field="product.price"`, la descripción con
     `data-cloudin-field="product.description"` (y `data-cloudin-if`), la foto con
     `<img data-cloudin-if="product.image" data-cloudin-src="product.image">` y el aviso de
     agotado con `data-cloudin-if="!product.available"`. La caja de textos lleva la clase
     `dish__body` (ahí `carrito.js` pone «Agregar»).
   - Toma **una** sección de categoría y hazla `<template data-cloudin-template="category">`,
     con el título en `data-cloudin-field="category.name"` y un `data-cloudin="products"`
     adentro.
   - **Todos los menús:** la carta entera va en `data-cloudin="menus"` con
     `<template data-cloudin-template="menu">` (el título del menú en
     `data-cloudin-field="menu.name"` y un `data-cloudin="categories"` adentro). Así un menú
     nuevo del panel (Mi menú → **Nuevo menú**) aparece solo, con sus categorías y sus platos
     (sección 4.1). **No** uses una raíz fija `data-cloudin="menu"`: muestra un solo menú.
   - **Borra todas las demás tarjetas y secciones escritas a mano.** (Opcional: una copia
     pre-renderizada dentro de `menus` como respaldo, regla 4.6.8.)
   - Barra de categorías: `data-cloudin="category-nav"` con
     `<template data-cloudin-template="category-link">` y
     `data-cloudin-href="category.anchor"`. Barra de menús: `data-cloudin="menu-nav"` con
     `<template data-cloudin-template="menu-link">`. Recomendados: `data-cloudin="featured"` (4.7).
   - **Todo lo de Personalizar**, con la **tabla 4.8** (es obligatoria, fila por fila):
     nombre, logo, portada, frase, descripción, bienvenida, WhatsApp, teléfono, correo,
     dirección, ciudad, Google Maps, horario, Instagram, Facebook, TikTok, medios de pago,
     Recoger y Domicilio. Un enlace fijo (`https://wa.me/57…`, `tel:…`, `mailto:…`,
     `https://facebook.com/…`) pasa a `data-cloudin-href`, y todo lo que puede quedar vacío o
     apagado lleva `data-cloudin-if` (se esconde solo y vuelve si el dueño lo llena).
   - **Colores (los 4):** donde el CSS tiene los colores de la marca escribe
     `var(--cloudin-primary, <el color de hoy>)` en botones y precios,
     `var(--cloudin-secondary, …)` en detalles y títulos, `var(--cloudin-background, …)` en el
     fondo y `var(--cloudin-text, …)` en el texto. El segundo valor es el color actual, por si
     el restaurante no eligió otro en Personalizar.
   - **Portada:** si es un `<img>`, `data-cloudin-if="business.cover"
     data-cloudin-src="business.cover"` (sin `srcset` ni `<picture>`); si es un fondo en el CSS,
     `background-image: var(--cloudin-cover, url(<la foto de hoy>))`.
6. **Quita los scripts propios que leen o «sincronizan» la carta:** un `fetch` a Cloudin, un
   arreglo de platos en JavaScript, algo que marca agotados a mano. El runtime hace todo eso,
   y mantiene la carta al día mientras la página está abierta. Lo que tu JavaScript le haga a
   los platos (animaciones, efectos) va en el evento `cloudin:rendered` (sección 4.5).
   `carrito.js` se queda.
7. **La mesa usa esta misma página.** El QR de cada mesa abre la «Página del menú» con
   `?mesa=<token>`: no hace falta otra página. Si el sitio tiene un `mesa.html` de antes
   (QR impresos con `mesa.html?m=<token>`), déjalo solo para redirigir, y esos QR siguen
   sirviendo:
   ```html
   <!doctype html><meta charset="utf-8"><title>Tu mesa</title>
   <script>
     const q = new URLSearchParams(location.search), t = q.get("mesa") || q.get("m");
     location.replace("./" + (t ? "?mesa=" + encodeURIComponent(t) : ""));
   </script>
   ```
8. **Prueba de fuego** (sección 10.4) hasta que no quede ningún ❌. Después, la prueba real
   con el usuario: que agote un plato en el panel y lo vea cambiar en el menú abierto (sin
   recargar, en máximo 15 s); que cree un menú nuevo con una categoría y un plato; que cambie
   una foto, un color, la portada y el logo; que ponga su correo y su Facebook; que apague
   Domicilio y lo vuelva a encender.
9. **Publicar solo con permiso** (sección 9), y repetir `?cloudin-check=1` en la dirección
   publicada.

---

## 1. Qué es cada cosa

```
 Teléfono del cliente                                   Internet
 ┌──────────────────────────────┐   HTML/CSS/JS    ┌─────────────────────────────────────┐
 │ Escanea el QR de la mesa     │ ───────────────▶ │ Cloudflare Pages: EL MENÚ (tu código) │
 │ https://<menu>/?mesa=<token> │                  │ estático, sin base de datos          │
 │                              │                  └─────────────────────────────────────┘
 │ cloudin-menu.v1.js ──────────┼── lee la carta ──▶ ┌─────────────────────────────────────┐
 │ carrito.js ──────────────────┼── carrito/pedido ▶│ CLOUDIN (Django) en Render           │
 └──────────────────────────────┘                  │ carta, fotos, mesas, pedidos, panel  │
                                                    └─────────────────────────────────────┘
 El restaurante edita la carta en su panel (/panel/) ──▶ el menú la muestra sola, sin volver a publicarlo
 Los pedidos llegan al panel: Mesas, Mensajes, Cocina ── y los meseros (Cloudin Meseros) ven las mismas mesas
```

- **Cloudin es la fuente de verdad** de todo lo que es dato: menús, categorías, platos,
  precios, fotos, descripciones, etiquetas, presentaciones, adiciones, agotados, logo,
  portada, colores, textos del negocio, contacto, horario, redes, medios de pago, Recoger y
  Domicilio, y mesas. **El menú solo diseña cómo se ve y trae los datos de Cloudin.**
- **El menú es un sitio estático** (HTML, CSS, JavaScript) publicado en Cloudflare Pages.
  Habla con Cloudin por HTTP desde el navegador del cliente.
- **Dos scripts hacen la conexión:** `cloudin-menu.v1.js` (lo sirve Cloudin; pinta la carta
  dentro de tu diseño) y `carrito.js` (va en el repositorio del menú; botón «Agregar»,
  carrito compartido de la mesa y envío del pedido).

### Reglas de oro (no negociables)

| Regla | Por qué |
|---|---|
| **Nada de la carta ni del negocio escrito a mano en el HTML:** ni menús, ni categorías, ni platos, ni precios, ni fotos, ni etiquetas, ni nombre, logo, portada, colores, frase, WhatsApp, teléfono, correo, dirección, horario, redes, medios de pago, Recoger o Domicilio. Todo sale de Cloudin con plantillas (sección 4) y se comprueba con `?cloudin-check=1` (10.4) | Lo que el restaurante cambia en su panel tiene que verse solo en el menú, sin tocar el código |
| **Todo lo del panel se muestra:** cada fila de la tabla 4.8 está en el menú (con `data-cloudin-if` si puede quedar vacía o apagada). No elijas «esto no lo pongo» | Si el dueño cambia algo en su panel y el menú no cambia, para él Cloudin no funciona |
| **El precio lo calcula Cloudin.** Muéstralo, nunca lo mandes en un pedido | El servidor lo recalcula y no deja cobrar menos |
| **El carrito vive en Cloudin** (`PUT …/borrador/`), no solo en el teléfono | Todos los de la mesa ven y editan el mismo carrito |
| **Llama a Cloudin directo desde el navegador.** Nada de Pages Functions, Workers o servidores «proxy» en medio | Los topes son por IP: con un proxy todos los clientes comparten una IP y se bloquea el restaurante |
| **No inventes datos de conexión.** La dirección del servidor, el identificador y la API key te los da el usuario (sección 2) | Un dato inventado deja el menú desconectado sin error visible |
| **El token de superadmin (`cld_…`) es secreto**: nunca en el repositorio, ni en el HTML, ni en un commit | Da acceso a importar cartas de cualquier restaurante |
| **No publiques (push a `main`) el menú de un cliente sin que el usuario lo confirme** | Publicar cambia lo que ven sus clientes al instante |
| **Nunca cambies nada del servidor Cloudin para un menú** (variables, `CREDENTIAL_KEY`, código) salvo que el usuario lo pida | El mismo servidor atiende a todos los restaurantes |

---

## 2. Lo que necesitas antes de empezar (pídeselo al usuario)

| Dato | Ejemplo | Dónde lo ve el usuario |
|---|---|---|
| **Dirección del servidor Cloudin** | `https://cloudin-x7k2.onrender.com` | Render → el servicio `cloudin` → arriba, debajo del nombre. Es la misma con la que entra a `/master/` |
| **Identificador (slug) del restaurante** | `culturabrisket` | Panel maestro (`/master/`) → la lista de restaurantes |
| **API key del restaurante** (`ck_…`) | `ck_bc6axscYu3K6…` | Panel maestro → el restaurante → tarjeta **Acceso** → «API key (para su sitio web)» |
| **¿Recibe pedidos por el QR?** | Sí | Todos los restaurantes tienen Cloudin completo; lo decide el interruptor «Pedidos desde el QR de la mesa» del panel del restaurante (sección 9.3). El panel maestro muestra cómo está |
| **Dirección donde se publicará el menú** | `https://culturabrisket.pages.dev/` | Cloudflare Pages, después de publicar (sección 9) |
| Token de superadmin (`cld_…`), **solo si vas a cargar la carta por importación** (sección 7.2) | `cld_…` | Panel maestro → **Tokens de API** → Crear token. Pídele que lo ponga en una variable de entorno (`CLOUDIN_ADMIN_TOKEN`), no en el chat ni en archivos |

**Atajo:** en el panel maestro → el restaurante → tarjeta **«Menú digital»** → **Copiar
código** entrega el bloque de conexión (sección 3.2) ya lleno con el servidor, el
identificador y la API key. Pídele al usuario que te lo pegue.

Si el restaurante todavía no existe en Cloudin, el usuario lo crea en el panel maestro →
**Nuevo restaurante**. Ver `PASO-A-PASO-NUEVO-RESTAURANTE.md` en el repositorio de
Cloudin.

**Comprueba la conexión antes de escribir código:** abre (o `curl`)
`https://<servidor>/api/public/<slug>/menu/`. Debe responder JSON con
`"schema": "cloudin.menu/v1"`. Si responde «Ese restaurante no existe o no está activo.»,
el slug está mal. En el plan gratis de Render, la primera petición después de 15 minutos
sin visitas tarda cerca de un minuto (el servidor despierta): espera, no es un error.

---

## 3. El repositorio del menú

### 3.1 Estructura

```
menu-<slug>/
├── CLAUDE.md             ← este archivo
├── site/                 ← LO ÚNICO QUE SE PUBLICA (Build output directory: site)
│   ├── index.html        ← tu diseño + zonas y plantillas data-cloudin + el bloque de conexión
│   ├── carrito.js        ← copia EXACTA de client/example/carrito.js de Cloudin
│   ├── assets/           ← imágenes del DISEÑO: fondos, íconos, fuentes
│   └── _headers          ← opcional (sección 9.4)
└── cloudin/              ← NO se publica: solo para cargar la carta (sección 7.2)
    ├── menu.seed.json    ← la carta completa (puede traer correo y teléfono del dueño)
    └── fotos/            ← fotos de platos y logo para importar
```

Todo lo que está dentro de `site/` queda público en internet; por eso la semilla y sus
fotos van afuera, en `cloudin/`.

Para empezar rápido, parte de la plantilla mínima (ya probada) y de `carrito.js`:

```bash
mkdir -p site cloudin/fotos
curl -fsSL -o site/index.html https://raw.githubusercontent.com/KennyHenning24/Cloudin-1.0/main/client/plantilla/index.html
curl -fsSL -o site/carrito.js https://raw.githubusercontent.com/KennyHenning24/Cloudin-1.0/main/client/example/carrito.js
```

Las **fotos de los platos no se publican con el menú**: las sube el restaurante en su panel
(o llegan por la importación, sección 7.2) y la carta trae su dirección absoluta.

### 3.2 El bloque de conexión

Al final de `index.html`, antes de `</body>`, **en este orden**:

```html
<script>
  window.CLOUDIN_CONFIG = {
    restaurant: "<slug>",
    api: "https://<servidor>/api/public/<slug>/menu/",
    hideSoldOut: false,
    cacheTtl: 60,
    live: 15,
    apiKey: "ck_…"
  };
</script>
<script src="https://<servidor>/static/cloudin-menu.v1.js" defer></script>
<script src="carrito.js" defer></script>
```

| Clave | ¿Obligatoria? | Qué es |
|---|---|---|
| `api` | **Sí** | La carta pública, completa: `https://` y `/` final. Sin ella el runtime y el carrito no hacen nada. De aquí sale también la dirección del servidor para los pedidos |
| `restaurant` | Sí | El slug. Nombre de la carta guardada en el teléfono (`localStorage["cloudin:<slug>"]`): con ella quien vuelve ve la carta al instante |
| `apiKey` | Para pedir | `ck_…`. Ponla siempre: si el restaurante apaga los pedidos por QR, el menú esconde los botones solo, y al encenderlos vuelven sin tocar la página. Vacía (`""`), la carta queda solo para mirar para siempre |
| `hideSoldOut` | No | `false` (lo agotado se ve apagado) o `true` (lo agotado no se muestra) |
| `cacheTtl` | No | Segundos que la carta guardada vale cuando se abre **sin** QR (60). Con QR siempre pide la carta al día |
| `live` | No | **Carta en vivo:** cada cuántos segundos pregunta, mientras la página está abierta y a la vista, si la carta cambió (15). Así un agotado, un plato nuevo o un precio nuevo aparecen solos, sin recargar. Sin cambios Cloudin responde vacío (304): casi no gasta datos. `0` la apaga (no lo hagas) |

`contract`, `locale` y `currency` (en ejemplos viejos) no las usa nadie: puedes omitirlas.

- **Carga el runtime desde Cloudin**, no lo copies al repositorio: así recibe arreglos sin
  republicar el menú.
- `apiKey` **no es secreta**: queda en el HTML y cualquiera puede verla. Solo dice de qué
  restaurante es la petición; no da acceso al panel. Lo que protege los pedidos es el token
  de la mesa (va en el QR), los orígenes autorizados (sección 9.2), los topes por IP y que
  el precio lo pone Cloudin.

---

## 4. Pintar la carta: el runtime `cloudin-menu.v1.js`

Es la forma recomendada. Lee la carta, la guarda en el teléfono, la pinta con **tus**
plantillas HTML, respeta agotados y horarios, pone los colores y la portada del
restaurante, esconde lo que está vacío o apagado, funciona con la vista previa del panel y
**mantiene la carta al día sola** mientras la página está abierta (`live`, sección 3.2). Tú
solo marcas el HTML con atributos.

### 4.1 El esqueleto mínimo que funciona

```html
<main data-cloudin="menus">
  <p class="cargando">Cargando la carta…</p>

  <!-- Un menú de «Mi menú» (Carta, Almuerzos, Bebidas…). Su raíz NO lleva data-cloudin. -->
  <template data-cloudin-template="menu">
    <section>
      <h2 data-cloudin-field="menu.name"></h2>
      <div data-cloudin="categories"></div>
    </section>
  </template>

  <template data-cloudin-template="category">
    <section>
      <h3 data-cloudin-field="category.name"></h3>
      <div data-cloudin="products"></div>
    </section>
  </template>

  <template data-cloudin-template="product">
    <article>
      <img data-cloudin-if="product.image" data-cloudin-src="product.image" loading="lazy">
      <div class="dish__body">
        <h4 data-cloudin-field="product.name"></h4>
        <p data-cloudin-if="product.description" data-cloudin-field="product.description"></p>
        <ul data-cloudin="tags"><template data-cloudin-template="tag"><li data-cloudin-field="tag.name"></li></template></ul>
        <strong data-cloudin-field="product.price"></strong>
        <span data-cloudin-if="!product.available">Agotado</span>
      </div>
    </article>
  </template>
</main>
```

El runtime borra lo que hay en `menus` (menos las `<template>`) y por cada menú con platos
pinta una copia de la plantilla `menu`; dentro de su `categories`, una copia de `category`
por categoría con platos; dentro de su `products`, una copia de `product` por plato. Un menú
que el restaurante crea en su panel aparece solo en cuanto tenga platos (y desaparece si
lo elimina). Todo el diseño (clases, estilos, estructura interna) es libre.

La plantilla completa, con todo lo de Personalizar (tabla 4.8) ya conectado, está en
`client/plantilla/index.html`: parte de ella.

### 4.2 Zonas (`data-cloudin="…"`)

Elementos que el runtime **vacía y vuelve a llenar** (conserva solo las `<template>`).

| Zona | Dónde va | Plantilla que usa | ¿Obligatoria? |
|---|---|---|---|
| `menus` | En cualquier parte. Es la raíz de la carta: **todos** los menús | `menu` | **Sí** |
| `categories` | Dentro de la plantilla `menu` | `category` | **Sí** |
| `products` | Dentro de la plantilla `category` | `product` | **Sí** |
| `menu-nav` | En cualquier parte: barra con un enlace por menú | `menu-link` | Sí si el diseño tiene pestañas o barra de menús |
| `category-nav` | Dentro de la plantilla `menu`: barra de categorías de ese menú | `category-link` | No |
| `variants` | Dentro de la plantilla `product` | `variant` | Sí si hay presentaciones |
| `tags` | Dentro de la plantilla `product` | `tag` | **Sí** (las etiquetas se ven, también las nuevas) |
| `featured` | En cualquier parte de la página | `featured`, y si no existe, `product` | No: platos con «Destacar en el menú» |
| `menu` | Raíz **fija** de un solo menú (la forma vieja): pinta `categories` y `category-nav` de un menú | — | **No la uses**: un menú nuevo del panel no sale |

- **Solo cuenta el primer elemento** de cada `<template>`: envuelve todo en uno.
- Las plantillas se buscan dentro de la zona, luego hacia afuera hasta el menú (o la raíz),
  y por último en toda la página. Pueden ir dentro de la plantilla `menu` o sueltas dentro
  de `menus`.
- La raíz de la plantilla `menu` **no** lleva `data-cloudin="menu"`.
- Un menú o una categoría sin platos visibles no se pinta; un menú nuevo aparece en cuanto
  tiene su primer plato.
- **Un solo menú fijo por página** (p. ej. una página solo de desayunos): una raíz
  `data-cloudin="menu"` con `data-cloudin-menu="<clave del menú>"` (la clave está en
  `menus[].key`); sin ese atributo pinta el primer menú. Úsalo solo si el usuario lo pide:
  lo que el restaurante agregue en otro menú no sale ahí.

### 4.3 Atributos

El valor siempre es `contexto.campo`: **exactamente dos partes** (`business.phone` sí;
`business.contact.phone` no existe).

| Atributo | Qué hace |
|---|---|
| `data-cloudin-field="…"` | **Reemplaza todo el contenido** del elemento por el texto del campo. No pongas otros elementos dentro |
| `data-cloudin-src="…"` | Pone el `src` (para `<img>`); si el campo está vacío, lo quita. Si el `<img>` no tiene `alt` o lo tiene vacío, le pone el nombre |
| `data-cloudin-href="…"` | Pone el `href` (para `<a>`); si el campo está vacío, lo quita |
| `data-cloudin-if="…"` | El elemento **no se ve** si el campo está vacío (sin dato, `""`, `false` o lista vacía): un servicio apagado, un correo que no está, un plato sin foto |
| `data-cloudin-if="!…"` | El elemento **no se ve** si el campo **no** está vacío (`!product.available` → «Agotado») |

Cómo lo hace `data-cloudin-if`:

- **Fuera de las plantillas** (encabezado, pie, botones fijos: todo lo de `business.*` y
  `table.*`) **esconde** el elemento con `style="display: none"` y lo **vuelve a mostrar**
  (quita ese `display`) en cuanto el dato llega, sin recargar. Así, si el dueño apaga
  Domicilio, el botón se va, y si lo enciende otra vez, vuelve solo.
- **Dentro de una plantilla**, la copia se arma de nuevo en cada repintado y lo que no
  aplica **no se pone** (se quita de la copia).
- No le pongas `display` en línea a un elemento con `data-cloudin-if` (el runtime lo
  reemplaza). En el HTML pre-renderizado, lo que la semilla trae vacío va con
  `style="display:none"`: el runtime lo muestra si el dueño lo llena.

### 4.4 Campos

`business.*` y `table.*` funcionan en toda la página; `menu.*` dentro de `menu`,
`menu-link` y todo lo de ese menú (sus categorías y platos); `category.*` dentro de
`category`, `category-link` y los platos de esa categoría; `product.*` dentro de la
plantilla del plato; `variant.*` y `tag.*` dentro de las suyas.

| Campo | Qué trae | Se edita en el panel |
|---|---|---|
| `business.name` | Nombre del restaurante | Panel maestro (al crearlo) o `/admin/` |
| `business.tagline` | Frase corta | Personalizar → Datos del negocio |
| `business.description` | Descripción | Personalizar → Datos del negocio |
| `business.welcome_message` | Mensaje de bienvenida («¡Bienvenido! Pide desde tu mesa.») | Personalizar → Datos del negocio |
| `business.logo` | URL del logo (para `data-cloudin-src`) | Personalizar → Logo y colores |
| `business.cover` | URL de la portada horizontal (para `data-cloudin-src`; como fondo: `var(--cloudin-cover)`, 4.5) | Personalizar → Portada |
| `business.address`, `business.city` | Dirección y ciudad | Personalizar → Contacto y WhatsApp |
| `business.phone` | Teléfono (`+573001234567`) | Personalizar → Contacto y WhatsApp |
| `business.phone_link` | `tel:+573001234567` (para `data-cloudin-href`) | ídem |
| `business.whatsapp` | Número de WhatsApp | ídem |
| `business.whatsapp_link` | `https://wa.me/573001234567` (para `data-cloudin-href`) | ídem |
| `business.email` | Correo (`hola@turestaurante.com`) | ídem |
| `business.email_link` | `mailto:hola@turestaurante.com` (para `data-cloudin-href`) | ídem |
| `business.maps_url` | Enlace de Google Maps (para `data-cloudin-href`) | ídem |
| `business.instagram`, `business.facebook`, `business.tiktok` | Enlaces completos (para `data-cloudin-href`) | Personalizar → Redes sociales |
| `business.hours_today` | «Hoy: 12:00 – 21:00», «Hoy: 12:00 – 15:00 y 18:00 – 22:00», «Hoy: cerrado»; vacío sin horario | Personalizar → Horario |
| `business.open_now` | Si está abierto ahora (hora de Colombia). Solo para `data-cloudin-if`. Sin horario = cerrado | ídem |
| `business.takeaway` | Si ofrece **Recoger** (encendido por defecto). Solo para `data-cloudin-if` | Personalizar → Servicios y medios de pago |
| `business.delivery` | Si ofrece **Domicilio** (encendido por defecto). Solo para `data-cloudin-if` | ídem |
| `business.payment_methods_text` | Medios de pago ya escritos: «Efectivo, Nequi y Tarjeta»; vacío si no eligió | ídem |
| `table.number` | Número de la mesa cuando se abrió desde su QR; vacío sin QR | Mesas y QR |
| `menu.name`, `menu.description` | Nombre y descripción del menú (Carta, Almuerzos, Bebidas…) | Mi menú → Nuevo menú / editar el menú |
| `menu.anchor` | `#menu-<clave>` (para la barra de menús, con `data-cloudin-href`) | — |
| `menu.key` | Clave (`carta`) | — |
| `category.name`, `category.description` | Nombre y descripción | Mi menú |
| `category.image` | Foto de la categoría, si tiene | Importación |
| `category.anchor` | `#cat-<clave>` (para la barra, con `data-cloudin-href`) | — |
| `category.key` | Clave (`hamburguesas`) | — |
| `product.name`, `product.description` | Nombre y descripción | Mi menú |
| `product.price` | Precio **ya escrito**: `$ 24.000`; con presentaciones `Desde $ 24.000`; vacío sin precio. No le agregues `$` | Mi menú |
| `product.image` | URL de la foto (para `data-cloudin-src`) | Mi menú → «Toma o elige una foto» |
| `product.available` | Si está disponible (para `data-cloudin-if`) | Mi menú → Disponible / Agotar |
| `product.featured` | Si está destacado (para `data-cloudin-if`) | Mi menú → «Destacar en el menú» |
| `product.variants`, `product.tags` | Listas: solo para `data-cloudin-if` | — |
| `product.key` | Clave (`hamburguesa-clasica`) | — |
| `variant.name`, `variant.price` | Presentación y su precio ya escrito (`Doble carne`, `$ 32.000`) | Mi menú → Tamaños o presentaciones |
| `tag.name`, `tag.key` | Etiqueta (`Vegetariano`, `vegetariano`), también las que el dueño crea | Mi menú → editor → Etiquetas (y «Nueva etiqueta» → Agregar) |

### 4.5 Lo que el runtime escribe (para tu CSS y tu JavaScript)

| Dónde | Qué | Uso |
|---|---|---|
| Cada copia pintada | `data-cloudin-key="<clave>"` | `carrito.js` pone el botón en los platos por esta clave |
| Cada plato | `data-available="true\|false"`, `data-featured="true\|false"` | `[data-available="false"] { opacity: .55 }` |
| Cada menú | `id="menu-<clave>"` | Destino de los enlaces de la barra de menús |
| Cada categoría | `id="cat-<clave>"` | Destino de los enlaces de la barra de categorías |
| Lo de `data-cloudin-if` fuera de las plantillas | `style="display: none"` mientras el dato esté vacío o el servicio apagado | Nada: vuelve a verse solo |
| `<html>` y cada raíz `menu` | `data-cloudin-state="static\|cached\|live\|error"` | `[data-cloudin-state="error"] .cargando::after { content: "No se pudo cargar la carta." }` |
| `<html>` | `--cloudin-primary`, `--cloudin-secondary`, `--cloudin-background`, `--cloudin-text` | Los 4 colores de Personalizar: `color: var(--cloudin-primary, #B3261E)` (el segundo valor, por si no eligió) |
| `<html>` | `--cloudin-cover`: `url("…")` de la portada | Portada como fondo: `background-image: var(--cloudin-cover, url(portada.jpg))`. Sin portada en el panel se quita y vale el respaldo |

Estados: `static` sin datos todavía · `cached` pintada la carta guardada en el teléfono ·
`live` pintada la carta que acaba de llegar · `error` Cloudin no respondió y no había carta
guardada (queda el HTML tal cual).

**La carta se repinta sola** mientras la página está abierta (cada `live` segundos y al
volver a la pestaña, solo si algo cambió en el panel): el runtime vacía las zonas, pinta las
copias nuevas y dispara `cloudin:rendered`. Por eso lo que tu JavaScript le haga a los platos
(animaciones de entrada, efectos, botones propios) se engancha en `cloudin:rendered` sobre
`detail.root`, **nunca una sola vez al cargar la página**: si no, se pierde en el siguiente
repintado. `carrito.js` ya lo hace así.

JavaScript: `window.Cloudin.data` (la carta completa, JSON de la sección 5.2),
`window.Cloudin.table` (`{token, number}` si vino del QR), `window.Cloudin.state`,
`window.Cloudin.refresh()` (vuelve a pedir la carta). Eventos en `document`:
`cloudin:ready` (`detail.state`), `cloudin:rendered` (`detail.root`, cada zona pintada) y
`cloudin:error` (`detail.error`).

### 4.6 Reglas que se rompen fácil

1. `menus` → plantilla `menu` → `categories` → plantilla `category` → `products` →
   plantilla `product`: cada zona **dentro** de la plantilla anterior.
2. Un solo elemento raíz por `<template>`; `categories`, `products`, `variants` y `tags`
   **dentro** de su plantilla.
3. `data-cloudin-field` reemplaza el contenido: para «Mesa 3» escribe
   `Mesa <span data-cloudin-field="table.number"></span>`.
4. `data-cloudin-if="table.number"` sirve para lo que solo se ve en la mesa (el aviso «Mesa 3»,
   la bienvenida de la mesa): el runtime lo esconde mientras no sabe el número y lo muestra
   cuando llega.
5. Define **`--fondo`** en `:root` con el color de fondo de tu página (tomado de
   `var(--cloudin-background, …)`): la ventana del carrito de `carrito.js` lo usa de fondo y
   hereda el color de texto de la página (sin `--fondo` sale `#1A1110`, oscura).
6. Pon la clase **`dish__body`** a la caja de textos del plato: ahí `carrito.js` agrega el
   botón «Agregar» (si no existe, lo pone al final de la tarjeta).
7. Deja un texto de carga (`Cargando la carta…`) dentro de `menus`: el runtime lo borra
   al pintar, y con el CSS del estado `error` explicas si falla.
8. **HTML pre-renderizado (opcional):** puedes dejar la carta escrita dentro de `menus` con
   la misma estructura de las plantillas (cada menú con `id="menu-<clave>"`), como respaldo
   si Cloudin no responde. El runtime la reemplaza en cuanto llegan los datos. **Nunca** es
   la fuente de los precios. Lo que la semilla trae vacío, pre-renderízalo con
   `style="display:none"`.
9. No bloquees que Cloudin muestre la página en un marco (sin `X-Frame-Options: DENY`):
   la vista previa del panel la abre dentro de un iframe (sección 8).
10. Las imágenes que vienen de Cloudin (logo, portada, fotos de platos) van en un `<img>`
    **sin `srcset` y fuera de `<picture>`**: con un `srcset` o un `<source>` escritos a mano,
    el navegador muestra esos y no la foto nueva del panel.
11. Ningún color de la marca fijo en el CSS: los 4 salen de `var(--cloudin-…)` (tabla 4.8).

### 4.7 Destacados, con la sección escondida cuando no hay ninguno

```html
<section class="destacados">
  <h2>Recomendados</h2>
  <div data-cloudin="featured"></div>
</section>
<style>.destacados:not(:has([data-cloudin-key])) { display: none; }</style>
```

La barra de menús, escondida cuando hay uno solo:

```html
<nav class="menus-nav" data-cloudin="menu-nav" aria-label="Menús">
  <template data-cloudin-template="menu-link"><a data-cloudin-href="menu.anchor" data-cloudin-field="menu.name"></a></template>
</nav>
<style>.menus-nav:not(:has(a + a)) { display: none; }</style>
```

### 4.8 Todo lo del panel tiene que verse (obligatorio, fila por fila)

Esto es lo que el menú **recibe** de Cloudin y cómo lo **tiene** que mostrar. Cada fila es
algo que el restaurante puede cambiar en su panel: si el menú no lo muestra, el dueño lo
cambia y «no pasa nada». Pon **todas** las filas (el lugar y el diseño los eliges tú). Lo
que puede quedar vacío o apagado lleva `data-cloudin-if`: se esconde solo y vuelve cuando el
dueño lo llena, sin recargar. `?cloudin-check=1` revisa cada fila (sección 10.4).

**Mi menú**

| En el panel | El menú recibe | Cómo se muestra (obligatorio) |
|---|---|---|
| **Nuevo menú** (Carta, Almuerzos, Bebidas…) | `menus[]` | `data-cloudin="menus"` + `<template data-cloudin-template="menu">` con `data-cloudin-field="menu.name"`; si hay barra de menús, `data-cloudin="menu-nav"` + `menu-link` |
| Descripción del menú | `menu.description` | `<p data-cloudin-if="menu.description" data-cloudin-field="menu.description">` |
| Categoría nueva, su nombre y descripción | `menus[].categories[]` | Plantilla `category` con `category.name` (y `category.description` con `data-cloudin-if`); barra con `category-link` |
| Plato nuevo, nombre, precio, descripción | `products[]` | Plantilla `product` con `product.name`, `product.price`, `product.description` (con `data-cloudin-if`) |
| Foto del plato | `product.image` | `<img data-cloudin-if="product.image" data-cloudin-src="product.image">` |
| Etiquetas (también las nuevas) | `product.tags` + `tags` | `data-cloudin="tags"` con `<template data-cloudin-template="tag">` y `tag.name` |
| Tamaños o presentaciones | `product.variants` | `data-cloudin="variants"` con `variant.name` y `variant.price` |
| Agotar / disponible | `product.available` | `data-available` (CSS) + `<span data-cloudin-if="!product.available">Agotado</span>` |
| Destacar en el menú | `product.featured` | `data-cloudin="featured"` (4.7) o `data-featured` en el CSS |
| Ordenar, mover, eliminar, archivar | el orden y la lista | Nada extra: la plantilla pinta lo que llega, en ese orden |

**Personalizar**

| En el panel | El menú recibe | Cómo se muestra (obligatorio) |
|---|---|---|
| Logo | `business.logo` | `<img data-cloudin-if="business.logo" data-cloudin-src="business.logo">` |
| Color principal | `--cloudin-primary` | `var(--cloudin-primary, #…)` en botones, precios, enlaces |
| Color secundario | `--cloudin-secondary` | `var(--cloudin-secondary, #…)` en detalles, títulos, etiquetas |
| Color de fondo | `--cloudin-background` | `var(--cloudin-background, #…)` en el fondo de la página (y en `--fondo`) |
| Color del texto | `--cloudin-text` | `var(--cloudin-text, #…)` en el texto |
| Portada | `business.cover` / `--cloudin-cover` | `<img data-cloudin-if="business.cover" data-cloudin-src="business.cover">` o `background-image: var(--cloudin-cover, url(…))` |
| Nombre | `business.name` | `data-cloudin-field="business.name"` |
| Frase corta | `business.tagline` | `data-cloudin-field="business.tagline"` + `data-cloudin-if` |
| Descripción | `business.description` | `data-cloudin-field="business.description"` + `data-cloudin-if` (p. ej. «Nosotros» o el pie) |
| Mensaje de bienvenida | `business.welcome_message` | `data-cloudin-field="business.welcome_message"` + `data-cloudin-if` (arriba de la carta) |
| WhatsApp | `business.whatsapp_link` | `<a data-cloudin-if="business.whatsapp_link" data-cloudin-href="business.whatsapp_link">` |
| Teléfono | `business.phone`, `business.phone_link` | `<a data-cloudin-if="business.phone_link" data-cloudin-href="business.phone_link" data-cloudin-field="business.phone">` |
| Correo | `business.email`, `business.email_link` | `<a data-cloudin-if="business.email_link" data-cloudin-href="business.email_link" data-cloudin-field="business.email">` |
| Dirección y ciudad | `business.address`, `business.city` | `data-cloudin-field` en cada una (+ `data-cloudin-if`) |
| Enlace de Google Maps | `business.maps_url` | `<a data-cloudin-if="business.maps_url" data-cloudin-href="business.maps_url">Cómo llegar</a>` |
| Horario | `business.hours_today`, `business.open_now` | `data-cloudin-field="business.hours_today"` + `data-cloudin-if` |
| Instagram, Facebook, TikTok | `business.instagram`, `.facebook`, `.tiktok` | Un `<a data-cloudin-if="business.facebook" data-cloudin-href="business.facebook">` por red, **las tres** |
| Servicios: **Recoger** | `business.takeaway` | Un aviso o botón con `data-cloudin-if="business.takeaway"` («Pide y recoge») |
| Servicios: **Domicilio** | `business.delivery` | Un aviso o botón con `data-cloudin-if="business.delivery"` («Domicilios») |
| Medios de pago | `business.payment_methods_text` | `<p data-cloudin-if="business.payment_methods_text">Pagos: <span data-cloudin-field="business.payment_methods_text"></span></p>` |

**Mesas y QR**

| En el panel | El menú recibe | Cómo se muestra |
|---|---|---|
| El QR de la mesa | `?mesa=<token>` → `table.number` | `<p data-cloudin-if="table.number">Mesa <span data-cloudin-field="table.number"></span></p>`; los pedidos, con `carrito.js` (sección 6) |
| Pedidos desde el QR (interruptor) | `recibe_pedidos` en `estado/` | `carrito.js` pone y quita los botones solo |

**Recoger y Domicilio** vienen encendidos en todos los restaurantes. Si el restaurante apaga
uno en Personalizar, el menú deja de ofrecerlo al instante (y si lo enciende, vuelve), **en
todas partes**: en la carta de la mesa y en el menú de domicilios (es la misma página). Todo
lo que diga «domicilio», «recoger» o «para llevar» (avisos, botones, el enlace de WhatsApp
para pedir a domicilio, el texto del pie) va dentro de un elemento con su `data-cloudin-if`;
nunca escrito suelto.

---

## 5. Leer la carta sin el runtime (si usas tu propio JavaScript o un framework)

Úsalo solo si el diseño no se puede hacer con plantillas. Pierdes la vista previa en vivo
del panel (sección 8), la caché del runtime, los colores y la portada automáticos, la carta
en vivo y la prueba de fuego (10.4); tienes que hacerlos tú. La carta en vivo es obligatoria
igual: con la página a la vista, vuelve a pedir la carta cada 15 s con `If-None-Match:
<ETag>` (Cloudin responde `304` si no cambió) y repinta solo cuando llega una nueva. Y la
tabla 4.8 también: todos los menús, todo lo de Personalizar, y Recoger y Domicilio según
`services`.
Con un framework (Astro, etc.), la salida tiene que ser **estática** y la carta se pide
**en el navegador**, nunca al construir el sitio (si no, un cambio de precio exigiría
republicar).

### 5.1 La petición

```
GET https://<servidor>/api/public/<slug>/menu/
GET https://<servidor>/api/public/<slug>/menu/?table=<token o número de mesa>
```

Sin autenticación, CORS abierto (`*`), sin cookies (`credentials: "omit"`). Responde con
`ETag` y `Cache-Control: public, max-age=30`: manda `If-None-Match` y recibes `304` si no
cambió. Con `?table=` la respuesta trae `"table": {"number": 3}`. Tope: 600 consultas cada
10 minutos por IP. `404` si el restaurante no existe o está inactivo; `429` si se pasa el
tope.

### 5.2 La respuesta (`cloudin.menu/v1`)

```json
{
  "schema": "cloudin.menu/v1",
  "business": {
    "slug": "la-casa", "name": "La Casa", "tagline": "Comida casera", "description": null,
    "welcome_message": "¡Bienvenido! Pide desde tu mesa.",
    "logo": "https://…/logo.webp", "cover": "https://…/portada.webp",
    "brand": { "primary": "#B3261E", "secondary": "#F2C14E", "background": "#1A1110", "text": null },
    "contact": { "whatsapp": "+573001234567", "phone": "+573001234567", "email": "hola@lacasa.co",
                 "address": "Cra 1 # 2-3", "city": "Cali", "maps_url": null },
    "social": { "instagram": null, "facebook": "https://facebook.com/lacasa", "tiktok": null },
    "hours": [ { "day": "mon", "closed": true }, { "day": "tue", "open": "12:00", "close": "21:00" } ],
    "services": { "dine_in": true, "takeaway": true, "delivery": false },
    "payment_methods": ["efectivo", "nequi"],
    "payment_methods_text": "Efectivo y Nequi"
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
              "description": "Carne de res, queso y papas.", "price": 24000,
              "image": "https://…/hamburguesa.webp",
              "available": true, "featured": false, "tags": ["recomendado"], "tax": null,
              "variants": [ { "id": "9a2e41c7-…", "key": "doble-carne", "name": "Doble carne", "price": 32000 } ],
              "modifier_groups": [
                { "id": "…", "key": "salsa", "name": "Salsa", "min": 1, "max": 1,
                  "options": [ { "id": "c1d0…", "key": "verde", "name": "Verde", "price": 0 },
                               { "id": "c2e7…", "key": "roja", "name": "Roja", "price": 1500 } ] }
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

| Campo | Qué es |
|---|---|
| `product.id` | **El id para pedir** (UUID). No cambia si el restaurante renombra el plato |
| `product.price` | Pesos enteros. `null` = sin precio: no se puede pedir (y viene `available: false`) |
| `product.available` | `false` = agotado: mostrarlo apagado, sin botón de pedir |
| `variants[].price` | **Precio completo** de esa presentación (no una diferencia) |
| `modifier_groups[]` | `min` ≥ 1 = obligatorio; `max` = 1 → se elige una (radio); `max` = `null` → sin tope |
| `options[].price` | **Lo que suma** al precio (0 si nada) |
| `image`, `logo`, `cover` | URLs absolutas, listas para `<img src>` |
| `menus[]` | **Todos** los menús de «Mi menú», en orden; cada uno con sus categorías. Un menú nuevo llega aquí |
| `services.takeaway`, `services.delivery` | Recoger y Domicilio: `true` salvo que el restaurante los apague en Personalizar. `dine_in` es siempre `true` (en la mesa se pide con el QR) |
| `payment_methods` / `payment_methods_text` | Claves (`efectivo`, `nequi`, `daviplata`, `tarjeta`, `transferencia`) / el mismo dato ya escrito para mostrar |
| `welcome_message` | Mensaje de bienvenida de Personalizar, o `null` |
| `tags` | Claves; el nombre está en `tags` de la raíz (también el de las etiquetas nuevas) |
| `hours[].day` | `mon`…`sun`. Varias entradas el mismo día = horario partido. Un cierre menor que la apertura pasa la medianoche |
| `meta.version` | Sube con cada cambio de la carta (va en el `ETag`) |

Precio de una línea, **igual que lo calcula Cloudin** (solo para mostrar):
`(presentación elegida ? su precio : precio del producto) + suma de las opciones elegidas`.

Escapa todo texto de la carta antes de meterlo con `innerHTML` (o usa `textContent`): lo
escribe el restaurante.

---

## 6. Pedidos de la mesa

### 6.1 Cuándo se puede pedir

El menú deja pedir solo si se cumplen **las cuatro**:

1. La página se abrió desde el QR de una mesa: `?mesa=<token>` (12 caracteres al azar;
   **el token, no el número**).
2. `CLOUDIN_CONFIG.apiKey` tiene la API key.
3. El restaurante tiene encendidos los **pedidos desde el QR de la mesa** (el interruptor
   de su panel; un restaurante nuevo los trae encendidos). Cloudin lo dice en
   `recibe_pedidos` (6.3).
4. La dirección desde la que se abre el menú está registrada en Cloudin (sección 9.2).

Sin eso, la carta se ve igual pero sin botones: es el menú «para mirar» (Instagram,
entrada del local).

### 6.2 Usa `carrito.js` (recomendado)

Cópialo **sin cambios** de `client/example/carrito.js` y cárgalo después del runtime.
Hace todo lo de esta sección:

- Pone **«Agregar»** en cada plato disponible con precio (al final de `.dish__body`).
- Si el plato tiene presentaciones o adiciones, abre una ventana para elegir y valida las
  obligatorias.
- Guarda el carrito compartido (`PUT borrador/`) y resuelve el `409` cuando dos teléfonos
  agregan a la vez.
- Barra flotante «Ver pedido (2) · $ 90.000» / «Mesa 3 · 1 pedido»; carrito con − / +;
  nombre de quien pide (recordado en el teléfono); lo ya pedido con su estado.
- «Enviar pedido» (`POST enviar/`) → «¡Pedido enviado! La cocina ya lo tiene.».
- Consulta `estado/` cada 5 s mientras la página está visible; si `recibe_pedidos` es
  `false`, quita los botones, y si vuelve a ser `true`, los pone otra vez.

Personalizarlo: los colores salen de `--cloudin-primary` (botones) y `--fondo` (ventanas);
los textos y el CSS están al principio del archivo. Si lo modificas, conserva el escape de
textos (`esc()`) y el manejo del `409`.

### 6.3 La API (si haces tu propio carrito)

Todas las rutas cuelgan de `https://<servidor>/api/v1/mesa/<token>/` y llevan la cabecera
**`X-API-Key: ck_…`** (dice el restaurante; el token en la ruta dice la mesa).

```
Abre el QR ─▶ GET  /api/public/<slug>/menu/?table=<token>   carta + número de mesa
          ─▶ GET  …/estado/                                 carrito y pedidos de la mesa
Agrega    ─▶ PUT  …/borrador/        {items, version}       (todos los de la mesa ven el mismo carrito)
Avisa     ─▶ POST …/aviso/           {by}                   opcional: «Ana va a enviar» durante 20 s
Envía     ─▶ POST …/enviar/          {by, note}             201: llegó a la cocina; la mesa quedó ocupada
Espera    ─▶ GET  …/estado/ cada 5 s                        Pendiente → En preparación → Servido
El restaurante cierra la cuenta en su panel ─▶ ocupada: false, cuenta: null
```

**`GET …/estado/`**

```json
{
  "mesa": 3, "recibe_pedidos": true, "ocupada": true,
  "cuenta": {
    "id": 46, "abierta_desde": "2026-09-26T22:39:30Z", "total": 90000.0,
    "pedidos": [ { "id": 48, "estado": "pending", "estado_texto": "Pendiente",
                   "creado": "2026-09-26T22:39:30Z", "por": "Ana", "total": 90000.0,
                   "items": [ { "nombre": "Hamburguesa clásica · Doble carne, Roja picante", "cantidad": 2,
                                "nota": "sin pepinillos" } ] } ]
  },
  "borrador": { "items": [], "version": 14, "total": 0.0, "actualizado": "2026-09-26T22:39:19Z" },
  "aviso": null,
  "servidor": "2026-09-26T22:39:30Z"
}
```

`recibe_pedidos: false` → no muestres el carrito. `cuenta: null` → la mesa está libre.
`aviso` → nombre de quien dijo «voy a enviar» hace menos de 20 s.

**`PUT …/borrador/`** — reemplaza el carrito **entero**:

```json
{
  "version": 14,
  "items": [
    { "product": "<product.id>", "variant": "<variant.id>" , "options": ["<option.id>"],
      "quantity": 2, "note": "sin pepinillos", "by": "Ana" }
  ]
}
```

- Para agregar: toma `borrador.items` del último estado, agrega o suma cantidad si es la
  misma línea (mismo producto, presentación y opciones), y manda la lista completa. Las
  líneas que ya estaban se mandan **tal como llegaron**.
- Responde `200` con el estado completo; cada línea vuelve calculada por Cloudin (`name`,
  `unit_price`), y `borrador.total`.
- Si `version` no es la actual → **`409`** con el estado al día: reaplica tu cambio sobre
  ese carrito y reintenta una vez.
- Una línea que no se puede cobrar (agotada, eliminada, falta una opción obligatoria) **no
  entra**, sin error: compara lo que mandaste con lo que volvió.
- Topes: 60 líneas, cantidad 1 a 99, `by` hasta 60 caracteres, `note` hasta 200 (la nota
  de un plato solo se guarda si el producto la permite en el panel). Armar el carrito **no**
  ocupa la mesa.

**`POST …/aviso/`** — `{"by": "Ana"}`. Opcional.

**`POST …/enviar/`** — `{"by": "Ana", "note": "Somos 3, una silla para bebé"}`. Responde
**`201`** con el estado (carrito vacío, el pedido en `cuenta.pedidos`) y
`"pedido_enviado": 48`. Si la mesa estaba libre, **se ocupa**: se abre su cuenta, el pedido
aparece en **Mensajes** y la comanda en **Cocina**. Si ya estaba ocupada (por otro pedido o
por un mesero), se suma a la misma cuenta. Los precios se recalculan al enviar.

**Pedido directo sin carrito compartido** — `POST https://<servidor>/api/v1/tables/<token>/orders/`
(cada teléfono arma su pedido y lo manda de una vez):

```json
{ "customer_name": "Luis", "note": "", "guests": 2,
  "items": [ { "product": "<product.id>", "variant": null, "options": ["<option.id>"], "quantity": 1 } ] }
```

Responde `201` con `{"pedido": {"id", "table_number", "status", "items": [...], "total"}, "cuenta_id"}`
(ahí `unit_price` viene como texto `"35000.00"`). Los errores de validación vienen por campo
(`{"items": ["Falta elegir «Salsa» para Hamburguesa."]}`).

**Formatos de línea** (en los dos): usa siempre los **id de la carta** (`product`,
`variant`, `options`). **Nunca mandes precio ni nombre**: los pone Cloudin.

### 6.4 Estados del pedido y cierre

| `estado` | `estado_texto` | Lo cambia |
|---|---|---|
| `pending` | Pendiente | Así llega |
| `preparing` | En preparación | Cocina, en el panel |
| `served` | Servido | Cocina o el mesero |
| `cancelled` | Anulado | El restaurante; no aparece en `estado` |

La mesa sigue ocupada hasta que el restaurante **cierra la cuenta** en su panel (Mesas →
la mesa → Cerrar cuenta). Entonces `estado` devuelve `"ocupada": false` y `"cuenta": null`:
muestra «¡Gracias por tu visita!» y deja el carrito limpio. Nada se cierra solo.

### 6.5 Errores

| Código | `codigo` | Qué pasó | Qué mostrar |
|---|---|---|---|
| `400` | — | Falta `X-API-Key` o está mala («No se identificó el restaurante…») | Error de configuración: revisa `apiKey` |
| `400` | — / `opciones` | Carrito vacío, opción obligatoria faltante o que ya no existe | El `detail` tal cual; `Cloudin.refresh()` |
| `403` | `sin_pedidos` | El restaurante apagó los pedidos por QR | «Pídele tu pedido al mesero.» y oculta el carrito |
| `404` | — | Token de mesa inexistente (QR viejo) | «Este QR ya no es válido, pide ayuda al mesero.» |
| `409` | — | El carrito cambió en otro teléfono | Reaplica y reintenta |
| `409` | `agotado` | Un plato del carrito se agotó | Quítalo y avisa |
| `429` | `demasiados` | Muchos pedidos seguidos desde la misma IP | El `detail`; no borres el carrito |
| — | — | `fetch` falla (sin señal o CORS) | «Sin conexión, reintentando…»; no borres el carrito |

Un error de **CORS** no llega como respuesta: el `fetch` falla y la consola dice «blocked by
CORS policy». Casi siempre es la dirección del menú sin registrar (sección 9.2).

Topes por IP y restaurante: carta 600 / 10 min · `PUT borrador` 240 / 10 min · `enviar` y
pedido directo 20 / 10 min. `estado/` cada 5 s y solo con la página visible.

**No uses `/api/v1/site/…`** en un menú público: piden por número de mesa sin token y son
para la tablet del propio restaurante.

---

## 7. Cambiar la carta: platos, precios, fotos, categorías

El menú **no** se edita para cambiar la carta. La carta vive en Cloudin y se cambia de dos
formas; en las dos el menú publicado muestra el cambio solo: al instante para quien lo abre,
y en máximo `live` segundos (15) para quien ya lo tiene abierto, sin recargar.

### 7.1 En el panel del restaurante (el día a día)

`https://<servidor>/panel/` con el usuario del restaurante (o el superusuario desde el panel
maestro → **Entrar en modo soporte**):

| Qué | Dónde | Efecto en el menú |
|---|---|---|
| Crear categoría | **Mi menú** → **+ Categoría** | Nueva sección (se ve cuando tenga productos) |
| Crear o editar un plato | **Mi menú** → **+ Producto** / tocar el plato | Nombre, precio, categoría, descripción, foto |
| Foto del plato | Editor → **Toma o elige una foto** | `product.image` (Cloudin la achica y la guarda) |
| Agotar / volver a tener | Editor → **Disponible**, o **Agotar** en la lista | `product.available` → «Agotado», sin botón |
| Destacar | Editor → **Destacar en el menú** | Aparece en `featured` |
| Tamaños | Editor → Opciones avanzadas → **Tamaños o presentaciones** | `variants`; precio «Desde» |
| Adiciones y opciones obligatorias | Editor → **Adiciones** → Crear grupo (Obligatorio, ¿Cuántas puede elegir?) | Ventana de opciones al agregar |
| Etiquetas | Editor → **Etiquetas** (una nueva: «Nueva etiqueta» → **Agregar**; queda en la lista para todos los platos) | `tags` |
| Subir precios en bloque | Mi menú → Seleccionar → **Subir precios %** | Precios nuevos |
| Otro menú (Almuerzos, Bebidas…) | Mi menú → **Nuevo menú**, y dentro sus categorías y platos | Otra sección en `menus` con su nombre, sus categorías y sus platos (sección 4.1): sale sola |
| Orden | Mi menú → **Ordenar** | El orden de la carta |
| Eliminar | Editor o lista → «⋯» → **Eliminar** (pide confirmar) / Archivar | Desaparece de la carta (se puede deshacer) |
| Logo, 4 colores, portada | **Personalizar** → Logo y colores / Portada | `business.logo`, `--cloudin-*`, `business.cover` y `--cloudin-cover` |
| Frase, descripción, bienvenida | Personalizar → Datos del negocio | `business.tagline`, `.description`, `.welcome_message` |
| WhatsApp, teléfono, correo, dirección, ciudad, Maps | Personalizar → Contacto y WhatsApp | `business.*` (tabla 4.8) |
| Horario | Personalizar → Horario | `business.hours_today`, `business.open_now` |
| Instagram, Facebook, TikTok | Personalizar → Redes sociales | `business.instagram`, `.facebook`, `.tiktok` |
| Recoger y Domicilio (encendidos por defecto) | Personalizar → Servicios y medios de pago | `business.takeaway`, `business.delivery`: lo apagado desaparece del menú |
| Medios de pago | Personalizar → Servicios y medios de pago | `business.payment_methods_text` |
| Mesas | **Códigos QR** → «¿Cuántas mesas tienes?» | Mesas 1..N con su QR |

Personalizar se ve en vivo en la vista previa del panel («Así se ve en tu menú», sección 8)
antes de guardar; al guardar, llega al menú publicado en máximo 15 s.

Un plato **sin precio** queda no disponible hasta que se le ponga precio.

### 7.2 Por importación (carga inicial o muchos cambios de una vez)

Cuando el restaurante ya tiene su carta (en PDF, en una foto, en su sitio viejo), **tú** la
escribes en `cloudin/menu.seed.json` y la importas. Así no hay que cargar plato por plato.

**El archivo** (esquema `cloudin.menu/v1`, el mismo de la carta pública pero sin `id`):

```json
{
  "schema": "cloudin.menu/v1",
  "business": {
    "slug": "la-casa",
    "name": "La Casa",
    "tagline": "Comida casera",
    "description": null,
    "logo": "fotos/logo.png",
    "cover": "fotos/portada.jpg",
    "brand": { "primary": "#B3261E", "secondary": "#F2C14E", "background": "#1A1110", "text": "#FFF6EC" },
    "contact": { "whatsapp": "3001234567", "phone": null, "email": "hola@lacasa.co",
                 "address": "Cra 1 # 2-3", "city": "Cali", "maps_url": null },
    "social": { "instagram": "https://instagram.com/lacasa", "facebook": "https://facebook.com/lacasa", "tiktok": null },
    "hours": [ { "day": "mon", "closed": true }, { "day": "tue", "open": "12:00", "close": "21:00" } ],
    "services": { "takeaway": true, "delivery": true },
    "payment_methods": ["efectivo", "nequi", "tarjeta"],
    "owner": { "name": null, "email": null, "phone": null }
  },
  "menus": [
    {
      "key": "carta", "name": "Carta", "description": null,
      "categories": [
        {
          "key": "hamburguesas", "name": "Hamburguesas", "description": "Todas con papas.", "image": null,
          "products": [
            {
              "key": "hamburguesa-clasica", "name": "Hamburguesa clásica",
              "description": "Carne de res, queso, lechuga y tomate.",
              "price": 24000, "image": "fotos/hamburguesa-clasica.jpg",
              "available": true, "featured": true, "tags": ["recomendado"], "tax": null,
              "variants": [ { "key": "doble", "name": "Doble carne", "price": 32000 } ],
              "modifier_groups": [
                { "key": "salsa", "name": "Elige tu salsa", "min": 1, "max": 1,
                  "options": [ { "key": "verde", "name": "Verde", "price": 0 },
                               { "key": "roja", "name": "Roja picante", "price": 1500 } ] }
              ]
            }
          ]
        }
      ]
    }
  ],
  "tables": { "count": 12 },
  "meta": { "menu_page": "https://la-casa.pages.dev/", "missing": ["business.nit"] }
}
```

Reglas del archivo (Cloudin las valida y dice exactamente dónde está cada error):

| Campo | Regla |
|---|---|
| `schema` | Exactamente `"cloudin.menu/v1"` |
| `business.slug` | El identificador del restaurante en Cloudin. Tiene que existir: el usuario lo crea antes en el panel maestro (sección 2) |
| `key` (menús, categorías, productos, presentaciones, grupos, opciones) | kebab-case: minúsculas, números y guiones, máximo 60 (`hamburguesa-clasica`). **Estables**: son las que reconocen el plato al reimportar. Únicas entre hermanos |
| `name` | Obligatorio. Producto hasta 120 caracteres; categoría y menú hasta 80; presentación, grupo y opción hasta 60 |
| `price` | Pesos **enteros** (`24000`, no `"24.000"` ni `24000.5`). En el producto puede ser `null` (queda no disponible y aparece en los avisos) |
| `variants[].price` | Precio completo de esa presentación (obligatorio) |
| `options[].price` | Lo que suma (0 si nada) |
| `min` / `max` | `min` ≥ 0; `max` vacío (`null`) = sin tope, o ≥ `min` y ≥ 1. Un grupo sin opciones se ignora |
| `description` | Hasta 2000; más de 140 se ve largo (aviso) |
| `tags` | Claves kebab-case; las nuevas se crean con su nombre |
| `tax` | `null`, `"INC8"`, `"IVA19"` o `"EXENTO"` |
| `image`, `logo`, `cover` | Ruta **relativa** a `cloudin/` (`fotos/hamburguesa-clasica.jpg`). JPG, PNG o WebP de hasta 8 MB (el logo también SVG). Una URL externa se ignora (aviso): Cloudin guarda la foto, no un enlace |
| `hours` | `day` = `mon`…`sun`; `open`/`close` en `HH:MM`; `{"day": "mon", "closed": true}` para cerrado |
| `brand.*` | `#RRGGBB` |
| `contact.whatsapp`, `phone` | Celular colombiano (`3001234567` o `+573001234567`) |
| `payment_methods` | De: `efectivo`, `nequi`, `daviplata`, `tarjeta`, `transferencia` |
| `services` | `takeaway` (Recoger) y `delivery` (Domicilio), `true` o `false`. El que no pongas queda **encendido**; `dine_in` se ignora (en la mesa se pide con el QR) |
| `tables.count` | 0 a 200: crea las mesas 1..N que falten (nunca borra) |
| `meta.menu_page` | La dirección del menú publicado: se registra si el restaurante no tenía una (sección 9.2) |
| `meta.missing` | Lista libre de lo que no sabías (precios, NIT…): sale en el resumen para que el usuario lo complete |

No pongas `meta.site_url`: es para otra integración (una tablet con sitio propio) y
registra ese sitio en otro campo.

**Importar por la API** (desde la carpeta `cloudin/` del repositorio del menú, con el
token en una variable de entorno):

```bash
cd cloudin
zip -r /tmp/fotos.zip fotos          # las rutas de la semilla (fotos/…) quedan igual dentro del zip

# 1) Revisar sin cambiar nada
curl -sS -X POST "https://<servidor>/api/admin/import-menu/" \
     -H "Authorization: Bearer $CLOUDIN_ADMIN_TOKEN" \
     -F seed=@menu.seed.json -F assets=@/tmp/fotos.zip -F dry_run=1 -F invite=0

# 2) Si la revisión no tiene errores ni sorpresas: importar de verdad
curl -sS -X POST "https://<servidor>/api/admin/import-menu/" \
     -H "Authorization: Bearer $CLOUDIN_ADMIN_TOKEN" \
     -F seed=@menu.seed.json -F assets=@/tmp/fotos.zip -F invite=0
```

Sin `assets`, la revisión cuenta todas las fotos como faltantes.

Campos del formulario: `seed` (obligatorio, JSON de hasta 2 MB), `assets` (zip de hasta
60 MB, 1000 archivos y 150 MB descomprimido; cada foto hasta 8 MB; las rutas de la semilla
se buscan tal cual dentro del zip, con o sin una carpeta `site/` delante), `dry_run` (`1` = solo revisar),
`invite` (`1` = si la semilla trae `owner.email` y el restaurante no tiene dueño, lo crea y
le manda la invitación), `create_tenant` (`1` = crear el restaurante si no existe; úsalo solo si el
usuario lo pide: lo normal es que lo cree en el panel maestro, donde recibe el usuario y
la contraseña del dueño).

Respuesta (`200`, o `201` si creó el restaurante):

```json
{ "restaurant": "la-casa", "name": "La Casa", "created": false, "applied": true,
  "counts": { "productos": { "creados": 12, "actualizados": 0, "sin_cambios": 0, "borrados_por_el_dueno": 0 } },
  "kept_owner_changes": ["Hamburguesa clásica · precio: se dejó lo que puso el dueño"],
  "warnings": ["«Jugo natural» no tiene precio: quedó no disponible hasta que el dueño lo complete."],
  "photos": { "subidas": 11, "faltantes": ["fotos/jugo-natural.jpg"] },
  "tables_created": 12, "invitation": "", "missing": ["business.nit"] }
```

Errores: `401` token inválido o revocado · `400` con `"errors": [...]` (cada error dice
dónde: `menus[0].categories[1].products[3].price: …`). Corrígelos todos y vuelve a intentar.

Con acceso al servidor (o a su base desde un PC), lo mismo por consola:
`python manage.py import_menu cloudin/menu.seed.json --assets cloudin --dry-run` y sin
`--dry-run` para aplicar (`--no-invite` para no invitar al dueño).

**Cómo se comporta la importación** (léelo antes de reimportar):

- **Idempotente por `key`:** reimportar actualiza, nunca duplica. Un producto se reconoce
  por su clave dentro del menú, aunque el dueño lo haya movido de categoría.
- **Respeta al dueño, campo por campo:** si un campo sigue igual a lo que trajo la última
  importación, se actualiza con la semilla nueva; si el dueño lo cambió en el panel, se
  deja el del dueño y sale en `kept_owner_changes`. Lo mismo con fotos, etiquetas y el
  horario. **Para cambiar algo que el dueño ya tocó en el panel, se cambia en el panel.**
- **Nunca borra**, y no revive lo que el dueño eliminó o archivó. Para quitar un plato se
  elimina en el panel.
- Las fotos se convierten a WebP (productos 800 px, portada 1600 px, logo 512 px; el logo
  puede ser SVG) y quedan guardadas en Cloudin.

### 7.3 Qué NO hacer con la carta

- No copies la carta al HTML como fuente de datos ni «actualices precios» en el código.
- No uses la API interna del panel (`/api/v1/staff/…`): exige la sesión del dueño y CSRF; es
  para el panel, no para menús.
- No crees el restaurante con `create_tenant=1` sin que el usuario lo pida.

---

## 8. La vista previa del panel

El panel del restaurante (Personalizar y el editor de productos) muestra el menú real en un
iframe: carga la «Página del menú» con `?cloudin-preview=1` y le manda por `postMessage` lo
que el dueño está editando, antes de guardarlo. El runtime lo acepta solo desde el origen
del servidor Cloudin. Para que funcione:

- Usa el **runtime** (sección 4). Un menú con JavaScript propio se ve en la vista previa, pero
  sin los cambios en vivo.
- No impidas el iframe: nada de `X-Frame-Options: DENY`. Si pones una política, que sea
  `Content-Security-Policy: frame-ancestors 'self' https://<servidor>`.
- Las visitas con `?cloudin-preview=1` no cuentan como visitas al menú.
- La vista previa tiene el ancho de un teléfono (unos 400 px) y una barra abajo para moverse
  de lado. Si el menú se sale por la derecha, no es responsive: arréglalo para 390 px.

---

## 9. Publicar y conectar

### 9.1 Cloudflare Pages

1. El usuario sube el repositorio del menú a GitHub.
2. Cloudflare → **Workers & Pages** → **Create application** → pestaña **Pages** →
   **Import an existing Git repository** → el repositorio → **Begin setup**.
3. Framework preset **None**, Build command **vacío**, Build output directory **`site`**
   (la carpeta de 3.1; si el `index.html` estuviera en la raíz, `/`), Production branch
   **`main`** → **Save and Deploy**.
4. La dirección es `https://<proyecto>.pages.dev` (si el nombre estaba tomado, Cloudflare le
   agrega letras). Cada push a `main` publica; los cambios de la carta no necesitan
   publicar.

Con Astro u otro generador: preset del framework, `npm run build`, salida `dist`.

### 9.2 Registrar la dirección en Cloudin (sin esto no hay QR ni pedidos)

Cloudin **no detecta el menú solo**. El usuario registra su dirección:

- Panel maestro → el restaurante → tarjeta **«Menú digital»** → **Página del menú (QR)** =
  `https://<proyecto>.pages.dev/` (exacta: `https://`, `/` final, sin `?mesa`) →
  **Guardar**. Si el mismo menú también se abre desde un dominio propio, va en **Otras
  direcciones autorizadas** (una por línea).
- (Alternativa: `https://<servidor>/admin/` → Restaurantes (panel maestro) → Restaurantes →
  el restaurante → «Página del menú (QR)» y «Otros sitios autorizados» como lista JSON.)

Eso hace tres cosas: **arma los QR** (`<página>?mesa=<token>` por mesa, y la página sola
como QR general), **autoriza esa dirección a pedir** (CORS: esquema + dominio + puerto) y
**activa la vista previa** del panel. Después de abrir el menú una vez, la tarjeta dice
**Conectado**.

Leer la carta funciona desde cualquier dirección; **pedir** solo desde las registradas. Una
vista previa de Pages (`https://<hash>.<proyecto>.pages.dev`) o `http://localhost:8080` no
pueden pedir mientras no estén en «Otras direcciones autorizadas».

### 9.3 Quién toma los pedidos

Todos los restaurantes tienen Cloudin completo: no hay planes. Son dos interruptores que
cambia el administrador del restaurante en su panel:

| Interruptor | Dónde | Encendido | Apagado |
|---|---|---|---|
| **Pedidos desde el QR de la mesa** (viene encendido) | Inicio, Códigos QR y Meseros | El menú deja pedir | La carta queda para mirar (`recibe_pedidos: false`, `403 sin_pedidos`) |
| **App de meseros** (viene encendida; sin cuentas de meseros nadie entra) | Meseros | Los meseros toman pedidos en su app, a la misma cuenta de la mesa | Los meseros no pueden entrar |

La misma plantilla y la misma `apiKey` sirven para todos: `carrito.js` consulta el estado
cada 5 segundos y esconde o muestra los botones solo cuando el restaurante cambia el
interruptor.

### 9.4 `_headers` (opcional)

```
/*
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
  Content-Security-Policy: frame-ancestors 'self' https://<servidor>
```

Si agregas `script-src`, `connect-src` o `img-src`, permite `https://<servidor>` y la
dirección de las fotos (R2: `https://pub-….r2.dev`), y recuerda que `CLOUDIN_CONFIG` es un
`<script>` en línea.

---

## 10. Probar

### 10.1 En tu computador

```bash
python -m http.server 8080 --directory site      # en Mac/Linux: python3
```

`http://localhost:8080/` debe mostrar la carta real del restaurante (leer funciona desde
cualquier origen). Para probar pedidos desde localhost, el usuario agrega temporalmente
`http://localhost:8080` en «Otras direcciones autorizadas» y abres
`http://localhost:8080/?mesa=<token>`. El token lo copia el usuario de su panel → Códigos
QR → la mesa → **Copiar enlace** (`https://<proyecto>.pages.dev/?mesa=<token>`; los QR
aparecen cuando ya hay «Página del menú», sección 9.2). Al terminar, que quite `localhost`.

### 10.2 Contra el servidor, con `curl`

```bash
S=https://<servidor>; K=ck_...; T=<token-de-mesa>
curl -s "$S/api/public/<slug>/menu/?table=$T" | head -c 300          # carta + número de mesa
curl -s -H "X-API-Key: $K" "$S/api/v1/mesa/$T/estado/"                 # carrito y pedidos
curl -s -X PUT -H "X-API-Key: $K" -H "Content-Type: application/json" \
     -d '{"items":[{"product":"<product.id>","quantity":1}]}' "$S/api/v1/mesa/$T/borrador/"
curl -s -X POST -H "X-API-Key: $K" -H "Content-Type: application/json" \
     -d '{"by":"Prueba"}' "$S/api/v1/mesa/$T/enviar/"
```

Un pedido de prueba ocupa la mesa de verdad: pide al usuario que cierre esa cuenta en su
panel (Mesas → la mesa → Cerrar cuenta).

### 10.3 En el navegador (si tienes Playwright)

Abre `…/?mesa=<token>`, espera `html[data-cloudin-state="live"]`, comprueba que hay
botones `.cl-agregar`, agrega un plato, abre `.cl-barra`, escribe en `#cl-nombre`, toca
«Enviar pedido» y espera el texto «¡Pedido enviado! La cocina ya lo tiene.». Sin `?mesa` no
debe haber `.cl-agregar`. Revisa que la consola no tenga errores y que no haya scroll
horizontal a 390 px de ancho.

### 10.4 Prueba de fuego: `?cloudin-check=1`

Abre el menú con `?cloudin-check=1`: en local `http://localhost:8080/?cloudin-check=1`, ya
publicado `https://<menú>/?cloudin-check=1`. El runtime carga el revisor de Cloudin
(`https://<servidor>/static/cloudin-check.v1.js`), que **sin guardar nada** le pasa a la
página cartas de prueba y mira si cambia:

| Prueba | Qué simula |
|---|---|
| Menú nuevo | El restaurante crea otro menú (Mi menú → Nuevo menú) con una categoría y un plato: tiene que salir con su nombre |
| Plato nuevo, categoría nueva | Los crea en el panel (y la categoría sale en la barra) |
| Cambiar nombre, precio, descripción y foto | Los edita en el panel (la foto no puede quedar tapada por un `srcset`) |
| Eliminar | Lo elimina |
| Agotado | Lo marca agotado |
| Escritos a mano | Quita todos los platos: lo que siga en la página está escrito en el HTML |
| Personalizar, fila por fila | Otro nombre, frase, descripción, bienvenida, logo, portada, WhatsApp, teléfono, correo, dirección, ciudad, Google Maps, horario, Instagram, Facebook, TikTok y medios de pago: cada uno tiene que verse |
| Recoger y Domicilio | Los apaga (no puede quedar nada que los ofrezca) y los enciende (tienen que ofrecerse) |
| Colores | Otros 4 colores en Personalizar: el principal, el secundario, el fondo y el texto tienen que usarse |
| Conexión | Bloque de conexión, `apiKey` y `carrito.js` |

Al final vuelve a pintar la carta real y muestra el informe: ✅ bien, ❌ hay que arreglarlo
(cada uno dice cómo, y si está escrito a mano o si no se muestra) y ⚠️ para revisar con el
usuario. **Mientras quede un ❌, el menú no está conectado.** El botón **Copiar informe** lo
deja listo para pegar. Si el servidor estaba dormido (Render gratis), espera hasta un minuto.

Con Playwright (Python):

```python
page.goto("http://localhost:8080/?cloudin-check=1")
page.wait_for_function("() => window.CloudinCheck && window.CloudinCheck.terminado", timeout=120000)
informe = page.evaluate("window.CloudinCheck")
print(informe["texto"])        # el mismo informe de la pantalla
assert informe["aprobado"], "quedan ❌"
```

Sin Playwright, pídele al usuario que abra la dirección con `?cloudin-check=1` y te pegue el
informe. Si la página no muestra ningún informe, es que no carga `cloudin-menu.v1.js` desde
el servidor (sección 3.2).

**Y la prueba en vivo, con el usuario:** con el menú abierto en su teléfono, que agote un
plato en el panel. En máximo 15 segundos el plato sale «Agotado», **sin recargar**; al
volverlo a poner disponible, regresa. Lo mismo con un plato nuevo, un menú nuevo, otro
color, otra portada y Domicilio apagado y vuelto a encender.

---

## 11. Diagnóstico

| Síntoma | Causa | Arreglo |
|---|---|---|
| «Cargando la carta…» cerca de un minuto y luego carga | Render gratis estaba dormido | Normal en el plan gratis |
| Estado `error` / «No se pudo cargar la carta» | `api` mal escrita (servidor o slug) o Cloudin caído | Abre la URL de `api` en el navegador |
| «Cargando…» sin errores, o carta vacía | El restaurante no tiene productos | Cargar la carta (sección 7) |
| Tu diseño con secciones vacías | Plantilla fuera de su zona, con dos elementos raíz, o sin `products` en la categoría | Compara con 4.1 |
| Un dato no aparece | No está lleno en el panel, o el campo está mal escrito (tres partes, mayúsculas) | Tabla 4.4 |
| No hay «Agregar» en ningún plato | Sin `?mesa`, `apiKey` vacía o mala, `carrito.js` no cargó (404), pedidos por QR apagados en el panel, o CORS | Sección 6.1 y la consola |
| «Agregar» falta en un plato | Agotado o sin precio | Panel → Mi menú |
| «blocked by CORS policy» en la consola | La dirección del menú no coincide con la registrada (http/https, www, otra de Pages) | Sección 9.2 |
| En el panel: «Tu menú todavía no está publicado» / sin QR | «Página del menú (QR)» vacía | Sección 9.2 |
| La ficha dice «Sin conexión todavía» | El menú no tiene el bloque de conexión o apunta a otro servidor | Sección 3.2 (Copiar código) |
| La ventana del carrito es ilegible | Falta `--fondo` | Regla 4.6.5 |
| «Enviaste muchos pedidos seguidos…» | Tope por IP (el wifi del local es una sola IP) | Esperar |
| Un cambio de precio no se ve | Carta guardada en el teléfono (hasta `cacheTtl` sin QR) | Esperar un minuto y recargar |
| La importación dice «se dejó lo que puso el dueño» | El dueño cambió ese campo en el panel | Cambiarlo en el panel |
| Un plato nuevo, una foto o un precio del panel no aparecen; a lo sumo cambian los agotados | La carta está escrita a mano en el HTML | Sección 0 y `?cloudin-check=1` |
| «Nuevo menú» en el panel no agrega nada a la carta | El menú usa una raíz fija `data-cloudin="menu"` (un solo menú) o el menú nuevo todavía no tiene platos | `data-cloudin="menus"` con la plantilla `menu` (4.1); agregarle una categoría y un plato |
| Cambiar colores en Personalizar no hace nada | El CSS tiene los colores fijos | `var(--cloudin-primary, …)` y los otros 3 (tabla 4.8) |
| Cambiar la portada o el logo no hace nada | La imagen está escrita a mano, o tiene `srcset` / `<picture>` | `data-cloudin-src` sin `srcset`; portada de fondo con `var(--cloudin-cover, …)` (regla 4.6.10) |
| El correo, Facebook, TikTok o Maps no aparecen | No hay elemento para ese dato, o el enlace está escrito a mano | La fila de la tabla 4.8 |
| Apagué Domicilio (o Recoger) y el menú lo sigue ofreciendo | El aviso o botón está escrito sin `data-cloudin-if` | `data-cloudin-if="business.delivery"` / `business.takeaway` |
| Una etiqueta nueva no sale en los platos | La plantilla `product` no tiene `data-cloudin="tags"` | Tabla 4.8 |
| En la vista previa del panel el menú sale cortado a la derecha | El menú no se ajusta a un teléfono (ancho fijo) | Que se vea bien a 390 px, sin scroll horizontal; en el panel la vista previa tiene una barra para moverse de lado |
| El menú solo cambia al recargar | `live: 0`, o tu propio JavaScript pinta la carta una sola vez | Quita `live: 0`; pinta con el runtime (sección 4) |
| Las animaciones o botones propios de los platos se pierden al rato | La carta se repintó sola (llegó un cambio del panel) | Engánchalos en `cloudin:rendered` (sección 4.5) |
| `?cloudin-check=1` no muestra nada | La página no carga el runtime desde el servidor | Sección 3.2 |

---

## 12. Antes de decir «listo»

```
[ ] ?cloudin-check=1 sin ❌ (los ⚠️ revisados con el usuario), en local y ya publicado
[ ] Con el menú abierto, un agotado del panel se ve en máximo 15 s, sin recargar
[ ] La carta sale de Cloudin: ningún menú, categoría, plato, precio, foto ni etiqueta escrito a mano
[ ] Todos los menús: menus > template menu > categories > template category (con products) + template product (con tags)
[ ] Tabla 4.8 completa: todo lo de Personalizar en la página (logo, portada, frase, descripción,
    bienvenida, WhatsApp, teléfono, correo, dirección, ciudad, Maps, horario, Instagram,
    Facebook, TikTok, pagos, Recoger y Domicilio) y los 4 colores con var(--cloudin-…)
[ ] Recoger y Domicilio: nada que los ofrezca fuera de su data-cloudin-if
[ ] Lo que el JavaScript propio hace a los platos, enganchado en cloudin:rendered
[ ] Si había mesa.html: solo redirige a ?mesa= (sección 0, paso 7)
[ ] Bloque de conexión con servidor, slug y apiKey reales (no inventados); runtime cargado desde el servidor
[ ] carrito.js junto a index.html, cargado después del runtime
[ ] Los datos opcionales llevan data-cloudin-if (sin display en línea); imágenes de Cloudin sin srcset
[ ] --fondo definido; .dish__body en la tarjeta del plato; texto de carga y estado error con CSS
[ ] Se ve bien a 390 px, sin scroll horizontal; imágenes con loading="lazy"
[ ] Sin X-Frame-Options: DENY (vista previa del panel)
[ ] Probado: carta en live, sin ?mesa no hay botones, con ?mesa se agrega y se envía (o curl de 10.2)
[ ] Publicado en Pages SOLO con confirmación del usuario
[ ] La dirección registrada en Cloudin (9.2) y la ficha dice «Conectado»
[ ] Si importaste la carta: dry_run primero, sin errores, y los avisos/missing reportados al usuario
[ ] Ningún token cld_ en el repositorio ni en el historial de git
```
