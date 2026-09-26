"""Operaciones de alta: crear restaurantes y sus usuarios.

Todo lo que hace el panel maestro pasa por aquí, para que el comando de consola
y la interfaz web se comporten igual.
"""

import secrets

from django.conf import settings
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from .crypto import cifrar, hay_llave
from .models import Tenant, TenantMembership
from .provisioning import provision_tenant

# Sin caracteres ambiguos (0/O, 1/l/I): estas contraseñas se dictan por teléfono
# o se copian a mano en la caja del restaurante.
ALFABETO = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generar_password(largo: int = 10) -> str:
    return "".join(secrets.choice(ALFABETO) for _ in range(largo))


def nombre_usuario_completo(tenant: Tenant, usuario: str) -> str:
    """Los usuarios son únicos en todo el sistema, así que se prefijan con el
    restaurante: 'carlos' en Cultura Brisket es 'culturabrisket.carlos'."""
    usuario = usuario.strip().lower()
    prefijo = f"{tenant.slug}."
    return usuario if usuario.startswith(prefijo) else prefijo + usuario


def enlace_panel(tenant: Tenant) -> str:
    """El enlace que se le comparte al restaurante para entrar a su panel."""
    if settings.CLOUDIN_PUBLIC_URL:
        return f"{settings.CLOUDIN_PUBLIC_URL}/panel/login/"
    if settings.DEBUG:
        return f"http://localhost:8000/panel/login/?tenant={tenant.slug}"
    return f"https://{tenant.domain}/panel/login/"


@transaction.atomic(using="default")
def crear_restaurante(*, nombre, slug, **datos) -> Tenant:
    """Crea el restaurante en la base de control. No toca todavía su base."""
    return Tenant.objects.create(name=nombre, slug=slug, **datos)


def aprovisionar(tenant: Tenant) -> str:
    """Crea la base de datos del restaurante y le aplica las migraciones."""
    return provision_tenant(tenant)


def crear_usuario(
    tenant: Tenant,
    usuario: str,
    *,
    rol: str = TenantMembership.ROLE_ADMIN,
    nombre: str = "",
    correo: str = "",
    password: str | None = None,
) -> tuple[User, str]:
    """Crea un empleado del restaurante. Devuelve (usuario, contraseña en claro).

    La contraseña solo existe en claro en este momento: en la base queda su
    hash. Si se pierde, se genera una nueva.
    """
    username = nombre_usuario_completo(tenant, usuario)
    password = password or generar_password()
    with transaction.atomic(using="default"):
        user = User.objects.create_user(
            username=username, password=password, first_name=nombre[:150], email=correo
        )
        TenantMembership.objects.create(
            user=user,
            tenant=tenant,
            role=rol,
            password_cifrada=cifrar(password) if hay_llave() else "",
            password_actualizada=timezone.now(),
        )
    return user, password


def cambiar_password(user: User, password: str | None = None) -> str:
    """Cambia la contraseña de un usuario. Si no se da una, se genera.

    Guarda el hash (para el login) y la copia cifrada (para que el panel
    maestro pueda volver a mostrarla).
    """
    password = password or generar_password()
    with transaction.atomic(using="default"):
        user.set_password(password)
        user.save(update_fields=["password"])
        membership = TenantMembership.objects.filter(user=user).first()
        if membership:
            membership.password_cifrada = cifrar(password) if hay_llave() else ""
            membership.password_actualizada = timezone.now()
            membership.save(update_fields=["password_cifrada", "password_actualizada"])
    return password


# Nombre anterior, mantenido para el código que lo usaba.
reiniciar_password = cambiar_password
