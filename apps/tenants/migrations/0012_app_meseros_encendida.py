"""La app de meseros viene encendida para todos: todos tienen Cloudin completo y, sin
cuentas de meseros (las crea el administrador en su panel → Meseros), nadie puede entrar.
Antes quedaba apagada en los restaurantes que solo pedían por QR (el modo por defecto), y
la app respondía «El servicio de meseros no está activo». Se puede volver a apagar en
Meseros → «App de meseros»."""

from django.db import migrations, models


def encender(apps, schema_editor):
    Tenant = apps.get_model("tenants", "Tenant")
    Tenant.objects.using(schema_editor.connection.alias).update(app_meseros=True)


class Migration(migrations.Migration):
    dependencies = [
        ("tenants", "0011_pedidos_qr_y_app_meseros"),
    ]

    operations = [
        migrations.AlterField(
            model_name="tenant",
            name="app_meseros",
            field=models.BooleanField(default=True, verbose_name="Usa la app de meseros"),
        ),
        # Hacia atrás no se apaga: no se sabe cuáles la tenían encendida a propósito.
        migrations.RunPython(encender, migrations.RunPython.noop),
    ]
