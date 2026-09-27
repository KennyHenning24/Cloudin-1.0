# Conectar el menú de un restaurante con Cloudin

> **Para quién es:** para Claude (o cualquier desarrollador) cuando le pidan
> «conecta el sitio/menú de este restaurante con mi panel Cloudin».
> Léelo completo antes de tocar código. Todo lo que está aquí existe y está
> probado en el código de Cloudin (rutas al final).
>
> **¿Es un menú digital nuevo, hecho por ti para el cliente?** Usa
> **`GUIA-MENU-DIGITAL.md`**: la carta pública `cloudin.menu/v1` (con un id por plato y
> por opción), el carrito compartido de la mesa y Cloudflare Pages paso a paso. Esta
> guía es para sitios que **ya tienen su carta** y la importan al panel.

---

## 0. Resumen en 30 segundos

1. El sitio del restaurante **publica su carta** en un archivo `cloudin-menu.json`
   (o incrustada en la página) con el **formato Cloudin** (sección 3).
2. En el panel: **Configuración → Menú → Importar desde mi sitio** → *Revisar* →
   *Importar*. Se crean categorías, productos, fotos, descripciones y toppings.
3. Desde ahí **el panel manda**: el restaurante agrega productos, fotos,
   descripciones, toppings y la opción de observación en el panel.
4. El sitio **lee la carta del panel** (`GET /api/v1/menu/?formato=cloudin`) y se
   pinta con eso, así cualquier cambio del panel aparece solo en el sitio y en la
   app de meseros.
5. Los pedidos se envían con `product_id` + `opciones` (+ `note` si el producto
   la permite). **El precio lo calcula el servidor**, nunca el sitio.

### Reglas de oro (no negociables)

| Regla | Por qué |
|---|---|
| El panel es la fuente de verdad de la carta | Lo decidió el dueño de Cloudin. El sitio solo lee. |
| Nunca mandes precios para productos del panel | El servidor ignora el precio del sitio y lo recalcula. |
| La importación nunca borra ni pisa | Solo crea lo nuevo y llena campos vacíos. |
| Lo eliminado en el panel no revive | Aunque siga en el sitio, reimportar no lo vuelve a crear. |
| La llave `ck_…` no va a un repositorio público | Si se filtra, se regenera en el panel maestro. |
| Los pedidos entran a cualquier hora | No hay turno de caja. La mesa se ocupa con el primer pedido y se libera al cerrar la cuenta. |
| Mesas solo por número | Nada de «Terraza 1»: lo pidió el usuario. |
| Pregunta antes de modificar el sitio de un cliente | El usuario quiere ir paso a paso. |

---

## 1. Lo que necesitas antes de empezar (pídeselo al usuario)

| Dato | Dónde se ve | Ejemplo |
|---|---|---|
| Dirección del panel | La del servidor Django | `http://localhost:8000` en local |
| Slug del restaurante | Panel maestro `/master/` | `culturabrisket` |
| Llave de conexión | Panel → Configuración → Sitio web | `ck_UOBE…` |
| Dirección del sitio | Donde vive la web del restaurante | `https://culturabrisket.pages.dev` |
| Página de mesas (QR) | Panel → Configuración → Sitio web | `/mesa.html` |

En **Configuración → Sitio web** del panel hay que guardar la dirección exacta del
sitio (con puerto si es local). Solo ese origen puede llamar a la API desde el
navegador (CORS dinámico por restaurante, `apps/tenants/cors.py`).

---

## 2. El flujo completo

```
 ┌─────────────── SITIO DEL RESTAURANTE ───────────────┐        ┌──────────── PANEL CLOUDIN ────────────┐
 │                                                     │        │                                       │
 │  cloudin-menu.json  ───── (1) importar una vez ─────┼──────▶ │  Carta: categorías, productos, fotos,  │
 │                                                     │        │  toppings, observación                │
 │                                                     │        │        ▲  (2) el restaurante edita     │
 │  Página del menú  ◀──── (3) GET /api/v1/menu/?formato=cloudin ─────────┤                               │
 │                                                     │        │                                       │
 │  Carrito / QR mesa ──── (4) POST pedido con product_id + opciones ────▶│  Mensajes · Cocina · Meseros   │
 │                                                     │        │  Mesas ocupadas · cuenta · precuenta  │
 └─────────────────────────────────────────────────────┘        └───────────────────────────────────────┘
```

- **(1)** se repite cuando el sitio agregue platos nuevos (botón en el panel o
  `python manage.py importar_menu --tenant <slug>`, o `--todos` en un cron).
- **(3)** conviene cachearlo unos minutos en el sitio y tener un respaldo local
  por si el panel no responde (sección 6).

---

## 3. Formato Cloudin de la carta (versión 1)

### 3.1 Ejemplo completo

```json
{
  "cloudin_menu": 1,
  "restaurante": "Cultura Brisket",
  "moneda": "COP",
  "base_imagenes": "https://culturabrisket.pages.dev/",
  "categorias": [
    {
      "id": "sandwiches",
      "nombre": "Sándwiches",
      "orden": 1,
      "productos": [
        {
          "id": "dos-quesos",
          "nombre": "Sandwich 2 Quesos",
          "precio": 35000,
          "descripcion": "Queso cheddar, mozzarella, pepinillos agridulces, pan brioche y 150 g de brisket o pastrami.",
          "imagen": "assets/menu/dos-quesos.jpg",
          "disponible": true,
          "permite_observacion": true,
          "opciones": [
            {
              "nombre": "Elige la carne",
              "tipo": "uno",
              "obligatorio": true,
              "valores": [
                { "nombre": "Brisket", "precio": 0 },
                { "nombre": "Pastrami", "precio": 0 }
              ]
            },
            {
              "nombre": "Hazlo combo",
              "tipo": "varios",
              "valores": [
                { "nombre": "Papas fritas y Coca-Cola", "precio": 10000 }
              ]
            }
          ]
        },
        {
          "id": "limonada",
          "nombre": "Limonada natural",
          "precio": 6000,
          "permite_observacion": false
        }
      ]
    }
  ]
}
```

### 3.2 Campos

**Raíz**

| Campo | Tipo | Obligatorio | Notas |
|---|---|---|---|
| `cloudin_menu` | número | recomendado | Versión del formato. Hoy `1`. |
| `restaurante` | texto | no | Solo informativo. |
| `moneda` | texto | no | Siempre `COP`. |
| `base_imagenes` | URL | no | Base para completar imágenes relativas. Si falta, se usa la dirección desde donde se leyó el archivo. |
| `categorias` | lista | **sí** | Máximo 60. |

**Categoría**

| Campo | Tipo | Obligatorio | Notas |
|---|---|---|---|
| `id` | texto | recomendado | Estable para siempre. Sirve para reimportar sin duplicar. |
| `nombre` | texto | **sí** | Máx. 80 caracteres. |
| `orden` | entero | no | Posición. Si falta, el orden del archivo. |
| `secciones` | lista de textos | no | Para sitios con varias cartas: en cuáles aparece (`["dia", "noche"]`, `["bebidas"]`). Una categoría nueva creada en el panel aparece en la carta que diga aquí. |
| `productos` | lista | **sí** | Máximo 300 por categoría. |

**Producto**

| Campo | Tipo | Obligatorio | Por defecto | Notas |
|---|---|---|---|---|
| `id` | texto | recomendado | — | **Estable**. Es la `clave_externa` en Cloudin. Sin él se reconoce por nombre dentro de la categoría. |
| `nombre` | texto | **sí** | — | Máx. 120. |
| `precio` | entero (pesos) | **sí** | — | Con impuesto incluido, como en la carta. Sin puntos: `35000`. |
| `descripcion` | texto | no | `""` | Máx. 2000. |
| `imagen` | URL o ruta | no | `""` | Absoluta (`https://…`) o relativa (`assets/menu/x.jpg`). JPG/PNG/WebP. |
| `disponible` | booleano | no | `true` | `false` = se importa apagado. |
| `permite_observacion` | booleano | no | `true` | Si es `false`, Cloudin descarta las notas de ese producto. |
| `opciones` | lista de grupos | no | `[]` | Toppings/adiciones/variantes (3.3). |

### 3.3 Toppings y opciones

Cada grupo es **una pregunta** al cliente:

| Campo | Tipo | Notas |
|---|---|---|
| `nombre` | texto | «Elige la carne», «Adiciones», «Salsas». Máx. 60. |
| `tipo` | `"uno"` \| `"varios"` | `uno` = radio (una sola). `varios` = checkbox (cero o más). |
| `obligatorio` | booleano | Solo aplica a `uno`. Sin elegir, el pedido se rechaza con 400. |
| `maximo` | entero | Solo `varios`. Tope de opciones marcadas. |
| `valores` | lista | `{ "nombre": "Tocineta", "precio": 4000 }`. Máx. 30 por grupo. |

**`precio` de una opción es lo que SUMA al precio del producto** (0 si no cambia).

⚠️ **Variantes con precio propio** (p. ej. «250 g $43.000 / 500 g $84.000 / 1 kilo
$168.000»): pon como `precio` del producto **el de la variante más barata** y en
cada valor la **diferencia**: `250 g → 0`, `500 g → 41000`, `1 kilo → 125000`, con
`"tipo": "uno", "obligatorio": true`. Ojo si la variante base no es la más barata
(«Porción $8.000 / Media porción $5.000»): el producto va a `5000`, «Media» a `0` y
«Porción» a `3000`, porque una opción no puede restar.

### 3.4 Dónde publicarlo (elige una)

**A. Archivo aparte (recomendado):** `https://<sitio>/cloudin-menu.json`. En el
panel se usa esa dirección tal cual. Sitios estáticos (Cloudflare Pages, Netlify):
basta con poner el archivo en la raíz del deploy.

**B. Incrustado en la página del menú:**

```html
<script type="application/json" id="cloudin-menu">
  { "cloudin_menu": 1, "categorias": [ … ] }
</script>
```

En el panel se pone la dirección de esa página. Cloudin busca exactamente
`id="cloudin-menu"`.

**C. Archivo subido a mano:** en *Importar desde mi sitio* se puede subir el
`.json` (útil si el sitio aún no está publicado).

### 3.5 Generarlo desde datos que ya tiene el sitio

Si el sitio ya guarda su carta en JavaScript (como `assets/menu-data.js` de
Cultura Brisket, con `CB_CATEGORIAS` y `CB_MENU`), genera el archivo con un script
en vez de escribirlo a mano. Ejemplo para Node (ajusta nombres a cada sitio):

```js
// generar-cloudin-menu.js  →  node generar-cloudin-menu.js > cloudin-menu.json
const fs = require("fs");
const vm = require("vm");
const ctx = { window: {} };
vm.runInNewContext(fs.readFileSync("assets/menu-data.js", "utf8"), ctx);
const { CB_CATEGORIAS, CB_MENU } = ctx.window;

// El producto queda con el precio de la variante más barata; cada variante, con la diferencia.
const base = (p) => {
  const g = (p.opciones || []).find((o) => o.tipo === "uno" && o.valores.some((v) => v.precio));
  return g ? Math.min(...g.valores.map((v) => v.precio)) : p.precio;
};
const grupo = (op, precioBase) => {
  const conPrecio = op.tipo === "uno" && op.valores.some((v) => v.precio);
  return {
    nombre: op.nombre,
    // En este sitio «uno» = elige una (obligatoria); «extra» = adición opcional.
    tipo: op.tipo === "uno" ? "uno" : "varios",
    obligatorio: op.tipo === "uno",
    valores: op.valores.map((v) => ({
      nombre: v.nombre,
      precio: conPrecio ? v.precio - precioBase : (v.precio || 0),
    })),
  };
};

const carta = {
  cloudin_menu: 1,
  restaurante: "Cultura Brisket",
  moneda: "COP",
  base_imagenes: "https://culturabrisket.pages.dev/",
  categorias: CB_CATEGORIAS.map((c, i) => ({
    id: c.id, nombre: c.nombre, orden: i,
    productos: CB_MENU.filter((p) => p.cat === c.id).map((p) => ({
      id: p.id, nombre: p.nombre, precio: base(p),
      descripcion: [p.etiqueta, p.desc].filter(Boolean).join(" · "),
      imagen: p.img, disponible: p.agotado !== true, permite_observacion: true,
      opciones: (p.opciones || []).map((op) => grupo(op, base(p))),
    })),
  })),
};
process.stdout.write(JSON.stringify(carta, null, 2));
```

Implementación real y probada: `Portafolio/Cultura Brisket/revision/generar-cloudin-menu.js`.

---

## 4. Conectar en el panel (lo que hace el restaurante)

1. **Configuración → Sitio web:** guardar la dirección del sitio. Copiar la llave.
2. **Configuración → Menú → Importar desde mi sitio:** pegar
   `https://<sitio>/cloudin-menu.json` → **Revisar sin cambiar nada** → leer el
   resumen (nuevos, completados, errores) → **Importar ahora**.
3. Revisar la carta: cada producto tiene **Editar** (nombre, precio, categoría,
   foto, descripción, toppings, observación); cada cambio queda en el historial y
   las comandas ya enviadas guardan su propio precio.
   **Eliminar** saca el producto de la carta en todas partes (sitio, meseros, QR,
   panel); por debajo se conserva para no romper los pedidos viejos, y se
   puede **Restaurar** desde «Eliminados de la carta» en cada categoría.
   **Agotado** solo lo oculta por hoy.
4. Opcional: cron diario `python manage.py importar_menu --todos` para traer
   platos nuevos del sitio.

Qué hace la importación con cada producto:

| Caso | Resultado |
|---|---|
| Producto nuevo (id o nombre no existe) | Se crea con todo |
| Ya existe | **No se toca** lo que tenga; solo se llenan descripción, foto, toppings o `id` si están vacíos |
| El sitio lo quitó | Sigue en el panel (el restaurante lo elimina o lo marca «Agotado») |
| El restaurante lo **eliminó** en el panel | No se vuelve a crear ni se toca (cuenta en «eliminados») |
| Precio inválido, etc. | Se reporta en el resumen y se sigue con los demás |

---

## 5. Autenticación y CORS

Toda llamada del sitio lleva:

```
X-API-Key: ck_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

La API responde a navegadores solo desde la dirección guardada en *Sitio web*.
Si ves un error de CORS en la consola, la dirección guardada no coincide
exactamente (protocolo, dominio y puerto).

---

## 6. El sitio lee la carta del panel

```js
const PANEL = "https://<dominio-del-panel>";   // en local: http://localhost:8000
const LLAVE = "ck_...";

async function cargarCarta() {
  try {
    const r = await fetch(`${PANEL}/api/v1/menu/?formato=cloudin`, { headers: { "X-API-Key": LLAVE } });
    if (!r.ok) throw new Error(r.status);
    const carta = await r.json();
    localStorage.setItem("carta-cloudin", JSON.stringify(carta));   // respaldo
    return carta;
  } catch (e) {
    // Panel caído o sin internet: la última carta buena, o el archivo local.
    const guardada = localStorage.getItem("carta-cloudin");
    if (guardada) return JSON.parse(guardada);
    return (await fetch("/cloudin-menu.json")).json();
  }
}
```

La respuesta tiene **el mismo formato de la sección 3**, con dos detalles:

- Cada producto y categoría trae `cloudin_id`: **ese es el `product_id` para los pedidos.**
- `imagen` ya viene absoluta (las fotos subidas al panel apuntan a `/media/...` del panel).
- Solo llegan categorías activas y productos disponibles.

---

## 7. Enviar pedidos con toppings

### 7.1 Cómo se arma una línea

```json
{
  "product_id": 12,
  "quantity": 2,
  "opciones": [ { "grupo": 0, "valor": 1 }, { "grupo": 1, "valor": 0 } ],
  "note": "sin pepinillos"
}
```

- `grupo` y `valor` son **posiciones** (empezando en 0) dentro de `opciones` del
  producto tal como llegó en la carta del panel.
- `note` solo si `permite_observacion` es `true` (si no, se descarta).
- **No mandes `unit_price` ni `name`** en líneas del menú: el servidor calcula
  `precio del producto + suma de opciones` y arma el nombre
  («Sandwich 2 Quesos · Pastrami, Papas fritas y Coca-Cola (+$10.000)»), que es
  lo que ven cocina, meseros y la precuenta.

```js
// Convierte la selección de la pantalla a lo que espera Cloudin.
function lineaCloudin(producto, seleccion, cantidad, nota) {
  // seleccion: { [indiceGrupo]: [indiceValor, ...] }
  const opciones = [];
  producto.opciones.forEach((g, gi) =>
    (seleccion[gi] || []).forEach((vi) => opciones.push({ grupo: gi, valor: vi })));
  return {
    product_id: producto.cloudin_id,
    quantity: cantidad,
    opciones,
    ...(producto.permite_observacion && nota ? { note: nota } : {}),
  };
}
// Precio para MOSTRAR (el que vale es el del servidor):
const precioMostrado = (p, sel) =>
  p.precio + p.opciones.reduce((s, g, gi) => s + (sel[gi] || []).reduce((t, vi) => t + (g.valores[vi].precio || 0), 0), 0);
```

### 7.2 Endpoints de pedido

| Situación | Endpoint | Cuerpo |
|---|---|---|
| Tablet/sitio elige la mesa por número | `POST /api/v1/site/orders/` | `{ table_number, customer_name?, note?, guests?, items: [línea…] }` |
| Cliente con QR de la mesa (un teléfono) | `POST /api/v1/tables/<token>/orders/` | `{ customer_name?, note?, items: [línea…] }` |
| QR con carrito compartido | `PUT /api/v1/mesa/<token>/borrador/` y luego `POST /api/v1/mesa/<token>/enviar/` | `items` del borrador aceptan `product_id` + `opciones` (+ `quantity`, `note`, `by`, `key`) |

La forma antigua `{ "name": "...", "unit_price": 35000 }` sigue funcionando para
sitios que no usan la carta del panel, pero **con la carta conectada usa siempre
`product_id`**.

Seguimiento del pedido: `GET /api/v1/site/tables/<numero>/orders/` (cada 8–10 s)
o `GET /api/v1/mesa/<token>/estado/` (cada 4 s). Detalle en
`INTEGRACION-SITIO-WEB.md`.

---

## 8. Errores que el sitio debe manejar

| Código | `codigo` / cuerpo | Qué pasó | Qué mostrar |
|---|---|---|---|
| `403` | `sin_pedidos` | (Pedidos por QR) el restaurante apagó los pedidos por QR en su panel | «Pídele tu pedido al mesero.» |
| `429` | `demasiados` | Muchos pedidos seguidos desde la misma IP | El mensaje tal cual (no borres el carrito) |
| `400` | `{"items": ["Falta elegir «Elige la carne» para …"]}` | Topping obligatorio sin elegir, máximo superado u opción que ya no existe | El mensaje tal cual y recargar la carta |
| `400` | `Productos no disponibles o inexistentes: [9]` | Se agotó o se borró | Recargar la carta |
| `409` | `agotado` (carrito compartido) | Un producto del borrador se apagó | Quitarlo del carrito |
| `404` | — | Mesa inexistente o token de QR viejo | «Este QR ya no es válido, pide ayuda al mesero.» |
| `400` | falta llave | `X-API-Key` ausente o mala | Revisar configuración |

---

## 9. Checklist para dar por terminada la conexión

- [ ] `https://<sitio>/cloudin-menu.json` abre en el navegador y es JSON válido (o la página tiene `id="cloudin-menu"`).
- [ ] En el panel, *Revisar* muestra el número correcto de categorías y productos, sin errores.
- [ ] Tras *Importar*, las fotos se ven en **Configuración → Menú** y en la app de meseros.
- [ ] Un producto con toppings obligatorios **no** se puede enviar sin elegir (400 con mensaje).
- [ ] Pedido de prueba con toppings → en **Mensajes** y **Cocina** aparece el nombre con las opciones y el precio correcto.
- [ ] Cambiar una descripción en el panel → el sitio la muestra al recargar (`?formato=cloudin`).
- [ ] La mesa del pedido de prueba aparece ocupada en **Mesas**.
- [ ] Cierra la cuenta de prueba en el panel (la mesa queda libre).

Prueba rápida desde la terminal (PowerShell):

```powershell
$h = @{ "X-API-Key" = "ck_..." }
Invoke-RestMethod "http://localhost:8000/api/v1/menu/?formato=cloudin" -Headers $h | ConvertTo-Json -Depth 8
python manage.py importar_menu --tenant culturabrisket --revisar --url https://culturabrisket.pages.dev/cloudin-menu.json
```

---

## 10. Qué NO hacer

- No calcules ni envíes precios para productos del panel.
- No borres productos del panel desde el sitio ni «sincronices» a la fuerza: la importación es aditiva a propósito. Para sacar un plato, se elimina en el panel.
- No cambies los `id` de productos en el sitio: se duplicarían al reimportar.
- No metas fotos en base64 dentro del JSON (límite 2 MB); usa enlaces.
- No pongas la llave en un repositorio público.
- No modifiques el sitio de un cliente sin preguntarle al usuario primero.

---

## 11. Dónde está el código en Cloudin (para mantenerlo)

| Qué | Archivo |
|---|---|
| Formato, importar, exportar, lectura segura de URL | `apps/catalog/formato.py` |
| Validación y precio de toppings | `apps/catalog/opciones.py` |
| Campos del producto (`opciones`, `permite_observacion`, `imagen`, `clave_externa`) | `apps/catalog/models.py` |
| Ficha del producto y pantalla de importación | `apps/panel/menu.py`, `templates/panel/producto_form.html`, `templates/panel/menu_importar.html` |
| Comando | `apps/catalog/management/commands/importar_menu.py` |
| Carta pública `?formato=cloudin` y pedidos | `apps/api/views.py` (`menu`, `_crear_pedido`) |
| Carrito compartido del QR | `apps/api/mesa_views.py` |
| App de meseros (fotos y hoja de toppings) | `apps/waiters/views.py`, `templates/mesero/app.html` |
| Guía general de la API (mesas, QR, seguimiento) | `INTEGRACION-SITIO-WEB.md` |
| Menú digital nuevo (carta pública v1, carrito de la mesa, Cloudflare Pages) | `GUIA-MENU-DIGITAL.md` |
