from django.contrib import admin, messages
from django.utils.html import format_html

from .models import Tenant, TenantMembership
from .provisioning import provision_tenant


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "domain_link", "is_active", "provisioned_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug", "nit")
    readonly_fields = ("api_key", "db_name", "provisioned_at", "created_at")
    actions = ("accion_aprovisionar",)
    fieldsets = (
        (None, {"fields": ("name", "slug", "is_active")}),
        ("Datos fiscales", {"fields": ("legal_name", "nit", "address", "city", "phone")}),
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
