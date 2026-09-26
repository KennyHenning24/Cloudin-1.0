# Cloudin en Cloudflare — despliegue y complicaciones

> Escrito el 26 de septiembre de 2026. Qué se puede y qué no se puede poner en
> Cloudflare, cómo quedó montado y los pasos para verlo funcionando.

## 1. La respuesta corta

**Cloudflare Pages no puede ejecutar Cloudin.** Pages publica archivos estáticos
(HTML, CSS, JS, imágenes) y, como mucho, pequeñas funciones en JavaScript. Cloudin
es un backend **Django (Python)** que renderiza el panel en el servidor, guarda en
bases de datos, crea una base nueva por cada restaurante, recibe fotos y habla con
Factus. Nada de eso corre en Pages.

Lo que sí sirve dentro de Cloudflare es **Cloudflare Containers**: el mismo Django,
sin reescribirlo, dentro de un contenedor Docker que Cloudflare enciende cuando
llega una visita. Delante va un Worker pequeño que recibe el tráfico. Y como el
disco del contenedor se borra, los datos van afuera:

```
 navegador ──► Worker "cloudin" (cloudflare/worker.js)
                  │  pone X-Forwarded-Proto y la IP real del cliente
                  ▼
            Contenedor (Dockerfile): Django + gunicorn, región ENAM
                  │                         │
                  ▼                         ▼
     Postgres (Neon, AWS us-east-1)    Cloudflare R2 (fotos del menú)
     cloudin_control + cloudin_<slug>
```

¿Y Pages? Pages es para **los sitios web de cada restaurante** (como
`client/example/`): son estáticos, cargan `cloudin-menu.v1.js` y leen la API de
Cloudin. Así fue diseñado el producto desde el principio (ver
`CONECTAR-MENU-A-CLOUDIN.md`).

## 2. Las complicaciones, una por una

### 2.1 El backend: Python no corre en Pages

| Opción | ¿Sirve? | Por qué |
|---|---|---|
| Cloudflare Pages | No | Solo estático + Functions en JavaScript. |
| Python Workers (Django sobre Pyodide) | No, sin reescribir mucho | Existe, pero sin hilos, sin disco, sin `psycopg`; el enrutamiento de bases por restaurante (`apps/tenants/db.py`), el contexto por hilo (`context.py`) y el correo SMTP no funcionan ahí. |
| **Cloudflare Containers** | **Sí** | Corre la imagen Docker tal cual. Es lo que quedó montado. |
| Otro hosting (Render, Railway, Fly, un VPS) + Cloudflare delante | Sí | El mismo `Dockerfile` sirve. Alternativa si no se quiere el plan de pago de Workers. |

Containers exige el plan **Workers Paid (5 USD/mes)**; en el plan gratis no existe.

### 2.2 La base de datos: SQLite no sobrevive

- Hoy Cloudin guarda todo en archivos SQLite (`control.sqlite3` y
  `tenant_dbs/cloudin_<slug>.sqlite3`). **El disco del contenedor es efímero**:
  cuando el contenedor se duerme (15 min sin visitas) y vuelve a encender, arranca
  con el disco vacío. Con SQLite se perdería todo cada vez.
- **D1** (la base SQLite de Cloudflare) tampoco encaja: se usa desde un Worker con
  bases declaradas de antemano en la configuración, y Cloudin crea una base nueva
  *en caliente* cada vez que se da de alta un restaurante. Django no tiene un
  conector para D1 desde un contenedor.
- **Solución: Postgres administrado afuera.** Recomendado **Neon** (tiene capa
  gratuita, se duerme cuando no se usa y permite `CREATE DATABASE`, que Cloudin
  necesita para crear `cloudin_<slug>` por restaurante). Alternativa dentro de la
  factura de Cloudflare: PlanetScale Postgres. Supabase encaja peor: está pensado
  para una sola base por proyecto.
- **Latencia.** Django hace decenas de consultas por página, y el alta de un
  restaurante son **626 sentencias SQL** (medido). Por eso el contenedor está
  restringido a la región **ENAM** (este de Norteamérica) y la base debe crearse
  en **AWS us-east-1 (Virginia)**: quedan a pocos milisegundos entre sí. Si la base
  quedara en otra región, cada página tardaría segundos.
- Neon también se duerme: la primera consulta tras varios minutos quietos tarda
  un poco más.

### 2.3 Los datos que ya existen

Los datos de tu PC (Cultura Brisket, El Bembé, usuarios, facturas de sandbox)
están en SQLite. **No se pasan solos a Postgres.** Con el router por restaurante,
`dumpdata`/`loaddata` no alcanza a las bases de restaurante sin un comando a medida.
Recomendación: arrancar el servidor limpio, dar de alta los restaurantes desde
`/master/` y, si hace falta traer el historial, hacerlo en un paso aparte con un
comando de migración escrito para eso. Si se migra, **vaciar las sesiones**
(`django_session`) y regenerar las contraseñas (ver §2.10).

### 2.4 Las fotos del menú

Mismo problema que la base: una foto guardada en el disco del contenedor
desaparece al dormirse. Van a **Cloudflare R2** (compatible con S3) usando
`django-storages`, que ya estaba en `requirements.txt`. Con `DEBUG=0` Django
tampoco sirve `/media/`, así que **sin R2 las fotos no se ven**.

**R2 no está activado en tu cuenta de Cloudflare** (se verificó): hay que activarlo
en el dashboard (tiene capa gratuita; Cloudflare pide un medio de pago).

### 2.5 La caché vive en memoria

Los topes de intentos de login, las llaves que evitan pedidos duplicados de la
tablet del mesero y el token de Factus se guardan en la caché de Django, que es la
memoria del proceso. Por eso hay **un solo contenedor** (`max_instances: 1`) con un
solo proceso de gunicorn con hilos. Si algún día hace falta más de un contenedor,
primero hay que mover esa caché a algo compartido (la base de datos o Redis).

### 2.6 Subdominios por restaurante

El diseño original usa `<slug>.cloudin.app`. En la dirección gratuita
`cloudin.<tu-cuenta>.workers.dev` **no hay subdominios comodín**. No bloquea nada:
el panel identifica al restaurante por el usuario que entra, la API por la
`X-API-Key` y el menú público por la ruta (`/api/public/<slug>/menu/`). Con un
dominio propio en Cloudflare se agrega una ruta `*.cloudin.app/*` al Worker y
`TENANT_BASE_DOMAIN=cloudin.app`.

### 2.7 Arranque en frío

Tras 15 minutos sin visitas el contenedor se apaga (y deja de cobrar). La visita
siguiente espera a que encienda: medido en local, **~3–4 s** (arranque + revisar
migraciones), más lo que tarde Neon en despertar. El **primer** arranque de todos
crea las tablas en Postgres y puede tardar un minuto o dos; el Worker espera hasta
3 minutos. Se puede subir `sleepAfter` en `cloudflare/worker.js` a cambio de más
horas cobradas.

### 2.8 No hay consola en el servidor

No existe un `ssh` cómodo al contenedor para correr `python manage.py …`. Lo que
necesita correr al arrancar ya lo hace solo (`preparar_servidor`: migraciones de
control y de todos los restaurantes, y el superusuario inicial). Para los demás
comandos (`seed_demo_menu`, `importar_menu`, `factus_diagnostico`,
`control_analizar --todos`…) se corren **desde tu PC apuntando a la base de
producción** (§5).

Tampoco hay tareas programadas: `control_analizar --todos` no corre solo, pero el
análisis ya se dispara al abrir Control o el Inicio y al cerrar cada turno. Si hace
falta, se agrega luego un *Cron Trigger* al Worker.

### 2.9 Correo, impresión y lo demás

- **Correo** (recuperar contraseña, invitaciones): hace falta un proveedor SMTP
  (`EMAIL_HOST`…). Sin él, los correos se escriben en el registro del contenedor.
- **Impresión** de tirillas: no cambia, la hace el navegador.
- **Factus**: sale a internet sin problema desde el contenedor.
- **Costo aproximado** con los precios publicados hoy: 5 USD/mes del plan, que
  incluye un cupo de uso; el contenedor `basic` (1 GiB) encendido las 24 horas
  suma unos 7–8 USD más; con el apagado automático y poco tráfico, casi nada. Neon
  y R2 tienen capa gratuita para empezar.

### 2.10 ⚠️ Seguridad: el `.rar` publicado

El repositorio `KennyHenning24/Cloudin-1.0` es **público** y el commit
`7d76200` («Add files via upload») contiene `Clowin.rar`, que traía:

- el `.env` con `SECRET_KEY`, `CREDENTIAL_KEY` y las credenciales **sandbox** de Factus;
- `control.sqlite3` con los usuarios (hashes), las contraseñas guardadas para el
  panel maestro **cifradas con esa misma `CREDENTIAL_KEY`** (o sea, descifrables) y
  80 sesiones;
- las bases de Cultura Brisket y El Bembé (clientes, reservas, meseros, facturas de prueba).

Además, el `README.md` muestra `juan` / `cloudin2026`.

Qué hacer (ya se quitó el `.rar` de la rama, pero **sigue en el historial**):

1. Poner el repositorio en **privado** (GitHub → Settings → General → Danger Zone),
   o reescribir el historial para borrar ese commit (lo decides tú: es irreversible).
2. En producción usar **llaves nuevas**: `SECRET_KEY` y `CREDENTIAL_KEY` nuevas, y
   una contraseña de superusuario nueva. No reutilizar nada del `.env`.
3. Pedir a Factus credenciales nuevas antes de pasar a producción.
4. En tu PC, cambiar las contraseñas de los usuarios y la de `juan`.

## 3. Qué se agregó al proyecto

| Archivo | Para qué |
|---|---|
| `Dockerfile`, `.dockerignore` | La imagen: Python 3.12, dependencias, `collectstatic`, usuario sin privilegios, gunicorn |
| `requirements-produccion.txt` | `psycopg` 3, `gunicorn`, `boto3`, `whitenoise` |
| `cloudflare/worker.js` | El Worker: pasa cada visita al contenedor con `X-Forwarded-Proto` y la IP real, y le entrega las variables y secretos |
| `wrangler.jsonc`, `package.json`, `package-lock.json` | Configuración de Cloudflare (contenedor `basic`, 1 instancia, región ENAM) |
| `apps/tenants/management/commands/preparar_servidor.py` | Lo que corre al arrancar: `migrate` + `migrate_tenants` + superusuario inicial |
| `config/entorno.py` | Lee `DATABASE_URL` |
| `config/settings.py` | `DATABASE_URL` (control en Postgres), `TENANT_PG_*` salen de ella, SSL, WhiteNoise, R2, registros a la consola, `.webp` |
| `apps/tenants/db.py`, `provisioning.py` | SSL y conexiones reutilizables por restaurante; `CREATE DATABASE` con psycopg 3 (antes exigía psycopg2) |
| `tests/test_despliegue.py` | Pruebas de lo anterior |

**En tu PC no cambia nada:** sin `DATABASE_URL` sigue usando SQLite y
`runserver` como siempre.

Verificado en este entorno: la imagen se construye; arrancada con `DEBUG=0`
contra un Postgres migra, crea el superusuario, sirve estáticos, deja entrar al
panel maestro, **da de alta un restaurante con su propia base** (`CREATE DATABASE`)
y responde su API pública; reinicia sin perder datos; las fotos se suben a un
almacenamiento S3 con su tipo `image/webp`; y con `wrangler dev` el recorrido
completo Worker → contenedor → Django funciona (redirecciones, login con CSRF).

## 4. Pasos para verlo funcionando

### 4.1 Antes de empezar
1. Resolver §2.10 (repositorio privado y llaves nuevas).
2. Fusionar la rama `claude/happy-volta-uwe784` en `main` (Workers Builds despliega
   la rama de producción).

### 4.2 Base de datos (Neon)
1. Crear cuenta en neon.tech → **New project** → región **AWS US East 1 (N. Virginia)**.
2. **Connect** → desactivar *Connection pooling* → copiar la cadena, algo como
   `postgresql://neondb_owner:…@ep-…us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require`.
   Esa es `DATABASE_URL`: ahí queda la base de control, y Cloudin crea al lado una
   base `cloudin_<slug>` por restaurante.

### 4.3 Fotos (R2)
1. Dashboard de Cloudflare → **R2** → activar R2.
2. **Create bucket** → `cloudin-fotos`.
3. En el bucket → **Settings → Public access → R2.dev subdomain → Allow**. Copiar
   el dominio `pub-….r2.dev` (sin `https://`): es `R2_PUBLIC_DOMAIN`.
4. R2 → **Manage API tokens → Create API token** → permiso *Object Read & Write*
   solo para `cloudin-fotos`. Da `R2_ACCESS_KEY_ID` y `R2_SECRET_ACCESS_KEY`.
   `R2_ACCOUNT_ID` es el ID de la cuenta (aparece en la misma página).

### 4.4 El Worker con el contenedor
1. Cambiar la cuenta a **Workers Paid** (Workers & Pages → Plans).
2. **Workers & Pages → Create → Import a repository** → `KennyHenning24/Cloudin-1.0`.
   - Nombre del proyecto: **`cloudin`** (debe coincidir con `name` en `wrangler.jsonc`).
   - Rama de producción: `main`.
   - Build command: `npm ci` · Deploy command: `npx wrangler deploy` · Directorio raíz: `/`.
3. El primer despliegue construye la imagen (varios minutos). Todavía no abre: faltan los secretos.
4. **Workers & Pages → cloudin → Settings → Variables and Secrets → Add**, tipo
   **Secret**:

| Secreto | Obligatorio | Valor |
|---|---|---|
| `SECRET_KEY` | Sí | `python -c "import secrets; print(secrets.token_urlsafe(50))"` |
| `CREDENTIAL_KEY` | Sí | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` — **nueva** |
| `DATABASE_URL` | Sí | La de Neon (§4.2) |
| `DJANGO_SUPERUSER_USERNAME` | Primer arranque | p. ej. `juan` |
| `DJANGO_SUPERUSER_PASSWORD` | Primer arranque | Una nueva y larga (no `cloudin2026`) |
| `DJANGO_SUPERUSER_EMAIL` | No | Tu correo |
| `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`, `R2_PUBLIC_DOMAIN` | Para ver fotos | §4.3 (`R2_BUCKET=cloudin-fotos`) |
| `FACTUS_URL`, `FACTUS_CLIENT_ID`, `FACTUS_CLIENT_SECRET`, `FACTUS_USERNAME`, `FACTUS_PASSWORD` | No | Sin ellas se usa el proveedor simulado |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL` | No | Sin ellas los correos van al registro |
| `LEGAL_RESPONSABLE`, `LEGAL_NIT`, `LEGAL_CORREO`, `LEGAL_DIRECCION`, `LEGAL_CIUDAD` | No | Datos de los términos |

   Lo que **no** es secreto (`DEBUG`, `ALLOWED_HOSTS`…) ya está en `wrangler.jsonc`.
   No lo pongas en el dashboard como texto plano: cada despliegue lo reemplaza.
5. **Deployments → Retry build** (o cualquier push a `main`). Al terminar, abrir
   `https://cloudin.<tu-cuenta>.workers.dev/master/` y entrar con el superusuario.
   La primera visita tarda (crea todas las tablas).
6. Dar de alta un restaurante en `/master/nuevo/`.

## 5. El día a día

- **Cambiar algo:** editar en GitHub (o en tu PC y `git push`) sobre `main` →
  Workers Builds construye la imagen y la despliega sola (unos minutos). El estado
  sale en **Workers & Pages → cloudin → Deployments** y como *check* en GitHub.
- **Cambiar modelos:** después de `makemigrations` basta con subir el código: al
  arrancar, el contenedor corre `migrate` y `migrate_tenants`.
- **Probar sin tocar producción:** trabajar en otra rama y abrir un PR. Ojo: en
  ramas que no son la de producción Workers Builds sube solo el Worker, **no** la
  imagen nueva del contenedor.
- **Ver errores:** Workers & Pages → cloudin → **Logs** (Worker) y la sección
  **Containers** del dashboard (salida de Django y gunicorn), o `npx wrangler tail`.
- **Cambiar un secreto:** se toma cuando el contenedor vuelve a arrancar (tras un
  despliegue, o al dormirse y despertar).
- **Correr un comando de `manage.py` en producción** desde tu PC (PowerShell),
  con las dependencias de producción instaladas en tu entorno virtual
  (`pip install -r requirements-produccion.txt`):

  ```powershell
  $env:DATABASE_URL = "postgresql://…neon.tech/neondb?sslmode=require"
  $env:CREDENTIAL_KEY = "<la misma del servidor>"
  # y las R2_* si el comando sube fotos (seed_demo_menu, importar_menu)
  python manage.py control_analizar --todos
  ```

  Las variables de la terminal ganan sobre tu `.env`. Cierra la terminal al
  terminar para no quedar apuntando a producción sin darte cuenta.

## 6. Dominio propio (cuando toque)

1. Agregar el dominio a Cloudflare (DNS).
2. Workers & Pages → cloudin → **Settings → Domains & Routes**: dominio del panel
   (p. ej. `app.cloudin.co`) y, para subdominios por restaurante, la ruta
   `*.cloudin.co/*` con un registro DNS comodín con proxy.
3. En `wrangler.jsonc`: `CLOUDIN_PUBLIC_URL`, `ALLOWED_HOSTS`,
   `CSRF_TRUSTED_ORIGINS` y `TENANT_BASE_DOMAIN` con el dominio nuevo.
