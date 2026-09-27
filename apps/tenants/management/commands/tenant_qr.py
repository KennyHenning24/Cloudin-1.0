"""Genera los QR de las mesas de un restaurante: los mismos del panel (Códigos QR).

    python manage.py tenant_qr --slug lajoya
    python manage.py tenant_qr --slug lajoya --base-url https://lajoya.pages.dev/

Cada QR es la página del menú + ?mesa=<token> (ver dining/qr.py y GUIA-MENU-DIGITAL.md).
Deja los PNG en qrcodes/<slug>/mesa-<n>.png y además imprime las URLs.
"""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.dining.models import Table
from apps.dining.qr import con_parametro, enlace_de_mesa
from apps.tenants.context import tenant_context
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = "Genera los códigos QR de las mesas de un restaurante."

    def add_arguments(self, parser):
        parser.add_argument("--slug", required=True)
        parser.add_argument(
            "--base-url",
            help="Página del menú a usar en vez de la registrada en el restaurante (menu_page).",
        )
        parser.add_argument("--no-png", action="store_true", help="Solo imprimir las URLs")

    def handle(self, *args, **opts):
        try:
            tenant = Tenant.objects.get(slug=opts["slug"])
        except Tenant.DoesNotExist:
            raise CommandError(f"No existe el restaurante '{opts['slug']}'.")

        destino = Path(settings.BASE_DIR) / "qrcodes" / tenant.slug
        if not opts["no_png"]:
            destino.mkdir(parents=True, exist_ok=True)

        with tenant_context(tenant):
            mesas = list(Table.objects.filter(is_active=True).order_by("number"))

        if not mesas:
            self.stdout.write(self.style.WARNING("El restaurante no tiene mesas."))
            return

        for mesa in mesas:
            url = (con_parametro(opts["base_url"], "mesa", mesa.token) if opts["base_url"]
                   else enlace_de_mesa(tenant, mesa))
            if not url:
                raise CommandError("El restaurante no tiene «Página del menú» (menu_page): regístrala en "
                                   "/admin/ o usa --base-url.")
            self.stdout.write(f"Mesa {mesa.number}: {url}")
            if not opts["no_png"]:
                import qrcode

                img = qrcode.make(url)
                img.save(destino / f"mesa-{mesa.number}.png")

        if not opts["no_png"]:
            self.stdout.write(self.style.SUCCESS(f"QRs guardados en {destino}"))
