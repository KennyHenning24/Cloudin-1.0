"""Entrar con el usuario o con el correo.

Los dueños que llegan por la importación reciben un usuario tipo
«mi-restaurante.dueno», difícil de recordar: pueden entrar con su correo. Si
el correo lo comparten varias cuentas, se exige el usuario (no se adivina).

El usuario no distingue mayúsculas: «Juan» entra como «juan» si hay una sola cuenta
con ese nombre escrito de cualquier forma (la contraseña sí las distingue).
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class UsuarioOCorreo(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        texto = (username or "").strip()
        User = get_user_model()
        if "@" in texto:
            usuarios = list(User.objects.filter(email__iexact=texto, is_active=True)[:2])
            if len(usuarios) != 1:
                return None
            texto = usuarios[0].get_username()
        elif texto and not User.objects.filter(username=texto).exists():
            iguales = list(User.objects.filter(username__iexact=texto, is_active=True)
                           .values_list("username", flat=True)[:2])
            if len(iguales) == 1:
                texto = iguales[0]
        return super().authenticate(request, username=texto, password=password, **kwargs)
