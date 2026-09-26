"""Meseros en el panel del administrador: cómo se toman los pedidos y quién.

Aquí se decide el modo del restaurante (autoservicio, meseros o ambos) y se
administran las cuentas de los meseros. Las cuentas son de la tablet, no del
panel: crear un mesero no le da acceso a nada de esta pantalla.
"""

from decimal import Decimal

from django.contrib import messages
from django.core.cache import cache
from django.http import JsonResponse
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.orders.models import Order, OrderItem
from apps.tenants.models import Tenant
from apps.waiters.forms import MeseroForm
from apps.waiters.models import Mesero

from .views import _qr_data_uri, panel_view

LINEA = ExpressionWrapper(F("unit_price") * F("quantity"),
                          output_field=DecimalField(max_digits=14, decimal_places=2))


@panel_view(solo_admin=True)
def meseros(request):
    tenant = request.tenant
    enlace = request.build_absolute_uri(reverse("mesero:app", kwargs={"slug": tenant.slug}))

    if request.method == "POST" and request.POST.get("accion") == "modo":
        modo = request.POST.get("modo")
        if modo in dict(Tenant.MODOS_SERVICIO):
            tenant.modo_servicio = modo
            tenant.save(update_fields=["modo_servicio"])
            textos = {
                Tenant.AUTOSERVICIO: "Solo autoservicio: la app de meseros queda apagada.",
                Tenant.MESEROS: "Solo meseros: el QR ya no recibe pedidos del cliente.",
                Tenant.MIXTO: "QR y meseros funcionando a la vez.",
            }
            messages.success(request, textos[modo])
        return redirect("panel:meseros")

    hoy = timezone.localdate()
    ventas_hoy = {
        fila["order__mesero"]: fila
        for fila in OrderItem.objects.filter(
            order__mesero__isnull=False, order__created_at__date=hoy,
        ).exclude(order__status=Order.STATUS_CANCELLED)
        .values("order__mesero")
        .annotate(total=Sum(LINEA), pedidos=Count("order", distinct=True))
    }
    equipo = []
    for m in Mesero.objects.select_related("empleado"):
        datos = ventas_hoy.get(m.id, {})
        equipo.append({
            "m": m,
            "pedidos": datos.get("pedidos", 0),
            "ventas": datos.get("total") or Decimal("0"),
        })

    return render(request, "panel/meseros.html", {
        "seccion": "meseros",
        "equipo": equipo,
        "activos": sum(1 for e in equipo if e["m"].activo),
        "ventas_hoy": sum((e["ventas"] for e in equipo), Decimal("0")),
        "pedidos_hoy": sum(e["pedidos"] for e in equipo),
        "enlace": enlace,
        "qr": _qr_data_uri(enlace),
        "MODOS": Tenant.MODOS_SERVICIO,
        "clave_confirmada": request.session.get(f"meseros_clave_ok:{tenant.slug}", 0)
        > timezone.now().timestamp(),
    })


@panel_view(solo_admin=True)
def mesero_nuevo(request):
    form = MeseroForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        mesero = form.save()
        messages.success(
            request,
            f"{mesero.nombre} ya puede entrar a la tablet con el usuario «{mesero.usuario}».",
        )
        return redirect("panel:meseros")
    return render(request, "panel/mesero_form.html",
                  {"seccion": "meseros", "form": form, "es_nuevo": True})


@panel_view(solo_admin=True)
def mesero_editar(request, mesero_id):
    mesero = get_object_or_404(Mesero, pk=mesero_id)
    form = MeseroForm(request.POST or None, instance=mesero)
    if request.method == "POST" and form.is_valid():
        cambio_clave = bool(form.cleaned_data.get("clave"))
        form.save()
        messages.success(
            request,
            f"{mesero.nombre} actualizado."
            + (" Su sesión en la tablet se cerró: entra con la contraseña nueva." if cambio_clave else ""),
        )
        return redirect("panel:meseros")
    return render(request, "panel/mesero_form.html",
                  {"seccion": "meseros", "form": form, "mesero": mesero})


@panel_view(solo_admin=True)
@require_POST
def mesero_activo(request, mesero_id):
    mesero = get_object_or_404(Mesero, pk=mesero_id)
    mesero.activo = not mesero.activo
    mesero.save(update_fields=["activo"])
    messages.success(
        request,
        f"{mesero.nombre} quedó {'activo' if mesero.activo else 'inactivo: ya no puede entrar a la tablet'}.",
    )
    return redirect("panel:meseros")


# Ver la contraseña de un mesero pide la contraseña del panel. Una vez confirmada,
# se pueden ver las demás durante unos minutos sin volver a escribirla.
MINUTOS_CONFIRMADO = 5
INTENTOS_CLAVE = 5


@panel_view(solo_admin=True)
@require_POST
def mesero_ver_clave(request, mesero_id):
    mesero = get_object_or_404(Mesero, pk=mesero_id)
    llave_sesion = f"meseros_clave_ok:{request.tenant.slug}"
    llave_intentos = f"meseros_clave_intentos:{request.user.pk}"
    ahora = timezone.now().timestamp()

    confirmado = request.session.get(llave_sesion, 0) > ahora
    if not confirmado:
        intentos = cache.get(llave_intentos, 0)
        if intentos >= INTENTOS_CLAVE:
            return JsonResponse({"ok": False, "detail": "Demasiados intentos. Espera 10 minutos."},
                                status=429)
        if not request.user.check_password(request.POST.get("clave_panel") or ""):
            cache.set(llave_intentos, intentos + 1, 600)
            return JsonResponse({"ok": False, "pide_clave": True,
                                 "detail": "Esa no es tu contraseña del panel."}, status=403)
        cache.delete(llave_intentos)
        request.session[llave_sesion] = ahora + MINUTOS_CONFIRMADO * 60

    clave = mesero.clave_visible()
    if clave is None:
        return JsonResponse({
            "ok": False,
            "detail": "Esta contraseña se creó antes de que Cloudin pudiera mostrarlas. "
                      "Ponle una nueva en «Editar» y desde ahí ya se podrá ver.",
        }, status=404)
    return JsonResponse({"ok": True, "clave": clave, "minutos": MINUTOS_CONFIRMADO})

