"""Filtros de plantilla propios del panel."""

from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def pesos(valor, decimales=0):
    """Formatea plata como se lee en Colombia: 50000 -> 50.000

    Django sin `USE_THOUSAND_SEPARATOR` imprime «50000», que en una pantalla de
    caja se lee mal. Esto lo arregla sin tocar la configuración global (que
    afectaría también a los campos numéricos de los formularios).
    """
    if valor in (None, ""):
        return "0"
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, ValueError, TypeError):
        return valor

    decimales = int(decimales)
    texto = f"{abs(numero):,.{decimales}f}"
    # En el formato de Python la coma separa miles y el punto los decimales;
    # en Colombia es al revés.
    texto = texto.replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    return ("-" if numero < 0 else "") + texto


@register.filter
def cantidad(valor, decimales=2):
    """Cantidades de inventario: quita los ceros que sobran (2,50 -> 2,5)."""
    texto = pesos(valor, decimales)
    if "," in texto:
        texto = texto.rstrip("0").rstrip(",")
    return texto or "0"


@register.simple_tag
def icono(nombre, clase="ico", etiqueta=""):
    """{% icono "mas" %} · {% icono "agotado" "ico sm" "Agotado" %} — ver apps/panel/iconos.py."""
    from django.utils.html import escape
    from django.utils.safestring import mark_safe

    from apps.panel.iconos import svg

    return mark_safe(svg(str(nombre), escape(clase), escape(etiqueta)))


@register.filter
def cop(valor):
    """12000 -> «$ 12.000» (el formato del contrato de menús)."""
    from apps.common.money import formato_cop

    return formato_cop(valor)


@register.filter
def palabras(texto):
    """«a b c» -> ["a", "b", "c"] (para recorrer listas cortas en una plantilla)."""
    return str(texto).split()


@register.filter
def get_item(diccionario, llave):
    return (diccionario or {}).get(llave, "")


@register.filter
def split_pares(texto):
    """«a:Uno,b:Dos» -> [("a", "Uno"), ("b", "Dos")], para armar opciones en la plantilla."""
    return [tuple(par.split(":", 1)) for par in str(texto).split(",") if ":" in par]
