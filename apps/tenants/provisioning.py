"""Alta de un restaurante: crear su base, migrarla y dejarla lista."""

from django.conf import settings
from django.core.management import call_command
from django.utils import timezone

from .db import ensure_tenant_connection


def _conectar_para_crear_bases():
    """Conexión en autocommit (CREATE DATABASE no corre dentro de una transacción)
    a una base que ya existe. Sirve psycopg 3 (el de requirements-produccion.txt) o
    psycopg2, el que esté instalado."""
    pg = settings.TENANT_PG
    datos = {
        "dbname": pg.get("MAINTENANCE_DB", "postgres"),
        "user": pg["USER"],
        "password": pg["PASSWORD"],
        "host": pg["HOST"],
        "port": pg["PORT"],
        **pg.get("OPTIONS", {}),
    }
    try:
        import psycopg  # importado aquí: solo hace falta con postgres
    except ImportError:
        import psycopg2
        from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

        conn = psycopg2.connect(**datos)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        return conn
    return psycopg.connect(autocommit=True, **datos)


def create_tenant_database(tenant) -> None:
    """Crea la base física. En sqlite basta con que exista el archivo (lo hace
    la primera conexión); en postgres hay que ejecutar CREATE DATABASE."""
    if settings.TENANT_DB_ENGINE != "postgres":
        return

    conn = _conectar_para_crear_bases()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", [tenant.db_name])
            if cur.fetchone() is None:
                cur.execute(f'CREATE DATABASE "{tenant.db_name}"')
    finally:
        conn.close()


def provision_tenant(tenant, verbosity: int = 0) -> str:
    """Deja al restaurante con su base creada y todas las migraciones aplicadas."""
    create_tenant_database(tenant)
    alias = ensure_tenant_connection(tenant)
    call_command("migrate", database=alias, interactive=False, verbosity=verbosity)
    tenant.provisioned_at = timezone.now()
    tenant.save(update_fields=["provisioned_at"])
    return alias
