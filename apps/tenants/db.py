"""Registro en caliente de las bases de datos de cada restaurante.

Django normalmente exige declarar todas las bases en settings.DATABASES. Aquí
las añadimos en tiempo de ejecución: cuando llega una petición de 'lajoya',
se asegura la conexión 'tenant_lajoya' y el router la usa para el menú,
las mesas y los pedidos.
"""

from django.conf import settings
from django.db import connections


def tenant_db_settings(tenant) -> dict:
    """Diccionario de conexión para un restaurante, según el motor configurado."""
    if settings.TENANT_DB_ENGINE == "postgres":
        cfg = {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": tenant.db_name,
            "USER": settings.TENANT_PG["USER"],
            "PASSWORD": settings.TENANT_PG["PASSWORD"],
            "HOST": settings.TENANT_PG["HOST"],
            "PORT": settings.TENANT_PG["PORT"],
        }
    else:
        cfg = {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": str(settings.TENANT_DB_DIR / f"{tenant.db_name}.sqlite3"),
        }

    # Django completa el resto de claves obligatorias (OPTIONS, CONN_MAX_AGE, ...)
    base = {
        "ATOMIC_REQUESTS": False,
        "AUTOCOMMIT": True,
        "CONN_MAX_AGE": 0,
        "CONN_HEALTH_CHECKS": False,
        "OPTIONS": {},
        "TIME_ZONE": None,
        "USER": "",
        "PASSWORD": "",
        "HOST": "",
        "PORT": "",
        "TEST": {"CHARSET": None, "COLLATION": None, "MIGRATE": True, "MIRROR": None, "NAME": None},
    }
    base.update(cfg)
    return base


def ensure_tenant_connection(tenant) -> str:
    """Registra (si hace falta) la conexión del restaurante y devuelve su alias."""
    alias = tenant.db_alias
    if alias not in settings.DATABASES:
        settings.DATABASES[alias] = tenant_db_settings(tenant)
    connections.databases[alias] = settings.DATABASES[alias]
    return alias


def close_tenant_connection(alias: str) -> None:
    if alias in connections:
        connections[alias].close()
