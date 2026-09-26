"""Los restaurantes que ya existían usan Cloudin completo (pedidos, turnos, facturación)."""

from django.db import migrations


def adelante(apps, schema_editor):
    Tenant = apps.get_model("tenants", "Tenant")
    Tenant.objects.using(schema_editor.connection.alias).update(plan="completo")


class Migration(migrations.Migration):
    dependencies = [
        ("tenants", "0009_tenant_allowed_origins_tenant_menu_page_tenant_plan_and_more"),
    ]

    operations = [
        migrations.RunPython(adelante, migrations.RunPython.noop),
    ]
