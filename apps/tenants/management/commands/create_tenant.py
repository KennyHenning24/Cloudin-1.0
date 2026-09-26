"""Alta de un restaurante desde la consola (el equivalente del panel maestro).

    python manage.py create_tenant --name "Cultura Brisket" --slug culturabrisket
"""

from django.core.management.base import BaseCommand, CommandError
from django.utils.text import slugify

from apps.tenants.models import Tenant
from apps.tenants.services import aprovisionar, crear_restaurante, crear_usuario, enlace_panel


class Command(BaseCommand):
    help = "Crea un restaurante: base de datos, migraciones, usuario administrador y API key."

    def add_arguments(self, parser):
        parser.add_argument("--name", required=True, help="Nombre del restaurante")
        parser.add_argument("--slug", help="Subdominio (por defecto se deriva del nombre)")
        parser.add_argument("--nit", default="")
        parser.add_argument("--phone", default="")
        parser.add_argument("--address", default="")
        parser.add_argument("--city", default="")
        parser.add_argument("--admin-user", default="admin", help="Usuario administrador")
        parser.add_argument("--admin-password", help="Contraseña (si se omite, se genera)")

    def handle(self, *args, **opts):
        slug = opts["slug"] or slugify(opts["name"])
        if Tenant.objects.filter(slug=slug).exists():
            raise CommandError(f"Ya existe un restaurante con el slug '{slug}'.")

        tenant = crear_restaurante(
            nombre=opts["name"],
            slug=slug,
            nit=opts["nit"],
            phone=opts["phone"],
            address=opts["address"],
            city=opts["city"],
        )
        self.stdout.write(f"Restaurante creado: {tenant.name} ({tenant.slug})")

        aprovisionar(tenant)
        self.stdout.write(self.style.SUCCESS(f"Base aprovisionada y migrada: {tenant.db_name}"))

        user, password = crear_usuario(
            tenant, opts["admin_user"], password=opts["admin_password"]
        )

        self.stdout.write("")
        self.stdout.write(self.style.HTTP_INFO("--- Credenciales del restaurante ---"))
        self.stdout.write(f"  Enlace  : {enlace_panel(tenant)}")
        self.stdout.write(self.style.SUCCESS(f"  Usuario : {user.username}"))
        self.stdout.write(self.style.SUCCESS(f"  Clave   : {password}"))
        self.stdout.write(f"  API key : {tenant.api_key}")
