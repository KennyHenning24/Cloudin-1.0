"""Router que separa la base de control de las bases de cada restaurante."""

from .context import get_current_db_alias, get_current_tenant

# Apps que viven en la base de control ('default').
SHARED_APPS = {
    "admin",
    "auth",
    "contenttypes",
    "sessions",
    "messages",
    "staticfiles",
    "tenants",
}

# Apps cuyos datos son privados de cada restaurante.
TENANT_APPS = {"catalog", "dining", "orders", "billing", "staffing", "shifts", "inventory", "waiters",
               "reservas", "control"}

TENANT_ALIAS_PREFIX = "tenant_"


class TenantRouter:
    def _db(self, model, **hints):
        if model._meta.app_label in TENANT_APPS:
            instance = hints.get("instance")
            if instance is not None and instance._state.db:
                return instance._state.db
            return get_current_db_alias()
        return "default"

    def db_for_read(self, model, **hints):
        return self._db(model, **hints)

    def db_for_write(self, model, **hints):
        return self._db(model, **hints)

    def allow_relation(self, obj1, obj2, **hints):
        # Solo se permiten relaciones dentro de la misma base.
        db1 = obj1._state.db
        db2 = obj2._state.db
        if db1 and db2:
            return db1 == db2
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if db == "default":
            return app_label in SHARED_APPS
        if db.startswith(TENANT_ALIAS_PREFIX):
            return app_label in TENANT_APPS
        return False


def current_tenant_or_none():
    return get_current_tenant()
