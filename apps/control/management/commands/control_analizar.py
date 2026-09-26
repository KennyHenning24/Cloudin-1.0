"""Corre Cloudin Control en uno o en todos los restaurantes.

    python manage.py control_analizar --todos
    python manage.py control_analizar --tenant elbembe

El panel ya analiza solo cuando alguien abre Cloudin Control o el Inicio (cada
10 minutos como máximo) y al cerrar cada turno. Este comando sirve para
programarlo en el servidor (por ejemplo, cada hora) y que las alertas estén
listas aunque nadie abra el panel.
"""

from django.core.management.base import BaseCommand, CommandError

from apps.tenants.context import tenant_context
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = "Revisa caja, inventario, anulaciones, descuentos, costos y demás, y deja las alertas."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", help="Slug del restaurante")
        parser.add_argument("--todos", action="store_true", help="Todos los restaurantes activos")

    def handle(self, *args, **opts):
        if opts["todos"]:
            tenants = Tenant.objects.filter(is_active=True)
        elif opts["tenant"]:
            tenants = Tenant.objects.filter(slug=opts["tenant"])
            if not tenants.exists():
                raise CommandError(f"No existe el restaurante '{opts['tenant']}'.")
        else:
            raise CommandError("Usa --tenant <slug> o --todos.")

        from apps.control.services import analizar

        for tenant in tenants:
            with tenant_context(tenant):
                a = analizar("programado")
            self.stdout.write(f"{tenant.slug}: {a.alertas_nuevas} nuevas, {a.alertas_actualizadas} actualizadas "
                              f"({a.duracion_ms} ms)")
