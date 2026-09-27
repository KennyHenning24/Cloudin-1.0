"""Claves estables (`key`) del contrato de menús.

Una clave es un texto en kebab-case (`hamburguesa-clasica`) que identifica una
entidad para siempre: se genera una vez, a partir del nombre, y nunca cambia
aunque el dueño renombre el producto. La importación la usa para actualizar
sin duplicar.
"""

import re
from collections.abc import Callable

from django.core.exceptions import ValidationError
from django.utils.text import slugify

KEY_MAX = 60
KEY_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def key_from(texto: str, respaldo: str = "item") -> str:
    """«Sándwich 2 Quesos» -> «sandwich-2-quesos»."""
    clave = slugify(str(texto or ""))[:KEY_MAX].strip("-")
    return clave or respaldo


def unique_key(base: str, existe: Callable[[str], bool]) -> str:
    """La primera variante libre de `base`: base, base-2, base-3…"""
    base = key_from(base)
    if not existe(base):
        return base
    n = 2
    while True:
        sufijo = f"-{n}"
        candidata = base[: KEY_MAX - len(sufijo)].rstrip("-") + sufijo
        if not existe(candidata):
            return candidata
        n += 1


def es_clave_valida(valor: str) -> bool:
    return bool(valor) and len(valor) <= KEY_MAX and bool(KEY_RE.match(valor))


def validar_clave(valor: str) -> None:
    if not es_clave_valida(valor):
        raise ValidationError(
            f"«{valor}» no es una clave válida: usa minúsculas, números y guiones (ej. «hamburguesa-clasica»)."
        )
