"""Lectura de variables de entorno que necesitan algo más que os.getenv.

En el servidor (Cloudflare Containers) no hay disco permanente: la base de control
y las de cada restaurante viven en Postgres, y la conexión llega en una sola
variable, DATABASE_URL, como la entregan Neon, Supabase o PlanetScale:

    postgresql://usuario:clave@servidor:5432/base?sslmode=require
"""

from urllib.parse import parse_qsl, unquote, urlsplit

ESQUEMAS_POSTGRES = ("postgres", "postgresql")


def es_postgres(url: str) -> bool:
    return urlsplit(url).scheme in ESQUEMAS_POSTGRES if url else False


def postgres_desde_url(url: str) -> dict:
    """Parte una DATABASE_URL de Postgres en las piezas que usa Django.

    Los parámetros de la consulta (sslmode, channel_binding…) pasan tal cual a
    OPTIONS: los entiende libpq, el cliente de Postgres que usa psycopg."""
    partes = urlsplit(url)
    if partes.scheme not in ESQUEMAS_POSTGRES:
        raise ValueError(f"DATABASE_URL no es de Postgres: «{partes.scheme}://…».")
    return {
        "NAME": unquote(partes.path.lstrip("/")) or "postgres",
        "USER": unquote(partes.username or ""),
        "PASSWORD": unquote(partes.password or ""),
        "HOST": partes.hostname or "localhost",
        "PORT": str(partes.port or 5432),
        "OPTIONS": dict(parse_qsl(partes.query)),
    }


def lista(valor: str) -> list[str]:
    """«a, b,,c» -> ["a", "b", "c"]"""
    return [v.strip() for v in (valor or "").split(",") if v.strip()]


def direccion_publica(cloudin_public_url: str, render_hostname: str = "") -> str:
    """La dirección pública del servidor, sin / al final.

    Es CLOUDIN_PUBLIC_URL. Si no se puso y el servidor corre en Render, la que Render le
    da al servicio: Render define RENDER_EXTERNAL_HOSTNAME (p. ej. cloudin-abcd.onrender.com)
    al arrancar. Sin ninguna de las dos queda vacía y cada enlace sale de la petición."""
    if (cloudin_public_url or "").strip():
        return cloudin_public_url.strip().rstrip("/")
    host = (render_hostname or "").strip().strip("/")
    return f"https://{host}" if host else ""
