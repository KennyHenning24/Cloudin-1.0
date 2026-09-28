"""Panel maestro: alta de restaurantes y de sus usuarios.

Solo para el superusuario (Juan). Cada alta deja al restaurante con su base de
datos creada, migrada y con credenciales listas para entregar.
"""

from datetime import datetime

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.core.cache import cache
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.tenants.crypto import hay_llave
from apps.tenants.models import ApiToken, Tenant, TenantMembership
from apps.tenants.services import (
    aprovisionar,
    cambiar_password,
    crear_restaurante,
    crear_usuario,
    enlace_panel,
)

from .forms import EmpleadoForm, MenuDigitalForm, RestauranteForm

solo_superusuario = user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")


def _guardar_credencial(request, *, tenant, username, password, titulo):
    """Las contraseñas se muestran una sola vez, al volver de un POST."""
    request.session["credencial"] = {
        "titulo": titulo,
        "usuario": username,
        "password": password,
        "enlace": enlace_panel(tenant),
        "restaurante": tenant.name,
    }


@solo_superusuario
def home(request):
    restaurantes = Tenant.objects.annotate(empleados=Count("memberships")).order_by("-created_at")
    return render(request, "master/home.html", {"restaurantes": restaurantes, "seccion": "restaurantes"})


@solo_superusuario
def restaurante_nuevo(request):
    if request.method == "POST":
        form = RestauranteForm(request.POST)
        if form.is_valid():
            tenant = crear_restaurante(
                nombre=form.cleaned_data["name"],
                slug=form.cleaned_data["slug"],
                menu_page=form.cleaned_data["menu_page"],
                legal_name=form.cleaned_data["legal_name"],
                nit=form.cleaned_data["nit"],
                address=form.cleaned_data["address"],
                city=form.cleaned_data["city"],
                phone=form.cleaned_data["phone"],
            )
            # Crea el archivo/base del restaurante y le corre las migraciones.
            aprovisionar(tenant)
            # El primer usuario es el dueño: administra todo y maneja al equipo.
            user, password = crear_usuario(
                tenant,
                form.cleaned_data["admin_usuario"],
                rol=TenantMembership.ROLE_OWNER,
                nombre=form.cleaned_data["admin_nombre"],
                correo=form.cleaned_data["admin_correo"],
            )
            _guardar_credencial(
                request,
                tenant=tenant,
                username=user.username,
                password=password,
                titulo=f"{tenant.name} quedó creado",
            )
            messages.success(
                request, f"Base de datos «{tenant.db_name}» creada y migrada."
            )
            return redirect("master:restaurante", slug=tenant.slug)
    else:
        form = RestauranteForm()
    return render(request, "master/restaurante_nuevo.html", {"form": form, "seccion": "nuevo"})


def _menu_digital(request, tenant) -> dict:
    """Lo de la tarjeta «Menú digital»: la página registrada, cuándo se pidió la carta
    por última vez y los datos que lleva el código del menú."""
    servidor = settings.CLOUDIN_PUBLIC_URL or request.build_absolute_uri("/").rstrip("/")
    visto = cache.get(f"menu_visto:{tenant.slug}")
    return {
        "menu_form": MenuDigitalForm(initial={
            "pagina": tenant.menu_page, "otros": "\n".join(tenant.allowed_origins or [])}),
        "servidor": servidor,
        "carta": f"{servidor}/api/public/{tenant.slug}/menu/",
        "menu_visto": datetime.fromtimestamp(visto, tz=timezone.get_current_timezone()) if visto else None,
    }


@solo_superusuario
def restaurante(request, slug):
    tenant = get_object_or_404(Tenant, slug=slug)
    return render(
        request,
        "master/restaurante.html",
        {
            "t": tenant,
            "empleados": tenant.memberships.select_related("user").order_by("-role", "id"),
            "form": EmpleadoForm(tenant=tenant, initial={"rol": TenantMembership.ROLE_STAFF}),
            "enlace": enlace_panel(tenant),
            "credencial": request.session.pop("credencial", None),
            "hay_llave": hay_llave(),
            "seccion": "restaurantes",
            **_menu_digital(request, tenant),
        },
    )


@solo_superusuario
@require_POST
def restaurante_menu(request, slug):
    """Registra la página del menú digital: de ahí salen los QR y es la que puede pedir."""
    tenant = get_object_or_404(Tenant, slug=slug)
    form = MenuDigitalForm(request.POST)
    if not form.is_valid():
        for errores in form.errors.values():
            messages.warning(request, errores[0])
        return redirect("master:restaurante", slug=tenant.slug)
    tenant.menu_page = form.cleaned_data["pagina"]
    tenant.allowed_origins = form.cleaned_data["otros"]
    tenant.save(update_fields=["menu_page", "allowed_origins"])
    if tenant.menu_page:
        messages.success(request, f"Menú de {tenant.name} registrado: los QR ya apuntan a "
                                  f"{tenant.menu_page} y esa página puede enviar pedidos.")
    else:
        messages.warning(request, f"{tenant.name} quedó sin página del menú: no hay QR ni pedidos.")
    return redirect("master:restaurante", slug=tenant.slug)


@solo_superusuario
def empleado_nuevo(request, slug):
    tenant = get_object_or_404(Tenant, slug=slug)
    form = EmpleadoForm(request.POST or None, tenant=tenant)
    if request.method == "POST" and form.is_valid():
        user, password = crear_usuario(
            tenant,
            form.cleaned_data["usuario"],
            rol=form.cleaned_data["rol"],
            nombre=form.cleaned_data["nombre"],
            correo=form.cleaned_data.get("correo", ""),
        )
        _guardar_credencial(
            request,
            tenant=tenant,
            username=user.username,
            password=password,
            titulo=f"Usuario creado para {tenant.name}",
        )
        return redirect("master:restaurante", slug=tenant.slug)

    return render(
        request,
        "master/restaurante.html",
        {
            "t": tenant,
            "empleados": tenant.memberships.select_related("user").order_by("-role", "id"),
            "form": form,
            "enlace": enlace_panel(tenant),
            "credencial": None,
            "hay_llave": hay_llave(),
            "seccion": "restaurantes",
            **_menu_digital(request, tenant),
        },
    )


@solo_superusuario
@require_POST
def empleado_password(request, slug, user_id):
    """Cambia la contraseña: la que escriba Juan, o una generada si viene vacía."""
    tenant = get_object_or_404(Tenant, slug=slug)
    membership = get_object_or_404(TenantMembership, tenant=tenant, user_id=user_id)

    nueva = (request.POST.get("password") or "").strip()
    if nueva and len(nueva) < 6:
        messages.warning(request, "La contraseña debe tener al menos 6 caracteres.")
        return redirect("master:restaurante", slug=tenant.slug)

    password = cambiar_password(membership.user, nueva or None)
    _guardar_credencial(
        request,
        tenant=tenant,
        username=membership.user.username,
        password=password,
        titulo="Contraseña actualizada",
    )
    return redirect("master:restaurante", slug=tenant.slug)


@solo_superusuario
@require_POST
def empleado_eliminar(request, slug, user_id):
    tenant = get_object_or_404(Tenant, slug=slug)
    membership = get_object_or_404(TenantMembership, tenant=tenant, user_id=user_id)
    nombre = membership.user.username
    membership.user.delete()  # la membresía se borra en cascada
    messages.success(request, f"Usuario {nombre} eliminado.")
    return redirect("master:restaurante", slug=tenant.slug)


@solo_superusuario
@require_POST
def restaurante_activo(request, slug):
    tenant = get_object_or_404(Tenant, slug=slug)
    tenant.is_active = not tenant.is_active
    tenant.save(update_fields=["is_active"])
    estado = "activado" if tenant.is_active else "desactivado"
    messages.success(request, f"{tenant.name} {estado}.")
    return redirect("master:restaurante", slug=tenant.slug)


@solo_superusuario
@require_POST
def restaurante_api_key(request, slug):
    tenant = get_object_or_404(Tenant, slug=slug)
    tenant.rotate_api_key()
    messages.warning(
        request,
        "API key regenerada. La web del restaurante deja de funcionar hasta que se actualice.",
    )
    return redirect("master:restaurante", slug=tenant.slug)


@solo_superusuario
def tokens(request):
    """Tokens personales para la API de superadmin (importar menús). El token en claro
    se muestra una sola vez; en la base queda solo su huella."""
    nuevo = request.session.pop("token_nuevo", None)
    if request.method == "POST":
        nombre = (request.POST.get("nombre") or "").strip()[:80]
        if not nombre:
            messages.warning(request, "Ponle un nombre al token (para qué o en qué equipo lo usas).")
        else:
            _, token = ApiToken.crear(request.user, nombre)
            request.session["token_nuevo"] = {"nombre": nombre, "token": token}
        return redirect("master:tokens")
    return render(request, "master/tokens.html", {
        "tokens": ApiToken.objects.select_related("user").all(), "nuevo": nuevo, "seccion": "tokens"})


@solo_superusuario
@require_POST
def token_revocar(request, token_id):
    registro = get_object_or_404(ApiToken, pk=token_id, revoked_at__isnull=True)
    registro.revoked_at = timezone.now()
    registro.save(update_fields=["revoked_at"])
    messages.success(request, f"Token «{registro.name}» revocado: ya no sirve.")
    return redirect("master:tokens")
