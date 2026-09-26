"""Aplica las migraciones a todas las bases de restaurante (o a una sola).

    python manage.py migrate_tenants
    python manage.py migrate_tenants --slug lajoya
"""

from django.core.management.base import BaseCommand

from apps.tenants.models import Tenant
from apps.tenants.provisioning import provision_tenant


class Command(BaseCommand):
    help = "Corre las migraciones sobre las bases de todos los restaurantes."

    def add_arguments(self, parser):
        parser.add_argument("--slug", help="Migrar solo este restaurante")

    def handle(self, *args, **opts):
        qs = Tenant.objects.filter(is_active=True)
        if opts["slug"]:
            qs = qs.filter(slug=opts["slug"])

        if not qs.exists():
            self.stdout.write(self.style.WARNING("No hay restaurantes que migrar."))
            return

        for tenant in qs:
            self.stdout.write(f"→ {tenant.name} ({tenant.db_name})")
            provision_tenant(tenant, verbosity=int(opts.get("verbosity", 1)) - 1)
            self.stdout.write(self.style.SUCCESS("  ok"))
