# Cloudin en internet sin pagar: Render + Neon + R2

> Para ver Cloudin funcionando en un servidor **sin pagar**. Render y Neon no piden
> tarjeta; R2 (las fotos) pide una tarjeta registrada pero cobra **$0** dentro de su capa
> gratis. Usa el mismo `Dockerfile` que la opción de Cloudflare
> (`DESPLIEGUE-CLOUDFLARE.md`), así que cuando haya presupuesto se cambia de servidor sin
> tocar el código.

## 1. Cómo queda

```
 navegador ──► Render (web service gratis, Docker): Django + gunicorn
                  │   (render.yaml en la raíz del repositorio)
                  ├──► Neon (Postgres gratis, AWS us-east-1):
                  │       cloudin_control + una base cloudin_<slug> por restaurante
                  └──► Cloudflare R2 (capa gratis): las fotos, bucket cloudin-fotos

 menús digitales ──► Cloudflare Pages (gratis) ──► leen la carta y mandan pedidos a Render
```

| Servicio | Plan gratis | Qué significa para Cloudin |
|---|---|---|
| **Render** (web service) | 512 MB de RAM, 750 horas al mes, **sin tarjeta**. Se duerme tras 15 minutos sin visitas y tarda cerca de un minuto en despertar | La primera visita después de un rato tarda. Para probar y mostrar sirve; para atender un restaurante de verdad conviene un plan pago (sección 6) |
| **Neon** (Postgres) | 0,5 GB por proyecto, 100 horas de cómputo al mes; se duerme a los 5 minutos | Alcanza para probar y para varios restaurantes pequeños. No vence (el Postgres gratis de Render sí: 30 días) |
| **Cloudflare R2** (fotos) | 10 GB, 1 millón de escrituras y 10 millones de lecturas al mes; descargas gratis. Pide tarjeta para activarse | Las fotos que se suben al panel. Llegan convertidas a WebP de pocos cientos de KB: en 10 GB caben decenas de miles |
| **Cloudflare Pages** | Gratis | Los menús digitales de cada cliente (`GUIA-MENU-DIGITAL.md`) |

**Por qué R2 para las fotos:** el disco de Render se borra cada vez que el servicio se
duerme o se despliega; una foto guardada ahí desaparecería. **Si no usas R2** (dejas
vacías las variables `R2_*`), las fotos se guardan en la base de Neon
(`FOTOS_EN_LA_BASE=1`, `apps/archivos`) y cuentan en sus 0,5 GB.

## 2. Antes de empezar

1. **Fusiona el PR** del repositorio en `main`. En GitHub, abre el PR → baja hasta el
   final → **Merge pull request** → **Confirm merge**. Render despliega la rama `main`.
2. Ten a mano tu cuenta de GitHub: Render y Neon se abren con ella.

## 3. Paso a paso

### 3.1 La base de datos (Neon)

1. Entra a **neon.tech** con tu cuenta de GitHub o Google.
2. Crea un proyecto: nombre `cloudin`, región **AWS US East 1 (N. Virginia)**.
3. Abre el proyecto: en su **Project Dashboard**, el botón **Connect** está arriba a la
   derecha. Deja la rama, la base (`neondb`) y el rol que trae, **apaga *Connection
   pooling*** y copia la dirección (`postgresql://…`). Trae la contraseña: no la
   compartas. Si en el servidor aparece `-pooler`, bórrale ese `-pooler`.

### 3.2 Las fotos (Cloudflare R2)

R2 ya está activado en tu cuenta y el bucket **`cloudin-fotos`** ya está creado (en
Norteamérica Este, cerca de Render y Neon). Falta:

1. **Dirección pública.** Cloudflare → **R2** → `cloudin-fotos` → **Settings** →
   **Public Development URL** → **Enable** → escribe `allow` → **Allow**. Copia la
   dirección que aparece (`https://pub-….r2.dev`): es `R2_PUBLIC_DOMAIN`.
2. **Llaves.** En la página principal de **R2**, en **Account Details**, **Manage** junto
   a **API Tokens** → **Create Account API token** → permiso **Object Read & Write** →
   solo el bucket `cloudin-fotos` → crear. Copia **Access Key ID** (`R2_ACCESS_KEY_ID`) y
   **Secret Access Key** (`R2_SECRET_ACCESS_KEY`). La secreta se muestra una sola vez: si
   se pierde, se crea otro token.
3. En esa misma sección **Account Details** está el **Account ID** (`R2_ACCOUNT_ID`).

### 3.3 El servidor (Render)

1. Entra a **render.com** → **Get Started** y regístrate con GitHub (no pide tarjeta).
2. En el panel de Render: **New** → **Blueprint**. Conecta tu GitHub si lo pide y elige
   el repositorio `KennyHenning24/Cloudin-1.0`.
3. Render lee `render.yaml` y muestra el servicio **cloudin** (Docker, plan *Free*,
   región Virginia). Te pide estos valores:

   | Variable | Qué poner |
   |---|---|
   | `DATABASE_URL` | La dirección de Neon (3.1) |
   | `DJANGO_SUPERUSER_USERNAME` | Tu usuario del panel maestro, p. ej. `juan` |
   | `DJANGO_SUPERUSER_PASSWORD` | Una contraseña nueva y larga (no la vieja del `.rar`). Solo se usa en el primer arranque: si la pierdes, §4 |
   | `R2_BUCKET` | `cloudin-fotos` |
   | `R2_ACCOUNT_ID` | El Account ID (3.2) |
   | `R2_ACCESS_KEY_ID` | El Access Key ID (3.2) |
   | `R2_SECRET_ACCESS_KEY` | El Secret Access Key (3.2) |
   | `R2_PUBLIC_DOMAIN` | La dirección `https://pub-….r2.dev` (3.2) |

   `SECRET_KEY` y `CREDENTIAL_KEY` las genera Render solo. Lo demás ya viene en
   `render.yaml`. Si el servicio ya existía sin las `R2_*` (se creó con una versión
   anterior de `render.yaml`), agrégalas a mano: servicio → **Environment** → agregar
   cada variable → guardar. Render lo reinicia y desde ahí las fotos van a R2.
4. **Deploy Blueprint** (o **Apply**). La primera vez construye la imagen: tarda varios
   minutos. En el servicio → **Logs** vas viendo el avance; cuando aparece
   `Servidor listo.` y después `Listening at`, ya está arriba. Si falta una llave de R2,
   el registro lo dice (`Con R2_BUCKET hacen falta…`).
5. La dirección sale arriba en la página del servicio: algo como
   `https://cloudin.onrender.com` (si ese nombre está tomado, Render le agrega letras:
   `https://cloudin-abcd.onrender.com`).

### 3.4 Apagar el Worker de Cloudflare

Sin el plan pago de Cloudflare el Worker `cloudin-1-0` no puede correr contenedores, y
seguiría intentando compilar en cada cambio de `main` (con avisos de error). En Cloudflare
→ **Workers & Pages** → `cloudin-1-0` → **Settings** → **Builds** → desconecta el
repositorio, o borra el Worker. Los archivos de Cloudflare del repositorio se quedan
para cuando haya presupuesto.

### 3.5 Entrar y crear el primer restaurante

1. Abre `https://<tu-servicio>.onrender.com/master/` y entra con el superusuario. Si el
   servicio estaba dormido, la primera carga tarda un minuto.
2. **Nuevo restaurante** (todos tienen Cloudin completo; los pedidos por QR vienen
   encendidos y el restaurante los apaga o enciende en su panel). El panel maestro muestra una sola vez el usuario, la contraseña y el enlace del panel
   (`https://<tu-servicio>.onrender.com/panel/login/`: Cloudin toma la dirección del
   servicio de `RENDER_EXTERNAL_HOSTNAME`, que Render define solo).
3. Entra al panel con esos datos: **Códigos QR** para crear las mesas y **Personalizar** para
   la carta y las fotos. Al subir una foto, su dirección empieza con
   `https://pub-….r2.dev/`: así sabes que quedó en R2.
4. El recorrido completo, con el menú en Cloudflare Pages y el pedido de prueba:
   **`PASO-A-PASO-NUEVO-RESTAURANTE.md`**.

## 4. El día a día

- **Cambiar algo:** cada cambio que llega a `main` en GitHub se despliega solo. El
  avance sale en el servicio → **Events** y **Logs**. Para repetir un despliegue:
  **Manual Deploy** → **Deploy latest commit**.
- **Cambiar modelos:** después de `makemigrations` basta con subir el código: al
  arrancar, el contenedor corre `migrate` y `migrate_tenants`.
- **Ver errores:** servicio → **Logs** (salida de Django y gunicorn).
- **Cambiar una variable:** servicio → **Environment** → editar → guardar (reinicia el
  servicio). **Nunca cambies `CREDENTIAL_KEY`**: las contraseñas guardadas para el panel
  maestro quedarían ilegibles.
- **No puedo entrar al panel maestro** (`/master/`, o `/admin/`: la pantalla «Cloudin ·
  datos en crudo», «…para obtener cuenta de personal»). Es solo para el superusuario: el
  usuario y la contraseña de `DJANGO_SUPERUSER_USERNAME` y `DJANGO_SUPERUSER_PASSWORD`
  **del primer arranque** (servicio → **Environment**; el ojo muestra el valor). Ojo con
  las mayúsculas de la contraseña. Cambiar `DJANGO_SUPERUSER_PASSWORD` después **no**
  cambia la clave. Para ponerle una nueva:
  1. **Environment** → `DJANGO_SUPERUSER_PASSWORD` = la clave nueva, y agrega
     `DJANGO_SUPERUSER_RESET` = `1` → guardar (Render reinicia el servicio).
  2. En **Logs** sale «Superusuario «…»: su contraseña es ahora la de
     DJANGO_SUPERUSER_PASSWORD». Entra con ella.
  3. Borra `DJANGO_SUPERUSER_RESET` y guarda.

  Cinco claves equivocadas seguidas bloquean ese usuario 15 minutos (el reinicio también
  lo desbloquea). Los restaurantes entran por `/panel/login/` y los meseros por
  `/mesero/<slug>/`: esas cuentas no sirven en `/admin/`.
- **Correr un comando de `manage.py`:** Render gratis no trae consola. Se corre desde tu
  PC apuntando a Neon, igual que en `DESPLIEGUE-CLOUDFLARE.md` §5: `DATABASE_URL` la de
  Neon, `CREDENTIAL_KEY` la misma del servidor (se copia en **Environment**) y las `R2_*`
  si el comando sube fotos.

## 5. Lo que hay que saber del plan gratis

- **Se duerme.** Tras 15 minutos sin visitas, la siguiente espera cerca de un minuto
  (más el despertar de Neon). El menú digital igual se ve, porque vive en Pages y trae
  la carta pre-cargada, pero un pedido o el panel esperan a que despierte.
- **750 horas al mes** por cuenta de Render: con un solo servicio no se acaban.
- **La dirección `r2.dev` es de desarrollo.** Cloudflare le pone un tope de velocidad y
  la recomienda solo para pruebas. Cuando haya un dominio propio en Cloudflare, se
  conecta al bucket (**Settings** → **Custom Domains**) y se cambia `R2_PUBLIC_DOMAIN`.
  Las fotos no se mueven: siguen en el mismo bucket.
- **Sin R2** (variables `R2_*` vacías), las fotos van a la base de Neon. Si después se
  configura R2, Cloudin deja de leer las fotos de la base: las que ya estaban hay que
  volver a subirlas (hoy no hay un comando para moverlas).
- **La IP de cada cliente** (para los topes de pedidos y de intentos de login) se toma
  de `CF-Connecting-IP`, que Render recibe de Cloudflare. Si Render dejara de mandarla,
  un cliente podría esquivar esos topes inventando `X-Forwarded-For`
  (`apps/panel/seguridad.py`, `ip_de`).
- **Correo:** sin `EMAIL_*` los correos (recuperar contraseña, invitaciones) se
  escriben en los **Logs**, no se envían.

## 6. Cuando haya presupuesto

- **Quedarse en Render** con una instancia paga: no se duerme. Cambia el plan del
  servicio en Render; no hay que tocar el código.
- **Pasarse a Cloudflare Containers** (Workers Paid): `DESPLIEGUE-CLOUDFLARE.md`. La
  misma base de Neon y el mismo bucket de R2 sirven: solo cambia dónde corre el
  contenedor.
