"""Dinero en pesos colombianos.

Siempre `Decimal`, nunca `float`. El formato para mostrar es el del contrato de
menús y el del runtime: «$ 12.000» (símbolo, espacio, punto de miles, sin
decimales).
"""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CERO = Decimal("0")


def a_pesos(valor) -> Decimal | None:
    """Convierte a Decimal entero (pesos). None si no hay valor."""
    if valor in (None, ""):
        return None
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"«{valor}» no es un precio válido.")
    return numero.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def formato_cop(valor) -> str:
    """12000 -> «$ 12.000». Vacío si no hay precio."""
    if valor in (None, ""):
        return ""
    numero = a_pesos(valor)
    texto = f"{abs(numero):,.0f}".replace(",", ".")
    return f"{'-' if numero < 0 else ''}$ {texto}"


def redondear_a(valor: Decimal, paso: int = 100) -> Decimal:
    """Redondea al múltiplo de `paso` más cercano (subir un 5 % no deja $25.237)."""
    paso = Decimal(paso)
    return ((Decimal(valor) / paso).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * paso).quantize(Decimal("1"))
