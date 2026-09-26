# Cómo conectar un sitio web con el panel de Cloudin

Esta guía es para quien construye la página desde la que el **personal** del
restaurante envía pedidos (la tablet del mostrador): elige la mesa por su número.
Todo lo que necesita son dos llamadas HTTP.

> **¿Construyes el menú digital que abre el cliente con el QR de su mesa?** Sigue
> **`GUIA-MENU-DIGITAL.md`**: carta pública con los id de cada plato, carrito
> compartido de la mesa y Cloudflare Pages paso a paso. Las rutas `/site/…` de esta
> guía piden por número de mesa, sin token: no las uses en una página pública.

> **¿Conectar la carta (fotos, toppings, observación) y que el panel mande?**
> Sigue `CONECTAR-MENU-A-CLOUDIN.md`: formato `cloudin-menu.json`, importación
> desde el panel, `GET /api/v1/menu/?formato=cloudin` y pedidos con
> `product_id` + `opciones`.

## Antes de empezar

En el panel del restaurante, en **Configuración → Sitio web**, hay que tener:

1. **El link del sitio guardado.** Solo esa dirección puede hablar con el panel.
   Si el sitio vive en `https://pedidos.mirestaurante.com`, ese es el valor a
   guardar. Cualquier otra dirección recibe un bloqueo del navegador (CORS).
2. **La llave de conexión** (empieza por `ck_`). Es la contraseña del sitio.

> En desarrollo, si el sitio corre en `http://localhost:5173`, se guarda esa
> dirección exacta, con su puerto.

## Autenticación

Cada petición lleva la llave en una cabecera:

```
X-API-Key: ck_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

No hay login ni tokens que expiren. Si la llave falta o está mal, la respuesta
es `400` con un mensaje explicando que no se identificó el restaurante.

## 1. Leer las mesas y el menú

```js
const PANEL = "https://<dominio-del-panel>";
const LLAVE = "ck_...";

const r = await fetch(`${PANEL}/api/v1/site/info/`, {
  headers: { "X-API-Key": LLAVE }
});
const info = await r.json();
```

Respuesta:

```json
{
  "restaurante": "Nombre del restaurante",
  "mesas": [
    { "id": 1, "numero": 1, "nombre": "Mesa 1", "puestos": 4, "ocupada": false }
  ],
  "categorias": [
    {
      "id": 1,
      "name": "Platos fuertes",
      "position": 0,
      "products": [
        { "id": 12, "category": 1, "name": "Hamburguesa", "description": "",
          "price": "32000.00", "image_url": "", "is_available": true }
      ]
    }
  ]
}
```

Solo llegan las mesas activas y los productos disponibles: lo que el
restaurante apaga en su panel desaparece del sitio sin tocar código.

Conviene volver a pedir esto cada vez que se abre la pantalla de comandas, para
que los agotados y los precios estén al día.

## 2. Ver el salón (mesas libres y ocupadas)

Más liviano que `/site/info/`, pensado para refrescarse cada pocos segundos y
pintar el plano de mesas:

```js
const { mesas } = await (await fetch(`${PANEL}/api/v1/site/tables/`, {
  headers: { "X-API-Key": LLAVE }
})).json();
// [{ "numero": 3, "puestos": 4, "zona": "Salón", "ocupada": true, "desde": "2026-09-12T01:57:00Z" }]
```

Una mesa está `ocupada` cuando tiene una cuenta abierta (se abre sola con su primer
pedido), y vuelve a estar libre cuando el restaurante la cierra desde su panel.
`desde` es la hora en que se abrió la cuenta. Las mesas vienen ordenadas por número;
`zona` sirve para agruparlas.

En El Bembé, el carrito usa esto en vez del campo «Número de mesa»: una ventanita
con el plano (libre / ocupada / tu mesa) que se refresca cada 8 s
mientras el carrito está abierto. Las ocupadas también se pueden elegir, porque los
amigos de una misma mesa suman pedidos a la misma cuenta.

## 3. Enviar un pedido

```js
const r = await fetch(`${PANEL}/api/v1/site/orders/`, {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "X-API-Key": LLAVE
  },
  body: JSON.stringify({
    table_number: 3,
    customer_name: "María",
    note: "Sin cebolla",
    items: [
      { product_id: 12, quantity: 2, note: "término medio" },
      { product_id: 15, quantity: 1 }
    ]
  })
});
const resultado = await r.json();
```

| Campo | Obligatorio | Qué es |
|---|---|---|
| `table_number` | sí | El número de la mesa, tal como aparece en el panel |
| `items` | sí | Lista con al menos un producto |
| `items[].product_id` | ver abajo | El `id` que vino en `/site/info/` |
| `items[].quantity` | no (1) | Entre 1 y 99 |
| `items[].note` | no | Detalle de ese producto (se descarta si el producto no permite observación) |
| `items[].opciones` | no | Toppings elegidos: `[{"grupo": 0, "valor": 1}]` (ver `CONECTAR-MENU-A-CLOUDIN.md`) |
| `customer_name` | no | Nombre del cliente; se ve en el panel de mensajes |
| `note` | no | Nota general para la cocina |
| `guests` | no | Número de personas en la mesa |

### Si el sitio tiene su propio catálogo

Cuando la página ya maneja su menú con opciones y combinaciones —gramajes,
extras, kits— el precio final no corresponde a un producto suelto del panel. En
ese caso la línea se manda con **nombre y precio**, sin `product_id`:

```json
{
  "table_number": 3,
  "customer_name": "Ana",
  "items": [
    { "name": "Sandwich 2 Quesos · Brisket", "unit_price": 35000, "quantity": 1 }
  ]
}
```

Las dos formas se pueden mezclar en el mismo pedido. Cada línea necesita
`product_id`, **o bien** `name` y `unit_price`.

La diferencia práctica: con `product_id`, el precio lo pone el panel y el
restaurante lo cambia sin tocar el sitio. Con `name` y `unit_price`, el precio
lo pone el sitio — más libertad, pero el menú se mantiene en dos lugares.

Respuesta `201`:

```json
{
  "ok": true,
  "pedido_id": 7,
  "mesa": 3,
  "cliente": "María",
  "total": 70000.0,
  "cuenta_id": 4,
  "cuenta_total": 118000.0
}
```

`total` es lo de este pedido; `cuenta_total` es lo que lleva la mesa en total,
sumando los pedidos anteriores. La mesa se marca ocupada sola con el primer
pedido, y se libera cuando el restaurante cierra la cuenta desde su panel.

## 4. Seguir el pedido en pantalla

El cliente puede ver cómo avanza lo que pidió. Se consulta por número de mesa y
devuelve la cuenta abierta completa:

```js
const estado = await (await fetch(`${PANEL}/api/v1/site/tables/3/orders/`, {
  headers: { "X-API-Key": LLAVE }
})).json();
```

```json
{
  "mesa": 3, "ocupada": true, "cuenta_id": 5, "total": 70000.0,
  "pedidos": [
    { "id": 9, "estado": "preparing", "estado_texto": "En preparación",
      "creado": "2026-09-12T02:57:11Z", "total": 35000.0,
      "items": [{ "nombre": "Sandwich 2 Quesos · Brisket", "cantidad": 1, "nota": "" }] }
  ]
}
```

`estado` avanza `pending` → `preparing` → `served` a medida que el restaurante
toca los botones en su panel. Consultarlo cada 8-10 segundos es suficiente.

Como la cuenta de la mesa se va acumulando, el cliente puede seguir pidiendo:
cada envío nuevo se suma a la misma cuenta y aparece en esta lista, hasta que el
restaurante cierra la mesa.

## 5. Página de mesa con QR (cuenta compartida)

> Para un menú digital nuevo, la guía completa (con ejemplos reales, errores y
> `carrito.js`) es **`GUIA-MENU-DIGITAL.md`**. Aquí va el resumen.

Cada mesa tiene su propio código QR con un enlace único. Si el restaurante tiene
registrada la **Página del menú**, el QR es esa página + `?mesa=<token>`; si no, en
el plan completo, el sitio + la ruta de mesas + `?m=<token>`
(`https://tusitio.com/mesa.html?m=<token>`). El panel los muestra e imprime en
**Códigos QR**.

Quien escanea abre la carta ya identificado con esa mesa: no la elige ni la
puede cambiar. Y como varias personas escanean el mismo código, el carrito vive
en el servidor y lo comparten.

Todos estos endpoints cuelgan de `/api/v1/mesa/<token>/` y llevan la cabecera
`X-API-Key`:

| Método | Ruta | Para qué |
|---|---|---|
| GET | `/api/v1/mesa/<token>/` | Carga inicial: restaurante, carta del panel y estado |
| GET | `/api/v1/mesa/<token>/estado/` | Sondeo liviano: cuenta, borrador y avisos |
| PUT | `/api/v1/mesa/<token>/borrador/` | Guarda el carrito compartido |
| POST | `/api/v1/mesa/<token>/aviso/` | «Voy a enviar»: los demás lo ven |
| POST | `/api/v1/mesa/<token>/enviar/` | Convierte el carrito en pedido |

El estado que devuelven todos:

```json
{
  "mesa": 3, "recibe_pedidos": true, "ocupada": true,
  "cuenta": { "id": 5, "total": 118000.0, "pedidos": [ /* con su estado */ ] },
  "borrador": { "items": [...], "version": 7, "total": 70000.0 },
  "aviso": "Ana"
}
```

`recibe_pedidos` es `false` si el restaurante no recibe pedidos por el QR (plan
«Menú digital» o solo meseros): en ese caso no muestres el carrito.

El `borrador` se guarda entero en cada cambio, mandando la `version` que se
tenía. Si otra persona escribió primero, la respuesta es `409` con el estado al
día: se muestra lo nuevo en vez de pisarlo. Sondear `/estado/` cada 4 o 5 segundos
alcanza para que todos vean lo mismo.


## Cookies

Si el sitio solo guarda en el teléfono el carrito y la carta (como los
de Cultura Brisket y El Bembé), **no necesita aviso de cookies**: es almacenamiento
necesario y no hay rastreadores. Si algún día se agrega analítica o publicidad
(Google Analytics, píxel de Meta), ahí sí hay que pedir consentimiento antes de
cargarlos.

## Errores

| Código | Qué pasó | Qué hacer |
|---|---|---|
| `400` | Falta la llave o es inválida | Revisar la cabecera `X-API-Key` |
| `400` | `{"items": ["Productos no disponibles o inexistentes: [9]"]}` | Recargar el menú: ese producto se agotó o se borró |
| `400` | Falta `table_number` | Enviar el número de mesa |
| `404` | Esa mesa no existe o está inactiva | Recargar las mesas |
| `400` | Falta elegir un topping obligatorio | Mostrar el mensaje y dejar elegir |
| `403` | `codigo: "solo_meseros"` · (pedidos por QR) el restaurante solo trabaja con meseros | Pedir que llamen al mesero |
| `403` | `codigo: "sin_pedidos"` · (pedidos por QR) el plan del restaurante no recibe pedidos | Pedir que llamen al mesero |
| `429` | `codigo: "demasiados"` · muchos pedidos seguidos desde la misma IP | Esperar unos minutos; no borrar el pedido |

Los pedidos entran a cualquier hora: no hay turno de caja que abrir.

El cuerpo del error siempre es JSON, así que conviene mostrarle al mesero el
mensaje tal cual en vez de un "error desconocido".

## Recomendaciones para el sitio

- **Botones grandes.** Se usa en una tablet, de pie y con prisa.
- **No bloquear por la red.** Si el envío falla, dejar el pedido en pantalla
  para reintentar en vez de perderlo.
- **Recargar el menú al abrir**, para no ofrecer lo que ya se agotó.
- **No publicar la llave en un repositorio público.** Si se filtra, se regenera
  desde el panel maestro y se cambia en el sitio.

## Cómo saber si quedó conectado

En **Configuración → Sitio web**, el panel muestra el estado en vivo: en cuanto
el sitio hace su primera llamada, el indicador pasa a verde y empieza a contar
los pedidos recibidos. Los pedidos aparecen en **Mensajes** con su número de
mesa y el nombre del cliente.
