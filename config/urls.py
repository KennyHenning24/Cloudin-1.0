from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from apps.panel import legal
from apps.panel.seguridad import LoginAdminSeguro
from apps.public_menu.views import raiz

admin.site.site_header = "Cloudin — Panel maestro"
admin.site.site_title = "Cloudin"
admin.site.index_title = "Administración de restaurantes"

urlpatterns = [
    # En <slug>.<dominio>/ se ve el menú; sin restaurante, lleva al panel.
    path("", raiz, name="raiz"),
    # Menú público: API cloudin.menu/v1 y menú de respaldo (/m/<slug>/).
    path("", include("apps.public_menu.urls")),
    # El login del panel maestro, con límite de intentos (va antes que el del admin).
    path("admin/login/", LoginAdminSeguro.as_view(), name="admin-login-seguro"),
    path("admin/", admin.site.urls),
    path("master/", include("apps.master.urls")),
    path("api/v1/", include("apps.api.urls")),
    path("panel/", include("apps.panel.urls")),
    path("mesero/", include("apps.waiters.urls")),
    # Términos, privacidad y la política de datos de cada restaurante
    path("legal/terminos/", legal.terminos, name="legal-terminos"),
    path("legal/privacidad/", legal.privacidad, name="legal-privacidad"),
    path("legal/aceptar/", legal.aceptar, name="legal-aceptar"),
    path("legal/r/<slug:slug>/datos/", legal.datos_restaurante, name="legal-datos"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
