# Cloudin gratis en internet: Render + Neon

> Para ver Cloudin funcionando en un servidor **sin pagar y sin tarjeta**. Usa el
> mismo `Dockerfile` que la opción de Cloudflare (`DESPLIEGUE-CLOUDFLARE.md`), así que
> cuando haya presupuesto se cambia de servidor sin tocar el código.

## 1. Cómo queda

```
 navegador ──► Render (web service gratis, Docker): Django + gunicorn
                  │   (render.yaml en la raíz del repositorio)
                  ▼
            Neon (Postgres gratis, AWS us-east-1)
            cloudin_control + una base cloudin_<slug> por restaurante + las fotos

 menús digitales ──► Cloudflare Pages (gratis) ──► leen la carta y mandan pedidos a Render
```

| Servicio | Plan gratis | Qué significa para Cloudin |
|---|---|---|
| **Render** (web service) | 512 MB de RAM, 750 horas al mes, **sin tarjeta**. Se duerme tras 15 minutos sin visitas y tarda cerca de un minuto en despertar | La primera visita después de un rato tarda. Para probar y mostrar sirve; para atender un restaurante de verdad conviene un plan pago (sección 6) |
| **Neon** (Postgres) | 0,5 GB por proyecto, 100 horas de cómputo al mes; se duerme a los 5 minutos | Alcanza para probar y para varios restaurantes pequeños. No vence (el Postgres gratis de Render sí: 30 días) |
| **Cloudflare Pages** | Gratis | Los menús digitales de cada cliente (`GUIA-MENU-DIGITAL.md`) |

**Las fotos.** El disco de Render se borra cada vez que el servicio se duerme o se
despliega, y R2 (las fotos en Cloudflare) pide tarjeta. Por eso aquí las fotos que se
suben al panel se guardan **en la base de Neon** (`FOTOS_EN_LA_BASE=1`, `apps/archivos`)
y Cloudin las sirve en `/media/`. Llegan convertidas a WebP de pocos cientos de KB: en
0,5 GB caben miles.

## 2. Antes de empezar

1. **Fusiona el PR** del repositorio en `main`. En GitHub, abre el PR →
   baja hasta el final → **Merge pull request** → **Confirm merge**. Render despliega
   la rama `main`.
2. Ten a mano tu cuenta de GitHub: Render y Neon se abren con ella.

## 3. Paso a paso

### 3.1 La base de datos (Neon)

1. Entra a **neon.tech** con tu cuenta de GitHub o Google.
2. Crea un proyecto: nombre `cloudin`, región **AWS US East 1 (N. Virginia)** (queda
   junto a Render en Virginia).
3. Abre el proyecto: en su **Project Dashboard**, el botón **Connect** está arriba a la
   derecha. Deja la rama, la base (`neondb`) y el rol que trae, **apaga *Connection
   pooling*** y copia la dirección. Empieza con `postgresql://…` y trae la contraseña:
   no la compartas. Si en el servidor aparece `-pooler`, bórrale ese `-pooler`.

### 3.2 El servidor (Render)

1. Entra a **render.com** → **Get Started** y regístrate con GitHub (no pide tarjeta).
2. En el panel de Render: **New** → **Blueprint**. Conecta tu GitHub si lo pide y elige
   el repositorio `KennyHenning24/Cloudin-1.0`.
3. Render lee `render.yaml` y muestra el servicio **cloudin** (Docker, plan *Free*,
   región Virginia). Te pide solo tres valores:

   | Variable | Qué poner |
   |---|---|
   | `DATABASE_URL` | La dirección de Neon del paso 3.1 |
   | `DJANGO_SUPERUSER_USERNAME` | Tu usuario del panel maestro, p. ej. `juan` |
   | `DJANGO_SUPERUSER_PASSWORD` | Una contraseña nueva y larga (no la vieja del `.rar`) |

   `SECRET_KEY` y `CREDENTIAL_KEY` las genera Render solo. Lo demás ya viene en
   `render.yaml`.
4. **Deploy Blueprint** (o **Apply**). La primera vez construye la imagen: tarda varios
   minutos. En el servicio → **Logs** vas viendo el avance; cuando aparece
   `Servidor listo.` y después `Listening at`, ya está arriba.
5. La dirección sale arriba en la página del servicio: algo como
   `https://cloudin.onrender.com` (si ese nombre está tomado, Render le agrega letras:
   `https://cloudin-abcd.onrender.com`).

### 3.3 Apagar el Worker de Cloudflare

Sin el plan pago de Cloudflare el Worker `cloudin-1-0` no puede correr contenedores, y
seguiría intentando compilar en cada cambio de `main` (con avisos de error). En Cloudflare
→ **Workers & Pages** → `cloudin-1-0` → **Settings** → **Builds** → desconecta el
repositorio, o borra el Worker. Los archivos de Cloudflare del repositorio se quedan
para cuando haya presupuesto.

### 3.4 Entrar y crear el primer restaurante

1. Abre `https://<tu-servicio>.onrender.com/master/` y entra con el superusuario. Si el
   servicio estaba dormido, la primera carga tarda un minuto.
2. **Nuevo restaurante**, con el plan **«Cloudin completo»** si va a recibir pedidos. El
   panel maestro muestra una sola vez el usuario y la contraseña del restaurante.
3. Entra a `https://<tu-servicio>.onrender.com/panel/login/` con esos datos: **Códigos
   QR** para crear las mesas y **Mi menú** para la carta y las fotos.
4. El menú digital del cliente, en Cloudflare Pages, apunta a esta dirección:
   `GUIA-MENU-DIGITAL.md`, sección 4.

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
- **Correr un comando de `manage.py`:** Render gratis no trae consola. Se corre desde tu
  PC apuntando a Neon, igual que en `DESPLIEGUE-CLOUDFLARE.md` §5: `DATABASE_URL` la de
  Neon y `CREDENTIAL_KEY` la misma del servidor (se copia en **Environment**). Para que
  las fotos que suba el comando lleguen a la base, agrega `FOTOS_EN_LA_BASE=1`.

## 5. Lo que hay que saber del plan gratis

- **Se duerme.** Tras 15 minutos sin visitas, la siguiente espera cerca de un minuto
  (más el despertar de Neon). El menú digital igual se ve, porque vive en Pages y trae
  la carta pre-cargada, pero un pedido o el panel esperan a que despierte.
- **750 horas al mes** por cuenta de Render: con un solo servicio no se acaban.
- **Las fotos cuentan en los 0,5 GB de Neon.** Si algún día no alcanza, el paso natural
  es R2 (`DESPLIEGUE-CLOUDFLARE.md` §4.3). Ojo: con R2 configurado Cloudin deja de leer
  fotos de la base, así que las que ya estaban hay que volver a subirlas o copiarlas al
  bucket (hoy no hay un comando para eso).
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
  misma base de Neon sirve: solo cambia dónde corre el contenedor. Para las fotos, R2.
