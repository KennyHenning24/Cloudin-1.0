# Cloudin — contexto para Codex (o cualquier agente que siga programando)

> Léeme completo antes de tocar una línea. Este archivo explica qué es el
> proyecto, cómo montarlo en un computador que no tiene **nada** instalado, qué
> hace cada archivo, dónde se empieza a modificar según lo que se pida, y las
> reglas que el dueño ya decidió y que no se deben cambiar por cuenta propia.
>
> Escrito el 15 de septiembre de 2026. Autor del código: Juan.
> Todo el código, los comentarios y la interfaz están **en español**. Sigue así.

---

## 0. Orden de lectura

| Archivo | Para qué |
|---|---|
| **Este archivo** | Montaje, mapa del código, reglas y recetas de cambio |
| `README.md` | Documentación técnica del producto, pantalla por pantalla |
| `CONECTAR-MENU-A-CLOUDIN.md` | Cómo el sitio web de un restaurante le entrega su carta al panel |
| `INTEGRACION-SITIO-WEB.md` | API para quien construya el sitio web del restaurante |
| `DESPLIEGUE-CLOUDFLARE.md` | Cómo corre en Cloudflare (Containers, Postgres, R2), por qué no en Pages y el día a día del despliegue |
| `..\Cloudin-para-restaurantes.md` | Qué problema resuelve el producto (material de venta) |
| `..\cloudin-arquitectura.md` | Plan original por fases |
| `..\especificacion-inventario-cloudin.md` | Especificación del módulo de inventario |

---

## 1. Qué es Cloudin

Software de gestión para restaurantes en Colombia. Un solo backend Django sirve a
todos los restaurantes (multi-tenant) y cubre: carta digital, pedidos por QR, app
de meseros en tablet, pantalla de cocina, mesas y cuentas, **facturación
electrónica DIAN** (vía Factus), turno de caja con informe de cierre, propinas,
inventario con recetas y costeo, reloj de empleados y analítica de ventas.

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

> **Aviso importante: hoy la carpeta NO es un repositorio Git.** Antes del primer
> cambio corre `git init`, haz un commit inicial con todo el estado actual y
> trabaja en ramas. Sin eso no hay cómo deshacer un error. El `.gitignore` ya
> existe y excluye `.env`, `*.sqlite3`, `tenant_dbs/`, `media/`, `staticfiles/`,
> `qrcodes/` y `__pycache__/`.

### 2.2 Opcional, según lo que vayas a hacer

| Herramienta | Cuándo la necesitas |
|---|---|
| **Node.js 18+** | Solo para servir o tocar el sitio web de un restaurante (`npx http-server`) y correr `generar-cloudin-menu.js` de Cultura Brisket |
| **PostgreSQL + `psycopg[binary]`** | Solo para producción (`DATABASE_URL`, ver `DESPLIEGUE-CLOUDFLARE.md`). En local se usa SQLite y no hay nada que instalar. `requirements-produccion.txt` trae lo del servidor |
| **Docker / `npx wrangler`** | Solo para probar la imagen del servidor o el Worker de Cloudflare en local. El despliegue normal lo hace Cloudflare en cada push a `main` |
| **Playwright** | Solo para capturas automáticas o generar guías en PDF (`pip install playwright`) |
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
| `FACTUS_*` | credenciales de sandbox | Sin ellas la facturación usa el proveedor simulado |

> **Después de tocar el `.env` hay que reiniciar el servidor.** Django lo lee solo
> al arrancar. Ya pasó una vez: una factura quedó en contingencia porque el
> proceso tenía credenciales viejas en memoria.

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
| `http://localhost:8000/panel/login/?tenant=<slug>` | Panel del restaurante | Admin o cajero del restaurante |
| `http://localhost:8000/mesero/<slug>/` | App del mesero (PWA para tablet) | Meseros, con su propia clave |
| `http://localhost:8000/admin/` | Django Admin (edición cruda) | Superusuario |
| `http://localhost:8000/api/v1/...` | API REST | Sitio web (X-API-Key) y panel (sesión) |

En local el restaurante se elige con `?tenant=<slug>`; en producción sale del
subdominio. `.claude/launch.json` ya trae la configuración para levantar el
servidor en el puerto 8000.

---

## 3. La arquitectura en cinco minutos

**Una sola aplicación Django, N bases de datos.**

```
control.sqlite3                     -> restaurantes, usuarios de Django, sesiones, admin
tenant_dbs/cloudin_<slug>.sqlite3   -> menú, mesas, pedidos, facturas, inventario,
                                       empleados, turnos y meseros de ESE restaurante
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
   `TENANT_APPS` (`catalog`, `dining`, `orders`, `billing`, `staffing`, `shifts`,
   `inventory`, `waiters`) van a la base del restaurante.

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
| `config/settings.py` | Bases de datos, apps, sesiones de 60 días, correo, CORS, media, Factus |
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

### 4.2 `apps/tenants` — multi-tenancy y alta de clientes (base de control)

| Archivo | Qué hace |
|---|---|
| `models.py` | `Tenant` (slug, api_key, `site_url`, `modo_servicio`, `menu_fuente`, activo) y `TenantMembership` (usuario ↔ restaurante, con rol y `password_cifrada`) |
| `middleware.py` | Resuelve el restaurante de cada petición |
| `context.py` | Restaurante activo por hilo; `tenant_context` |
| `db.py` | Alta en caliente de la conexión de un restaurante |
| `routers.py` | Reparte modelos entre la base de control y la del restaurante |
| `provisioning.py` | Crea la base del restaurante y le corre las migraciones |
| `services.py` | Alta de restaurantes y usuarios (lo usan el panel maestro y el comando) |
| `crypto.py` | Cifrado Fernet reversible de las contraseñas que el maestro muestra |
| `cors.py` | Permite CORS **solo** al `site_url` del restaurante de la petición |
| `admin.py` | Django Admin de tenants |
| `management/commands/create_tenant.py` | Alta desde consola |
| `management/commands/migrate_tenants.py` | Migra todas las bases de restaurante |
| `management/commands/tenant_qr.py` | Genera los PNG de los QR de mesa |

### 4.3 Modelos y lógica del restaurante

| App | Archivo | Responsabilidad |
|---|---|---|
| `catalog` | `models.py` | `Category`, `Product` (precio, `imagen`, `opciones` JSON, `permite_observacion`, `clave_externa`, `eliminado`) |
| `catalog` | `opciones.py` | Toppings y variantes: valida grupos y **calcula nombre y precio en el servidor** (`aplicar`) |
| `catalog` | `formato.py` | Formato Cloudin de la carta: `extraer`, `leer_fuente`, `normalizar`, `importar` (aditivo), `exportar` |
| `catalog` | `forms.py` | `ProductoForm`: el cliente edita foto, descripción, toppings y observación; nombre, precio y categoría solo el superusuario |
| `catalog` | `management/commands/importar_menu.py` | Importar la carta desde consola |
| `dining` | `models.py` | `Table` (número y token del QR) |
| `orders` | `models.py` | `TableSession` (cuenta de la mesa, `propina`, `propina_medio`), `Order` (comanda: estado, mesero, `impresiones`), `OrderItem` (`opciones`), `TableDraft` (carrito compartido del QR) |
| `billing` | `models.py` | `EmpresaFiscal`, `ResolucionNumeracion`, `ClienteFiscal`, `Impuesto`, `DocumentoFiscal`, `LogAuditoria` |
| `billing` | `taxes.py` | Motor tributario: los precios de carta **incluyen** impuesto, se extrae la base |
| `billing` | `services.py` | Flujo de facturar una cuenta cerrada; contingencia si el proveedor no responde |
| `billing` | `providers/base.py` | Interfaz que debe cumplir cualquier proveedor tecnológico |
| `billing` | `providers/factus.py` | Factus API v2: OAuth, armado de la factura, traducción de errores |
| `billing` | `providers/simulado.py` | Proveedor falso para desarrollo (marca las facturas como simuladas) |
| `billing` | `tests/test_factus.py` | Pruebas del adaptador, sin red |
| `shifts` | `models.py` | `TurnoCaja`: apertura, cierre, `resumen` congelado, efectivo esperado, propinas pagadas |
| `shifts` | `services.py` | `abrir_turno`, `cerrar_turno`, `turno_actual`, `exigir_turno`, `SinTurno`, `resumen_turno` |
| `shifts` | `propinas.py` | Registrar la propina y repartirla por horas marcadas |
| `shifts` | `context_processors.py` | El turno abierto disponible en todas las plantillas |
| `staffing` | `models.py` | `Empleado` y `Turno` (jornada de una persona, marcación por código) |
| `inventory` | `models.py` | Insumos, existencias, movimientos (kardex), recetas y subrecetas, proveedores, compras, conteos |
| `inventory` | `services.py` | **Única puerta** para mover stock: entradas, salidas, costo promedio ponderado, `descontar_inventario` al facturar, reportes |
| `waiters` | `models.py` | `Mesero` (clave en hash + copia Fernet `clave_cifrada`) |
| `waiters` | `views.py` | La app de la tablet: login propio, `api_mesas`, `api_menu`, `api_pedido` |
| `orders` | `novedades.py` | **Única puerta** para anular, dar cortesía, registrar devoluciones y descuentos (motivo + autorización de admin). Deja `NovedadCuenta` |
| `reservas` | `models.py` | `Cliente` (por teléfono), `AjustesReservas`, `ServicioReserva` (horarios «mesa» o «día»), `BloqueoFecha`, `Reserva` (estados `pending`→`confirmed`→`arrived`→`seated`→`completed`, o `cancelled`/`no_show`) |
| `reservas` | `services.py` | El motor: calendario, horas libres, asignación de mesa, sugerencias, crear/confirmar/llegó/sentar/completar, WhatsApp e historial del cliente |
| `reservas` | `forms.py` | Formularios del panel (ajustes, horarios, bloqueos, reserva por teléfono) |
| `control` | `models.py` | `AlertaControl` (tabla `control_alert`), `AjustesControl` (sensibilidad), `Analisis` |
| `control` | `detectores.py` | Un detector por tema; devuelven alertas como diccionarios con su **huella** |
| `control` | `services.py` | `analizar` (guarda sin repetir), `fugas` (el Detector de fugas), `resumen_alertas` |
| `control` | `recomendaciones.py` | Ranking de platos, ingeniería de menú, combos y las tarjetas de recomendación |
| `tenants` | `models.py` → `AceptacionLegal` | Constancia de que un usuario aceptó términos y privacidad (por versión) |

### 4.4 `apps/api` — la API REST (`/api/v1/`)

| Archivo | Qué hace |
|---|---|
| `views.py` | Casi todo: endpoints del QR (`menu/`, `tables/<token>/…`), del sitio web (`site/…`, con `X-API-Key`) y del panel (`staff/…`, con sesión) |
| `mesa_views.py` | Mesa con QR: carta, **carrito compartido en el servidor**, estado del pedido, enviar |
| `serializers.py` | Menú, mesas, pedidos y cuentas; valida `opciones` con `catalog.opciones.aplicar` |
| `permissions.py` | `IsTenantStaff`: usuario del restaurante y, para métodos que escriben, **turno abierto** |
| `analitica.py` | Datos del tablero de ventas |
| `reservas_views.py` | API pública de reservas (X-API-Key, **sin** turno): configuración, días, horas, crear, detalle, cancelar |
| `avisos.py` | `staff/avisos/` (contadores de la campana), anular/cortesía/devolución por línea y descuento de cuenta |
| `urls.py` | Índice de todas las rutas de la API |

### 4.5 `apps/panel` — las pantallas del restaurante (`/panel/`)

| Archivo | Pantallas |
|---|---|
| `views.py` | Decorador `panel_view`, inicio, mesas, detalle de mesa, cocina, mensajes, configuración, QR de mesas, ventas, facturación, cerrar y facturar, y las impresiones |
| `turnos.py` | Abrir, cerrar, detalle e impresión del turno |
| `propinas.py` | Sección de propinas y marcar un turno como entregado |
| `menu.py` | Producto nuevo, editar, eliminar e importar la carta del sitio |
| `meseros.py` | Modo de servicio, cuentas de mesero y ver la clave de un mesero |
| `inventario.py` | Todo el inventario: insumos, compras, proveedores, recetas, conteos y reportes |
| `reservas.py` | Agenda, reserva nueva/detalle/acciones, clientes e historial, horarios y mesas (sin turno) |
| `control.py` | Cloudin Control: detector de fugas, situaciones a revisar, analizar ahora, sensibilidad (sin turno) |
| `legal.py` | Términos, privacidad, política de datos por restaurante y la pantalla de aceptar |
| `templatetags/cloudin.py` | Filtro `pesos` (miles con punto) |
| `urls.py` | El índice de todas las rutas del panel — **empieza a leer aquí** |

### 4.6 `apps/master` — panel maestro (`/master/`)

`views.py` y `forms.py`: alta de restaurantes (crea la base, la migra, genera la
API key y el usuario admin con su contraseña), alta de empleados, ver y cambiar
contraseñas, activar o desactivar un restaurante y rotar su API key. Solo
superusuario.

### 4.7 Plantillas

| Archivo | Qué es |
|---|---|
| `templates/base.html` | **El sistema de diseño**: tokens de color, `.card`, `.btn`, `.pill`, `.tabla-wrap`, `.subnav`, `.barra`, y los ayudantes de impresión (`botonImprimir`, `marcarImpreso`) |
| `templates/panel/_base.html` | Cáscara del panel: barra lateral, estado del turno, contador de mensajes |
| `templates/panel/_form_page.html` | Tarjeta centrada para pantallas de alta y edición |
| `templates/panel/_auth_base.html` | Login y recuperación de contraseña |
| `templates/panel/print_order.html`, `print_bill.html`, `print_factura.html`, `print_turno.html` | Tirillas de 80 mm: comanda, precuenta, **factura legal con QR y CUFE**, informe Z |
| `templates/mesero/app.html` | La app del mesero completa (HTML, CSS y JS en un archivo) |
| `templates/master/*.html` | Panel maestro |
| `templates/legal/*.html` | Términos, privacidad, datos del restaurante y aceptación |
| `templates/panel/reservas*.html`, `reserva_*.html`, `cliente*.html`, `_reservas_nav.html` | Cloudin Reservas |
| `templates/panel/control*.html` | Cloudin Control |
| `templates/panel/_icono_reco.html` | Íconos de las tarjetas de recomendación |
| `templates/admin/base_site.html` | Django Admin reestilizado con la paleta |

---

## 5. Reglas del proyecto (no las cambies sin permiso)

1. **Sin turno abierto no funciona nada.** Es un pedido explícito del dueño.
   `panel_view(requiere_turno=True)` redirige a `/panel/turnos/`; la API del panel
   responde 403 y el QR, el sitio y la app del mesero responden **409 con
   `codigo: "sin_turno"`**. Exentas: las pantallas de turnos y `documento`. El
   turno solo lo abre el administrador a mano.
2. **El precio lo calcula siempre el servidor**, nunca el cliente ni la tablet.
   Los pedidos viajan con `product_id` + `opciones` (por posición) y
   `catalog/opciones.py` arma el nombre y el precio.
3. **La carta: el panel manda.** El sitio publica `cloudin-menu.json`, el panel lo
   importa de forma **aditiva** (nunca pisa, nunca borra, nunca revive eliminados)
   y el sitio lee `GET /api/v1/menu/?formato=cloudin`.
4. **El stock nunca se edita a mano.** Todo entra como `Movimiento` por
   `inventory/services.py`, con autor, costo del momento y motivo. Costeo por
   promedio ponderado.
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
11. **Propina fuera de la factura** (Ley 1935 de 2018), en bolsa común repartida
    por horas marcadas en el reloj.
12. **Nada de datos de restaurantes de ejemplo** salvo que el dueño lo pida.
13. **Nunca la palabra «robo»** (ni «hurto», ni acusaciones) en Cloudin Control: se
    dice «diferencia», «posible fuga», «situación a revisar», «variación detectada».
14. **Anular, cortesía, devolución y descuento solo por `apps/orders/novedades.py`**:
    motivo obligatorio y autorización (admin directo; cajero con la clave de un
    admin). Lo no cobrado vale 0, no se factura y queda en `NovedadCuenta`.
15. **Las reservas no piden turno** (ni la API pública ni la agenda del panel);
    sentar a alguien sí, porque abre la cuenta.
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
    - Escribir en carta, mesas y categorías por la API es solo del admin
      (`IsTenantAdminParaEscribir`); el precio solo se cambia en el panel.
    - Redirecciones con `volver_seguro`. Cabeceras CSP y no-store en
      `config/seguridad.py`. En producción, `settings.py` exige `SECRET_KEY`,
      `ALLOWED_HOSTS` y `CREDENTIAL_KEY`.
19. **La caja arranca con mínimo $10.000** (`BASE_MINIMA` en `apps/shifts/services.py`).
20. **Plano de mesas público** (`GET /api/v1/reservas/mesas/`, `rs.plano_de_mesas`):
    solo número, zona, puestos y estado. Nunca nombres ni datos de la reserva. Tope
    de 180 consultas cada 10 min por IP. La mesa que pide el cliente es una
    preferencia (`rs.mesa_pedida`): si ya no está libre, Cloudin asigna otra.

---

## 6. Dónde empezar a modificar, según lo que te pidan

### Cambiar algo de una pantalla del panel
1. Busca la ruta en `apps/panel/urls.py`.
2. Esa ruta apunta a una función en `views.py`, `turnos.py`, `menu.py`,
   `meseros.py`, `propinas.py` o `inventario.py`.
3. La función renderiza una plantilla de `templates/panel/`.
4. Si el dato no existe, míralo en el modelo y pásalo por el contexto. No calcules
   cosas dentro de la plantilla.

### Agregar un campo a un modelo del restaurante
1. Edita el `models.py` de la app (`catalog`, `orders`, `inventory`…).
2. `makemigrations <app>` → `migrate` → **`migrate_tenants`**.
3. Si debe salir en la API, agrégalo a `apps/api/serializers.py`.
4. Si debe verse en el panel, al formulario de esa app y a la plantilla.

### Agregar un endpoint a la API
1. Escribe la vista en `apps/api/views.py`, o en `mesa_views.py` si cuelga del
   token de la mesa.
2. Regístrala en `apps/api/urls.py` respetando el prefijo: `menu/` y `tables/` son
   del QR, `site/` del sitio web, `staff/` del panel.
3. Si escribe datos, **exige turno abierto**: `IsTenantStaff` para el panel, o
   devuelve 409 `sin_turno` con el ayudante que ya existe para público y sitio.
4. Documenta el endpoint en `INTEGRACION-SITIO-WEB.md` si lo va a usar un sitio.

### Tocar la app del mesero
Todo vive en `apps/waiters/views.py` (los endpoints `api_*`) y
`templates/mesero/app.html` (la interfaz completa). El login y la sesión están
atados al slug del restaurante y a una huella de la contraseña, para que cambiar
la clave saque al mesero de inmediato.

### Tocar facturación
Nunca escribas HTTP suelto contra la DIAN. El flujo es
`panel/views.py` → `billing/services.py` → `billing/providers/<proveedor>.py`.
Con un proveedor real **Cloudin no reserva número**: lo asigna el proveedor al
validar. Un rechazo de la DIAN hay que borrarlo en Factus o bloquea las
siguientes.

### Tocar inventario
Toda entrada o salida pasa por `inventory/services.py`. Ninguna vista escribe
`Existencia.cantidad` ni `Insumo.costo_promedio` directamente.

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

No hay suite de pruebas general; hoy solo existe `apps/billing/tests/test_factus.py`.

```bash
C:\Users\<usuario>\.venvs\cloudin\Scripts\python manage.py test apps.billing.tests.test_factus
```

```bash
C:\Users\<usuario>\.venvs\cloudin\Scripts\python manage.py factus_diagnostico
```

```bash
C:\Users\<usuario>\.venvs\cloudin\Scripts\python manage.py importar_menu --tenant <slug> --revisar
```

```bash
C:\Users\<usuario>\.venvs\cloudin\Scripts\python manage.py control_analizar --todos
```

Además de las pruebas de Factus (incluye el descuento por línea), los cambios grandes
se verificaron con scripts de punta a punta que corren dentro de una transacción y
la deshacen al final (no dejan rastro en los datos reales): motor de reservas (21
comprobaciones), anulaciones/cortesías/descuentos con autorización + factura +
detector de fugas (18) y recorrido de todas las pantallas con la aceptación legal.
Si escribes uno, sigue ese patrón: `transaction.atomic(using=...)` en la base de
control y en la del restaurante, y `set_rollback(True)` al final.

Para verificar un cambio a mano, la ruta corta es: abrir turno → crear una mesa →
tomar un pedido (panel, QR o app del mesero) → cerrar y facturar → cerrar turno y
revisar el informe. **Si algo "no deja hacer nada", casi siempre es que no hay
turno abierto.** Es el comportamiento correcto, no un error.

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
- **El disco del servidor se borra** cada vez que el contenedor se duerme: nada
  que deba durar se guarda en archivos locales (fotos → R2, datos → Postgres).
- **La caché de Django vive en la memoria del único contenedor** (topes de login,
  llaves anti-duplicado del mesero, token de Factus). No subas `max_instances` ni
  los `--workers` de gunicorn sin mover antes esa caché a algo compartido.

---

## 9. Estado actual y qué sigue

**Funcionando y verificado:** multi-tenancy, panel maestro, panel del restaurante
completo (inicio, mesas, cocina, mensajes, ventas, configuración) con tema claro y
oscuro, Cloudin Reservas (sitio web + panel + historial del cliente), Cloudin
Control con detector de fugas, recomendaciones de ventas, anulaciones/cortesías/
descuentos con autorización, aceptación de términos y privacidad, QR por mesa con
carrito compartido, app de meseros, carta conectada al sitio web, facturación
electrónica con Factus (primera factura real aceptada por la DIAN en sandbox el 14
de septiembre de 2026), turno de caja con informe Z, propinas, inventario
completo, reloj de empleados y recuperación de contraseña por correo.

**Lo que falta, en orden de importancia:**

1. **Desplegar el panel en un servidor público.** Es lo único que impide operar de
   verdad. Cloudflare Pages no sirve para Django; el código ya quedó listo para
   **Cloudflare Containers** (Worker + contenedor, Postgres por restaurante con
   `DATABASE_URL`, fotos en R2, WhiteNoise, `preparar_servidor` al arrancar). Falta
   crear las cuentas y cargar los secretos: `DESPLIEGUE-CLOUDFLARE.md`.
2. Habilitación de Factus en producción (hoy sandbox).
3. Nómina electrónica con las horas de `staffing`.
4. Notas crédito y débito, y exportes contables.
5. Traslados entre bodegas y órdenes de compra sugeridas por stock mínimo.
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
