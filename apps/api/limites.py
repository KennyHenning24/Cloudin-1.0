"""Protecciones de la API pública (la que usan los sitios web con la X-API-Key).

La llave del sitio vive dentro del JavaScript de la página, así que cualquiera
puede leerla. Por eso lo público se protege por su cuenta:

- **Topes de envío** por dirección IP: nadie puede inundar la cocina de pedidos
  falsos ni el calendario de reservas.
- **Precios que no se pueden rebajar**: una línea sin `product_id` («armada en el
  sitio») tiene que corresponder a un plato de la carta, y nunca se cobra por
  debajo de su precio en el panel. Quien edite el JavaScript para mandar
  «Hamburguesa a $1» se encuentra con el precio real.
"""

from decimal import Decimal, InvalidOperation

from django.core.cache import cache
from rest_framework import status
from rest_framework.response import Response

from apps.panel.seguridad import ip_de


def permitido(request, nombre: str, maximo: int, ventana: int) -> bool:
    """Suma un envío y dice si todavía está dentro del tope."""
    tenant = getattr(request, "tenant", None)
    llave = f"tope:{nombre}:{tenant.slug if tenant else '-'}:{ip_de(request)}"
    actual = cache.get(llave, 0)
    if actual >= maximo:
        return False
    cache.set(llave, actual + 1, ventana)
    return True


def demasiados():
    return Response(
        {"detail": "Enviaste muchos pedidos seguidos. Espera unos minutos o pídele ayuda al mesero.",
         "codigo": "demasiados"},
        status=status.HTTP_429_TOO_MANY_REQUESTS,
    )


def producto_de_linea_libre(nombre: str):
    """El plato de la carta al que corresponde una línea armada en el sitio, o None.

    «Sandwich 2 Quesos · Brisket, papas» corresponde a «Sandwich 2 Quesos»."""
    from apps.catalog.models import Product

    nombre = (nombre or "").strip()
    if not nombre:
        return None
    candidatos = [nombre, nombre.split(" · ")[0].strip()]
    for candidato in candidatos:
        producto = (Product.objects.filter(name__iexact=candidato, eliminado=False)
                    .order_by("-is_available", "price").first())
        if producto:
            return producto
    return None


def precio_seguro(nombre: str, precio_enviado):
    """(producto, precio) para una línea sin product_id. Lanza ValueError si el
    plato no está en la carta o está agotado."""
    producto = producto_de_linea_libre(nombre)
    if producto is None:
        raise ValueError(f"«{nombre[:60]}» no está en la carta del restaurante.")
    if not producto.is_available:
        raise ValueError(f"«{producto.name}» está agotado.")
    try:
        precio = Decimal(str(precio_enviado))
    except (InvalidOperation, TypeError, ValueError):
        precio = Decimal("0")
    if producto.price is None:
        return producto, precio
    return producto, max(precio, producto.price)
