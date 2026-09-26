"""Alta de un restaurante: crear su base, migrarla y dejarla lista."""

from django.conf import settings
from django.core.management import call_command
from django.utils import timezone

from .db import ensure_tenant_connection


def create_tenant_database(tenant) -> None:
    """Crea la base física. En sqlite basta con que exista el archivo (lo hace
    la primera conexión); en postgres hay que ejecutar CREATE DATABASE."""
    if settings.TENANT_DB_ENGINE != "postgres":
        return

    import psycopg2  # importado aquí: solo hace falta con postgres
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

    conn = psycopg2.connect(
        dbname="postgres",
        user=settings.TENANT_PG["USER"],
        password=settings.TENANT_PG["PASSWORD"],
        host=settings.TENANT_PG["HOST"],
        port=settings.TENANT_PG["PORT"],
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
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
