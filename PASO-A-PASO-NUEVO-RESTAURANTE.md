# Paso a paso: registrar un restaurante y conectar su menú digital

> **Qué es:** la receta completa, en orden, para dar de alta un restaurante en Cloudin y
> dejar su menú digital (publicado en Cloudflare Pages) mostrando la carta y recibiendo
> pedidos desde el QR de cada mesa. Sirve para **cualquier** menú que diseñes: la Parte 3
> dice exactamente qué tiene que tener tu HTML.
>
> Lo que se usa del repositorio:
>
> - **`client/plantilla/index.html`**: la plantilla mínima de un menú conectado. Es la base
>   recomendada.
> - **`client/example/carrito.js`**: el botón «Agregar», el carrito de la mesa y el envío
>   del pedido. Se copia tal cual.
> - `GUIA-MENU-DIGITAL.md`: la referencia larga (la API, los errores, la seguridad). Para
>   seguir esta guía no hace falta.
> - `CLAUDE-MENU-DIGITAL.md`: si el menú lo va a construir Claude Code, dale este archivo
>   (cópialo al repositorio del menú como `CLAUDE.md`). Incluye cómo cargar la carta
>   completa de una vez con `menu.seed.json`.
>
> Todo lo que sigue está comprobado en el código y en un navegador: la plantilla pinta la
> carta, el pedido llega a la cocina, y los nombres de pantallas y botones son los del
> panel.

---

## 0. Antes de empezar

Necesitas:

1. **Cloudin funcionando en internet** (`DESPLIEGUE-GRATIS.md`) y su dirección, por ejemplo
   `https://cloudin-abcd.onrender.com`.
2. **El superusuario**: el usuario y la contraseña que pusiste en Render
   (`DJANGO_SUPERUSER_USERNAME` y `DJANGO_SUPERUSER_PASSWORD`).
3. **Una cuenta de GitHub y una de Cloudflare**, las dos gratis.
4. **Del restaurante**: su nombre, el correo de quien lo administra, cuántas mesas tiene, la
   carta (platos, precios y fotos), el logo y sus datos de contacto y horario.

Nombres que se repiten en la guía:

| En la guía | Qué es | Ejemplo |
|---|---|---|
| `<servidor-cloudin>` | La dirección de Cloudin, sin `https://` y sin `/` al final | `cloudin-abcd.onrender.com` |
| `<slug>` | El identificador del restaurante (lo eliges en la Parte 1) | `la-casa` |
| `ck_…` | La API key del restaurante (Parte 1, paso 6): `ck_` y 43 caracteres más | `ck_Xa3…` |
| `<proyecto>` | El nombre del proyecto en Cloudflare Pages (Parte 4) | `la-casa-menu` |
| token de mesa | El código de cada mesa que va dentro de su QR (`?mesa=…`). Lo crea Cloudin | `td8vIrnwaZPF` |

El recorrido:

```
Parte 1. Registrar el restaurante ........ panel maestro   https://<servidor-cloudin>/master/
Parte 2. Cargar su carta y sus datos ..... su panel        https://<servidor-cloudin>/panel/
Parte 3. Armar el menú (HTML) ............ tu computador   client/plantilla/index.html
Parte 4. Publicarlo ...................... Cloudflare Pages
Parte 5. Registrar su dirección .......... panel maestro   el restaurante → «Menú digital»
Parte 6. Imprimir los QR y probar ........ su panel → Códigos QR
```

---

## Parte 1. Registrar el restaurante (panel maestro)

1. Abre `https://<servidor-cloudin>/master/`. Te lleva al inicio de sesión: escribe el
   usuario y la contraseña del superusuario → **Iniciar sesión**. En el plan gratis de
   Render, si nadie entró en los últimos 15 minutos, la primera carga tarda cerca de un
   minuto: es normal.
2. En la barra lateral: **Nuevo restaurante**.
3. Llena el formulario:

   | Campo | Qué poner | Detalle |
   |---|---|---|
   | **Nombre del restaurante** | `La Casa` | Obligatorio. Es el título del menú (`business.name`). Se corrige después en `/admin/` |
   | **Identificador (subdominio)** | `la-casa` | Obligatorio y único. Solo minúsculas, números y guiones: sin espacios ni tildes. No se permiten `www`, `api`, `admin`, `app`, `master`, `panel` ni `static`. Va dentro de la dirección de la carta y es el nombre de su base de datos: **no lo cambies después** |
   | **Ciudad**, **Teléfono**, **Dirección** | Los del local | Opcionales. La primera vez que se abre **Personalizar** pasan a «Contacto y WhatsApp»; desde ahí se cambian allá |
   | **Página del menú digital** | Vacía por ahora | La dirección del menú publicado (`https://la-casa-menu.pages.dev/`). Como todavía no está publicado, se pone en la Parte 5 |
   | **Razón social**, **NIT** | Si los tienes | Opcionales |
   | **Usuario del administrador** | Deja `admin` | El usuario queda `<slug>.admin`, p. ej. `la-casa.admin` |
   | **Nombre de la persona** | `Ana Gómez` | Opcional |
   | **Correo del administrador** | `ana@lacasa.com` | Obligatorio. Con él recupera su contraseña |

4. **Crear restaurante**. Cloudin crea la base de datos del restaurante
   (`cloudin_<slug>`), le aplica las migraciones y crea su usuario administrador. Se abre la
   página del restaurante con el aviso «Base de datos «cloudin_la-casa» creada y migrada.»
5. Arriba sale la tarjeta **«✅ La Casa quedó creado»** con **Usuario**, **Contraseña** y
   **Enlace** (`https://<servidor-cloudin>/panel/login/`), cada uno con su botón **Copiar**.
   **Copiar mensaje para enviar** copia los tres en un mensaje listo para mandarle por
   WhatsApp al restaurante. Esa tarjeta sale una sola vez; si la pierdes, la contraseña
   queda en la tabla **Usuarios** de esa misma página, columna Contraseña → **Ver**.
6. En la tarjeta **Acceso**, junto a **API key (para su sitio web)** → **Copiar**. (No
   hace falta copiarla a mano: la tarjeta **Menú digital** de esta misma página trae el
   código del menú ya armado con ella, Parte 3.1.) Empieza
   por `ck_`: guárdala para la Parte 3. No es secreta: queda dentro de la página del menú y
   cualquiera puede verla. Los pedidos los protegen el token de cada mesa (va en su QR), la
   dirección autorizada (Parte 5), los topes de Cloudin y que el precio lo pone siempre
   Cloudin. **Regenerar API key** crea otra y la anterior deja de servir: si algún día la
   regeneras, cambia `apiKey` en el menú y vuelve a publicarlo.

> **La dirección de la carta** de este restaurante queda así, y ya responde (con la carta
> vacía): `https://<servidor-cloudin>/api/public/<slug>/menu/`.

---

## Parte 2. Cargar la carta y los datos (panel del restaurante)

Lo hace el restaurante con su usuario. Si lo haces tú, tienes dos caminos: entrar con su
usuario, o desde el panel maestro → el restaurante → **Entrar en modo soporte** → tu
contraseña de Cloudin → **Entrar en modo soporte**.

### 2.1 Entrar por primera vez

1. Abre el **Enlace** de la Parte 1 (`https://<servidor-cloudin>/panel/login/`).
2. Escribe el usuario (`la-casa.admin`, o su correo) y la contraseña → **Entrar**.
3. La primera vez aparece «Hola, … Antes de empezar…»: marca las dos casillas (términos y
   condiciones, y política de privacidad) → **Acepto y continúo**.

La primera vez, el panel abre el asistente «Empecemos por tu marca» (logo y colores,
datos del negocio, primera categoría y primer producto). Se puede seguir o tocar
**Saltar por ahora**; se retoma desde el Inicio.

En la barra lateral verás: *Día a día* (Inicio, Mesas, Mensajes, Cocina), *Tu menú* (Mi
menú, Personalizar, Códigos QR) y *Administración* (Meseros, Configuración). Todos los
restaurantes tienen todo: no hay planes.

### 2.2 Las mesas

**Códigos QR** → en «¿Cuántas mesas tienes?» escribe el número (p. ej. `12`) → **Guardar**. Cloudin crea las mesas 1 a 12,
cada una con su token. Nunca borra una mesa ni le cambia el QR.

Todavía no se ven los QR: cada mesa dice «Su QR aparece cuando tu menú digital esté
publicado.» Aparecen en la Parte 6.

### 2.3 La carta

En **Mi menú**:

1. **+ Categoría** → Nombre (p. ej. `Hamburguesas`) → **Crear categoría**. Repite por cada
   categoría.
2. **+ Producto** → se abre «Nuevo producto». En **Lo básico**:
   - **Toma o elige una foto**: la foto del plato. Cloudin la achica y la guarda (en R2,
     si está configurado): no hay que subirla a Pages.
   - **Nombre**, **Precio**, **Categoría**, **Descripción**.
   - **Disponible** (encendido) y **Destacar en el menú** (si quieres que salga en
     «destacados»).
3. En **Opciones avanzadas**, si el plato las necesita:
   - **Tamaños o presentaciones** → **Agregar tamaño**: cada presentación con su precio
     completo (no la diferencia). El menú muestra «Desde» el más barato.
   - **Adiciones** → **Crear grupo** → «Nuevo grupo de adiciones»: **Nombre del grupo**
     (p. ej. `Salsa`), **Obligatorio** si el cliente tiene que elegir, **¿Cuántas puede
     elegir?** (Solo una, Hasta 2, Hasta 3, Hasta 5 o Las que quiera) y sus opciones con lo
     que suman al precio → **Crear grupo**. Un grupo ya creado se reutiliza con **Usar un
     grupo existente**.
   - **Etiquetas** (Vegetariano, Picante, Nuevo…).
4. **Guardar producto**.

Cómo se ve cada cosa en el menú:

| En el panel | En el menú digital |
|---|---|
| Producto con precio y **Disponible** | Se muestra, con botón **Agregar** cuando se abre desde el QR de una mesa |
| **Disponible** apagado | Se muestra apagado, con «Agotado» y sin botón (o no se muestra, con `hideSoldOut: true`) |
| Producto **sin precio** | Cloudin lo deja no disponible: se muestra como agotado, sin precio, y **no se puede pedir** |
| **Tamaños o presentaciones** | Precio «Desde $ …» y la lista de presentaciones; al pedir, el cliente elige una |
| **Adiciones** | Al tocar **Agregar** se abre una ventana para elegirlas (las obligatorias no se pueden saltar) |
| **Destacar en el menú** | Sale también en la zona de destacados, si tu diseño la tiene (Parte 3.4) |
| Una categoría sin productos | No se muestra |

Los cambios de la carta (precios, fotos, agotados) se ven en el menú **sin volver a
publicarlo**, en cuanto alguien lo abre o lo recarga: al instante desde el QR, y en máximo
un minuto sin QR (la carta guardada en el teléfono, `cacheTtl`).

### 2.4 Los datos del negocio

En **Personalizar** (se guarda solo: arriba dice «Todo guardado»):

| Sección | Campo | En el menú (Parte 3) |
|---|---|---|
| Logo y colores | Logo (cuadrado; se ve redondo) | `business.logo` |
| Logo y colores | Principal, Secundario, Fondo, Texto | Las variables CSS `--cloudin-primary`, `--cloudin-secondary`, `--cloudin-background` y `--cloudin-text` |
| Portada | Una foto horizontal | `business.cover` |
| Datos del negocio | Frase corta | `business.tagline` |
| Datos del negocio | Descripción | `business.description` |
| Contacto y WhatsApp | WhatsApp | `business.whatsapp` y `business.whatsapp_link` (`https://wa.me/57…`) |
| Contacto y WhatsApp | Teléfono | `business.phone` y `business.phone_link` (`tel:+57…`) |
| Contacto y WhatsApp | Correo, Dirección, Ciudad, Enlace de Google Maps | `business.email`, `business.address`, `business.city`, `business.maps_url` |
| Horario | Los tramos de cada día | `business.hours_today` («Hoy: 12:00 – 21:00») y `business.open_now` |
| Redes sociales | Instagram, Facebook, TikTok | `business.instagram`, `business.facebook`, `business.tiktok` |

El **nombre** del restaurante no está en Personalizar: es el de la Parte 1. «Mensaje de
bienvenida» no llega al menú digital, y «Servicios y medios de pago» llegan solo en los
datos (`window.Cloudin.data.business`), sin campo para el HTML.

### 2.5 Quién toma los pedidos

Son dos interruptores; se cambian al tocarlos (solo el administrador; el resto del
equipo ve cómo están):

| Interruptor | Dónde | Encendido | Apagado |
|---|---|---|---|
| **Pedidos desde el QR de la mesa** (viene encendido) | **Inicio** (en «Pedidos y mesas»), **Códigos QR** y **Meseros** | El cliente pide desde el menú y el pedido llega a Mensajes y Cocina | El menú muestra la carta, pero no deja pedir |
| **App de meseros** (viene apagada) | **Meseros** | Los meseros toman pedidos en su app y van a la misma cuenta de la mesa | Los meseros no pueden entrar |

Sirve, por ejemplo, para pausar los pedidos por QR cuando la cocina está llena o el local
cerró: el menú abierto en los teléfonos esconde el botón «Agregar» en segundos, y al
encenderlo vuelve solo. No hay que tocar ni volver a publicar el menú.

### 2.6 Comprobar la carta

Abre en el navegador `https://<servidor-cloudin>/api/public/<slug>/menu/`. Debe verse la
carta en formato JSON: empieza con `"schema": "cloudin.menu/v1"` y trae el nombre del
restaurante, tus categorías y tus productos. Si dice «Ese restaurante no existe o no está
activo.», el `<slug>` está mal escrito o el restaurante está desactivado.

---

## Parte 3. Armar el menú

Un menú conectado a Cloudin es una página HTML normal con tu diseño, más **cuatro cosas**:

1. **La configuración** (`window.CLOUDIN_CONFIG`) y **dos scripts**: el runtime
   `cloudin-menu.v1.js` (pinta la carta) y `carrito.js` (el carrito y el pedido).
2. **Las zonas** que el runtime llena: `data-cloudin="menu"`, y adentro
   `data-cloudin="categories"`.
3. **Las plantillas**: un `<template>` para una categoría y otro para un plato.
4. **Los campos**: atributos `data-cloudin-field`, `data-cloudin-src`, `data-cloudin-href`
   y `data-cloudin-if` donde va cada dato.

Cloudin no guarda tu HTML ni lo modifica: tu página se publica sola (Parte 4) y trae los
datos de Cloudin cada vez que alguien la abre.

### 3.1 Camino corto: la plantilla

1. Crea una carpeta para el menú, p. ej. `menu-la-casa/`.
2. Copia ahí `client/plantilla/index.html` y `client/example/carrito.js`:

   ```
   menu-la-casa/
   ├── index.html     ← copia de client/plantilla/index.html
   └── carrito.js     ← copia de client/example/carrito.js, sin cambios
   ```

3. Al final de `index.html` cambia **tres cosas, y nada más** (el comentario del
   principio también las nombra: ese no importa):

   | Busca | Cámbialo por | Dónde |
   |---|---|---|
   | `<servidor-cloudin>` | La dirección de Cloudin, sin `https://`: `cloudin-abcd.onrender.com` | En `api` y en el `src` de `cloudin-menu.v1.js` |
   | `<slug>` | El identificador: `la-casa` | En `restaurant` y en `api` |
   | `apiKey: ""` | `apiKey: "ck_…"` con la API key de la Parte 1 (déjala `""` si el restaurante no recibe pedidos por QR) | En `apiKey` |

   **Más fácil:** en el panel maestro → el restaurante → tarjeta **Menú digital** →
   **Copiar código** copia este bloque ya lleno con la dirección del servidor, el
   identificador y la API key. Pégalo en lugar del que trae la plantilla.

   Queda así:

   ```html
   <script>
     window.CLOUDIN_CONFIG = {
       restaurant: "la-casa",
       api: "https://cloudin-abcd.onrender.com/api/public/la-casa/menu/",
       hideSoldOut: false,
       cacheTtl: 60,
       apiKey: "ck_Xa3…"
     };
   </script>
   <script src="https://cloudin-abcd.onrender.com/static/cloudin-menu.v1.js" defer></script>
   <script src="carrito.js" defer></script>
   ```

4. Cambia el diseño como quieras: colores, fuentes, orden, textos fijos, imágenes propias
   (en una carpeta `assets/`). La regla es **conservar los atributos `data-cloudin…` y las
   `<template>`**.

La plantilla ya trae: encabezado con logo, nombre, frase, horario de hoy y botón de
WhatsApp; barra de categorías; cada plato con foto, descripción, presentaciones, precio y
«Agotado»; y pie con dirección y teléfono. Lo que el restaurante no llenó en su panel
desaparece solo (por eso cada dato opcional lleva `data-cloudin-if`).

### 3.2 Camino largo: conectar un menú que ya diseñaste

Si ya tienes un menú hecho (con los platos escritos a mano en el HTML), conviértelo así:

1. **Configuración y scripts.** Pega antes de `</body>` el bloque de 3.1 (paso 3) con tus
   datos, y copia `carrito.js` junto a tu `index.html`.
2. **La raíz.** Al elemento que envuelve toda la carta (p. ej. tu `<main>`) ponle
   `data-cloudin="menu"`.
3. **El contenedor de categorías.** Al elemento **dentro de la raíz** que contiene todas
   las categorías ponle `data-cloudin="categories"`. Tiene que ser **otro elemento**, dentro
   de la raíz: no pongas los dos atributos en el mismo.
4. **La plantilla de categoría.** Toma el HTML de **una** de tus categorías (el título y la
   caja de sus platos) y mételo en `<template data-cloudin-template="category">…</template>`
   dentro del contenedor de categorías. En esa copia:
   - al título, `data-cloudin-field="category.name"`;
   - a la caja donde van los platos, `data-cloudin="products"` y déjala **vacía**.
5. **La plantilla de plato.** Toma el HTML de **un** plato y mételo en
   `<template data-cloudin-template="product">…</template>`, también dentro del contenedor
   de categorías. Cambia cada texto fijo por su campo (tabla de 3.5): el nombre por
   `data-cloudin-field="product.name"`, el precio por `data-cloudin-field="product.price"`,
   la foto por `data-cloudin-src="product.image"`, etc. Si quieres que el botón **Agregar**
   quede en un lugar preciso, ponle `class="dish__body"` a la caja de textos del plato.
6. **Borra los platos escritos a mano** que quedaron en el contenedor de categorías, o
   déjalos como respaldo: el runtime borra todo lo que hay ahí (menos las `<template>`) y
   pinta la carta real en cuanto Cloudin responde.
7. **Encabezado y pie.** Cambia el nombre, el teléfono, la dirección, etc. por sus campos
   `business.…` (tabla de 3.5). Esos funcionan en cualquier parte de la página.
8. **El color de fondo.** En tu CSS, define `--fondo` con el color de fondo de tu página
   (`:root { --fondo: #1A1110; }`). La ventana del carrito usa ese fondo y el color de texto
   de tu página: si no lo defines, sale oscura (`#1A1110`) y en una página clara el texto
   queda ilegible.

El esqueleto mínimo que funciona (todo lo demás es diseño):

```html
<main data-cloudin="menu">
  <div data-cloudin="categories">
    <p>Cargando la carta…</p>

    <template data-cloudin-template="category">
      <section>
        <h2 data-cloudin-field="category.name"></h2>
        <div data-cloudin="products"></div>
      </section>
    </template>

    <template data-cloudin-template="product">
      <article>
        <div class="dish__body">
          <h3 data-cloudin-field="product.name"></h3>
          <strong data-cloudin-field="product.price"></strong>
        </div>
      </article>
    </template>
  </div>
</main>

<script>
  window.CLOUDIN_CONFIG = {
    restaurant: "la-casa",
    api: "https://cloudin-abcd.onrender.com/api/public/la-casa/menu/",
    apiKey: "ck_Xa3…"
  };
</script>
<script src="https://cloudin-abcd.onrender.com/static/cloudin-menu.v1.js" defer></script>
<script src="carrito.js" defer></script>
```

### 3.3 La configuración (`window.CLOUDIN_CONFIG`)

| Clave | ¿Obligatoria? | Valor |
|---|---|---|
| `api` | **Sí** | `https://<servidor-cloudin>/api/public/<slug>/menu/`, completa: con `https://` y con la `/` final. Sin ella el runtime y el carrito no hacen nada. De aquí sacan también la dirección del servidor para los pedidos |
| `restaurant` | Ponla siempre | El `<slug>`. Es el nombre con que se guarda la carta en el teléfono (`cloudin:<slug>`), la que se pinta al instante cuando alguien vuelve, antes de que Cloudin responda. Sin ella, dos menús publicados en la misma dirección mezclarían sus cartas guardadas |
| `apiKey` | Para pedir | La API key `ck_…`. Vacía: la carta queda solo para mirar |
| `hideSoldOut` | No | `false` (lo normal): lo agotado se ve apagado. `true`: lo agotado no se muestra |
| `cacheTtl` | No | Segundos que la carta guardada se da por buena cuando se abre **sin** QR (por defecto `60`). Con QR siempre se pide la carta al día |

En otros ejemplos verás `contract`, `locale` y `currency`: el runtime no las usa; puedes
dejarlas o quitarlas.

**El orden importa:** primero el `<script>` con `CLOUDIN_CONFIG`, después
`cloudin-menu.v1.js` y al final `carrito.js`, los dos con `defer`. El runtime se carga
desde Cloudin (no lo copies): así recibe los arreglos sin volver a publicar el menú.

### 3.4 Las zonas y las plantillas

**Zonas** (`data-cloudin="…"`): elementos que el runtime **vacía y vuelve a llenar**.
Borra todo lo que tengan adentro menos las `<template>`, así que no pongas en ellas nada
que quieras conservar.

| Zona | Dónde va | Plantilla que usa | ¿Obligatoria? |
|---|---|---|---|
| `data-cloudin="menu"` | En cualquier parte: la raíz de la carta | — | **Sí** |
| `data-cloudin="categories"` | Dentro de la raíz | `category` | **Sí** |
| `data-cloudin="products"` | Dentro de la plantilla `category` | `product` | **Sí** |
| `data-cloudin="category-nav"` | Dentro de la raíz | `category-link` | No: la barra de categorías |
| `data-cloudin="variants"` | Dentro de la plantilla `product` | `variant` | No: las presentaciones |
| `data-cloudin="tags"` | Dentro de la plantilla `product` | `tag` | No: las etiquetas |
| `data-cloudin="featured"` | En cualquier parte | `featured`, o si no hay, `product` | No: los platos con «Destacar en el menú» |

**Plantillas** (`<template data-cloudin-template="…">`): se buscan primero dentro de la
zona, después hacia afuera hasta la raíz, y por último en toda la página. Lo más simple es
ponerlas dentro de la zona que las usa, como en la plantilla.

- **Solo cuenta el primer elemento** de cada `<template>`. Envuelve todo en uno solo
  (`<article>…</article>`); si pones dos elementos seguidos, el segundo se ignora.
- El runtime pinta **una copia por cada ítem**, en el orden del panel.

Lo que el runtime les pone a las copias (para tu CSS o tu JavaScript):

| Dónde | Atributo | Ejemplo de uso |
|---|---|---|
| Cada copia (categoría, plato, presentación, etiqueta) | `data-cloudin-key="<clave>"` | `[data-cloudin-key="picante"] { color: red; }` en las etiquetas |
| Cada plato | `data-available="true"` o `"false"` | `.plato[data-available="false"] { opacity: .55; }` |
| Cada plato | `data-featured="true"` o `"false"` | Resaltar los destacados |
| Cada categoría | `id="cat-<clave>"` | El destino de los enlaces de la barra (`#cat-hamburguesas`) |
| `<html>` y cada raíz | `data-cloudin-state="static"`, `"cached"`, `"live"` o `"error"` | `[data-cloudin-state="error"] .cargando::after { content: "…"; }` |
| `<html>` | Las variables `--cloudin-primary`, `--cloudin-secondary`, `--cloudin-background`, `--cloudin-text` | `color: var(--cloudin-primary, #B3261E);` (el segundo valor es por si el restaurante no eligió color) |

Los estados: `static` = todavía no hay datos; `cached` = se pintó la carta guardada en el
teléfono; `live` = se pintó la carta que acaba de responder Cloudin; `error` = Cloudin no
respondió y no había carta guardada.

Destacados, si los quieres (usan la misma plantilla del plato; el `:has` esconde la sección
cuando no hay ninguno):

```html
<section class="destacados">
  <h2>Recomendados</h2>
  <div data-cloudin="featured"></div>
</section>
<style>.destacados:not(:has([data-cloudin-key])) { display: none; }</style>
```

Varios menús (p. ej. «Desayunos» y «Carta», creados en **Mi menú** → **Nuevo menú**): una
raíz por menú, cada una con `data-cloudin-menu="<clave del menú>"`. La clave está en la
carta (Parte 2.6), en `"menus": [{"key": "…"}]`. Sin ese atributo, la raíz pinta el primer
menú.

### 3.5 Los atributos y los campos

**Atributos** (el valor siempre es `contexto.campo`, ver la tabla siguiente):

| Atributo | Qué hace | Ejemplo |
|---|---|---|
| `data-cloudin-field="…"` | **Reemplaza todo el contenido** del elemento por el texto del campo | `<h3 data-cloudin-field="product.name"></h3>` |
| `data-cloudin-src="…"` | Pone el `src` (para `<img>`). Si el campo está vacío, quita el `src`. Si el `<img>` no tiene `alt`, le pone el nombre | `<img data-cloudin-src="product.image">` |
| `data-cloudin-href="…"` | Pone el `href` (para `<a>`). Si el campo está vacío, quita el `href` | `<a data-cloudin-href="business.whatsapp_link">` |
| `data-cloudin-if="…"` | **Borra el elemento** si el campo está vacío | `<p data-cloudin-if="product.description" …>` |
| `data-cloudin-if="!…"` | **Borra el elemento** si el campo **no** está vacío | `<span data-cloudin-if="!product.available">Agotado</span>` |

«Vacío» es: sin dato, texto vacío, `false` o una lista sin elementos.

**Campos por contexto.** `business.*` y `table.*` funcionan en cualquier parte de la
página; `category.*` dentro de las plantillas `category`, `category-link` y de los platos
de esa categoría; `product.*` dentro de la plantilla del plato; `variant.*` y `tag.*`
dentro de las suyas.

| Campo | Qué trae |
|---|---|
| `business.name` | Nombre del restaurante |
| `business.tagline` | Frase corta |
| `business.description` | Descripción |
| `business.logo` | Dirección de la imagen del logo (para `data-cloudin-src`) |
| `business.cover` | Dirección de la foto de portada (para `data-cloudin-src`) |
| `business.address`, `business.city` | Dirección y ciudad |
| `business.phone` | Teléfono, como lo guarda Cloudin (`+573001234567`) |
| `business.phone_link` | `tel:+573001234567` (para `data-cloudin-href`) |
| `business.whatsapp` | Número de WhatsApp |
| `business.whatsapp_link` | `https://wa.me/573001234567` (para `data-cloudin-href`) |
| `business.email` | Correo |
| `business.maps_url` | Enlace de Google Maps (para `data-cloudin-href`) |
| `business.instagram`, `business.facebook`, `business.tiktok` | Enlaces a las redes (para `data-cloudin-href`) |
| `business.hours_today` | «Hoy: 12:00 – 21:00», «Hoy: 12:00 – 15:00 y 18:00 – 22:00» o «Hoy: cerrado». Vacío si no hay horario |
| `business.open_now` | Si está abierto ahora, en hora de Colombia. Solo para `data-cloudin-if` (`"business.open_now"` / `"!business.open_now"`). Sin horario cargado cuenta como cerrado |
| `table.number` | El número de la mesa, cuando la página se abrió desde su QR. Vacío sin QR |
| `category.name` | Nombre de la categoría |
| `category.description` | Descripción de la categoría, si tiene |
| `category.image` | Foto de la categoría, si tiene |
| `category.anchor` | `#cat-<clave>` (para los enlaces de la barra, con `data-cloudin-href`) |
| `category.key` | La clave (`hamburguesas`) |
| `product.name` | Nombre del plato |
| `product.description` | Descripción, si tiene |
| `product.price` | El precio **ya escrito**: `$ 24.000`; con presentaciones, `Desde $ 24.000`; vacío si no tiene precio. No le agregues `$` |
| `product.image` | Dirección de la foto (para `data-cloudin-src`) |
| `product.available` | Si está disponible. Para `data-cloudin-if` |
| `product.featured` | Si está destacado. Para `data-cloudin-if` |
| `product.variants`, `product.tags` | Las listas: solo para `data-cloudin-if` (p. ej. esconder el título «Tamaños» si no hay) |
| `product.key` | La clave (`hamburguesa-clasica`) |
| `variant.name`, `variant.price` | Nombre y precio ya escrito de cada presentación (`Doble carne`, `$ 32.000`) |
| `tag.name`, `tag.key` | Nombre (`Vegetariano`) y clave (`vegetariano`) de cada etiqueta |

### 3.6 Reglas que es fácil romper

1. **Dos partes, siempre.** `business.phone` sí; `business.contact.phone` no funciona. Usa
   los nombres de la tabla 3.5.
2. **`data-cloudin-field` borra lo que el elemento tenga adentro.** No pongas otros
   elementos dentro. Para «Mesa 3», el texto fijo afuera y el campo en su propio elemento:
   `Mesa <span data-cloudin-field="table.number"></span>`.
3. **`data-cloudin-if` borra, no esconde.** El elemento no vuelve hasta que se recarga la
   página.
4. **No uses `data-cloudin-if` con `table.number`.** Desde la segunda visita, la carta
   guardada se pinta antes de que Cloudin diga el número de la mesa y el elemento se
   borraría. Muéstralo sin condición (la barra del carrito ya dice «Mesa 3»).
5. **Un solo elemento por `<template>`**, y las zonas `products`, `variants` y `tags`
   **dentro** de su plantilla.
6. **La raíz (`menu`) y el contenedor (`categories`) son elementos distintos**, uno dentro
   del otro.
7. **El botón «Agregar» lo pone `carrito.js`**: al final del elemento `.dish__body` del
   plato, o al final de la tarjeta si no hay `.dish__body`. Solo en platos disponibles y con
   precio, solo si la página se abrió desde un QR (`?mesa=<token>`) con `apiKey`, y solo si
   el restaurante tiene encendidos los pedidos por QR (Parte 2.5).
8. **El QR lleva el token, no el número.** `?mesa=td8vIrnwaZPF` permite pedir; `?mesa=3`
   muestra «Mesa 3» pero no deja pedir. Los QR de la Parte 6 ya traen el token.
9. **Define `--fondo`** con el color de fondo de tu página (Parte 3.2, paso 8).
10. **No impidas que Cloudin muestre tu página en un marco** (nada de
    `X-Frame-Options: DENY`): la **Vista previa en vivo** de Personalizar y del editor de
    productos abre tu menú dentro del panel.
11. **Un menú, un restaurante.** `restaurant`, el `<slug>` de `api` y la `apiKey` tienen que
    ser del mismo restaurante.

### 3.7 Mirarlo en tu computador (opcional)

En la carpeta del menú, con Python instalado (en Windows el comando es `python`; en Mac
y Linux, `python3`):

```
python -m http.server 8080
```

Abre `http://localhost:8080/`: debe verse la carta del restaurante con sus datos (la carta
se puede leer desde cualquier dirección). Los pedidos se prueban después de publicar
(Parte 6).

---

## Parte 4. Publicar el menú en Cloudflare Pages

### 4.1 Subir la carpeta a GitHub

1. En github.com: **New repository** → nombre `menu-la-casa` → puede ser **Private** →
   **Create repository**.
2. En el repositorio vacío: **uploading an existing file** (o **Add file** → **Upload
   files**) → arrastra **el contenido** de la carpeta (`index.html`, `carrito.js` y
   `assets/` si hay; no la carpeta misma, para que `index.html` quede en la raíz) →
   **Commit changes**.

### 4.2 Crear el proyecto en Pages

1. En dash.cloudflare.com: **Workers & Pages** → **Create application** → pestaña
   **Pages** → **Import an existing Git repository**.
2. Conecta GitHub si lo pide (dale acceso al repositorio `menu-la-casa`) → elige el
   repositorio → **Begin setup**.
3. Configura:

   | Opción | Valor |
   |---|---|
   | Project name | `la-casa-menu`: será la dirección `https://la-casa-menu.pages.dev` |
   | Production branch | `main` |
   | Framework preset | **None** |
   | Build command | *(vacío)* |
   | Build output directory | `/` |

4. **Save and Deploy**. En menos de un minuto queda publicado. **Copia la dirección que te
   muestra Cloudflare** (`https://<proyecto>.pages.dev`; si el nombre estaba tomado,
   Cloudflare le agrega letras): es la que va en la Parte 5, tal cual.
5. Ábrela: debe verse la carta del restaurante.

Desde ahí, **cada cambio que subas a `main` se publica solo**. Un cambio de diseño se sube
igual que en 4.1 (subir el archivo nuevo → **Commit changes**). Los cambios de la carta
(precios, fotos, agotados) no necesitan esto: salen del panel (Parte 2.3).

> Cloudflare sugiere ahora Workers para proyectos nuevos; para un menú estático Pages
> funciona igual, es gratis y es lo más simple. Detalles y dominio propio:
> `GUIA-MENU-DIGITAL.md` §4.3 y §4.6.

---

## Parte 5. Registrar la dirección del menú en Cloudin

Hasta aquí el menú ya **muestra** la carta. Cloudin no busca el menú por su cuenta: hay
que decirle cuál es su dirección. Sin eso no hay QR, el panel dice «Tu menú todavía no está
publicado» y el menú no puede mandar pedidos.

1. Abre `https://<servidor-cloudin>/master/` → **Restaurantes** → el restaurante.
2. En la tarjeta **Menú digital**:

   | Campo | Qué poner | Ejemplo |
   |---|---|---|
   | **Página del menú (QR)** | La dirección de la Parte 4, **exacta**: con `https://`, con la `/` final y sin `?mesa` | `https://la-casa-menu.pages.dev/` |
   | **Otras direcciones autorizadas** | Vacío. Solo si el mismo menú también se abre desde otra dirección (su dominio propio), una por línea | `https://menu.lacasa.com` |

3. **Guardar**. Arriba sale «Menú de La Casa registrado: los QR ya apuntan a …».
4. Abre el menú una vez en el navegador y recarga la ficha: la tarjeta pasa de **Sin
   conexión todavía** a **Conectado** («Un menú pidió la carta de La Casa hace un
   momento»). Si sigue sin conexión, al menú le falta el código de la Parte 3 o apunta a
   otro servidor.

(Lo mismo se puede hacer en `https://<servidor-cloudin>/admin/` → **Restaurantes (panel
maestro)** → **Restaurantes** → el restaurante → sección «Sitio web y menú»: «Página del
menú (QR)» y «Otros sitios autorizados», este último como lista JSON:
`["https://menu.lacasa.com"]`.)

Qué hace «Página del menú (QR)»:

- **Arma los QR**: el de cada mesa es esa dirección + `?mesa=<token>`
  (`https://la-casa-menu.pages.dev/?mesa=td8vIrnwaZPF`), y el QR general es la dirección sola.
- **Autoriza esa dirección para pedir.** El navegador solo deja mandar pedidos desde los
  sitios registrados (esquema + dominio + puerto, sin la ruta). Leer la carta funciona desde
  cualquier lado; pedir, no.
- **Activa la vista previa** del panel: Personalizar y el editor de productos muestran el
  menú real mientras se edita.

---

## Parte 6. Imprimir los QR y probar

### 6.1 Los QR

En el panel del restaurante → **Códigos QR** (pantalla «Mesas y QR»):

- **El QR de tu menú**: la carta sin mesa, para la entrada, la vitrina o las redes.
  **Copiar enlace**, **PNG**, **SVG** o **Imprimir**. Sirve para mirar, no para pedir.
- **Mesas**: cada mesa con su QR y los botones **PNG** y **SVG**.
- Arriba, **PDF con todas las mesas**; abajo, **Imprimir todas (PDF, 4 por hoja)**.

Imprime los QR cuando la dirección del menú sea la definitiva: si después cambias
«Página del menú (QR)», los QR nuevos cambian.

### 6.2 La prueba completa (5 minutos)

1. Abre el **PNG** de la **Mesa 1** en la pantalla del computador y escanéalo con la
   cámara del teléfono.
2. Se abre el menú con `?mesa=…` en la dirección. Bajo cada plato disponible y con precio
   aparece **Agregar**.
3. **Agregar** en un plato (si tiene tamaños o adiciones, se abre una ventana: elige y
   **Agregar al pedido**). Abajo aparece la barra **Ver pedido (1) · $ …**.
4. Toca la barra → escribe un nombre en «Tu nombre» → **Enviar pedido**. Debe decir
   **«¡Pedido enviado! La cocina ya lo tiene.»**
5. En el panel: **Mesas** → la Mesa 1 está ocupada; **Mensajes** → el pedido;
   **Cocina** → la comanda. Al cerrar la cuenta de la mesa, queda libre otra vez.
6. Abre la dirección del menú **sin** `?mesa`: la carta se ve igual, sin botones.

Si todo eso pasó, el restaurante está listo. Para el siguiente restaurante se repiten las
Partes 1 a 6: la plantilla es la misma y solo cambian el `<slug>` y la `apiKey`.

---

## Parte 7. Si algo no funciona

Para ver los errores del menú en el computador: abre la página → clic derecho →
**Inspeccionar** → pestaña **Console**. Ahí aparecen los errores de conexión.

| Lo que pasa | Por qué | Qué hacer |
|---|---|---|
| Se queda en «Cargando la carta…» cerca de un minuto y luego carga | Render gratis estaba dormido | Normal en el plan gratis (`DESPLIEGUE-GRATIS.md` §5). Para que no pase, un plan pago de Render |
| «No se pudo cargar la carta» (la plantilla lo agrega en estado `error`) | `api` mal escrita (el `<slug>` o el servidor), o Cloudin caído | Abre la dirección de `api` en el navegador (Parte 2.6): tiene que mostrar la carta |
| Se queda en «Cargando la carta…» (o la carta sale vacía) y no hay errores | El restaurante todavía no tiene productos | Parte 2.3 |
| Se ve tu diseño con las secciones vacías | Una `<template>` está mal: fuera de su zona, con dos elementos, o sin `data-cloudin="products"` dentro de la categoría | Compara con el esqueleto de 3.2 |
| Un dato no aparece (p. ej. el horario) | No está lleno en Personalizar, o el atributo está mal escrito | Parte 2.4; revisa el nombre en la tabla 3.5 |
| No aparece **Agregar** en ningún plato | Falta `?mesa=<token>` en la dirección, o `apiKey` está vacía o equivocada, o no se cargó `carrito.js` (en la consola: 404), o los pedidos por QR están apagados | Abre desde un QR de la Parte 6; revisa `apiKey` contra la del panel maestro; revisa que `carrito.js` esté junto a `index.html`; enciende los pedidos por QR (Parte 2.5) |
| **Agregar** falta en un solo plato | Está agotado o no tiene precio | Mi menú → el plato → Precio y Disponible |
| En la consola: «blocked by CORS policy» | La dirección desde la que abriste el menú no coincide **exactamente** con «Página del menú (QR)» (`http` o `https`, `www`, otra dirección de Pages) | Corrige la Parte 5. Abre el menú con `https://<proyecto>.pages.dev`, no con la dirección de un despliegue (la que tiene letras y números antes del nombre del proyecto) |
| Dice «Enviaste muchos pedidos seguidos…» | Más de 20 envíos (o 240 cambios al carrito) en 10 minutos desde la misma conexión; el wifi del local cuenta como una sola | Esperar unos minutos (`GUIA-MENU-DIGITAL.md` §8) |
| En Códigos QR: «Su QR aparece cuando tu menú digital esté publicado.», o en el panel «Tu menú todavía no está publicado» | «Página del menú (QR)» está vacía: Cloudin no detecta el menú solo | Parte 5 |
| La ficha dice **Sin conexión todavía** aunque el menú está publicado | El menú no tiene el código de la Parte 3, o su `api` apunta a otro servidor o a otro identificador | Parte 3.1: **Copiar código** en la tarjeta Menú digital y pégalo en el menú; publícalo otra vez |
| El enlace del panel sale como `https://<slug>.localhost/panel/login/` | El servidor todavía no tiene el arreglo que usa la dirección de Render | El enlace correcto es `https://<servidor-cloudin>/panel/login/`. Para que el panel maestro lo muestre bien: en Render → el servicio → **Environment** → agrega `CLOUDIN_PUBLIC_URL` = `https://<servidor-cloudin>` → guardar |
| La ventana del carrito sale oscura con letra oscura | Falta `--fondo` en tu CSS | Parte 3.2, paso 8 |
| Un cambio de diseño no se ve | No se subió a `main`, o el navegador tiene la página vieja | Revisa en Pages → el proyecto → **Deployments**; recarga la página |
| Un cambio de precio no se ve | La carta guardada en el teléfono (hasta `cacheTtl` segundos sin QR) | Espera un minuto y recarga |
| Las fotos no salen | No se subieron en Mi menú, o R2 no tiene la dirección pública | `DESPLIEGUE-GRATIS.md` §3.2 |

---

## Parte 8. Checklist por restaurante

```
[ ] 1. /master/ → Nuevo restaurante
[ ] 1. Copiados: usuario, contraseña, enlace del panel y API key (ck_…)
[ ] 2. Términos aceptados en su panel
[ ] 2. Mesas creadas (Códigos QR → ¿Cuántas mesas tienes?)
[ ] 2. Categorías y productos con precio y foto (Mi menú)
[ ] 2. Logo, colores, contacto, WhatsApp y horario (Personalizar)
[ ] 2. Pedidos por QR encendidos (Inicio); app de meseros si la van a usar (Meseros)
[ ] 2. https://<servidor-cloudin>/api/public/<slug>/menu/ muestra la carta
[ ] 3. index.html con el código de «Menú digital» → Copiar código; carrito.js al lado
[ ] 4. Publicado en Pages; https://<proyecto>.pages.dev muestra la carta
[ ] 5. Ficha → «Menú digital» → Página del menú (QR) = https://<proyecto>.pages.dev/ → Guardar
[ ] 5. La ficha dice «Conectado» después de abrir el menú
[ ] 6. Pedido de prueba desde el QR de la Mesa 1 → llegó a Mensajes y Cocina
[ ] 6. QR impresos (PDF con todas las mesas)
[ ] 6. Mensaje con el acceso enviado al restaurante (Copiar mensaje para enviar)
```
