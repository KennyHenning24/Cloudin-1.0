from django.contrib import admin, messages
from django.utils.html import format_html

from .models import ApiToken, Tenant, TenantMembership
from .provisioning import provision_tenant


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "plan", "domain_link", "is_active", "provisioned_at")
    list_filter = ("is_active", "plan")
    search_fields = ("name", "slug", "nit")
    readonly_fields = ("api_key", "db_name", "provisioned_at", "created_at")
    actions = ("accion_aprovisionar",)
    fieldsets = (
        (None, {"fields": ("name", "slug", "plan", "is_active")}),
        ("Datos fiscales", {"fields": ("legal_name", "nit", "address", "city", "phone")}),
        ("Sitio web y menú", {"fields": ("site_url", "allowed_origins", "menu_page", "table_page_path",
                                         "menu_fuente", "modo_servicio")}),
        ("Técnico", {"fields": ("api_key", "db_name", "provisioned_at", "created_at")}),
    )

    @admin.display(description="Dominio")
    def domain_link(self, obj):
        return format_html("<code>{}</code>", obj.domain)

    @admin.action(description="Aprovisionar (crear base y migrar)")
    def accion_aprovisionar(self, request, queryset):
        for tenant in queryset:
            provision_tenant(tenant)
            self.message_user(
                request, f"{tenant.name}: base aprovisionada.", level=messages.SUCCESS
            )


@admin.register(TenantMembership)
class TenantMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "tenant", "role")
    list_filter = ("tenant", "role")
    search_fields = ("user__username", "tenant__name")


@admin.register(ApiToken)
class ApiTokenAdmin(admin.ModelAdmin):
    """Los tokens se crean en el panel maestro (ahí se muestra el token una sola vez).
    Aquí solo se consultan y se revocan."""

    list_display = ("name", "prefix", "user", "created_at", "last_used_at", "revoked_at")
    list_filter = ("revoked_at",)
    readonly_fields = ("user", "name", "prefix", "created_at", "last_used_at")
    fields = ("user", "name", "prefix", "created_at", "last_used_at", "revoked_at")

    def has_add_permission(self, request):
        return False
