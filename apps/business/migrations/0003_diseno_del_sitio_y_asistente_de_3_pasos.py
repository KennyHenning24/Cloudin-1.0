"""El diseño del menú (colores, logo y portada) es de su página: el panel ya no lo cambia y
la API manda los colores vacíos (brand en null). Se sube la versión del menú para que los
menús que guardaron la carta (por su ETag) la vuelvan a pedir y dejen de usar esos colores.

El asistente de la primera vez pasa de 4 pasos a 3 (sale «Tu marca»): el paso guardado se
corre uno hacia atrás para que cada restaurante siga donde iba."""

from django.db import migrations
from django.db.models import F


def adelante(apps, schema_editor):
    RestaurantSettings = apps.get_model("business", "RestaurantSettings")
    filas = RestaurantSettings.objects.using(schema_editor.connection.alias)
    filas.update(menu_version=F("menu_version") + 1)
    # Antes: 1 marca, 2 negocio, 3 categoría, 4 producto, 5 final. Ahora: 1 negocio,
    # 2 categoría, 3 producto, 4 final. Quien iba en «Tu marca» sigue en «Datos del negocio».
    filas.filter(onboarding_step__gte=2).update(onboarding_step=F("onboarding_step") - 1)


def atras(apps, schema_editor):
    RestaurantSettings = apps.get_model("business", "RestaurantSettings")
    RestaurantSettings.objects.using(schema_editor.connection.alias).filter(
        onboarding_step__gte=2).update(onboarding_step=F("onboarding_step") + 1)


class Migration(migrations.Migration):
    dependencies = [
        ("business", "0002_servicios_recoger_y_domicilio"),
    ]

    operations = [
        migrations.RunPython(adelante, atras),
    ]
