"""Piezas compartidas por todas las pruebas.

Cómo se aíslan los datos:

- La base de control es la base de pruebas de pytest-django: cada prueba corre
  dentro de una transacción que se deshace al final.
- Las bases de restaurante se crean en una carpeta temporal. Al empezar la sesión
  se migra UNA base plantilla; cada restaurante de cada prueba recibe una copia
  nueva de ese archivo (copiar es mucho más rápido que migrar).

Nunca se tocan `control.sqlite3` ni `tenant_dbs/` reales.
"""

import shutil
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.conf import settings
from django.core.cache import cache
from django.core.management import call_command
from django.db import connections
from django.db.backends.base.base import BaseDatabaseWrapper
from django.test import testcases
from django.utils import timezone

from apps.tenants.db import tenant_db_settings

ALIAS_PLANTILLA = "tenant__plantilla"

# Django bloquea en las pruebas cualquier base que no esté declarada en la prueba.
# Las bases de restaurante se registran en caliente (igual que en producción), así
# que aquí se permiten las que empiezan por "tenant_". Cada una es un archivo nuevo
# por prueba, de modo que no hace falta deshacer nada en ellas.
_parche_original = testcases.SimpleTestCase.ensure_connection_patch_method.__func__


def _permitir_bases_de_restaurante(cls):
    parche = _parche_original(cls)
    conectar_de_verdad = BaseDatabaseWrapper.ensure_connection

    def ensure_connection(self, *args, **kwargs):
        if self.alias.startswith("tenant_"):
            return conectar_de_verdad(self, *args, **kwargs)
        return parche(self, *args, **kwargs)

    return ensure_connection


testcases.SimpleTestCase.ensure_connection_patch_method = classmethod(_permitir_bases_de_restaurante)


def _olvidar_conexion(alias: str) -> None:
    if alias in connections.databases:
        try:
            connections[alias].close()
            del connections[alias]
        except (AttributeError, KeyError):
            pass
        connections.databases.pop(alias, None)
    settings.DATABASES.pop(alias, None)


def _registrar_conexion(alias: str, config: dict) -> None:
    """Apunta el alias a otra base, cerrando la conexión vieja si existía."""
    _olvidar_conexion(alias)
    settings.DATABASES[alias] = config
    connections.databases[alias] = config


@pytest.fixture(scope="session", autouse=True)
def _entorno_de_pruebas(tmp_path_factory):
    carpeta = tmp_path_factory.mktemp("tenant_dbs")
    settings.TENANT_DB_DIR = carpeta
    settings.TENANT_DB_ENGINE = "sqlite"
    settings.TENANT_BASE_DOMAIN = "localhost"
    settings.ALLOWED_HOSTS = ["*"]
    return carpeta


@pytest.fixture(scope="session")
def plantilla_restaurante(django_db_setup, django_db_blocker, _entorno_de_pruebas):
    """Una base de restaurante con todas las migraciones, creada una sola vez."""
    with django_db_blocker.unblock():
        config = tenant_db_settings(SimpleNamespace(db_name="_plantilla"))
        _registrar_conexion(ALIAS_PLANTILLA, config)
        call_command("migrate", database=ALIAS_PLANTILLA, interactive=False, verbosity=0)
        _olvidar_conexion(ALIAS_PLANTILLA)
    return _entorno_de_pruebas / "_plantilla.sqlite3"


@pytest.fixture(autouse=True)
def _limpiar_cache():
    # Los topes de intentos y de peticiones viven en la caché: cada prueba empieza de cero.
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def crear_restaurante(db, plantilla_restaurante):
    """Fábrica: crea un restaurante con su propia base (copia de la plantilla)."""
    from apps.tenants.models import Tenant

    creados = []

    def _crear(slug="restaurante-a", nombre=None, **datos):
        tenant = Tenant.objects.create(
            name=nombre or slug.replace("-", " ").title(),
            slug=slug,
            # Un archivo distinto en cada prueba: en Windows un archivo abierto no se puede pisar.
            db_name=f"cloudin_{slug}_{uuid.uuid4().hex[:8]}",
            **datos,
        )
        destino = settings.TENANT_DB_DIR / f"{tenant.db_name}.sqlite3"
        shutil.copyfile(plantilla_restaurante, destino)
        _registrar_conexion(tenant.db_alias, tenant_db_settings(tenant))
        tenant.provisioned_at = timezone.now()
        tenant.save(update_fields=["provisioned_at"])
        creados.append(tenant.db_alias)
        return tenant

    yield _crear

    # Se sacan de la configuración antes de que Django cierre la prueba: así no
    # intenta restaurar conexiones que él no preparó.
    for alias in creados:
        _olvidar_conexion(alias)


@pytest.fixture(scope="module")
def navegador():
    """Edge del sistema, sin ventana, para probar el runtime y las pantallas.
    Si el equipo no tiene Edge, las pruebas que lo usan se saltan."""
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="msedge", headless=True)
        except Exception as e:  # pragma: no cover - depende del equipo
            pytest.skip(f"No se pudo abrir Edge: {e}")
        yield browser
        browser.close()


@pytest.fixture
def bases_creadas_en_la_prueba():
    """Para pruebas que crean restaurantes «de verdad» (importar con --create-tenant,
    create_restaurant): anota aquí su slug y al final se cierra y borra su base."""
    slugs = []
    yield slugs
    for slug in slugs:
        _olvidar_conexion(f"tenant_{slug}")
        for archivo in settings.TENANT_DB_DIR.glob(f"cloudin_{slug}.sqlite3"):
            try:
                archivo.unlink()
            except OSError:
                pass


@pytest.fixture
def crear_usuario(db):
    """Fábrica: usuario del restaurante que ya aceptó los términos vigentes."""
    from apps.tenants.models import AceptacionLegal, TenantMembership
    from apps.tenants.services import crear_usuario as crear

    def _crear(tenant, usuario="admin", rol=TenantMembership.ROLE_ADMIN, **datos):
        user, _ = crear(tenant, usuario, rol=rol, password="clave-de-prueba-123", **datos)
        AceptacionLegal.objects.create(user=user, version=settings.LEGAL_VERSION)
        return user

    return _crear


@pytest.fixture
def abrir_turno():
    """Abre el turno de caja del restaurante (sin turno, el panel no deja operar)."""
    from apps.shifts.services import abrir_turno as abrir
    from apps.tenants.context import tenant_context

    def _abrir(tenant):
        with tenant_context(tenant):
            return abrir(por="Pruebas", base_inicial=Decimal("10000"))

    return _abrir


@pytest.fixture
def en_restaurante():
    """Atajo para `with en_restaurante(tenant): ...` dentro de una prueba."""
    from apps.tenants.context import tenant_context

    return tenant_context
