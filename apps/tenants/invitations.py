"""Invitación al dueño: un correo con un enlace para crear su contraseña.

El enlace usa el mismo mecanismo seguro que «Olvidé mi contraseña» de Django
(token de un solo uso que vence en PASSWORD_RESET_TIMEOUT, 7 días) y lleva a
/panel/invitacion/<uid>/<token>/. Al crear la contraseña queda con sesión
iniciada. Después entra con su correo o su usuario.
"""

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode


def base_publica() -> str:
    return (settings.CLOUDIN_PUBLIC_URL or "http://localhost:8000").rstrip("/")


def enlace_de_invitacion(user) -> str:
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    return f"{base_publica()}/panel/invitacion/{uid}/{default_token_generator.make_token(user)}/"


def enviar_invitacion(user, tenant) -> str:
    """Envía el correo y devuelve el enlace (para mostrarlo también en el resumen)."""
    enlace = enlace_de_invitacion(user)
    contexto = {
        "nombre": (user.first_name or "").split(" ")[0] or "hola",
        "restaurante": tenant.name,
        "enlace": enlace,
        "correo": user.email,
        "usuario": user.username,
        "panel": f"{base_publica()}/panel/",
        "dias": settings.PASSWORD_RESET_TIMEOUT // 86400,
    }
    send_mail(
        subject=f"Tu menú de {tenant.name} ya está en Cloudin: crea tu contraseña",
        message=render_to_string("correos/invitacion.txt", contexto),
        html_message=render_to_string("correos/invitacion.html", contexto),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
    )
    return enlace
