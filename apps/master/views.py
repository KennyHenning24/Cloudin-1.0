"""Panel maestro: alta de restaurantes y de sus usuarios.

Solo para el superusuario (Juan). Cada alta deja al restaurante con su base de
datos creada, migrada y con credenciales listas para entregar.
"""

from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.tenants.crypto import hay_llave
from apps.tenants.models import Tenant, TenantMembership
from apps.tenants.services import (
    aprovisionar,
    cambiar_password,
    crear_restaurante,
    crear_usuario,
    enlace_panel,
)

from .forms import EmpleadoForm, RestauranteForm

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
                site_url=form.cleaned_data["site_url"],
                legal_name=form.cleaned_data["legal_name"],
                nit=form.cleaned_data["nit"],
                address=form.cleaned_data["address"],
                city=form.cleaned_data["city"],
                phone=form.cleaned_data["phone"],
            )
            # Crea el archivo/base del restaurante y le corre las migraciones.
            aprovisionar(tenant)
            user, password = crear_usuario(
                tenant,
                form.cleaned_data["admin_usuario"],
                rol=TenantMembership.ROLE_ADMIN,
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
        },
    )


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
