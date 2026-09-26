"""Deja el servidor listo antes de recibir visitas. Lo corre el contenedor al arrancar.

    python manage.py preparar_servidor

1. `migrate` en la base de control.
2. `migrate_tenants`: todas las bases de restaurante (crea la que falte).
3. Si existen DJANGO_SUPERUSER_USERNAME y DJANGO_SUPERUSER_PASSWORD y ese usuario no
   existe, crea el superusuario del panel maestro. Si ya existe no se toca: la clave
   que se cambie después desde el panel no se pisa en cada arranque.

Se puede correr las veces que sea: lo que ya está hecho no se repite.
"""

import os

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Migraciones de control y de restaurantes, y superusuario inicial (para el arranque en el servidor)."

    def handle(self, *args, **opts):
        verbosidad = int(opts.get("verbosity", 1))

        self.stdout.write("Migrando la base de control…")
        call_command("migrate", database="default", interactive=False, verbosity=max(verbosidad - 1, 0))

        self.stdout.write("Migrando las bases de los restaurantes…")
        call_command("migrate_tenants", verbosity=verbosidad)

        usuario = os.getenv("DJANGO_SUPERUSER_USERNAME", "").strip()
        clave = os.getenv("DJANGO_SUPERUSER_PASSWORD", "")
        if usuario and clave:
            User = get_user_model()
            if User.objects.filter(username=usuario).exists():
                self.stdout.write(f"Superusuario «{usuario}»: ya existe.")
            else:
                User.objects.create_superuser(usuario, os.getenv("DJANGO_SUPERUSER_EMAIL", ""), clave)
                self.stdout.write(self.style.SUCCESS(f"Superusuario «{usuario}» creado."))

        self.stdout.write(self.style.SUCCESS("Servidor listo."))
