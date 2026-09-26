# Cloudin — Fase 1 (MVP)

Backend único multi-tenant para restaurantes: mesas, pedidos por QR, panel del
restaurante e impresión de comandas. Sin facturación electrónica todavía (fase 2).

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
- `apps/tenants/routers.py` — manda `catalog`, `dining` y `orders` a la base del
  restaurante, y `auth`/`sessions`/`admin`/`tenants` a la de control.

Dar de alta un cliente no despliega nada nuevo: se crea su base, se migra y se
generan sus credenciales.

## Apps

- `master` — panel maestro: alta de restaurantes y entrega de credenciales.
- `tenants` — restaurantes, usuarios de cada restaurante, aprovisionamiento.
- `catalog` — categorías y productos del menú.
- `dining` — mesas y su token de QR.
- `orders` — cuenta de mesa (`TableSession`) → comandas (`Order`) → ítems.
- `api` — endpoints REST (web del QR + panel).
- `billing` — facturación electrónica: datos fiscales, resoluciones, documentos DIAN.
- `staffing` — Cloudin Employees: empleados, marcación y horas.
- `shifts` — turno de caja: apertura, cierre e informe del turno.
- `inventory` — insumos, recetas, kardex, compras y conteos físicos.
- `waiters` — Cloudin Meseros: cuentas de mesero y la app de la tablet (`/mesero/<slug>/`).
- `panel` — pantallas del restaurante (mesas, cocina, tirillas de impresión).

## Arrancar en local

```bash
C:\Users\guerr\.venvs\cloudin\Scripts\python.exe manage.py runserver
```

El entorno virtual vive fuera de OneDrive (`C:\Users\guerr\.venvs\cloudin`) para
que OneDrive no sincronice miles de archivos. Para recrearlo:

```bash
python -m venv C:\Users\guerr\.venvs\cloudin && C:\Users\guerr\.venvs\cloudin\Scripts\pip install -r requirements.txt
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

En la ficha del restaurante se agregan los demás empleados (mesero/cajero o
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

# Migrar todas las bases de restaurante después de cambiar modelos
python manage.py migrate_tenants

# QR de cada mesa (PNG en qrcodes/<slug>/)
python manage.py tenant_qr --slug <slug> --base-url https://<dominio>/mesa
```

> Después de cualquier `makemigrations`: primero `migrate` (base de control) y
> luego `migrate_tenants` (todas las bases de restaurante).

## Panel del restaurante

| Pantalla | Para qué |
|---|---|
| **Inicio** (`/panel/`) | Portada: ventas del día, indicadores, gráfica de 14 días y estado del turno |
| **Mesas** (`/panel/mesas/`) | Tablero: mesa libre/ocupada, cliente y total en curso |
| **Mensajes** (`/panel/mensajes/`) | Bandeja de pedidos que llegan del sitio web, con mesa y cliente. Marca los nuevos, avisa con sonido y lleva un contador en la barra |
| **Cocina** (`/panel/cocina/`) | Comandas activas con semáforo por tiempo de espera |
| **Turnos** (`/panel/turnos/`) | Abrir y cerrar el turno de caja, y el informe de cada turno |
| **Inventario** (`/panel/inventario/`) | Insumos, compras, recetas, kardex, conteos y reportes |
| **Ventas** (`/panel/ventas/`) | Analítica: series, mapa de calor, lo más vendido |
| **Facturación** (`/panel/facturacion/`) | Habilitación DIAN, resoluciones y documentos emitidos |
| **Empleados** (`/panel/empleados/`) | Cloudin Employees: reloj de marcación y horas del equipo |
| **Meseros** (`/panel/meseros/`) | Modo de servicio (autoservicio, meseros o ambos) y cuentas de los meseros |
| **Configuración** (`/panel/configuracion/`) | Los tres pasos del montaje: mesas, menú y sitio web. Solo el administrador del restaurante |

### El turno de caja

Todo lo que pasa en el local cuelga de un **turno**: las cuentas de mesa, los
pedidos, las facturas y el consumo de insumos. Mensajes, Cocina y Mesas muestran
**solo el turno abierto**, así que al cerrarlo el panel queda en blanco y listo
para la jornada siguiente — lo anterior no se borra, queda en el informe de ese
turno.

Al cerrar se liquidan las mesas que quedaron abiertas (se cierran y se facturan),
se congela el resultado y se aterriza en el **informe de cierre**: total vendido,
lista de facturas emitidas con su CUFE, cuadre de caja, lo más vendido, quién
trabajó y qué insumos se consumieron. Se imprime en tirilla como un informe Z.
No reemplaza a las facturas: en Colombia cada venta lleva la suya, y el informe
las resume.

Si llega un pedido y nadie abrió turno, **se abre uno solo** (queda anotado como
apertura automática): el servicio nunca se cae por eso.

### Cloudin Meseros

Cada restaurante elige en **Meseros** cómo se toman los pedidos:

| Modo | QR del cliente | App de meseros |
|---|---|---|
| Autoservicio (por defecto) | recibe pedidos | apagada |
| Meseros | responde 403 «los pedidos los toma el mesero» | encendida |
| Ambos | recibe pedidos | encendida |

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

### Inventario

Dos ideas sostienen el módulo:

1. **Insumo ≠ producto vendible.** El insumo se compra y tiene stock real; el
   plato del menú no tiene stock propio — su costo y su disponibilidad salen de
   la receta.
2. **El stock nunca se edita a mano.** Todo entra como `Movimiento`, con fecha,
   autor, costo del momento y motivo obligatorio en los ajustes.

Costeo por **promedio ponderado**, recalculado con cada compra:
`(valor del saldo + valor de la entrada) / (cantidad del saldo + cantidad que entra)`.
Las salidas usan el promedio vigente y no se recalculan hacia atrás.

El orden para ponerlo a andar: crear insumos → registrar una compra (carga stock
y fija el costo) → armar las recetas. Desde ahí, **al facturar una mesa el stock
baja solo** según la receta, incluidas las subrecetas. Las líneas que llegan del
sitio web sin `product_id` se cruzan por nombre contra el menú, para que esas
ventas también muevan inventario.

Las mesas se identifican **solo por su número** — así las nombra el personal. Una
mesa que ya tuvo cuentas no se borra: se desactiva, para no perder su historial.
Lo mismo con un producto que ya se vendió: se marca agotado.

## El sitio web que envía los pedidos

Cada restaurante registra **una** dirección, al darlo de alta o después desde su
panel. Solo ese origen puede llamar a la API desde un navegador — lo controla
`apps/tenants/cors.py`, así que no hay que tocar la configuración del servidor
cuando entra un cliente nuevo.

La pantalla de Configuración muestra el estado de la conexión en vivo: gris sin
sitio registrado, ámbar cuando está autorizado pero nunca se ha comunicado, y
verde cuando el sitio llamó a la API hace menos de cinco minutos, con el conteo
de pedidos recibidos.

**[INTEGRACION-SITIO-WEB.md](INTEGRACION-SITIO-WEB.md)** tiene la guía completa
para quien construya esa página: autenticación, endpoints, formato de los
pedidos y errores. La misma guía, con la llave y la dirección ya rellenadas,
aparece dentro del panel.

> Mientras no exista el QR por mesa, la llave de la API basta para enviar
> pedidos y queda dentro del sitio. Es aceptable para una tablet que maneja el
> personal; cuando entre el QR por mesa, cada mesa tendrá además su token.

## API

Todas las rutas cuelgan de `/api/v1/`.

**Sitio web del restaurante (la tablet del mesero)** — cabecera `X-API-Key: <api key>`

| Método | Ruta | Para qué |
|---|---|---|
| GET | `/site/info/` | Mesas activas + menú, todo lo que el sitio necesita |
| POST | `/site/orders/` | Enviar un pedido |

```json
POST /api/v1/site/orders/
{ "table_number": 2, "customer_name": "María", "items": [{"product_id": 3, "quantity": 2}] }
```

**Web del cliente por QR (fase siguiente)** — misma API key, y el token de la mesa en la URL

| Método | Ruta | Para qué |
|---|---|---|
| GET | `/menu/` | Menú completo por categorías |
| GET | `/tables/<token>/` | Mesa + su cuenta actual |
| POST | `/tables/<token>/orders/` | Enviar pedido |

**Panel del restaurante** — sesión de Django, el usuario debe pertenecer al restaurante

| Método | Ruta |
|---|---|
| GET, POST | `/staff/tables/` |
| PATCH, DELETE | `/staff/tables/<id>/` |
| GET | `/staff/messages/` |
| GET | `/staff/site/status/` |
| GET | `/staff/menu/` |
| POST | `/staff/menu/categories/` · PATCH, DELETE `/staff/menu/categories/<id>/` |
| POST | `/staff/menu/products/` · PATCH, DELETE `/staff/menu/products/<id>/` |
| POST | `/staff/orders/<id>/visto/` |
| POST | `/staff/tables/<id>/open/` |
| POST | `/staff/tables/<id>/orders/` |
| PATCH | `/staff/orders/<id>/status/` |
| GET | `/staff/kitchen/` |
| GET | `/staff/sessions/<id>/` |
| POST | `/staff/sessions/<id>/close/` |

El panel se actualiza por *polling* cada 5 segundos. Websockets queda para más
adelante si hace falta.

## Facturación electrónica con Factus

Factus es el proveedor tecnológico (PT) certificado ante la DIAN. El adaptador está
en `apps/billing/providers/factus.py`, contra la **API v2**:

- `ClienteFactus` — OAuth2 (`grant_type=password`), token en caché con renovación por
  refresh token, y traducción de respuestas: 422 → rechazo con los campos explicados;
  401 → token nuevo y un reintento; 409, 429, 5xx y caídas de red → contingencia;
  credenciales o plan inválidos → contingencia con el motivo claro.
- `ProveedorFactus` — arma `POST /v2/bills/validate` desde el `DocumentoFiscal`:
  base sin INC por unidad (la carta trae el impuesto incluido), `cash_rounding_amount`
  para los centavos, consumidor final, medio de pago. Un rechazo de la DIAN borra la
  factura no validada en Factus (si no, bloquea las siguientes); una demora se
  reintenta con la misma `reference_code`.

Credenciales en el `.env` (`FACTUS_URL`, `FACTUS_CLIENT_ID`, `FACTUS_CLIENT_SECRET`,
`FACTUS_USERNAME`, `FACTUS_PASSWORD`). Un restaurante puede tener las suyas propias,
cifradas, desde **Facturación → Proveedor tecnológico**. Ahí mismo se elige Factus, se
prueba la conexión y se traen los rangos de numeración.

```bash
python manage.py factus_diagnostico
python manage.py factus_diagnostico --tenant culturabrisket --sincronizar-rangos
python manage.py test apps.billing.tests.test_factus
```

## Impresión

`/panel/comanda/<id>/imprimir/` y `/panel/cuenta/<id>/imprimir/` son tirillas de
80 mm que abren el diálogo de impresión del navegador contra la térmica
configurada como impresora del sistema. La impresión automática por red (fase 4)
necesitará un agente en la red local del restaurante.

## Pasar a producción

1. `TENANT_DB_ENGINE=postgres` en `.env` + `pip install psycopg2-binary`.
   `provision_tenant` ya hace el `CREATE DATABASE` por restaurante.
2. `TENANT_BASE_DOMAIN=cloudin.app` y DNS comodín `*.cloudin.app`.
3. `DEBUG=0`, `SECRET_KEY` real, `ALLOWED_HOSTS=.cloudin.app`.
4. Gunicorn + Nginx (o el hosting que se elija) — un solo despliegue para todos.

## Lo que sigue

- **Desplegar el panel en un host público.** Es lo único que falta para operar de
  verdad: Cloudflare Pages no sirve para Django, y un sitio publicado no alcanza
  `localhost:8000`.
- **Proveedor tecnológico real** en lugar del simulado (`apps/billing/providers/`),
  y el set de pruebas de habilitación ante la DIAN.
- **Nómina electrónica** con las horas de Cloudin Employees: el modelo ya guarda
  lo que esa emisión necesita.
- **Notas crédito/débito** y exportes contables.
- **Inventario:** traslados entre bodegas desde la interfaz y órdenes de compra
  sugeridas a partir del stock mínimo.
- **Impresión automática por red** y ajuste fino de la tirilla contra una
  impresora térmica real.


## Cloudin Reservas (`apps/reservas`)

El recorrido completo: **reserva → llegada → mesa → pedido → factura → historial**.

- **Horarios** (`ServicioReserva`): «mesa» (por hora, ocupa una mesa un tiempo) o
  «día» (cupo de personas, como una pasadía). Días de la semana, abre/cierra
  (cerrar a medianoche funciona), intervalo y duración. Todo editable en
  *Reservas → Horarios y mesas*, junto con los días bloqueados y la zona, los
  puestos y si cada mesa se ofrece en línea.
- **Disponibilidad** (`services.py`): calendario y horas con cupo según mesas libres
  (sin choques de horario), anticipación mínima y días máximos. Si algo se llena,
  responde con sugerencias (horas cercanas y próximos días).
- **Confirmación automática** si hay cupo (configurable), con mesa asignada: la más
  justa para el grupo, prefiriendo la zona pedida.
- **Llegada y mesa**: «Llegó» y «Sentar» abren la cuenta de la mesa con la reserva
  (necesita turno abierto). Al cerrar la cuenta la reserva queda completada y la
  visita entra al **historial del cliente** (`Cliente`: visitas, gasto, ticket, lo
  que más pide, cumplimiento).
- **Avisos**: la campana y el menú lateral cuentan reservas nuevas, recordatorios
  por enviar y reservas atrasadas; suena un «ding» con cada reserva nueva.
- **WhatsApp**: el sitio le da al cliente el enlace para avisar al restaurante; el
  panel tiene «Recordar» (wa.me con el mensaje configurable) y el cliente puede
  agregar la cita a su calendario (.ics / Google Calendar).
- API pública en `/api/v1/reservas/…` (ver INTEGRACION-SITIO-WEB.md §6). No pide turno.

## Cloudin Control (`apps/control`)

> Cloudin no solamente registra lo que ocurre en el restaurante: detecta, explica y
> ayuda a corregir lo que afecta la rentabilidad.

- `AlertaControl` (tabla `control_alert`): tipo, severidad (`info`/`warning`/`critical`),
  título, descripción, **qué revisar**, impacto estimado, entidad, período, estado
  (`new`/`reviewed`/`resolved`/`dismissed`), metadata y una **huella** que evita
  repetir la misma alerta al volver a analizar.
- `detectores.py`: caja (faltantes y sobrantes), turnos largos o sin contar
  efectivo, anulaciones por turno (y si se concentran en una persona), descuentos
  excepcionales, cortesías y devoluciones, inventario real vs. teórico por insumo,
  mermas, márgenes que caen porque subieron los insumos, productos sin receta,
  compras más caras que el promedio, food cost, cuentas cerradas sin factura,
  cuentas abiertas por horas, empleados sin marcar salida, tiempos de cocina,
  días con ventas bajas y reservas que no llegaron.
- **Detector de fugas** (`services.fugas`): consolida las posibles fugas del período
  por categoría y el total identificado.
- **Lenguaje**: nunca «robo». Siempre «diferencia», «posible fuga», «situación a
  revisar», «variación detectada».
- Se analiza al abrir Control o el Inicio (máximo cada 10 min), al cerrar cada turno
  y con `python manage.py control_analizar --todos` (para programarlo en el servidor).
- Sensibilidad por restaurante en *Cloudin Control → Sensibilidad* (`AjustesControl`).

### Anulaciones, cortesías, devoluciones y descuentos

`apps/orders/novedades.py`. En el detalle de la mesa, el botón «⋯» de cada línea
permite anular, dar en cortesía o registrar una devolución (toda la línea o parte),
y la cuenta tiene «Hacer un descuento» (porcentaje o valor). Siempre con motivo;
un administrador lo hace directo y un cajero necesita que un administrador escriba
su contraseña en ese momento. Cada caso queda en `NovedadCuenta` con quién lo
registró y quién lo autorizó. Lo que no se cobra no va a la factura; el descuento
viaja a Factus como `discount_rate` por línea.

## Ventas y platos (recomendaciones)

`apps/control/recomendaciones.py`: ranking de platos con tendencia y margen,
**ingeniería de menú** (estrellas, caballos de batalla, enigmas y platos por
replantear), productos que se piden juntos y tarjetas de recomendación en lenguaje
sencillo («Tu plato X genera el 18% de tus ventas…»). Se ven en *Ventas y platos* y
las tres más importantes en el Inicio.

## Términos, privacidad y datos

- Cada usuario del panel acepta **una vez por versión** los términos y la política de
  privacidad (`/legal/aceptar/`); sin aceptar no se puede usar (`AceptacionLegal`,
  `LEGAL_VERSION` en settings). «No acepto» cierra la sesión.
- Páginas públicas: `/legal/terminos/`, `/legal/privacidad/` y, por restaurante,
  `/legal/r/<slug>/datos/` (la política para sus comensales, que enlazan los
  formularios de reserva).
- Datos del responsable en el `.env`: `LEGAL_RESPONSABLE`, `LEGAL_NIT`,
  `LEGAL_CORREO`, `LEGAL_DIRECCION`, `LEGAL_CIUDAD`. **Los textos son una base: deben
  revisarse con un abogado antes de vender.**

## Diseño

`templates/base.html` tiene el sistema de diseño con **tema oscuro y claro** (tokens
en `:root` y `[data-theme="claro"]`, elección guardada en el navegador), paleta
pastel para íconos y gráficas (`durazno`, `lavanda`, `menta`, `cielo`, `amarillo`,
`rosa`; en gráficas `--g1…--g6`), transiciones entre pantallas (View Transitions),
entradas escalonadas, números que cuentan y la barra inferior en el celular. El
logotipo tiene versión para fondo claro (`cloudin-texto-claro.png`).
