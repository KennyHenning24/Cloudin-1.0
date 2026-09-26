"""POST /api/admin/import-menu/ — importar una semilla por la API (superadmin).

    curl -X POST https://<servidor>/api/admin/import-menu/ \
         -H "Authorization: Bearer $CLOUDIN_ADMIN_TOKEN" \
         -F seed=@cloudin/menu.seed.json -F assets=@assets.zip -F create_tenant=1

Multipart: `seed` (archivo JSON), `assets` (zip de site/, opcional), `create_tenant`,
`dry_run` y `invite` (1/0). El token se crea en el panel maestro y se guarda con
su huella: nunca en archivos del proyecto.
"""

import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.tenants.models import ApiToken

from .assets import SinFotos, Zip
from .semilla import SemillaInvalida
from .services import importar_semilla

MAX_SEMILLA = 2 * 1024 * 1024
MAX_ZIP = 60 * 1024 * 1024


def _si(valor) -> bool:
    return str(valor).lower() in ("1", "true", "si", "sí", "yes", "on")


@csrf_exempt  # se autentica con el token Bearer, no con la sesión
@require_POST
def import_menu(request):
    cabecera = request.headers.get("Authorization", "")
    token = cabecera[7:].strip() if cabecera.lower().startswith("bearer ") else ""
    if ApiToken.validar(token) is None:
        return JsonResponse({"detail": "Token inválido o revocado."}, status=401)

    archivo = request.FILES.get("seed")
    if archivo is None:
        return JsonResponse({"detail": "Falta el archivo «seed» (menu.seed.json)."}, status=400)
    if archivo.size > MAX_SEMILLA:
        return JsonResponse({"detail": "La semilla pesa más de 2 MB."}, status=400)
    try:
        datos = json.loads(archivo.read().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        return JsonResponse({"detail": f"La semilla no es un JSON válido: {e}"}, status=400)

    assets = SinFotos()
    if request.FILES.get("assets"):
        if request.FILES["assets"].size > MAX_ZIP:
            return JsonResponse({"detail": "El zip de fotos pesa más de 60 MB."}, status=400)
        try:
            assets = Zip(request.FILES["assets"])
        except Exception as e:
            return JsonResponse({"detail": f"El zip de fotos no se pudo abrir: {e}"}, status=400)

    try:
        resumen = importar_semilla(datos, assets, crear_restaurante=_si(request.POST.get("create_tenant", "0")),
                                   aplicar=not _si(request.POST.get("dry_run", "0")),
                                   invitar=_si(request.POST.get("invite", "1")))
    except SemillaInvalida as e:
        return JsonResponse({"detail": "La semilla tiene errores.", "errors": e.errores}, status=400)
    return JsonResponse(resumen.como_dict(), status=201 if resumen.creado and resumen.aplicado else 200,
                        json_dumps_params={"ensure_ascii": False})
