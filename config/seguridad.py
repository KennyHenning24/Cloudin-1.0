"""Cabeceras de seguridad para todas las respuestas.

- Content-Security-Policy: el navegador solo carga scripts de este sitio y de
  cdn.jsdelivr.net (Chart.js), fuentes de Google, y solo habla con este mismo
  servidor. Si alguien lograra meter HTML en una pantalla, no podría cargar un
  script de afuera ni mandarle datos a otro servidor.
- Permissions-Policy: la página no pide cámara, micrófono ni ubicación.
- Las pantallas con sesión no se guardan en caché: después de «Salir», el botón
  «atrás» del navegador no muestra datos del restaurante.
"""

CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com data:",
    "img-src 'self' data: blob: https:",
    "connect-src 'self'",
    "frame-src 'self'",
    "frame-ancestors 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "worker-src 'self'",
    "manifest-src 'self'",
])
PERMISOS = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
PRIVADAS = ("/panel/", "/master/", "/admin/", "/mesero/", "/legal/aceptar/")


class CabecerasSeguridad:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        tipo = response.get("Content-Type", "")
        if tipo.startswith("text/html"):
            response.setdefault("Content-Security-Policy", CSP)
            response.setdefault("Permissions-Policy", PERMISOS)
            if request.path.startswith(PRIVADAS) and getattr(request, "user", None) is not None \
                    and request.user.is_authenticated:
                response["Cache-Control"] = "no-store, private"
        return response
