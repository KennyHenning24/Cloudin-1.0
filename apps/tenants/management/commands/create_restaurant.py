"""Alta de un restaurante con su dueño (el que recibe la invitación por correo).

    python manage.py create_restaurant --name "La Esquina" --slug la-esquina \
        --owner-email dueno@correo.com --owner-name "Ana Ruiz" [--plan menu|completo]

Crea el restaurante en la base de control, su base de datos (migrada), el menú
«Carta» y al dueño, y le envía la invitación para crear su contraseña. Para
traer además la carta, usa `import_menu` con la semilla del sitio.
"""

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email

from apps.common.keys import es_clave_valida, key_from
from apps.tenants.context import tenant_context
from apps.tenants.models import Tenant, TenantMembership
from apps.tenants.services import aprovisionar, crear_restaurante, crear_usuario


class Command(BaseCommand):
    help = "Crea un restaurante, su base, el menú «Carta» y el dueño (con invitación por correo)."

    def add_arguments(self, parser):
        parser.add_argument("--name", required=True, help="Nombre comercial")
        parser.add_argument("--slug", help="Identificador en kebab-case (por defecto, del nombre)")
        parser.add_argument("--plan", choices=[p for p, _ in Tenant.PLANES], default=Tenant.PLAN_MENU)
        parser.add_argument("--owner-email", required=True)
        parser.add_argument("--owner-name", default="")
        parser.add_argument("--nit", default="")
        parser.add_argument("--legal-name", default="")
        parser.add_argument("--city", default="")
        parser.add_argument("--address", default="")
        parser.add_argument("--phone", default="")
        parser.add_argument("--no-invite", action="store_true", help="No enviar la invitación (se muestra el enlace)")

    def handle(self, *args, **o):
        slug = o["slug"] or key_from(o["name"])
        if not es_clave_valida(slug):
            raise CommandError(f"«{slug}» no sirve como identificador: usa minúsculas, números y guiones.")
        if Tenant.objects.filter(slug=slug).exists():
            raise CommandError(f"Ya existe un restaurante «{slug}».")
        try:
            validate_email(o["owner_email"])
        except ValidationError:
            raise CommandError("El correo del dueño no es válido.")

        tenant = crear_restaurante(nombre=o["name"], slug=slug, plan=o["plan"], nit=o["nit"],
                                   legal_name=o["legal_name"], city=o["city"], address=o["address"],
                                   phone=o["phone"])
        aprovisionar(tenant)
        with tenant_context(tenant):
            from apps.catalog.models import Menu

            Menu.principal()
        user, _ = crear_usuario(tenant, "dueno", rol=TenantMembership.ROLE_OWNER, nombre=o["owner_name"],
                                correo=o["owner_email"])

        from apps.tenants.invitations import enlace_de_invitacion, enviar_invitacion

        if o["no_invite"]:
            enlace = enlace_de_invitacion(user)
            self.stdout.write(self.style.WARNING("No se envió el correo. Enlace de invitación (7 días):"))
            self.stdout.write(f"  {enlace}")
        else:
            enviar_invitacion(user, tenant)
            self.stdout.write(f"Invitación enviada a {o['owner_email']}.")
        self.stdout.write(self.style.SUCCESS(
            f"Listo: {tenant.name} ({tenant.slug}) · plan {tenant.get_plan_display()} · usuario {user.username}"))
