"""Minifica el runtime de los menús: static/src/cloudin-menu.v1.src.js -> static/cloudin-menu.v1.js

    python manage.py build_runtime
    python manage.py build_runtime --check   # falla si el publicado no está al día

Sin Node ni bundler: usa rjsmin (Python). El contrato exige menos de 8 KB.
"""

from pathlib import Path

import rjsmin
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

LIMITE = 8 * 1024


def rutas() -> tuple[Path, Path]:
    base = Path(settings.BASE_DIR) / "static"
    return base / "src" / "cloudin-menu.v1.src.js", base / "cloudin-menu.v1.js"


def minificar(fuente: str) -> str:
    return rjsmin.jsmin(fuente, keep_bang_comments=True).strip() + "\n"


class Command(BaseCommand):
    help = "Minifica cloudin-menu.v1.js (menos de 8 KB)."

    def add_arguments(self, parser):
        parser.add_argument("--check", action="store_true", help="Solo verifica que el publicado esté al día.")

    def handle(self, *args, **opts):
        fuente, destino = rutas()
        minificado = minificar(fuente.read_text(encoding="utf-8"))
        peso = len(minificado.encode("utf-8"))
        if peso >= LIMITE:
            raise CommandError(f"El runtime pesa {peso} bytes: el límite es {LIMITE}.")
        if opts["check"]:
            actual = destino.read_text(encoding="utf-8") if destino.exists() else ""
            if actual != minificado:
                raise CommandError("static/cloudin-menu.v1.js no está al día: corre `python manage.py build_runtime`.")
            self.stdout.write(self.style.SUCCESS(f"Al día · {peso} bytes"))
            return
        destino.write_text(minificado, encoding="utf-8", newline="\n")
        self.stdout.write(self.style.SUCCESS(f"{destino.name}: {peso} bytes (límite {LIMITE})"))
