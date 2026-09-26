from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsTenantStaff(BasePermission):
    """Solo usuarios logueados que pertenezcan al restaurante de la petición.

    Además, mientras no haya turno abierto el panel es de solo lectura: ninguna
    petición que cambie algo (pedidos, mesas, menú, cuentas) pasa.
    """

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

        if request.method not in SAFE_METHODS:
            from apps.shifts.services import MENSAJE_SIN_TURNO, turno_actual

            if turno_actual() is None:
                self.message = MENSAJE_SIN_TURNO
                self.code = "sin_turno"
                return False
        return True


class IsTenantAdminParaEscribir(IsTenantStaff):
    """Leer: cualquiera del restaurante. Cambiar la carta o las mesas: solo el
    administrador (un cajero no puede, ni siquiera llamando a la API a mano)."""

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        if request.method in SAFE_METHODS or request.user.is_superuser:
            return True
        from apps.tenants.models import TenantMembership

        membership = getattr(request.user, "tenant_membership", None)
        if membership is None or membership.role != TenantMembership.ROLE_ADMIN:
            self.message = "Solo el administrador del restaurante puede cambiar la carta y las mesas."
            return False
        return True
