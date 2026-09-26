"""Filtros del menú público."""

import re

from django import template

register = template.Library()
HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


@register.filter
def color_seguro(valor, respaldo="#FFFFFF"):
    """El color si es un #RRGGBB válido; si no, el de respaldo (nunca CSS arbitrario)."""
    return valor if isinstance(valor, str) and HEX.match(valor) else respaldo
