"""Importa (o revisa) la carta de un restaurante desde su sitio web.

    python manage.py importar_menu --tenant culturabrisket --revisar
    python manage.py importar_menu --tenant culturabrisket
    python manage.py importar_menu --tenant culturabrisket --url https://sitio.com/cloudin-menu.json
    python manage.py importar_menu --todos          (para un cron diario)

Sin --url usa la «dirección de la carta» guardada en el panel. Nunca borra ni
pisa lo editado en el panel: solo crea lo nuevo y completa lo vacío.
"""

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.catalog.formato import importar, leer_fuente
from apps.tenants.context import tenant_context
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = "Trae la carta del sitio web del restaurante (formato cloudin-menu.json)."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", help="slug del restaurante")
        parser.add_argument("--todos", action="store_true", help="todos los que tengan dirección de carta")
        parser.add_argument("--url", help="dirección del cloudin-menu.json (si no, la guardada)")
        parser.add_argument("--revisar", action="store_true", help="solo mostrar qué haría")

    def handle(self, *args, **opts):
        if opts["todos"]:
            tenants = Tenant.objects.filter(is_active=True).exclude(menu_fuente="")
        elif opts["tenant"]:
            tenants = Tenant.objects.filter(slug=opts["tenant"])
            if not tenants.exists():
                raise CommandError(f"No existe el restaurante «{opts['tenant']}».")
        else:
            raise CommandError("Indica --tenant <slug> o --todos.")

        for tenant in tenants:
            url = opts["url"] or tenant.menu_fuente
            if not url:
                self.stdout.write(self.style.WARNING(f"{tenant.slug}: no tiene dirección de carta."))
                continue
            try:
                datos = leer_fuente(url)
                with tenant_context(tenant):
                    r = importar(datos, url, aplicar=not opts["revisar"])
            except ValidationError as e:
                self.stdout.write(self.style.ERROR(f"{tenant.slug}: {e.messages[0]}"))
                continue
            verbo = "haría" if opts["revisar"] else "hizo"
            self.stdout.write(self.style.SUCCESS(
                f"{tenant.slug} ({verbo}): {r['productos_nuevos']} productos nuevos, "
                f"{r['categorias_nuevas']} categorías nuevas, {r['productos_completados']} completados, "
                f"{r['sin_cambios']} sin cambios."
            ))
            for error in r["errores"]:
                self.stdout.write(self.style.WARNING(f"  · {error}"))
