# Cloudin

Backend único multi-tenant para restaurantes. Sirve para dos cosas:

1. **Manejar el menú digital**: carta, precios, fotos, personalización y los QR de las
   mesas. El menú digital de cada restaurante es un sitio aparte (Cloudflare Pages) que
   lee la carta de Cloudin.
2. **Recibir los pedidos de ese menú**: el cliente pide desde el QR de su mesa, la mesa
   queda ocupada sola, el pedido llega a Mensajes y Cocina, y los meseros (Cloudin
   Meseros) trabajan sobre las mismas mesas.

Cómo construir y conectar un menú digital: **[GUIA-MENU-DIGITAL.md](GUIA-MENU-DIGITAL.md)**.
La facturación electrónica (Factus), el turno de caja, el inventario, las reservas,
los empleados, las propinas, Cloudin Control y la analítica de ventas **se quitaron**
(ver «Módulos retirados»).

## Cómo está montado

Una sola aplicación Django, **N bases de datos**: una de control y una por restaurante.

| Base | Qué guarda |
|---|---|
| `control.sqlite3` (`default`) | Restaurantes, usuarios, sesiones, panel maestro |
| `tenant_dbs/cloudin_<slug>.sqlite3` | Menú, mesas, cuentas y pedidos de **ese** restaurante |

La pieza que lo hace posible:

- `apps/tenants/middleware.py` — decide de qué restaurante es cada petición
  (cabecera `X-API-Key` → subdominio → usuario logueado → `?tenant=` en local).
- `apps/tenants/db.py` — registra la conexión de ese restaurante en caliente.
- `apps/tenants/routers.py` — manda `catalog`, `dining`, `orders`, `waiters` y
  `business` a la base del restaurante, y `auth`/`sessions`/`admin`/`tenants` a la de
  control.

Dar de alta un cliente no despliega nada nuevo: se crea su base, se migra y se
generan sus credenciales.

## Apps

- `master` — panel maestro: alta de restaurantes y entrega de credenciales.
- `tenants` — restaurantes, usuarios de cada restaurante, aprovisionamiento, CORS.
- `catalog` — la carta: menús, categorías, productos, presentaciones y adiciones.
- `business` — datos del negocio para el menú: marca, contacto, horario.
- `public_menu` — la carta pública `cloudin.menu/v1` y el runtime `cloudin-menu.v1.js`.
- `importer` — importa la semilla de un menú digital (`import_menu`).
- `dining` — mesas, su token y sus códigos QR.
- `orders` — cuenta de mesa (`TableSession`) → comandas (`Order`) → ítems, y las
  novedades (anulaciones, cortesías, devoluciones, descuentos).
- `api` — endpoints REST: menú digital (QR), sitio del restaurante y panel.
- `waiters` — Cloudin Meseros: cuentas de mesero y la app de la tablet (`/mesero/<slug>/`).
- `panel` — pantallas del restaurante (menú, mesas, mensajes, cocina, tirillas).
- `billing`, `staffing`, `shifts`, `inventory`, `reservas`, `control` — **retiradas**:
  solo quedan sus migraciones (ver «Módulos retirados»).

## Arrancar en local

```bash
C:\Users\guerr\.venvs\cloudin312\Scripts\python.exe manage.py runserver
```

Python 3.12 + Django 5.2 LTS. El entorno virtual vive fuera de OneDrive
(`C:\Users\guerr\.venvs\cloudin312`) para que OneDrive no sincronice miles de
archivos. Para recrearlo (incluye pytest y ruff):

```bash
py -3.12 -m venv C:\Users\guerr\.venvs\cloudin312 && C:\Users\guerr\.venvs\cloudin312\Scripts\pip install -r requirements-dev.txt
```

Pruebas y revisión de estilo (no tocan las bases reales: usan bases temporales):

```bash
C:\Users\guerr\.venvs\cloudin312\Scripts\python.exe -m pytest
```

```bash
C:\Users\guerr\.venvs\cloudin312\Scripts\ruff.exe check .
```

Accesos:

- **Panel maestro:** http://localhost:8000/master/ — `juan` / `cloudin2026`
- Django Admin (edición cruda): http://localhost:8000/admin/
- Panel de un restaurante: http://localhost:8000/panel/login/?tenant=&lt;slug&gt;

En producción cada restaurante entra por su subdominio (`<slug>.cloudin.app`) y
el `?tenant=` deja de hacer falta.

## Panel maestro

En `/master/` se da de alta un restaurante llenando un formulario. Al enviarlo,
en un solo paso el sistema:

1. registra el restaurante en la base de control,
2. **crea su base de datos** (`tenant_dbs/cloudin_<slug>.sqlite3`) y le corre las migraciones,
3. genera su API key,
4. crea el usuario administrador con una contraseña aleatoria,
5. muestra usuario, contraseña y enlace **una sola vez**, con un botón que copia
   el mensaje listo para enviarle al cliente.

En la ficha del restaurante se agregan los demás usuarios del panel (personal o
administrador). Cada uno recibe su propia contraseña generada. Los nombres de
usuario se prefijan con el restaurante (`culturabrisket.carlos`) porque son
únicos en todo el sistema.

También se puede desactivar un restaurante (deja de poder entrar sin borrar sus
datos) y rotar su API key.

### Contraseñas visibles para el dueño del sistema

En la tabla de usuarios, cada contraseña se puede **ver las veces que haga
falta** (botón «Ver») y **cambiar** por una escrita a mano o por una generada
(botón «Cambiar»). Esa pantalla es solo para el superusuario: un empleado del
restaurante que intente abrirla es redirigido al login.

Cómo está guardado, que es lo que importa:

| Dato | Dónde | Forma |
|---|---|---|
| Contraseña de login | `auth_user.password` | hash PBKDF2 — irreversible, es lo que valida Django |
| Copia para consultar | `tenants_tenantmembership.password_cifrada` | cifrada con Fernet (AES) |
| La llave del cifrado | `.env` → `CREDENTIAL_KEY` | **fuera** de la base de datos y del repositorio |

Es decir: quien se robe `control.sqlite3` no obtiene ninguna contraseña; hace
falta además el `.env` del servidor. Verificado — las contraseñas no aparecen en
claro dentro del archivo de la base.

Si se pierde `CREDENTIAL_KEY`, nadie queda bloqueado (el login usa el hash), pero
el panel deja de poder mostrar las contraseñas viejas y hay que regenerarlas.

## Comandos

```bash
# Lo mismo que hace el panel maestro, desde la consola
python manage.py create_tenant --name "<Nombre>" --slug <slug> --nit <nit>
# …o con el menú «Carta» creado y la invitación por correo al dueño
python manage.py create_restaurant --name "<Nombre>" ...

# Migrar todas las bases de restaurante después de cambiar modelos
python manage.py migrate_tenants

# QR de cada mesa (PNG en qrcodes/<slug>/): la página del menú + ?mesa=<token>, igual que el panel
python manage.py tenant_qr --slug <slug>

# Importar la semilla de un menú digital (contrato cloudin.menu/v1)
python manage.py import_menu <ruta>/menu.seed.json --assets <carpeta del sitio> --create-tenant

# Regenerar el runtime minificado de los menús después de editar static/src/
python manage.py build_runtime
```

> Después de cualquier `makemigrations`: primero `migrate` (base de control) y
> luego `migrate_tenants` (todas las bases de restaurante).

## Panel del restaurante

| Pantalla | Para qué |
|---|---|
| **Inicio** (`/panel/`) | Estado del menú (publicado, en línea) y, en el plan completo, «Pedidos y mesas»: mesas ocupadas, pedidos por atender y pedidos de hoy |
| **Mesas** (`/panel/mesas/`) | Tablero: mesa libre u ocupada, cliente y total en curso. Desde la mesa se agregan pedidos, se registran novedades y se **cierra la cuenta** |
| **Mensajes** (`/panel/mensajes/`) | Los pedidos que llegan del menú digital y de los meseros, con mesa y cliente. Marca los nuevos y lleva un contador en la barra |
| **Cocina** (`/panel/cocina/`) | Comandas por hacer, con semáforo por tiempo de espera |
| **Mi menú** (`/panel/mi-menu/`) | La carta: categorías, productos, precios, fotos, presentaciones, adiciones y agotados |
| **Personalizar** (`/panel/personalizar/`) | Marca, colores, portada, datos del negocio y horario, con vista previa del menú digital |
| **Códigos QR** (`/panel/mesas-y-qr/`) | Cuántas mesas hay y el QR de cada una (PNG, SVG o PDF) |
| **Meseros** (`/panel/meseros/`) | Cómo se toman los pedidos (autoservicio, meseros o ambos) y las cuentas de los meseros |
| **Configuración** (`/panel/configuracion/`) | Mesas, importación de la carta y el sitio web conectado (con su llave) |

Con el plan **Menú digital** el panel muestra solo lo del menú (Inicio, Mi menú,
Personalizar, Códigos QR): ese plan no recibe pedidos.

### Mesas y cuentas

No hay turno de caja ni reservas: **los pedidos entran a cualquier hora**.

- Una mesa se **ocupa** cuando llega su primer pedido (del menú digital, de un mesero
  o del panel): se abre su cuenta (`TableSession`) y todos la ven ocupada.
- Los pedidos siguientes de esa mesa se suman a la misma cuenta.
- Mensajes, Cocina y Mesas muestran **los pedidos de las cuentas abiertas**.
- Al **cerrar la cuenta** (Mesas → la mesa → Cerrar cuenta) se abre la precuenta para
  imprimir, la mesa queda libre y sus pedidos salen de esas pantallas. Nada se borra:
  la cuenta cerrada queda en la base con su total.

### Cloudin Meseros

Cada restaurante elige en **Meseros** cómo se toman los pedidos:

| Modo | QR del cliente | App de meseros |
|---|---|---|
| Autoservicio (por defecto) | recibe pedidos | apagada |
| Meseros | responde 403 «los pedidos los toma el mesero» (`solo_meseros`) | encendida |
| Ambos | recibe pedidos | encendida |

Con el plan «Menú digital» el QR no recibe pedidos en ningún modo (`403 sin_pedidos`).

La app vive en `/mesero/<slug>/` y es una PWA: se abre en la tablet, se agrega a la
pantalla de inicio y queda como app. Tres pantallas: mesas → mesa (tomar pedido /
cuenta) → pedido. En tablet apaisada el pedido va al lado del menú.

- **Login propio.** El mesero (`waiters.Mesero`) vive en la base de su restaurante,
  con contraseña en hash y su propia sesión. No es un usuario de Django: entrar como
  mesero no abre el panel, y «Salir» de la tablet no cierra la sesión de un admin.
- **Solo su restaurante.** La sesión guarda el slug y una huella de la contraseña: en
  otro restaurante no vale, y si el admin cambia la clave o lo desactiva, queda afuera
  en la siguiente petición. Tras 6 intentos fallidos el login se bloquea 10 minutos.
- **La comanda lleva su nombre.** `Order.mesero` + `Order.mesero_nombre` (copia, para
  que el historial no cambie si se borra el mesero). Cocina, Mensajes y la tirilla lo
  muestran. Si llegó por QR, `mesero` queda en null.
- **Sin pedidos duplicados.** Cada envío lleva una llave; si la red se cae justo al
  enviar y la tablet reintenta, la cocina no recibe la comanda dos veces. El carrito de
  cada mesa se guarda en la tablet, así que cambiar de mesa o perder señal no lo borra.
- El precio siempre sale del menú del panel, nunca de la tablet.

Las mesas se identifican **solo por su número** — así las nombra el personal. Una
mesa que ya tuvo cuentas no se borra: se desactiva, para no perder su historial.
Lo mismo con un producto que ya se vendió: se elimina de la carta pero se conserva.

## El menú digital y los sitios conectados

- **[GUIA-MENU-DIGITAL.md](GUIA-MENU-DIGITAL.md)** — la guía para construir el menú
  digital de un cliente: tecnologías, Cloudflare Pages paso a paso, la carta pública,
  el carrito compartido de la mesa, errores, seguridad y un checklist. La implementación
  de referencia está en `client/example/` (`index.html` + `carrito.js`).
- **[CONECTAR-MENU-A-CLOUDIN.md](CONECTAR-MENU-A-CLOUDIN.md)** — para sitios que ya
  tienen su carta y la importan al panel (formato `cloudin_menu: 1`).
- **[INTEGRACION-SITIO-WEB.md](INTEGRACION-SITIO-WEB.md)** — la API de la tablet o del
  sitio del restaurante (pedidos por número de mesa).

Solo los orígenes registrados del restaurante (su «Página del menú», su sitio y «Otros
sitios autorizados») pueden pedir desde un navegador — lo controla
`apps/tenants/cors.py`, así que no hay que tocar la configuración del servidor cuando
entra un cliente nuevo. La carta pública (`/api/public/…`) responde a cualquier origen.

## API

**Carta pública** — sin llave, CORS abierto, con `ETag`:
`GET /api/public/<slug>/menu/[?table=<token>]`.

Lo demás cuelga de `/api/v1/`.

**Menú digital (QR de la mesa)** — cabecera `X-API-Key` y el token de la mesa en la ruta

| Método | Ruta | Para qué |
|---|---|---|
| GET | `/mesa/<token>/estado/` | Carrito compartido, pedidos de la mesa y si recibe pedidos |
| PUT | `/mesa/<token>/borrador/` | Guardar el carrito compartido (`{items, version}`) |
| POST | `/mesa/<token>/aviso/` | «Voy a enviar el pedido» |
| POST | `/mesa/<token>/enviar/` | Enviar el carrito a la cocina (ocupa la mesa) |
| GET | `/mesa/<token>/` | Carga inicial: estado + carta en la forma vieja |
| GET | `/tables/<token>/` | Mesa + su cuenta actual |
| POST | `/tables/<token>/orders/` | Pedido directo, sin carrito compartido |

**Sitio web del restaurante (la tablet)** — cabecera `X-API-Key`

| Método | Ruta | Para qué |
|---|---|---|
| GET | `/menu/` | La carta por categorías (`?formato=cloudin` en el formato de importación) |
| GET | `/site/info/` | Mesas activas + menú |
| GET | `/site/tables/` | Mesas libres y ocupadas |
| GET | `/site/tables/<numero>/orders/` | Lo pedido por una mesa y en qué va |
| POST | `/site/orders/` | Enviar un pedido por número de mesa |

**Panel del restaurante** — sesión de Django, el usuario debe pertenecer al restaurante

| Método | Ruta |
|---|---|
| GET, POST | `/staff/tables/` · PATCH, DELETE `/staff/tables/<id>/` |
| GET | `/staff/avisos/` · `/staff/messages/` · `/staff/kitchen/` · `/staff/site/status/` |
| POST | `/staff/orders/<id>/visto/` · `/staff/orders/<id>/impreso/` |
| PATCH | `/staff/orders/<id>/status/` |
| POST | `/staff/tables/<id>/open/` · `/staff/tables/<id>/orders/` |
| GET | `/staff/sessions/<id>/` · POST `/staff/sessions/<id>/close/` |
| POST | `/staff/items/<id>/novedad/` · `/staff/sessions/<id>/descuento/` |
| GET | `/staff/menu/` · POST, PATCH, DELETE en `/staff/menu/categories/` y `/staff/menu/products/` |
| — | Carta v1 por UUID: `/staff/catalog/…` (menús, categorías, productos, grupos, etiquetas, orden, acciones masivas, historial), `/staff/settings/`, `/staff/mesas/`, `/staff/qr/…` |

El panel se actualiza por *polling* cada 5 segundos. Websockets queda para más
adelante si hace falta.

## Impresión

`/panel/comanda/<id>/imprimir/` y `/panel/cuenta/<id>/imprimir/` son tirillas de
80 mm que abren el diálogo de impresión del navegador contra la térmica
configurada como impresora del sistema. La impresión automática por red (fase 4)
necesitará un agente en la red local del restaurante.

## Pasar a producción

Montado para **Cloudflare Containers** (Pages no ejecuta Django): un Worker
(`cloudflare/worker.js`) delante de un contenedor con Django + gunicorn
(`Dockerfile`), la base de control y las de cada restaurante en Postgres
(`DATABASE_URL`) y las fotos en Cloudflare R2. Cada push a `main` se despliega solo.
Pasos, secretos y complicaciones: **[DESPLIEGUE-CLOUDFLARE.md](DESPLIEGUE-CLOUDFLARE.md)**.

- Con `DATABASE_URL` de Postgres, `TENANT_DB_ENGINE` pasa a `postgres` y
  `TENANT_PG_*` salen de esa misma URL; `provision_tenant` hace el
  `CREATE DATABASE` de cada restaurante (psycopg 3 o psycopg2).
- Al arrancar, el contenedor corre `python manage.py preparar_servidor`
  (`migrate` + `migrate_tenants` + superusuario inicial).
- El mismo `Dockerfile` sirve en cualquier otro servidor con Docker.

## Módulos retirados

Se quitaron la facturación electrónica (Factus), el turno de caja, el inventario,
Cloudin Reservas, Cloudin Employees, las propinas, Cloudin Control y la analítica de
ventas. De cada app (`billing`, `shifts`, `inventory`, `reservas`, `staffing`,
`control`) queda solo `apps.py`, un `models.py` mínimo y sus **migraciones**: la
última (`…_retirar_modulos`) borra sus tablas en la base de control y en la de cada
restaurante. Por eso siguen en `INSTALLED_APPS` y en `TENANT_APPS`: sin ellas,
Django no puede migrar las bases que ya existen.

Cuando todas las bases (local y servidor) hayan corrido esas migraciones, se pueden
borrar del todo (la app, su entrada en settings y en `routers.py`, y las
dependencias de migración que apuntan a ellas). Mientras tanto, no les agregues código.

## Lo que sigue

- **Desplegar el panel en un host público.** El código ya está listo para
  Cloudflare Containers; faltan la cuenta (Workers Paid, Neon, R2) y los secretos:
  ver DESPLIEGUE-CLOUDFLARE.md.
- **El primer menú digital en Cloudflare Pages** con pedidos por QR, siguiendo
  GUIA-MENU-DIGITAL.md.
- **Pausar pedidos**: un interruptor para que el menú deje de recibir pedidos fuera de
  horario (hoy entran a cualquier hora).
- **Rotar el token de una mesa desde el panel** (hoy solo desde la consola).
- **Impresión automática por red** y ajuste fino de la tirilla contra una
  impresora térmica real.


## Anulaciones, cortesías, devoluciones y descuentos

`apps/orders/novedades.py`. En el detalle de la mesa, el botón «⋯» de cada línea
permite anular, dar en cortesía o registrar una devolución (toda la línea o parte),
y la cuenta tiene «Hacer un descuento» (porcentaje o valor). Siempre con motivo;
un administrador lo hace directo y un cajero necesita que un administrador escriba
su contraseña en ese momento. Cada caso queda en `NovedadCuenta` con quién lo
registró y quién lo autorizó. Lo que no se cobra queda en $0 en la cuenta y el
descuento se resta del total (la precuenta lo muestra).

## Términos, privacidad y datos

- Cada usuario del panel acepta **una vez por versión** los términos y la política de
  privacidad (`/legal/aceptar/`); sin aceptar no se puede usar (`AceptacionLegal`,
  `LEGAL_VERSION` en settings). «No acepto» cierra la sesión.
- Páginas públicas: `/legal/terminos/`, `/legal/privacidad/` y, por restaurante,
  `/legal/r/<slug>/datos/` (la política para sus comensales, para enlazarla desde su
  menú digital).
- Datos del responsable en el `.env`: `LEGAL_RESPONSABLE`, `LEGAL_NIT`,
  `LEGAL_CORREO`, `LEGAL_DIRECCION`, `LEGAL_CIUDAD`. **Los textos son una base: deben
  revisarse con un abogado antes de vender.**
- ⚠️ Los textos (`templates/legal/`) todavía describen los módulos retirados
  (facturación, reservas, inventario, turnos, propinas, Control). Hay que
  actualizarlos con el abogado y subir `LEGAL_VERSION` para que todos los acepten de
  nuevo.

## Diseño

`templates/base.html` tiene el sistema de diseño con **tema oscuro y claro** (tokens
en `:root` y `[data-theme="claro"]`, elección guardada en el navegador), paleta
pastel para íconos y gráficas (`durazno`, `lavanda`, `menta`, `cielo`, `amarillo`,
`rosa`; en gráficas `--g1…--g6`), transiciones entre pantallas (View Transitions),
entradas escalonadas, números que cuentan y la barra inferior en el celular. El
logotipo tiene versión para fondo claro (`cloudin-texto-claro.png`).
