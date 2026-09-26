"""Términos y condiciones, política de privacidad y su aceptación.

- Los usuarios del panel aceptan los términos y la política una sola vez por
  versión. Sin aceptarlos no pueden usar Cloudin: «No acepto» cierra la sesión.
- Cada restaurante tiene además una página pública con su política de
  tratamiento de datos para los comensales (Ley 1581 de 2012). Es la que
  enlazan los formularios de reserva y pedido de su sitio web.
"""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from apps.tenants.models import AceptacionLegal, Tenant


def _datos_legales():
    return {
        "version": settings.LEGAL_VERSION,
        "responsable": settings.LEGAL_RESPONSABLE,
        "nit": settings.LEGAL_NIT,
        "correo": settings.LEGAL_CORREO,
        "direccion": settings.LEGAL_DIRECCION,
        "ciudad": settings.LEGAL_CIUDAD,
    }


def llave_sesion() -> str:
    return f"legal_ok:{settings.LEGAL_VERSION}"


def ya_acepto(request) -> bool:
    """Si el usuario aceptó la versión vigente. Se recuerda en la sesión para no
    consultar la base en cada pantalla."""
    user = request.user
    if not user.is_authenticated or user.is_superuser:
        return True
    if request.session.get(llave_sesion()):
        return True
    acepto = AceptacionLegal.objects.filter(user=user, version=settings.LEGAL_VERSION).exists()
    if acepto:
        request.session[llave_sesion()] = True
    return acepto


def terminos(request):
    return render(request, "legal/terminos.html", {"legal": _datos_legales()})


def privacidad(request):
    return render(request, "legal/privacidad.html", {"legal": _datos_legales()})


def datos_restaurante(request, slug):
    """La política de datos de un restaurante, para quien reserva o pide en su sitio."""
    tenant = Tenant.objects.filter(slug=slug, is_active=True).first()
    if tenant is None:
        raise Http404("Restaurante no encontrado")
    whatsapp = ""
    try:
        from apps.business.models import RestaurantSettings
        from apps.tenants.context import tenant_context

        with tenant_context(tenant):
            whatsapp = RestaurantSettings.load().whatsapp
    except Exception:  # noqa: BLE001 — la página se muestra igual sin el WhatsApp
        whatsapp = ""
    return render(request, "legal/datos_restaurante.html",
                  {"legal": _datos_legales(), "r": tenant, "whatsapp": whatsapp})


@login_required
def aceptar(request):
    siguiente = request.GET.get("next") or request.POST.get("next") or "/panel/"
    if not url_has_allowed_host_and_scheme(siguiente, allowed_hosts={request.get_host()}):
        siguiente = "/panel/"
    if ya_acepto(request):
        return redirect(siguiente)

    error = ""
    if request.method == "POST":
        if request.POST.get("accion") == "rechazar":
            logout(request)
            messages.warning(
                request,
                "Para usar Cloudin es necesario aceptar los términos y la política de privacidad. "
                "Cuando quieras, vuelve a entrar y acéptalos.",
            )
            return redirect("panel:login")
        if request.POST.get("terminos") and request.POST.get("privacidad"):
            ip = (request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
                  or request.META.get("REMOTE_ADDR"))
            AceptacionLegal.objects.get_or_create(
                user=request.user, version=settings.LEGAL_VERSION,
                defaults={"ip": ip or None, "navegador": request.META.get("HTTP_USER_AGENT", "")[:300]},
            )
            request.session[llave_sesion()] = True
            messages.success(request, "¡Listo! Gracias por aceptar. Ya puedes usar Cloudin.")
            return redirect(siguiente)
        error = "Marca las dos casillas para continuar."
    return render(request, "legal/aceptar.html",
                  {"legal": _datos_legales(), "next": siguiente, "error": error})
