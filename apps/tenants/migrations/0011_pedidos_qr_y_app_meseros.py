"""Todos los restaurantes pasan a Cloudin completo, y «cómo se toman los pedidos» deja
de ser un modo (autoservicio, meseros o ambos) para ser dos interruptores: pedidos
desde el QR de la mesa y app de meseros. Cada restaurante sigue recibiendo lo mismo
que antes: el plan «Menú digital» no recibía pedidos por el QR, así que queda con
ese interruptor apagado hasta que su administrador lo encienda."""

from django.db import migrations, models


def adelante(apps, schema_editor):
    Tenant = apps.get_model("tenants", "Tenant")
    for t in Tenant.objects.using(schema_editor.connection.alias).all():
        t.pedidos_qr = t.plan == "completo" and t.modo_servicio in ("autoservicio", "mixto")
        t.app_meseros = t.modo_servicio in ("meseros", "mixto")
        t.save(update_fields=["pedidos_qr", "app_meseros"])


def atras(apps, schema_editor):
    Tenant = apps.get_model("tenants", "Tenant")
    for t in Tenant.objects.using(schema_editor.connection.alias).all():
        if t.pedidos_qr and t.app_meseros:
            t.plan, t.modo_servicio = "completo", "mixto"
        elif t.app_meseros:
            t.plan, t.modo_servicio = "completo", "meseros"
        elif t.pedidos_qr:
            t.plan, t.modo_servicio = "completo", "autoservicio"
        else:  # ni QR ni meseros: era el plan «Menú digital»
            t.plan, t.modo_servicio = "menu", "autoservicio"
        t.save(update_fields=["plan", "modo_servicio"])


class Migration(migrations.Migration):
    dependencies = [
        ("tenants", "0010_planes_existentes"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenant",
            name="pedidos_qr",
            field=models.BooleanField(default=True, verbose_name="Recibe pedidos desde el QR de la mesa"),
        ),
        migrations.AddField(
            model_name="tenant",
            name="app_meseros",
            field=models.BooleanField(default=False, verbose_name="Usa la app de meseros"),
        ),
        migrations.RunPython(adelante, atras),
        migrations.RemoveField(model_name="tenant", name="modo_servicio"),
        migrations.RemoveField(model_name="tenant", name="plan"),
    ]
