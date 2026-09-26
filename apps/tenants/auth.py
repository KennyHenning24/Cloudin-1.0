"""Entrar con el usuario o con el correo.

Los dueños que llegan por la importación reciben un usuario tipo
«mi-restaurante.dueno», difícil de recordar: pueden entrar con su correo. Si
el correo lo comparten varias cuentas, se exige el usuario (no se adivina).
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class UsuarioOCorreo(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        texto = (username or "").strip()
        if "@" in texto:
            usuarios = list(get_user_model().objects.filter(email__iexact=texto, is_active=True)[:2])
            if len(usuarios) != 1:
                return None
            texto = usuarios[0].get_username()
        return super().authenticate(request, username=texto, password=password, **kwargs)
