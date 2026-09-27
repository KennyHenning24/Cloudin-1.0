# Cloudin — contexto para Codex (o cualquier agente que siga programando)

> Léeme completo antes de tocar una línea. Este archivo explica qué es el
> proyecto, cómo montarlo en un computador que no tiene **nada** instalado, qué
> hace cada archivo, dónde se empieza a modificar según lo que se pida, y las
> reglas que el dueño ya decidió y que no se deben cambiar por cuenta propia.
>
> Escrito el 15 de septiembre de 2026 y actualizado el 26 de septiembre (se quitaron
> facturación, turno, inventario, reservas y Control). Autor del código: Juan.
> Todo el código, los comentarios y la interfaz están **en español**. Sigue así.

---

## 0. Orden de lectura

| Archivo | Para qué |
|---|---|
| **Este archivo** | Montaje, mapa del código, reglas y recetas de cambio |
| `README.md` | Documentación técnica del producto, pantalla por pantalla |
| `CLAUDE-MENU-DIGITAL.md` | Instrucciones para Claude Code al crear un menú digital: carta, pedidos, importación de la carta, publicar y probar (se copia al repo del menú como `CLAUDE.md`) |
| `PASO-A-PASO-NUEVO-RESTAURANTE.md` | Registrar un restaurante y conectar su menú, paso a paso, con la plantilla `client/plantilla/index.html` |
| `GUIA-MENU-DIGITAL.md` | Cómo construir el menú digital de un cliente en Cloudflare Pages y cómo lee la carta y manda pedidos |
| `CONECTAR-MENU-A-CLOUDIN.md` | Cómo el sitio web de un restaurante le entrega su carta al panel |
| `INTEGRACION-SITIO-WEB.md` | API para la tablet o el sitio del restaurante (pedidos por número de mesa) |
| `DESPLIEGUE-GRATIS.md` | Cómo ponerlo en internet sin pagar: Render + Neon + R2 para las fotos (`render.yaml`) |
| `DESPLIEGUE-CLOUDFLARE.md` | Cómo corre en Cloudflare (Containers, Postgres, R2), por qué no en Pages y el día a día del despliegue |
| `..\Cloudin-para-restaurantes.md` | Qué problema resuelve el producto (material de venta; describe módulos que ya se quitaron) |
| `..\cloudin-arquitectura.md` | Plan original por fases |

---

## 1. Qué es Cloudin

Software para restaurantes en Colombia. Un solo backend Django sirve a todos los
restaurantes (multi-tenant) y cubre dos cosas:

1. **El menú digital**: la carta (productos, precios, fotos, presentaciones,
   adiciones), la personalización y los QR de las mesas. El menú que ve el cliente
   es un sitio aparte por restaurante (Cloudflare Pages) que lee la carta de
   Cloudin: `GUIA-MENU-DIGITAL.md`.
2. **Los pedidos de ese menú**: carrito compartido por mesa, mesas que se ocupan
   solas con el primer pedido, Mensajes, Cocina, la app de meseros en tablet, las
   novedades (anulación, cortesía, devolución, descuento) y la precuenta impresa.

El 26 de septiembre de 2026 el dueño decidió quitar la facturación electrónica
(Factus), el turno de caja, el inventario, Cloudin Reservas, el reloj de
empleados, las propinas, Cloudin Control y la analítica de ventas (ver 4.8 «Apps
retiradas»).

**No es un SPA.** Es Django renderizando HTML en el servidor, con JavaScript
plano cuando hace falta. **No metas React, Next.js ni un bundler.** Si piden un
efecto de biblioteca React, recréalo en CSS/JS plano.

---

## 2. Montar el equipo desde cero

Supón un computador limpio. Esto es todo lo que hace falta.

### 2.1 Obligatorio

| Herramienta | Versión | Para qué | Cómo |
|---|---|---|---|
| **Python** | 3.10 – 3.12 (hoy corre en 3.10.4) | Todo el backend | python.org/downloads — en Windows marca *Add python.exe to PATH* |
| **pip + venv** | vienen con Python | Dependencias aisladas | `python -m venv` |
| **Git** | cualquiera reciente | Control de versiones (ver aviso) | git-scm.com |
| **Un navegador** | Chrome, Edge o Firefox | Probar el panel y la app del mesero | — |

> El proyecto vive en GitHub (`KennyHenning24/Cloudin-1.0`): trabaja en ramas y
> sube cambios pequeños. El `.gitignore` excluye `.env`, `*.sqlite3`, `tenant_dbs/`,
> `media/`, `staticfiles/`, `qrcodes/`, `node_modules/` y `__pycache__/`: nunca subas
> datos de restaurantes ni llaves.

### 2.2 Opcional, según lo que vayas a hacer

| Herramienta | Cuándo la necesitas |
|---|---|
| **Node.js 18+** | Solo para servir o tocar el sitio web de un restaurante (`npx http-server`) y correr `generar-cloudin-menu.js` de Cultura Brisket |
| **PostgreSQL + `psycopg[binary]`** | Solo para producción (`DATABASE_URL`, ver `DESPLIEGUE-CLOUDFLARE.md`). En local se usa SQLite y no hay nada que instalar. `requirements-produccion.txt` trae lo del servidor |
| **Docker / `npx wrangler`** | Solo para probar la imagen del servidor o el Worker de Cloudflare en local. El despliegue normal lo hace Cloudflare en cada push a `main` |
| **Playwright** | Para las pruebas de navegador (§7), capturas automáticas o guías en PDF (viene en `requirements-dev.txt`) |
| **Impresora térmica de 80 mm** | Solo para probar impresión real; sin ella el diálogo de impresión igual abre |
| **`gunicorn`** | Solo al desplegar en un servidor Linux |

### 2.3 Instalación paso a paso (Windows, que es la máquina del dueño)

```bash
python -m venv C:\Users\<usuario>\.venvs\cloudin
```

El entorno virtual va **fuera de OneDrive** a propósito: dentro, OneDrive
sincronizaría miles de archivos y todo se vuelve lentísimo.

```bash
C:\Users\<usuario>\.venvs\cloudin\Scripts\pip install -r requirements.txt
```

```bash
copy .env.example .env
```

En Linux o Mac es lo mismo con `python3 -m venv ~/.venvs/cloudin` y
`~/.venvs/cloudin/bin/pip`.

### 2.4 Llenar el `.env`

Generar la llave de cifrado de contraseñas (Fernet) y pegarla en `CREDENTIAL_KEY`:

```bash
C:\Users\<usuario>\.venvs\cloudin\Scripts\python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Variables que importan (todas documentadas en `.env.example`):

| Variable | En local | Nota |
|---|---|---|
| `SECRET_KEY` | cualquiera | En producción, una real y secreta |
| `DEBUG` | `1` | En producción `0` |
| `ALLOWED_HOSTS` | `*` | En producción, el dominio |
| `CREDENTIAL_KEY` | la que generaste | **Si se pierde, las contraseñas guardadas quedan ilegibles.** No la cambies en una instalación con datos |
| `TENANT_BASE_DOMAIN` | `localhost` | En producción `cloudin.app` con DNS comodín |
| `TENANT_DB_ENGINE` | `sqlite` | `postgres` en producción |
| `CORS_ALLOWED_ORIGINS` | vacío | Casi nunca hace falta: el permiso se da por restaurante en `apps/tenants/cors.py` |

> **Después de tocar el `.env` hay que reiniciar el servidor.** Django lo lee solo
> al arrancar. Ya pasó una vez: el proceso siguió con credenciales viejas en memoria.

### 2.5 Crear las bases y arrancar

```bash
C:\Users\<usuario>\.venvs\cloudin\Scripts\python manage.py migrate
```

```bash
C:\Users\<usuario>\.venvs\cloudin\Scripts\python manage.py migrate_tenants
```

```bash
C:\Users\<usuario>\.venvs\cloudin\Scripts\python manage.py createsuperuser
```

```bash
C:\Users\<usuario>\.venvs\cloudin\Scripts\python manage.py create_tenant --name "Mi Restaurante" --slug mirestaurante
```

```bash
C:\Users\<usuario>\.venvs\cloudin\Scripts\python manage.py runserver
```

Si la máquina ya tiene el proyecto con datos (la del dueño), los pasos de
`createsuperuser` y `create_tenant` sobran: `control.sqlite3` y
`tenant_dbs/cloudin_culturabrisket.sqlite3` ya existen.

### 2.6 Dónde entrar

| Dirección | Qué es | Quién entra |
|---|---|---|
| `http://localhost:8000/master/` | Panel maestro: alta de restaurantes y credenciales | Solo el superusuario |
| `http://localhost:8000/panel/login/?tenant=<slug>` | Panel del restaurante | Dueño, administrador o personal del restaurante |
| `http://localhost:8000/mesero/<slug>/` | App del mesero (PWA para tablet) | Meseros, con su propia clave |
| `http://localhost:8000/admin/` | Django Admin (edición cruda) | Superusuario |
| `http://localhost:8000/api/v1/...` | API REST | Menú digital y sitio web (X-API-Key) y panel (sesión) |
| `http://localhost:8000/api/public/<slug>/menu/` | Carta pública `cloudin.menu/v1` | Cualquiera, sin llave (la leen los menús digitales) |

En local el restaurante se elige con `?tenant=<slug>`; en producción sale del
subdominio. `.claude/launch.json` ya trae la configuración para levantar el
servidor en el puerto 8000.

---

## 3. La arquitectura en cinco minutos

**Una sola aplicación Django, N bases de datos.**

```
control.sqlite3                     -> restaurantes, usuarios de Django, sesiones, admin
tenant_dbs/cloudin_<slug>.sqlite3   -> menú, ajustes del negocio, mesas, cuentas,
                                       pedidos y meseros de ESE restaurante
```

Las piezas que lo sostienen, en `apps/tenants/`:

1. `middleware.py` — decide de qué restaurante es cada petición, en este orden:
   cabecera `X-API-Key` → subdominio → usuario logueado → `?tenant=` (solo local).
2. `context.py` — guarda el restaurante activo en un *thread local*; expone
   `get_current_tenant()` y el administrador de contexto `tenant_context(tenant)`,
   **obligatorio en scripts y comandos** para poder tocar datos de un restaurante.
3. `db.py` — registra en caliente la conexión de esa base. Django normalmente
   exige declararlas en `settings.DATABASES`; aquí se añaden en tiempo de ejecución.
4. `routers.py` — manda cada modelo a su base. `SHARED_APPS` van a `default`;
   `TENANT_APPS` (`catalog`, `dining`, `orders`, `waiters`, `business`, y las
   retiradas mientras corren sus últimas migraciones) van a la base del restaurante.

**Reglas que se derivan de esto y que se olvidan siempre:**

- Después de `makemigrations`: primero `migrate` (base de control) y **luego
  `migrate_tenants`** (todas las bases de restaurante). Si olvidas la segunda, el
  panel revienta con *no such column*.
- Un modelo de restaurante **no puede** tener ForeignKey a uno de la base de
  control, ni al revés. Por eso el mesero (`waiters.Mesero`) no es un `User` de
  Django y por eso `Order` guarda `mesero_nombre` como copia.
- En un script suelto: `with tenant_context(Tenant.objects.get(slug="..."))`.

---

## 4. Mapa del código

### 4.1 Raíz

| Archivo o carpeta | Qué es |
|---|---|
| `manage.py` | Entrada de Django |
| `config/settings.py` | Bases de datos, apps, sesiones de 60 días, correo, CORS, media, R2 |
| `config/urls.py` | Rutas raíz: `/admin/`, `/master/`, `/api/v1/`, `/panel/`, `/mesero/` |
| `config/wsgi.py`, `config/asgi.py` | Despliegue |
| `templates/` | Todas las plantillas (no viven dentro de cada app) |
| `static/img/` | Logo, marca e íconos de pestaña |
| `static/mesero/sw.js` | Service worker de la PWA del mesero |
| `media/` | Fotos del menú subidas desde el panel (ignorado por git) |
| `control.sqlite3`, `tenant_dbs/` | Bases de datos (ignoradas por git) |
| `requirements.txt` | Django 5.2, DRF, cors-headers, python-dotenv, cryptography, qrcode, requests |
| `requirements-produccion.txt` | Lo que suma el servidor: psycopg 3, gunicorn, boto3 (R2), whitenoise |
| `config/entorno.py` | Lee `DATABASE_URL` (Postgres) para la base de control y las de restaurante |
| `Dockerfile`, `.dockerignore` | La imagen del servidor (Django + gunicorn) |
| `wrangler.jsonc`, `cloudflare/worker.js`, `package.json` | Cloudflare: el Worker que pasa las visitas al contenedor. Guía: `DESPLIEGUE-CLOUDFLARE.md` |
| `render.yaml` | Render, plan gratis: el web service con el `Dockerfile`, las variables y las llaves que genera Render. Guía: `DESPLIEGUE-GRATIS.md` |
| `static/cloudin-menu.v1.js` | Runtime de los menús digitales (se genera desde `static/src/` con `build_runtime`) |
| `client/example/` | Menú digital de ejemplo: `index.html` (plantillas del runtime) y `carrito.js` (pedido a la mesa) |
| `tests/`, `conftest.py` | La suite de pytest (§7) |

### 4.2 `apps/tenants` — multi-tenancy y alta de clientes (base de control)

| Archivo | Qué hace |
|---|---|
| `models.py` | `Tenant` (slug, api_key, `pedidos_qr`, `app_meseros`, `site_url`, `menu_page`, `allowed_origins`, `menu_fuente`, activo; `origenes_permitidos`) y `TenantMembership` (usuario ↔ restaurante, con rol y `password_cifrada`) |
| `middleware.py` | Resuelve el restaurante de cada petición |
| `context.py` | Restaurante activo por hilo; `tenant_context` |
| `db.py` | Alta en caliente de la conexión de un restaurante |
| `routers.py` | Reparte modelos entre la base de control y la del restaurante |
| `provisioning.py` | Crea la base del restaurante y le corre las migraciones |
| `services.py` | Alta de restaurantes y usuarios (lo usan el panel maestro y el comando) |
| `crypto.py` | Cifrado Fernet reversible de las contraseñas que el maestro muestra |
| `cors.py` | Permite CORS **solo** a los orígenes de los restaurantes: `site_url`, `menu_page` y `allowed_origins` |
| `admin.py` | Django Admin de tenants |
| `management/commands/create_tenant.py` | Alta desde consola |
| `management/commands/migrate_tenants.py` | Migra todas las bases de restaurante |
| `management/commands/tenant_qr.py` | Genera los PNG de los QR de mesa (página del menú + `?mesa=<token>`, igual que el panel) |
| `management/commands/preparar_servidor.py` | Al arrancar el servidor: `migrate`, `migrate_tenants` y el superusuario inicial |

### 4.3 Modelos y lógica del restaurante

| App | Archivo | Responsabilidad |
|---|---|---|
| `catalog` | `models.py` | `Menu`, `Category`, `Product` (precio, foto, `permite_observacion`, `clave_externa`, `eliminado`), `ProductVariant` (presentaciones), `ModifierGroup`/`ModifierOption` (adiciones) y `Tag`; cada uno con su `uuid` público |
| `catalog` | `opciones.py` | Adiciones y presentaciones: valida lo elegido y **calcula nombre y precio en el servidor** (`aplicar`) |
| `catalog` | `legacy.py` | La carta en la forma vieja por posiciones (`opciones`) y `linea_desde_v1`: traduce una línea con los id de la carta (`product`, `variant`, `options`) a esa forma |
| `catalog` | `formato.py` | Formato Cloudin de la carta: `extraer`, `leer_fuente`, `normalizar`, `importar` (aditivo), `exportar` |
| `catalog` | `forms.py` | `ProductoForm`: el dueño o el administrador cambian todo (nombre, precio, categoría, foto, descripción, adiciones, observación); cada cambio queda en el historial |
| `catalog` | `management/commands/importar_menu.py` | Importar la carta desde consola |
| `business` | `models.py` | `RestaurantSettings` (marca, contacto, redes, servicios, `menu_version`) y `OpeningHours` (horario) |
| `public_menu` | `views.py`, `serializers.py` | La carta pública `cloudin.menu/v1` (`/api/public/<slug>/menu/`): sin llave, CORS abierto, `ETag` |
| `importer` | `services.py`, `semilla.py` | Importa la semilla `menu.seed.json` de un menú digital (`import_menu`) |
| `dining` | `models.py` | `Table` (número, puestos, zona y token del QR) |
| `dining` | `qr.py` | El enlace del QR de cada mesa (`enlace_de_mesa`: `menu_page?mesa=<token>`) y sus PNG, SVG y PDF |
| `orders` | `models.py` | `TableSession` (la cuenta: abierta = mesa ocupada; `descuento`), `Order` (comanda: estado, origen, mesero, `impresiones`), `OrderItem` (`opciones`), `TableDraft` (carrito compartido del QR) y `NovedadCuenta` |
| `orders` | `novedades.py` | **Única puerta** para anular, dar cortesía, registrar devoluciones y descuentos (motivo + autorización de admin). Deja `NovedadCuenta` |
| `waiters` | `models.py` | `Mesero` (clave en hash + copia Fernet `clave_cifrada`) |
| `waiters` | `views.py` | La app de la tablet: login propio, `api_mesas`, `api_menu`, `api_pedido` |
| `tenants` | `models.py` → `AceptacionLegal` | Constancia de que un usuario aceptó términos y privacidad (por versión) |
| `archivos` | `almacen.py`, `views.py` | Con `FOTOS_EN_LA_BASE=1` (plan gratis sin R2), las fotos subidas se guardan en la base de control (`Archivo`) y se sirven en `/media/` con caché de un año. Es app compartida (`SHARED_APPS`) |

### 4.4 `apps/api` — la API REST (`/api/v1/`)

| Archivo | Qué hace |
|---|---|
| `views.py` | Endpoints del QR (`menu/`, `tables/<token>/…`), del sitio web (`site/…`, con `X-API-Key`) y del panel (`staff/…`, con sesión). `pedidos_del_menu_apagados` decide si el QR puede pedir |
| `mesa_views.py` | Mesa con QR: **carrito compartido en el servidor**, estado de la mesa (con `recibe_pedidos`), aviso y enviar. Acepta líneas con los id de la carta |
| `catalogo_views.py` | La carta v1 del panel por UUID (`staff/catalog/…`), ajustes del negocio, mesas y QR |
| `serializers.py` | Menú, mesas, pedidos y cuentas; valida las líneas (`linea_desde_v1` y `catalog.opciones.aplicar`) |
| `permissions.py` | `IsTenantStaff` (usuario del restaurante), `IsTenantAdminParaEscribir` y los permisos de la carta |
| `limites.py` | Topes por IP de la API pública y `precio_seguro` para las líneas armadas en el sitio |
| `avisos.py` | `staff/avisos/` (pedidos nuevos para la campana), anular/cortesía/devolución por línea y descuento de cuenta |
| `urls.py` | Índice de todas las rutas de la API |

### 4.5 `apps/panel` — las pantallas del restaurante (`/panel/`)

| Archivo | Pantallas |
|---|---|
| `views.py` | Decorador `panel_view` (acceso, legal, soporte), Inicio, mesas, detalle de mesa, cocina, mensajes, configuración, QR de mesas e impresiones (comanda y precuenta) |
| `duenio.py` | Las pantallas del dueño: Inicio del menú, bienvenida, Mi menú, producto, Personalizar, Códigos QR («Mesas y QR») y Cuenta |
| `menu.py` | Producto nuevo, editar, eliminar e importar la carta del sitio |
| `meseros.py` | Modo de servicio, cuentas de mesero y ver la clave de un mesero |
| `seguridad.py` | Login con topes, recuperar contraseña y modo soporte del superusuario |
| `legal.py` | Términos, privacidad, política de datos por restaurante y la pantalla de aceptar |
| `templatetags/cloudin.py` | Filtro `pesos` (miles con punto) |
| `urls.py` | El índice de todas las rutas del panel — **empieza a leer aquí** |

### 4.6 `apps/master` — panel maestro (`/master/`)

`views.py` y `forms.py`: alta de restaurantes (crea la base, la migra, genera la
API key y el usuario admin con su contraseña), alta de usuarios del panel, ver y cambiar
contraseñas, activar o desactivar un restaurante y rotar su API key. Solo
superusuario.

### 4.7 Plantillas

| Archivo | Qué es |
|---|---|
| `templates/base.html` | **El sistema de diseño**: tokens de color, `.card`, `.btn`, `.pill`, `.tabla-wrap`, `.subnav`, `.barra`, y los ayudantes de impresión (`botonImprimir`, `marcarImpreso`) |
| `templates/panel/_base.html` | Cáscara del panel: barra lateral, contador de mensajes y campana de pedidos nuevos |
| `templates/panel/_form_page.html` | Tarjeta centrada para pantallas de alta y edición |
| `templates/panel/_auth_base.html` | Login y recuperación de contraseña |
| `templates/panel/print_order.html`, `print_bill.html` | Tirillas de 80 mm: comanda y precuenta («Documento no válido como factura») |
| `templates/panel/duenio/*.html` | Pantallas del dueño: inicio, mi menú, producto, personalizar, mesas y QR, cuenta |
| `templates/mesero/app.html` | La app del mesero completa (HTML, CSS y JS en un archivo) |
| `templates/master/*.html` | Panel maestro |
| `templates/legal/*.html` | Términos, privacidad, datos del restaurante y aceptación |
| `templates/admin/base_site.html` | Django Admin reestilizado con la paleta |

### 4.8 Apps retiradas

`billing` (facturación con Factus), `shifts` (turno de caja), `inventory`,
`reservas`, `staffing` (reloj de empleados) y `control` (Cloudin Control) se
quitaron el 26 de septiembre de 2026, junto con las propinas y la analítica de
ventas. De cada una quedan:

- `apps.py` (su nombre dice «(retirada)»), un `models.py` mínimo (en `reservas`,
  `nuevo_codigo()`, porque su migración 0001 lo usa como valor por defecto) y sus
  **migraciones**. La última, `…_retirar_modulos`, borra sus tablas; también hay
  `…_retirar_modulos` en `orders`, `dining` y `waiters` para los campos que
  apuntaban a ellas (turno, reserva, propina, empleado, `reservable`).
- Siguen al final de `INSTALLED_APPS` y en `TENANT_APPS`: así `migrate` y
  `migrate_tenants` pueden correr esas migraciones en las bases que ya existen.

Reglas:

- **No les agregues código** ni las importes desde otras apps.
- Cuando todas las bases (tu PC y el servidor) hayan migrado, se pueden borrar del
  todo: la carpeta, su entrada en `INSTALLED_APPS` y `TENANT_APPS`, y las
  dependencias que otras migraciones (`orders`, `waiters`, `dining`…) tienen hacia
  ellas. Es un cambio delicado: hazlo aparte y pruébalo con una base recién creada y
  con una copia de una base vieja.
- Los textos legales (`templates/legal/`) todavía las mencionan: los actualiza el
  dueño con su abogado (y se sube `LEGAL_VERSION`).

---

## 5. Reglas del proyecto (no las cambies sin permiso)

1. **No hay turno de caja: los pedidos entran a cualquier hora.** (Antes era «sin
   turno abierto no funciona nada»; el dueño lo cambió el 26-09-2026.) La mesa se
   **ocupa sola** con el primer pedido (se abre su `TableSession`) y queda **libre**
   cuando el restaurante cierra la cuenta; Mensajes, Cocina y Mesas muestran los
   pedidos de las cuentas abiertas. No hay reservas.
2. **El precio lo calcula siempre el servidor**, nunca el cliente ni la tablet.
   Los pedidos viajan con los id de la carta (`product` + `variant` + `options`, la
   forma del menú digital) o con `product_id` + `opciones` (por posición), y
   `catalog/opciones.py` arma el nombre y el precio.
3. **La carta: el panel manda.** Los menús digitales leen
   `GET /api/public/<slug>/menu/`; un sitio que ya tiene su carta la publica en
   `cloudin-menu.json`, el panel la importa de forma **aditiva** (nunca pisa, nunca
   borra, nunca revive eliminados) y el sitio lee `GET /api/v1/menu/?formato=cloudin`.
4. *(Retirada con el inventario.)*
5. **Borrado suave.** Un producto vendido no se borra: `eliminado=True`. Una mesa
   con historial se desactiva. Nunca pierdas historial.
6. **Dinero en plantillas con el filtro `pesos`** (`{% load cloudin %}`). Números
   dentro de JS o de un `<input type=number>` con `{{ x|unlocalize }}`
   (`{% load l10n %}`): en español Django escribe `1000,0000` y rompe el script en
   silencio. **No** actives `USE_THOUSAND_SEPARATOR` global: dañaría los inputs.
7. **Las mesas se identifican solo por número.** Nada de "Terraza 1".
8. **Marca en todo.** Paleta: fondo `#13151C`, naranja `#F77A27`, blanco cálido
   `#E9ECF3`. Cualquier pantalla nueva lleva logo, paleta y favicon, y usa las
   clases de `templates/base.html`; no agregues estilos sueltos.
9. **Las tirillas se imprimen en un iframe oculto:** la vista necesita
   `@xframe_options_sameorigin`, el iframe debe ser de 1px (no 0) y la URL debe
   cambiar en cada impresión.
10. **Las contraseñas de los clientes se pueden ver.** Hash de Django para entrar,
    más una copia cifrada con Fernet para mostrarla (`CREDENTIAL_KEY` en el
    `.env`). Es un requisito del dueño: **no propongas volver a solo-hash.**
11. *(Retirada con las propinas.)*
12. **Nada de datos de restaurantes de ejemplo** salvo que el dueño lo pida.
13. **Nunca la palabra «robo»** (ni «hurto», ni acusaciones) en lo que ve el
    restaurante: se dice «diferencia», «situación a revisar». (Nació con Cloudin
    Control, que se retiró; sigue valiendo para las novedades.)
14. **Anular, cortesía, devolución y descuento solo por `apps/orders/novedades.py`**:
    motivo obligatorio y autorización (admin directo; cajero con la clave de un
    admin). Lo no cobrado vale 0 y queda en `NovedadCuenta`.
15. *(Retirada con Cloudin Reservas.)*
16. **Términos y privacidad se aceptan una vez por versión** (`LEGAL_VERSION`); sin
    eso `panel_view` manda a `/legal/aceptar/`. Si cambias los textos de fondo,
    sube la versión.
17. **Tema claro y oscuro**: usa siempre los tokens (`var(--surface)`, `--text`,
    pasteles `--lavanda`…). Un color fijo claro en texto se pierde en el tema claro.
    En Chart.js lee los colores con `colorTema("brand")` y repinta en el evento
    `cambio-tema`.
18. **Seguridad (no la aflojes).**
    - Todo texto que venga de clientes (nombres, notas, platos) se pinta con
      `escHTML()` (está en `base.html`); nunca con `${...}` directo en `innerHTML`.
    - Login con tope de intentos (`apps/panel/seguridad.py`: 5 por usuario, 20 por
      IP, 15 min).
    - El superusuario entra a un restaurante solo en **modo soporte**: confirma su
      contraseña, se ve la franja amarilla y vence (1 h sin uso, 8 h máximo).
    - La API pública tiene topes por IP (`apps/api/limites.py`), y una línea sin
      `product_id` nunca se cobra por debajo del precio del panel (`precio_seguro`).
    - La llave `ck_…` va dentro del JavaScript del menú digital: es pública. Lo que
      protege una mesa es el **token** de su QR. Las rutas `/api/v1/site/…` piden
      por número de mesa: nunca las uses en una página pública.
    - Escribir en carta, mesas y categorías por la API es solo del admin
      (`IsTenantAdminParaEscribir`); el precio solo se cambia en el panel.
    - Redirecciones con `volver_seguro`. Cabeceras CSP y no-store en
      `config/seguridad.py`. En producción, `settings.py` exige `SECRET_KEY`,
      `ALLOWED_HOSTS` y `CREDENTIAL_KEY`.
19. *(Retirada con el turno de caja.)*
20. *(Retirada con Cloudin Reservas.)*
21. **Cloudin no sirve un menú propio.** El menú de cada restaurante es un sitio
    aparte (Cloudflare Pages). Su dirección va en `Tenant.menu_page`: con ella se
    arman los QR (`menu_page?mesa=<token>`) y se autoriza por CORS, junto con
    `site_url` y `allowed_origins`. Guía: `GUIA-MENU-DIGITAL.md`.
22. **Todos los restaurantes tienen Cloudin completo; no hay planes** (lo decidió el
    dueño el 27 de septiembre de 2026). Cómo se toman los pedidos son dos
    interruptores que cambia el administrador del restaurante en su panel:
    `Tenant.pedidos_qr` (Inicio, Códigos QR y Meseros; `panel:pedidos-qr`) y
    `Tenant.app_meseros` (Meseros). Con `pedidos_qr` apagado el estado de la mesa trae
    `recibe_pedidos: false` y los envíos responden `403 sin_pedidos`
    (`apps/api/views.py`, `pedidos_del_menu_apagados`).
23. **Las apps retiradas no se tocan** (4.8): no les agregues código ni las borres
    sin migrar antes todas las bases.

---

## 6. Dónde empezar a modificar, según lo que te pidan

### Cambiar algo de una pantalla del panel
1. Busca la ruta en `apps/panel/urls.py`.
2. Esa ruta apunta a una función en `views.py`, `duenio.py`, `menu.py`,
   `meseros.py`, `seguridad.py` o `legal.py`.
3. La función renderiza una plantilla de `templates/panel/`.
4. Si el dato no existe, míralo en el modelo y pásalo por el contexto. No calcules
   cosas dentro de la plantilla.

### Agregar un campo a un modelo del restaurante
1. Edita el `models.py` de la app (`catalog`, `orders`, `dining`…).
2. `makemigrations <app>` → `migrate` → **`migrate_tenants`**.
3. Si debe salir en la API, agrégalo a `apps/api/serializers.py`.
4. Si debe verse en el panel, al formulario de esa app y a la plantilla.

### Agregar un endpoint a la API
1. Escribe la vista en `apps/api/views.py`, o en `mesa_views.py` si cuelga del
   token de la mesa.
2. Regístrala en `apps/api/urls.py` respetando el prefijo: `menu/`, `tables/` y
   `mesa/` son del QR, `site/` del sitio web, `staff/` del panel.
3. Si es pública, ponle tope por IP con `permitido` (`apps/api/limites.py`); si crea
   pedidos desde el QR, respeta `pedidos_del_menu_apagados`. Si es del panel,
   `IsTenantStaff` (o `IsTenantAdminParaEscribir` si escribe la carta o las mesas).
4. Documenta el endpoint en `GUIA-MENU-DIGITAL.md` si lo usa el menú digital, o en
   `INTEGRACION-SITIO-WEB.md` si lo usa un sitio o una tablet.

### Tocar la app del mesero
Todo vive en `apps/waiters/views.py` (los endpoints `api_*`) y
`templates/mesero/app.html` (la interfaz completa). El login y la sesión están
atados al slug del restaurante y a una huella de la contraseña, para que cambiar
la clave saque al mesero de inmediato.

### Tocar el menú digital o el pedido desde la mesa
- La carta pública: `apps/public_menu/serializers.py`. Es un contrato
  (`cloudin.menu/v1`): puedes **agregar** campos, nunca quitar ni cambiar los que hay,
  porque hay menús publicados que los leen.
- El carrito y el envío: `apps/api/mesa_views.py`; la traducción de las líneas:
  `apps/catalog/legacy.py`; el precio: `apps/catalog/opciones.py`.
- La implementación de referencia: `client/example/carrito.js`. Si cambias la API,
  actualiza `carrito.js`, `GUIA-MENU-DIGITAL.md` y
  `tests/test_pedidos_menu_digital.py` en el mismo cambio.
- El runtime (`static/cloudin-menu.v1.js`) se edita en `static/src/` y se regenera
  con `python manage.py build_runtime` (tope de 8 KB).

### Si te piden volver a facturar, llevar inventario o tomar reservas
Esas apps se retiraron (4.8). No las revivas en su lugar: es una decisión del dueño
y va como módulo nuevo, con su propio diseño, sus migraciones y sus pruebas.

### Crear un módulo nuevo
1. `apps/<nombre>/` con `apps.py`, `models.py` y lo que necesite.
2. Agrégala a `INSTALLED_APPS` en `config/settings.py`.
3. Agrégala a `TENANT_APPS` en `apps/tenants/routers.py` si sus datos son de cada
   restaurante (casi siempre lo son), o a `SHARED_APPS` si son globales.
4. `makemigrations` → `migrate` → `migrate_tenants`.
5. Pantallas en `apps/panel/<nombre>.py`, rutas en `apps/panel/urls.py` y
   plantillas que extiendan `panel/_base.html`.

---

## 7. Cómo probar

Hay una suite de **pytest** en `tests/` (con `conftest.py` en la raíz). Crea bases
temporales: no toca las bases reales.

```bash
C:\Users\<usuario>\.venvs\cloudin\Scripts\python -m pytest
```

```bash
C:\Users\<usuario>\.venvs\cloudin\Scripts\ruff check .
```

- Instala antes `requirements-dev.txt` (pytest, pytest-django, ruff, Playwright).
- Necesita una `CREDENTIAL_KEY` válida en el `.env` (la prueba de invitaciones la usa).
- Las pruebas de navegador (`tests/test_panel_navegador.py`) usan Playwright con
  Edge; si no está, usan el Chromium de la variable `CLOUDIN_CHROMIUM`; si no hay
  ninguno, se saltan.
- `tests/test_pedidos_menu_digital.py` cubre el menú digital: carta pública,
  carrito compartido, pedido directo, CORS, pedidos por QR apagados, y el comando
  de QR.
- Antes de subir: `python manage.py makemigrations --check --dry-run` (no debe
  quedar ninguna migración sin crear).

Para verificar un cambio a mano, la ruta corta es: crear las mesas (Códigos QR) →
abrir el menú de ejemplo (`client/example/`) con `?mesa=<token>` → pedir → verlo en
Mensajes y Cocina con la mesa ocupada → cerrar la cuenta → la mesa queda libre.
Los pasos exactos están en `GUIA-MENU-DIGITAL.md` §11.

Cuando escribas un script de prueba, ponlo fuera del proyecto, úsalo con
`tenant_context` y prefiere transacciones con rollback para no ensuciar los datos
reales del restaurante del dueño.

---

## 8. Trampas conocidas (ya costaron tiempo una vez)

- **Olvidar `migrate_tenants`** después de migrar: el panel revienta con columnas
  que no existen.
- **Cambiar el `.env` sin reiniciar** el servidor: Django sigue con los valores
  viejos en memoria.
- **Números localizados**: `{{ x }}` dentro de JS imprime `1000,0000`. Usa
  `unlocalize`.
- **Heredocs de shell con comillas invertidas** dentro: rompen el comando. Escribe
  el archivo con un script o con la herramienta de escritura del editor.
- **Los archivos del proyecto usan saltos de línea CRLF.** Si generas archivos con
  Python, respeta esa convención.
- **El proyecto vive dentro de OneDrive**: no metas entornos virtuales ni
  `node_modules` en la carpeta; se sincronizarían miles de archivos.
- **El sitio de Cultura Brisket está conectado a este panel.** No publiques
  cambios de ese sitio sin permiso explícito del dueño.
- En el emulador móvil de algunos navegadores automatizados, los clics de la app
  del mesero llegan a coordenadas equivocadas; usa el preset de tablet.
- **`DATABASE_URL` en la terminal apunta a producción.** Si existe, Django deja
  SQLite y usa ese Postgres (base de control y restaurantes). Úsala solo a
  propósito para correr un comando en el servidor, y cierra la terminal después.
- **El disco del servidor se borra** cada vez que el contenedor se duerme (en Render
  y en Cloudflare): nada que deba durar se guarda en archivos locales. Datos →
  Postgres; fotos → R2, o la base con `FOTOS_EN_LA_BASE=1` (plan gratis).
- **La IP del cliente sale de `ip_de`** (`apps/panel/seguridad.py`): primero
  `CF-Connecting-IP`, que el cliente no puede falsear. No leas `X-Forwarded-For` a
  mano: Render solo le agrega al final, y la primera la puede escribir cualquiera.
- **La caché de Django vive en la memoria del único contenedor** (topes de login y
  de pedidos, llaves anti-duplicado del mesero, carta pública armada). No subas
  `max_instances` ni los `--workers` de gunicorn sin mover antes esa caché a algo
  compartido.
- **Apps retiradas en `INSTALLED_APPS`.** Parecen código muerto, pero sin ellas
  Django no puede migrar las bases viejas (4.8).
- **Probar un menú digital contra el Cloudin local:** sirve la página también desde
  `localhost` o `127.0.0.1`. Chrome no deja que una página publicada en internet le
  hable a `localhost`, y los pedidos solo salen de orígenes registrados (`menu_page`
  o `allowed_origins`, con el puerto exacto).

---

## 9. Estado actual y qué sigue

**Funcionando y verificado:** multi-tenancy, panel maestro, panel del restaurante
(Inicio, Mesas, Mensajes, Cocina, Mi menú, Personalizar, Códigos QR, Meseros,
Configuración) con tema claro y oscuro, carta pública `cloudin.menu/v1` con el
runtime de los menús, pedidos desde el menú digital con carrito compartido por mesa
(probado de punta a punta en el navegador con la carta real de Cultura Brisket),
mesas que se ocupan solas y se liberan al cerrar la cuenta, app de meseros,
anulaciones/cortesías/devoluciones/descuentos con autorización, precuenta impresa,
aceptación de términos y privacidad, recuperación de contraseña por correo, y el
montaje para Cloudflare Containers.

**Lo que falta, en orden de importancia:**

1. **Desplegar el panel en un servidor público.** Cloudflare Pages no sirve para
   Django. El código quedó listo para dos servidores con el mismo `Dockerfile`:
   **Render gratis** (`render.yaml`, fotos en R2 o en la base:
   `DESPLIEGUE-GRATIS.md`), que es el camino mientras no haya presupuesto, y
   **Cloudflare Containers** con el plan pago (Worker + contenedor, fotos en R2:
   `DESPLIEGUE-CLOUDFLARE.md`). Falta crear las cuentas y cargar los secretos. El
   bucket `cloudin-fotos` de R2 ya existe.
2. **El primer menú digital en Cloudflare Pages** con pedidos por QR:
   `GUIA-MENU-DIGITAL.md`.
3. **Actualizar los textos legales** (todavía describen los módulos retirados) con
   el abogado, y subir `LEGAL_VERSION`.
4. Un interruptor para **pausar los pedidos** fuera de horario (hoy entran siempre).
5. Rotar el token de una mesa desde el panel (hoy solo por consola).
6. Impresión automática por red (necesita un agente en la red local del
   restaurante).

---

## 10. Cómo trabaja el dueño (para que no choquen)

- Prefiere **avanzar por pasos y verificar cada uno** antes de seguir. No entregues
  diez cambios juntos sin mostrar que el primero funciona.
- Quiere que le **pregunten cuando la decisión es suya**: precios, textos que ve el
  cliente, tocar el sitio de un restaurante, publicar algo.
- Todo en **español**, incluidos nombres de funciones, comentarios y mensajes de la
  interfaz.
- **No inventes credenciales ni las adivines.** Si hace falta una contraseña,
  pídesela o propón regenerarla.
- Cualquier decisión nueva que cambie una regla de este archivo: **actualiza este
  archivo** en el mismo cambio.
