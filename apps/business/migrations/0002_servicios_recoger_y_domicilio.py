"""Servicios: quedan solo Recoger y Domicilio, los dos encendidos. «En la mesa» sale de la
lista: en la mesa se pide con el QR (interruptor «Pedidos desde el QR de la mesa») o con los
meseros. Antes venían apagados y el menú digital no los recibía, así que nadie dependía de
ellos: se encienden en todos los restaurantes, y cada uno los apaga en Personalizar.

También sube la versión del menú: así los menús que guardaron la carta (por su ETag) la
vuelven a pedir y reciben los servicios encendidos y los campos nuevos de la API."""

from django.db import migrations
from django.db.models import F


def encender(apps, schema_editor):
    RestaurantSettings = apps.get_model("business", "RestaurantSettings")
    RestaurantSettings.objects.using(schema_editor.connection.alias).update(
        services={"takeaway": True, "delivery": True}, menu_version=F("menu_version") + 1)


class Migration(migrations.Migration):
    dependencies = [
        ("business", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(encender, migrations.RunPython.noop),
    ]
