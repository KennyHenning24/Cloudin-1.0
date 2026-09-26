"""Cifrado reversible de las contraseñas que el panel maestro debe poder mostrar.

Django guarda las contraseñas hasheadas (no se pueden deshacer) y eso no cambia:
`auth_user.password` sigue siendo un hash. Aparte de eso, guardamos una copia
**cifrada** para que el panel maestro pueda mostrársela a Juan cuando la
necesite.

La llave (CREDENTIAL_KEY) vive en el archivo .env, nunca en la base de datos ni
en el repositorio. Sin esa llave, la columna cifrada es basura ilegible.
"""

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

_fernet = None


class LlaveNoConfigurada(RuntimeError):
    pass


def hay_llave() -> bool:
    return bool(getattr(settings, "CREDENTIAL_KEY", ""))


def _obtener_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        if not hay_llave():
            raise LlaveNoConfigurada(
                "Falta CREDENTIAL_KEY en el .env. Genere una con:\n"
                "  python -c \"from cryptography.fernet import Fernet;"
                ' print(Fernet.generate_key().decode())"'
            )
        _fernet = Fernet(settings.CREDENTIAL_KEY.encode())
    return _fernet


def cifrar(texto: str) -> str:
    return _obtener_fernet().encrypt(texto.encode()).decode()


def descifrar(token: str) -> str | None:
    """Devuelve None si el token no se puede leer (llave cambiada o dato viejo)."""
    if not token:
        return None
    try:
        return _obtener_fernet().decrypt(token.encode()).decode()
    except (InvalidToken, LlaveNoConfigurada, ValueError):
        return None
