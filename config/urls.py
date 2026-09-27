from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.importer.views import import_menu
from apps.panel import legal
from apps.panel.seguridad import LoginAdminSeguro
from apps.public_menu.views import raiz


def solo_superusuario(vista):
    """La documentación de la API: con DEBUG, o para el superusuario en producción.
    Swagger carga sus archivos de cdn.jsdelivr.net: se le da una CSP a su medida."""
    from functools import wraps

    from django.http import Http404

    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        if not (settings.DEBUG or (request.user.is_authenticated and request.user.is_superuser)):
            raise Http404
        respuesta = vista(request, *args, **kwargs)
        respuesta["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: https:; "
            "connect-src 'self'; frame-ancestors 'self'")
        return respuesta

    return envoltura

admin.site.site_header = "Cloudin — Panel maestro"
admin.site.site_title = "Cloudin"
admin.site.index_title = "Administración de restaurantes"

urlpatterns = [
    # En <slug>.<dominio>/ se ve el menú; sin restaurante, lleva al panel.
    path("", raiz, name="raiz"),
    # API pública del menú (cloudin.menu/v1). El menú lo pone cada restaurante en su sitio.
    path("", include("apps.public_menu.urls")),
    # El login del panel maestro, con límite de intentos (va antes que el del admin).
    path("admin/login/", LoginAdminSeguro.as_view(), name="admin-login-seguro"),
    path("admin/", admin.site.urls),
    path("master/", include("apps.master.urls")),
    path("api/v1/", include("apps.api.urls")),
    # Superadmin: importar la semilla de un menú (Bearer) y la documentación de la API.
    path("api/admin/import-menu/", import_menu, name="api-import-menu"),
    path("api/schema/", solo_superusuario(SpectacularAPIView.as_view()), name="api-schema"),
    path("api/docs/", solo_superusuario(SpectacularSwaggerView.as_view(url_name="api-schema")), name="api-docs"),
    path("panel/", include("apps.panel.urls")),
    path("mesero/", include("apps.waiters.urls")),
    # Términos, privacidad y la política de datos de cada restaurante
    path("legal/terminos/", legal.terminos, name="legal-terminos"),
    path("legal/privacidad/", legal.privacidad, name="legal-privacidad"),
    path("legal/aceptar/", legal.aceptar, name="legal-aceptar"),
    path("legal/r/<slug:slug>/datos/", legal.datos_restaurante, name="legal-datos"),
]

if settings.FOTOS_EN_LA_BASE:
    # Plan gratis: las fotos viven en la base de datos (apps/archivos).
    from apps.archivos.views import servir

    urlpatterns += [re_path(r"^media/(?P<nombre>.+)$", servir, name="archivo")]
elif settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
