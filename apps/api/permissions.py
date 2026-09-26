from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsTenantStaff(BasePermission):
    """Solo usuarios logueados que pertenezcan al restaurante de la petición."""

    message = "No tiene acceso a este restaurante."

    def has_permission(self, request, view):
        user = request.user
        tenant = getattr(request, "tenant", None)
        if not user.is_authenticated or tenant is None:
            return False
        if user.is_superuser:
            # Modo soporte: confirmó su contraseña para este restaurante hace poco.
            from apps.panel.seguridad import soporte_vigente

            if not soporte_vigente(request, tenant):
                self.message = "Confirma tu contraseña para entrar en modo soporte."
                return False
        else:
            membership = getattr(user, "tenant_membership", None)
            if membership is None or membership.tenant_id != tenant.id:
                return False
        return True


def _es_del_restaurante(permiso, request) -> bool:
    """Usuario del restaurante de la petición, o superusuario en modo soporte."""
    user = request.user
    tenant = getattr(request, "tenant", None)
    if not user.is_authenticated or tenant is None:
        return False
    if user.is_superuser:
        from apps.panel.seguridad import soporte_vigente

        if not soporte_vigente(request, tenant):
            permiso.message = "Confirma tu contraseña para entrar en modo soporte."
            return False
        return True
    membership = getattr(user, "tenant_membership", None)
    return membership is not None and membership.tenant_id == tenant.id


def _administra(request) -> bool:
    if request.user.is_superuser:
        return True
    membership = getattr(request.user, "tenant_membership", None)
    return membership is not None and membership.es_admin


class LeeLaCarta(BasePermission):
    """Menú, ajustes y QR: cualquiera del restaurante puede leer."""

    message = "No tienes acceso a este restaurante."

    def has_permission(self, request, view):
        return _es_del_restaurante(self, request)


class AdministraLaCarta(LeeLaCarta):
    """Leer: todo el equipo. Crear, cambiar, reordenar o borrar: dueño o administrador."""

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        if request.method in SAFE_METHODS or _administra(request):
            return True
        self.message = "Solo el dueño o el administrador pueden cambiar la carta."
        return False


class PuedeAgotar(LeeLaCarta):
    """Marcar agotado o disponible: todo el equipo (el cajero lo hace en pleno servicio)."""


class IsTenantAdminParaEscribir(IsTenantStaff):
    """Leer: cualquiera del restaurante. Cambiar la carta o las mesas: solo el
    administrador (un cajero no puede, ni siquiera llamando a la API a mano)."""

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        if request.method in SAFE_METHODS or request.user.is_superuser:
            return True
        membership = getattr(request.user, "tenant_membership", None)
        if membership is None or not membership.es_admin:
            self.message = "Solo el administrador del restaurante puede cambiar la carta y las mesas."
            return False
        return True
