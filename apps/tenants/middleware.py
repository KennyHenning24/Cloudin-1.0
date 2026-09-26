"""Identifica de qué restaurante es cada petición.

Orden de resolución:
  1. Cabecera X-API-Key  -> la usa el sitio web del restaurante.
  2. Subdominio          -> lajoya.cloudin.app, o lajoya.localhost:8000 en local.
  3. Usuario autenticado -> el mesero/admin logueado pertenece a un restaurante.
  4. Sesión              -> el superusuario que abrió un panel con ?tenant=slug
                            sigue "dentro" de ese restaurante mientras navega.
  5. ?tenant=slug o cabecera X-Tenant -> solo en DEBUG, para pruebas locales.
"""

from django.conf import settings
from django.http import JsonResponse

from .context import set_current_tenant
from .models import Tenant

# Rutas que nunca pertenecen a un restaurante (panel maestro de Juan).
MASTER_PREFIXES = ("/admin/", "/static/", "/master/")


def _tenant_from_api_key(request):
    key = request.headers.get("X-API-Key")
    if not key:
        return None
    return Tenant.objects.filter(api_key=key, is_active=True).first()


def _tenant_from_host(request):
    host = request.get_host().split(":")[0].lower()
    base = settings.TENANT_BASE_DOMAIN.lower()
    if host in (base, f"www.{base}", "127.0.0.1", "localhost"):
        return None
    if not host.endswith("." + base):
        return None
    slug = host[: -(len(base) + 1)].split(".")[-1]
    if slug in ("www", "app", "api", "admin"):
        return None
    return Tenant.objects.filter(slug=slug, is_active=True).first()


def _tenant_from_user(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return None
    membership = getattr(user, "tenant_membership", None)
    if membership is None or not membership.tenant.is_active:
        return None
    return membership.tenant


def _tenant_from_session(request):
    """El superusuario no pertenece a ningún restaurante, pero puede entrar a
    cualquiera: al abrir una página con ?tenant=slug queda recordado en su
    sesión, para que también las llamadas a la API sepan cuál es."""
    user = getattr(request, "user", None)
    if user is None or not user.is_superuser:
        return None
    slug = request.session.get("tenant_activo")
    if not slug:
        return None
    return Tenant.objects.filter(slug=slug, is_active=True).first()


def _recordar_tenant_del_superusuario(request):
    slug = request.GET.get("tenant")
    user = getattr(request, "user", None)
    if not slug or user is None or not user.is_superuser:
        return None
    tenant = Tenant.objects.filter(slug=slug, is_active=True).first()
    if tenant is not None:
        request.session["tenant_activo"] = tenant.slug
    return tenant


def _tenant_from_debug_hint(request):
    if not settings.DEBUG:
        return None
    slug = request.GET.get("tenant") or request.headers.get("X-Tenant")
    if not slug:
        return None
    return Tenant.objects.filter(slug=slug, is_active=True).first()


class TenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tenant = None
        if not request.path.startswith(MASTER_PREFIXES):
            for resolver in (
                _tenant_from_api_key,
                _tenant_from_host,
                _tenant_from_user,
                _recordar_tenant_del_superusuario,
                _tenant_from_session,
                _tenant_from_debug_hint,
            ):
                tenant = resolver(request)
                if tenant is not None:
                    break

        request.tenant = tenant
        set_current_tenant(tenant)

        if tenant is None and request.path.startswith("/api/v1/") and not request.path.startswith(
            "/api/v1/ping"
        ):
            return JsonResponse(
                {"detail": "No se identificó el restaurante (falta X-API-Key o subdominio)."},
                status=400,
            )

        try:
            response = self.get_response(request)
        finally:
            set_current_tenant(None)
        return response
