"""Anular, dar en cortesía, aceptar una devolución o hacer un descuento.

Todo pasa por aquí para que siempre quede el rastro completo: qué, cuánto,
por qué, quién lo registró y quién lo autorizó. Un cajero o mesero necesita
la contraseña de un administrador en ese momento; el administrador lo hace
directo.

Solo se hace sobre cuentas abiertas: una cuenta cerrada ya no se toca.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from .models import NovedadCuenta, Order, OrderItem, TableSession

INTENTOS_CLAVE = 5
CENTAVO = Decimal("0.01")

A_LINEA = {
    NovedadCuenta.ANULACION: OrderItem.ANULADO,
    NovedadCuenta.CORTESIA: OrderItem.CORTESIA,
    NovedadCuenta.DEVOLUCION: OrderItem.DEVOLUCION,
}


def _nombre(user) -> str:
    return (user.get_full_name() or user.username) if user else ""


def es_admin(user) -> bool:

    if user.is_superuser:
        return True
    membresia = getattr(user, "tenant_membership", None)
    return bool(membresia and membresia.es_admin)


def autorizar(request, clave: str = "") -> str:
    """Quién autoriza. Un administrador se autoriza solo; los demás necesitan
    que un administrador del restaurante escriba su contraseña.

    Devuelve el nombre de quien autorizó o lanza PermissionDenied.
    """
    from apps.tenants.models import TenantMembership

    if es_admin(request.user):
        return _nombre(request.user)

    llave = f"novedades_intentos:{request.user.pk}"
    intentos = cache.get(llave, 0)
    if intentos >= INTENTOS_CLAVE:
        raise PermissionDenied("Demasiados intentos. Espera 10 minutos.")
    if not clave:
        raise PermissionDenied("Hace falta la contraseña de un administrador para autorizarlo.")

    admins = TenantMembership.objects.filter(
        tenant=request.tenant, role__in=TenantMembership.ROLES_ADMIN
    ).select_related("user")
    for membresia in admins:
        if membresia.user.is_active and membresia.user.check_password(clave):
            cache.delete(llave)
            return _nombre(membresia.user)
    cache.set(llave, intentos + 1, 600)
    raise PermissionDenied("Esa no es la contraseña de un administrador del restaurante.")


def _motivo(motivo: str) -> str:
    motivo = (motivo or "").strip()
    if len(motivo) < 4:
        raise ValidationError("Escribe el motivo: queda registrado junto con quién lo autorizó.")
    return motivo[:200]


def _cuenta_abierta(session):
    if session.status != TableSession.STATUS_OPEN:
        raise ValidationError("La cuenta ya está cerrada: ya no se le pueden hacer cambios.")


@transaction.atomic
def novedad_en_linea(item, tipo, cantidad, motivo, *, registrado_por="", autorizado_por=""):
    """Saca de la cuenta `cantidad` unidades de una línea: anuladas, en cortesía
    o devueltas. La línea (o la parte) queda en $0 y el precio de carta se guarda."""
    if tipo not in A_LINEA:
        raise ValidationError("Tipo de novedad inválido.")
    order = item.order
    session = order.session
    _cuenta_abierta(session)
    motivo = _motivo(motivo)
    if item.novedad:
        raise ValidationError("Esa línea ya tiene una novedad registrada.")
    try:
        cantidad = int(cantidad)
    except (TypeError, ValueError):
        cantidad = 0
    if not 1 <= cantidad <= item.quantity:
        raise ValidationError(f"La cantidad debe estar entre 1 y {item.quantity}.")

    precio = item.unit_price
    if cantidad == item.quantity:
        afectada = item
        afectada.novedad = A_LINEA[tipo]
        afectada.precio_original = precio
        afectada.unit_price = Decimal("0")
        afectada.save(update_fields=["novedad", "precio_original", "unit_price"])
    else:
        item.quantity -= cantidad
        item.save(update_fields=["quantity"])
        afectada = OrderItem.objects.create(
            order=order, product=item.product, product_name=item.product_name,
            unit_price=Decimal("0"), quantity=cantidad, note=item.note, opciones=item.opciones,
            novedad=A_LINEA[tipo], precio_original=precio,
        )

    novedad = NovedadCuenta.objects.create(
        tipo=tipo, sesion=session, pedido=order, item=afectada,
        producto_nombre=item.product_name[:120], cantidad=cantidad,
        valor=(precio * cantidad).quantize(CENTAVO), motivo=motivo,
        registrado_por=registrado_por[:120], autorizado_por=autorizado_por[:120],
        mesero_nombre=order.mesero_nombre,
        ya_preparado=order.status in (Order.STATUS_PREPARING, Order.STATUS_SERVED),
    )

    # Si se anuló todo lo de una comanda, la cocina ya no la ve.
    if tipo == NovedadCuenta.ANULACION and not order.items.exclude(novedad=OrderItem.ANULADO).exists():
        order.cambiar_estado(Order.STATUS_CANCELLED)
    return novedad


@transaction.atomic
def aplicar_descuento(session, *, valor=None, porcentaje=None, motivo="", registrado_por="",
                      autorizado_por=""):
    """Un descuento sobre toda la cuenta. Uno por cuenta: el nuevo reemplaza al anterior.
    Con valor 0 se quita."""
    _cuenta_abierta(session)
    subtotal = session.subtotal()
    try:
        if porcentaje not in (None, ""):
            pct = Decimal(str(porcentaje))
            if not 0 <= pct <= 100:
                raise ValidationError("El porcentaje debe estar entre 0 y 100.")
            valor = (subtotal * pct / 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        else:
            valor = Decimal(str(valor or 0)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    except ArithmeticError:
        raise ValidationError("Escribe un valor válido.")

    anterior = session.novedades.filter(tipo=NovedadCuenta.DESCUENTO).first()
    if valor <= 0:
        session.descuento = Decimal("0")
        session.descuento_motivo = ""
        session.save(update_fields=["descuento", "descuento_motivo"])
        if anterior:
            anterior.delete()
        return None

    if valor > subtotal:
        raise ValidationError("El descuento no puede ser mayor que la cuenta.")
    motivo = _motivo(motivo)
    session.descuento = valor
    session.descuento_motivo = motivo
    session.save(update_fields=["descuento", "descuento_motivo"])

    datos = dict(
        tipo=NovedadCuenta.DESCUENTO, sesion=session, producto_nombre="",
        cantidad=1, valor=valor, porcentaje=(valor * 100 / subtotal).quantize(CENTAVO) if subtotal else 0,
        motivo=motivo, registrado_por=registrado_por[:120], autorizado_por=autorizado_por[:120],
        mesero_nombre=session.mesero.nombre if session.mesero_id else "",
    )
    if anterior:
        for campo, v in datos.items():
            setattr(anterior, campo, v)
        anterior.save()
        return anterior
    return NovedadCuenta.objects.create(**datos)

