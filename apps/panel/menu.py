"""La carta de antes en el panel: eliminar desde el menú rápido e importar la
carta desde el sitio web del restaurante.

La ficha del producto ahora es el editor de Personalizar (duenio.py); las rutas
viejas llevan allá para no romper enlaces guardados.
"""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.catalog.formato import extraer, importar, leer_fuente
from apps.catalog.models import Category, Product

from .views import panel_view


def _volver():
    return reverse("panel:configuracion") + "?paso=menu"


@panel_view(solo_admin=True)
def producto_nuevo(request):
    """La ficha de antes: ahora los productos se crean en el editor de Personalizar."""
    destino = reverse("panel:carta-producto-nuevo")
    categoria = Category.objects.filter(pk=request.GET.get("categoria") or 0).first() \
        if str(request.GET.get("categoria", "")).isdigit() else None
    return redirect(f"{destino}?categoria={categoria.uuid}" if categoria else destino)


@panel_view(solo_admin=True)
def producto_editar(request, producto_id):
    """Los enlaces viejos (Configuración → Menú) abren el editor nuevo."""
    producto = get_object_or_404(Product, pk=producto_id, eliminado=False)
    return redirect("panel:carta-producto", producto=producto.uuid)


@panel_view(solo_admin=True)
@require_POST
def producto_eliminar(request, producto_id):
    """Saca el producto de la carta en todas partes."""
    producto = get_object_or_404(Product, pk=producto_id, eliminado=False)
    producto.eliminado = True
    producto.is_available = False
    producto.save(update_fields=["eliminado", "is_available"])
    messages.success(
        request,
        f"«{producto.name}» salió de la carta: ya no aparece en el sitio, en la app de meseros ni en el QR. "
        "Si fue un error, lo restauras abajo en «Eliminados».",
    )
    return redirect(_volver())


@panel_view(solo_admin=True)
def menu_importar(request):
    """Trae la carta del sitio: primero muestra qué va a pasar, después importa."""
    tenant = request.tenant
    sugerida = tenant.menu_fuente or (
        f"{tenant.site_url.rstrip('/')}/cloudin-menu.json" if tenant.site_url else "")
    contexto = {"seccion": "config", "fuente": sugerida, "resumen": None, "aplicado": False}

    if request.method == "POST":
        fuente = (request.POST.get("fuente") or "").strip()
        archivo = request.FILES.get("archivo")
        aplicar = request.POST.get("accion") == "importar"
        # Un archivo subido para revisar se guarda en la sesión: el navegador no lo
        # vuelve a mandar cuando se pulsa «Importar ahora».
        llave = f"menu_importar:{tenant.slug}"
        contexto["fuente"] = fuente
        try:
            if archivo:
                if archivo.size > 2 * 1024 * 1024:
                    raise ValidationError("El archivo pesa más de 2 MB.")
                datos = extraer(archivo.read().decode("utf-8", errors="replace"))
                base = fuente if fuente.startswith(("http://", "https://")) else ""
                request.session[llave] = datos
            elif aplicar and request.session.get(llave):
                datos = request.session[llave]
                base = fuente if fuente.startswith(("http://", "https://")) else ""
            elif fuente:
                request.session.pop(llave, None)  # se revisa la dirección, no un archivo viejo
                datos = leer_fuente(fuente)
                base = fuente
            else:
                raise ValidationError("Escribe la dirección de la carta o sube el archivo.")
            resumen = importar(datos, base, aplicar=aplicar)
            if aplicar:
                request.session.pop(llave, None)
        except ValidationError as e:
            messages.warning(request, e.messages[0])
            return render(request, "panel/menu_importar.html", contexto)

        if fuente.startswith(("http://", "https://")) and fuente != tenant.menu_fuente:
            tenant.menu_fuente = fuente[:500]
            tenant.save(update_fields=["menu_fuente"])
        contexto.update(resumen=resumen, aplicado=aplicar, restaurante=datos.get("restaurante", ""))
        if aplicar:
            messages.success(
                request,
                f"Carta importada: {resumen['productos_nuevos']} producto(s) nuevo(s), "
                f"{resumen['productos_completados']} completado(s).",
            )
    return render(request, "panel/menu_importar.html", contexto)
