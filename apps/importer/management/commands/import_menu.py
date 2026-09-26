"""Importa la semilla de un menú digital (contrato cloudin.menu/v1).

    python manage.py import_menu ../proyecto-x/cloudin/menu.seed.json --assets ../proyecto-x/site --create-tenant
    python manage.py import_menu semilla.json --dry-run      # solo muestra qué pasaría

Reimportar es seguro: actualiza por clave, respeta lo que cambió el dueño y nunca borra.
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.importer.assets import Carpeta, SinFotos
from apps.importer.semilla import SemillaInvalida
from apps.importer.services import importar_semilla


class Command(BaseCommand):
    help = "Importa menu.seed.json (cloudin.menu/v1): crea o actualiza el restaurante y su carta."

    def add_arguments(self, parser):
        parser.add_argument("semilla", help="Ruta de menu.seed.json")
        parser.add_argument("--assets", help="Carpeta desde la que se leen las fotos (normalmente site/)")
        parser.add_argument("--create-tenant", action="store_true", help="Crear el restaurante si no existe")
        parser.add_argument("--dry-run", action="store_true", help="Revisar sin cambiar nada")
        parser.add_argument("--no-invite", action="store_true", help="No enviar la invitación al dueño")

    def handle(self, *args, **opts):
        ruta = Path(opts["semilla"])
        if not ruta.is_file():
            raise CommandError(f"No encuentro {ruta}.")
        try:
            datos = json.loads(ruta.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise CommandError(f"{ruta} no es un JSON válido: {e}")
        if opts["assets"] and not Path(opts["assets"]).is_dir():
            raise CommandError(f"La carpeta de fotos {opts['assets']} no existe.")
        assets = Carpeta(opts["assets"]) if opts["assets"] else SinFotos()
        try:
            resumen = importar_semilla(datos, assets, crear_restaurante=opts["create_tenant"],
                                       aplicar=not opts["dry_run"], invitar=not opts["no_invite"])
        except SemillaInvalida as e:
            for error in e.errores:
                self.stderr.write(f"  ✗ {error}")
            raise CommandError("La semilla tiene errores: corrígelos y vuelve a intentar.")
        self._imprimir(resumen)

    def _imprimir(self, r):
        titulo = "REVISIÓN (no se cambió nada)" if not r.aplicado else "Importación lista"
        self.stdout.write(self.style.SUCCESS(f"{titulo}: {r.nombre} ({r.restaurante})"
                                             f"{' · restaurante nuevo' if r.creado else ''}"))
        for entidad, c in r.contadores.items():
            partes = [f"{v} {k.replace('_', ' ')}" for k, v in c.items() if v]
            self.stdout.write(f"  {entidad}: {', '.join(partes) or 'sin cambios'}")
        self.stdout.write(f"  fotos subidas: {r.fotos['subidas']}"
                          + (f" · faltan: {', '.join(r.fotos['faltantes'])}" if r.fotos["faltantes"] else ""))
        if r.mesas_creadas:
            self.stdout.write(f"  mesas nuevas: {r.mesas_creadas}")
        if r.invitacion:
            self.stdout.write(f"  dueño: {r.invitacion}")
        for texto in r.conservados:
            self.stdout.write(self.style.WARNING(f"  = {texto}"))
        for texto in r.avisos:
            self.stdout.write(self.style.WARNING(f"  ! {texto}"))
