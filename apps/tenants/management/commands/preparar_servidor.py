"""Deja el servidor listo antes de recibir visitas. Lo corre el contenedor al arrancar.

    python manage.py preparar_servidor

1. `migrate` en la base de control.
2. `migrate_tenants`: todas las bases de restaurante (crea la que falte).
3. El superusuario del panel maestro, con DJANGO_SUPERUSER_USERNAME y
   DJANGO_SUPERUSER_PASSWORD: si no existe, se crea. Si ya existe no se toca (la clave
   que se cambie después no se pisa en cada arranque), salvo con
   DJANGO_SUPERUSER_RESET=1: entonces su contraseña pasa a ser la de
   DJANGO_SUPERUSER_PASSWORD. Es para cuando se pierde la clave en un servidor sin
   consola (Render gratis); después de entrar, se quita DJANGO_SUPERUSER_RESET.

Se puede correr las veces que sea: lo que ya está hecho no se repite.
"""

import os

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand


def superusuario_inicial(entorno=os.environ) -> tuple[str, str]:
    """Crea (o, con DJANGO_SUPERUSER_RESET=1, le cambia la clave a) el superusuario del panel
    maestro. Devuelve (nivel, mensaje para el registro): nivel es «ok», «aviso» o «info»."""
    usuario = entorno.get("DJANGO_SUPERUSER_USERNAME", "").strip()
    clave = entorno.get("DJANGO_SUPERUSER_PASSWORD", "")
    if not usuario or not clave:
        if usuario or clave:
            return "aviso", ("Falta DJANGO_SUPERUSER_USERNAME o DJANGO_SUPERUSER_PASSWORD: no se creó ni se "
                             "cambió el superusuario.")
        return "info", ""
    User = get_user_model()
    existente = User.objects.filter(username=usuario).first()
    if existente is None:
        User.objects.create_superuser(usuario, entorno.get("DJANGO_SUPERUSER_EMAIL", ""), clave)
        return "ok", f"Superusuario «{usuario}» creado."
    if entorno.get("DJANGO_SUPERUSER_RESET", "").strip() != "1":
        return "info", (f"Superusuario «{usuario}»: ya existe. Su contraseña no cambia con "
                        "DJANGO_SUPERUSER_PASSWORD; para cambiarla, DJANGO_SUPERUSER_RESET=1.")
    if not existente.is_superuser:
        return "aviso", (f"«{usuario}» existe pero no es superusuario (es una cuenta de un restaurante): "
                         "no se cambió su contraseña. Revisa DJANGO_SUPERUSER_USERNAME.")
    existente.set_password(clave)
    existente.is_active = True
    existente.save(update_fields=["password", "is_active"])
    return "aviso", (f"Superusuario «{usuario}»: su contraseña es ahora la de DJANGO_SUPERUSER_PASSWORD. "
                     "Ya puedes entrar; quita DJANGO_SUPERUSER_RESET para que no se repita en cada arranque.")


class Command(BaseCommand):
    help = "Migraciones de control y de restaurantes, y superusuario inicial (para el arranque en el servidor)."

    def handle(self, *args, **opts):
        verbosidad = int(opts.get("verbosity", 1))

        self.stdout.write("Migrando la base de control…")
        call_command("migrate", database="default", interactive=False, verbosity=max(verbosidad - 1, 0))

        self.stdout.write("Migrando las bases de los restaurantes…")
        call_command("migrate_tenants", verbosity=verbosidad)

        nivel, mensaje = superusuario_inicial()
        if mensaje:
            estilo = {"ok": self.style.SUCCESS, "aviso": self.style.WARNING}.get(nivel, str)
            self.stdout.write(estilo(mensaje))

        self.stdout.write(self.style.SUCCESS("Servidor listo."))
