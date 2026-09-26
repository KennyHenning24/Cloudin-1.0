"""
Configuración de Cloudin — backend único multi-tenant.

Dos "capas" de base de datos:
  - default: base de control (tenants, usuarios, sesiones, admin de Juan).
  - tenant_<slug>: una base por restaurante, con su menú, mesas y pedidos.

Las bases de tenant no se declaran aquí: se registran en caliente desde
apps/tenants/db.py cuando llega una petición de ese restaurante.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("SECRET_KEY", "dev-insecure-cambiar-en-produccion")
DEBUG = os.getenv("DEBUG", "1") == "1"

# Llave con la que se cifran las contraseñas que el panel maestro puede mostrar.
# Vive solo en el .env: si se pierde, esas copias quedan ilegibles (las cuentas
# siguen funcionando, pero habría que regenerar cada contraseña).
CREDENTIAL_KEY = os.getenv("CREDENTIAL_KEY", "")

# Términos y condiciones y política de privacidad. Al cambiar la versión, cada
# usuario los vuelve a aceptar al entrar. Los datos del responsable salen del
# .env para no dejar datos personales en el código.
LEGAL_VERSION = os.getenv("LEGAL_VERSION", "2026-09-22")
LEGAL_RESPONSABLE = os.getenv("LEGAL_RESPONSABLE", "Cloudin")
LEGAL_NIT = os.getenv("LEGAL_NIT", "")
LEGAL_CORREO = os.getenv("LEGAL_CORREO", "")
LEGAL_DIRECCION = os.getenv("LEGAL_DIRECCION", "")
LEGAL_CIUDAD = os.getenv("LEGAL_CIUDAD", "Colombia")

# Factus, proveedor tecnológico ante la DIAN. Estas son las credenciales
# globales de Cloudin como Aliado; un restaurante puede tener las suyas propias
# (se guardan cifradas en EmpresaFiscal.credenciales_pt y ganan sobre estas).
FACTUS_URL = os.getenv("FACTUS_URL", "https://api-sandbox.factus.com.co")
FACTUS_CLIENT_ID = os.getenv("FACTUS_CLIENT_ID", "")
FACTUS_CLIENT_SECRET = os.getenv("FACTUS_CLIENT_SECRET", "")
FACTUS_USERNAME = os.getenv("FACTUS_USERNAME", "")
FACTUS_PASSWORD = os.getenv("FACTUS_PASSWORD", "")

ALLOWED_HOSTS = [h.strip() for h in os.getenv("ALLOWED_HOSTS", "*").split(",") if h.strip()]

# Dominio base sobre el que se resuelven los subdominios de cada restaurante:
# lajoya.cloudin.co -> slug "lajoya". En local: lajoya.localhost:8000. Es opcional:
# sin dominio propio, cada restaurante se identifica por la ruta (/api/public/<slug>/…).
TENANT_BASE_DOMAIN = os.getenv("TENANT_BASE_DOMAIN", "localhost")

# Dirección pública de este servidor (sin / al final). Con ella se arman los enlaces
# absolutos del menú público (fotos, API, runtime). Vacía: se usa la de la petición.
CLOUDIN_PUBLIC_URL = os.getenv("CLOUDIN_PUBLIC_URL", "").rstrip("/")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "drf_spectacular",
    "simple_history",
    "apps.common",
    "apps.tenants",
    "apps.business",
    "apps.catalog",
    "apps.public_menu",
    "apps.importer",
    "apps.dining",
    "apps.orders",
    "apps.billing",
    "apps.staffing",
    "apps.shifts",
    "apps.inventory",
    "apps.waiters",
    "apps.reservas",
    "apps.control",
    "apps.panel",
    "apps.master",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.tenants.middleware.TenantMiddleware",
    # Quién hizo cada cambio de la carta (precios incluidos) queda en el historial.
    "simple_history.middleware.HistoryRequestMiddleware",
    "config.seguridad.CabecerasSeguridad",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.tenants.context_processors.tenant",
                "apps.shifts.context_processors.turno",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# --- Bases de datos -------------------------------------------------------

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "control.sqlite3",
    }
}

DATABASE_ROUTERS = ["apps.tenants.routers.TenantRouter"]

# Motor de las bases por restaurante: "sqlite" (MVP local) o "postgres".
TENANT_DB_ENGINE = os.getenv("TENANT_DB_ENGINE", "sqlite")
TENANT_DB_DIR = Path(os.getenv("TENANT_DB_DIR", BASE_DIR / "tenant_dbs"))
TENANT_DB_DIR.mkdir(parents=True, exist_ok=True)

# Solo se usan cuando TENANT_DB_ENGINE == "postgres"
TENANT_PG = {
    "HOST": os.getenv("TENANT_PG_HOST", "localhost"),
    "PORT": os.getenv("TENANT_PG_PORT", "5432"),
    "USER": os.getenv("TENANT_PG_USER", "postgres"),
    "PASSWORD": os.getenv("TENANT_PG_PASSWORD", ""),
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "es-co"
TIME_ZONE = "America/Bogota"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"] if (BASE_DIR / "static").exists() else []

# Fotos del menú subidas desde el panel. Cada restaurante en su carpeta.
# En producción van a un almacenamiento de archivos (S3, R2…), no al disco del servidor.
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Una dirección escrita sin "http" se completa con https (lo que hará Django 6).
FORMS_URLFIELD_ASSUME_HTTPS = True

# Se entra con el usuario o con el correo (apps/tenants/auth.py).
AUTHENTICATION_BACKENDS = ["apps.tenants.auth.UsuarioOCorreo"]
# Enlaces de invitación y de recuperar contraseña: 7 días.
PASSWORD_RESET_TIMEOUT = 7 * 24 * 60 * 60

LOGIN_URL = "/panel/login/"
LOGIN_REDIRECT_URL = "/panel/"
LOGOUT_REDIRECT_URL = "/panel/login/"

# La sesión sobrevive a cerrar la pestaña y el navegador: en un restaurante la
# caja se apaga y se prende todo el día, y nadie quiere volver a escribir la
# clave. Solo se cierra con el botón "Salir".
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
SESSION_COOKIE_AGE = 60 * 60 * 24 * 60  # 60 días
SESSION_SAVE_EVERY_REQUEST = True  # cada visita renueva esos 60 días
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_SECURE = not DEBUG
# El JavaScript del panel toma el token CSRF de la plantilla, no de la cookie:
# así un script inyectado tampoco puede leerla.
CSRF_COOKIE_HTTPONLY = True
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

# Producción: HTTPS obligatorio y sin configuraciones de prueba. Si falta algo
# crítico, Cloudin no arranca (mejor eso que quedar expuesto sin saberlo).
if not DEBUG:
    from django.core.exceptions import ImproperlyConfigured

    if SECRET_KEY.startswith("dev-insecure") or len(SECRET_KEY) < 40:
        raise ImproperlyConfigured("Falta un SECRET_KEY real y largo en el .env de producción.")
    if "*" in ALLOWED_HOSTS:
        raise ImproperlyConfigured("ALLOWED_HOSTS no puede ser «*» en producción: pon el dominio.")
    if not CREDENTIAL_KEY:
        raise ImproperlyConfigured("Falta CREDENTIAL_KEY en el .env de producción.")
    SECURE_SSL_REDIRECT = os.getenv("SECURE_SSL_REDIRECT", "1") == "1"
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", str(60 * 60 * 24 * 365)))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()]

# Correo: en desarrollo se imprime en la consola, así el enlace de recuperación
# se puede copiar sin montar un servidor de correo.
if DEBUG or not os.getenv("EMAIL_HOST"):
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
else:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = os.getenv("EMAIL_HOST")
    EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
    EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
    EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "1") == "1"
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "Cloudin <no-responder@cloudin.app>")

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.AllowAny",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "API de Cloudin",
    "DESCRIPTION": "Menú público (cloudin.menu/v1), panel del dueño, pedidos y facturación. "
                   "Ver docs/API.md para ejemplos.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

# La web de cada restaurante vive en otro dominio y consume la API. No se abre
# a todo el mundo: apps/tenants/cors.py permite el sitio que cada restaurante
# registró en su panel, y esta lista sirve para excepciones manuales.
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = [
    o.strip() for o in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",") if o.strip()
]
CORS_ALLOW_HEADERS = (
    "accept",
    "authorization",
    "content-type",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
    "x-api-key",
    "x-tenant",
)
