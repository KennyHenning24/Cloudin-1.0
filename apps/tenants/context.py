"""Restaurante activo durante una petición (o un comando de gestión)."""

import contextlib
from threading import local

from .db import ensure_tenant_connection

_state = local()


class NoTenantError(RuntimeError):
    """Se intentó tocar datos de restaurante sin saber de qué restaurante."""


def set_current_tenant(tenant):
    _state.tenant = tenant
    if tenant is not None:
        ensure_tenant_connection(tenant)


def get_current_tenant():
    return getattr(_state, "tenant", None)


def get_current_db_alias() -> str:
    tenant = get_current_tenant()
    if tenant is None:
        raise NoTenantError(
            "No hay restaurante activo para esta operación. "
            "Use la cabecera X-API-Key, el subdominio, o el contexto tenant_context()."
        )
    return tenant.db_alias


@contextlib.contextmanager
def tenant_context(tenant):
    """Ejecuta un bloque de código 'dentro' de un restaurante.

    with tenant_context(t):
        Table.objects.create(number=1)
    """
    previous = get_current_tenant()
    set_current_tenant(tenant)
    try:
        yield tenant
    finally:
        set_current_tenant(previous)
