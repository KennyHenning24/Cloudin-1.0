"""Crea (o actualiza) el restaurante de demostración: una birriería con su carta completa.

    python manage.py seed_demo_menu                      # demo-birrieria, contraseña nueva
    python manage.py seed_demo_menu --slug demo-2 --password "Demo-2026-segura"

Sirve para mostrar Cloudin y para revisar el panel con datos de verdad. Pasa por la
misma importación que un menú real (apps/importer/demo/birrieria.seed.json): dos
menús, 14 productos, tamaños, adiciones, etiquetas, un agotado y uno sin precio.
Sin fotos inventadas: las fotos las pone el restaurante. No envía correos.
Reimportar es seguro: no duplica nada y respeta lo que se haya cambiado en el panel.
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.utils.text import slugify

from apps.importer.assets import SinFotos
from apps.importer.management.commands.import_menu import Command as ImportMenu
from apps.importer.semilla import SemillaInvalida
from apps.importer.services import importar_semilla

SEMILLA = Path(__file__).resolve().parents[2] / "demo" / "birrieria.seed.json"


class Command(BaseCommand):
    help = "Crea el restaurante de demostración (una birriería con su carta, sin fotos)."

    def add_arguments(self, parser):
        parser.add_argument("--slug", default="demo-birrieria", help="Identificador del restaurante demo")
        parser.add_argument("--password", help="Contraseña del dueño demo (si no se da, se genera una)")
        parser.add_argument("--con-asistente", action="store_true",
                            help="Dejar pendiente el asistente de la primera vez (para mostrarlo)")

    def handle(self, *args, **opts):
        from apps.business.models import RestaurantSettings
        from apps.tenants.context import tenant_context
        from apps.tenants.models import Tenant, TenantMembership
        from apps.tenants.services import cambiar_password, enlace_panel

        slug = slugify(opts["slug"])
        if not slug:
            raise CommandError("El slug no es válido.")
        datos = json.loads(SEMILLA.read_text(encoding="utf-8"))
        datos["business"]["slug"] = slug
        datos["business"]["owner"]["email"] = f"dueno@{slug}.test"
        try:
            resumen = importar_semilla(datos, SinFotos(), crear_restaurante=True, invitar=False)
        except SemillaInvalida as e:  # pragma: no cover - la semilla del repositorio es válida
            raise CommandError("; ".join(e.errores))
        ImportMenu(stdout=self.stdout, stderr=self.stderr)._imprimir(resumen)

        tenant = Tenant.objects.get(slug=slug)
        dueno = TenantMembership.objects.get(tenant=tenant, role=TenantMembership.ROLE_OWNER).user
        # Solo la primera vez (o si se pide): volver a correrlo no cierra la sesión del dueño.
        clave = cambiar_password(dueno, opts["password"] or None) if (resumen.creado or opts["password"]) else None
        with tenant_context(tenant):
            ajustes = RestaurantSettings.load()
            if opts["con_asistente"]:
                ajustes.onboarding_step, ajustes.onboarding_done_at = 0, None
            elif ajustes.onboarding_done_at is None:
                from apps.panel.duenio import PASOS

                ajustes.onboarding_step, ajustes.onboarding_done_at = len(PASOS) + 1, timezone.now()
            ajustes.save(update_fields=["onboarding_step", "onboarding_done_at", "updated_at"])

        self.stdout.write(self.style.SUCCESS("\nRestaurante de demostración listo"))
        self.stdout.write(f"  panel:      {enlace_panel(tenant)}")
        self.stdout.write(f"  usuario:    {dueno.username}  (o {dueno.email})")
        self.stdout.write(f"  contraseña: {clave or 'la misma de antes (usa --password para cambiarla)'}")
        self.stdout.write(f"  menú:       /m/{slug}/")
