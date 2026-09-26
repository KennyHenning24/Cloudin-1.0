"""Motor de cálculo tributario.

No sabe nada del proveedor tecnológico ni de la DIAN: recibe líneas de un
pedido y devuelve bases e impuestos. Eso lo hace probable por sí solo.

El detalle que importa en restaurantes: el precio de la carta **ya incluye** el
impuesto. Si un plato vale $35.000 con INC del 8%, la base no es 35.000 sino
35.000 / 1.08 = 32.407,41 y el impuesto son 2.592,59. Facturar 35.000 como base
y sumarle el 8% encima le cobraría de más al cliente.
"""

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

CENTAVO = Decimal("0.01")


def _redondear(valor: Decimal) -> Decimal:
    return Decimal(valor).quantize(CENTAVO, rounding=ROUND_HALF_UP)


@dataclass
class LineaCalculada:
    nombre: str
    cantidad: int
    precio_unitario: Decimal      # tal como se cobró (con o sin impuesto)
    base: Decimal                 # base gravable de la línea
    impuesto_tipo: str
    impuesto_tarifa: Decimal
    impuesto_valor: Decimal
    total: Decimal                # lo que paga el cliente por esta línea
    descuento_pct: Decimal = Decimal("0")    # descuento de la cuenta repartido en la línea
    descuento_valor: Decimal = Decimal("0")

    def como_dict(self) -> dict:
        return {
            "nombre": self.nombre,
            "cantidad": self.cantidad,
            "precio_unitario": str(self.precio_unitario),
            "descuento": {"porcentaje": str(self.descuento_pct), "valor": str(self.descuento_valor)},
            "base": str(self.base),
            "impuesto": {
                "tipo": self.impuesto_tipo,
                "tarifa": str(self.impuesto_tarifa),
                "valor": str(self.impuesto_valor),
            },
            "total": str(self.total),
        }


@dataclass
class Calculo:
    lineas: list = field(default_factory=list)
    total_base: Decimal = Decimal("0")
    total_impuestos: Decimal = Decimal("0")
    total_general: Decimal = Decimal("0")
    detalle: dict = field(default_factory=dict)   # {"INC": {"tarifa","base","valor"}}

    def como_dict(self) -> dict:
        return {
            "lineas": [ln.como_dict() for ln in self.lineas],
            "total_base": str(self.total_base),
            "total_impuestos": str(self.total_impuestos),
            "total_general": str(self.total_general),
            "detalle": {
                k: {kk: str(vv) for kk, vv in v.items()} for k, v in self.detalle.items()
            },
        }


class MotorTributario:
    """Aplica las reglas del restaurante a las líneas de un pedido.

    `reglas` es una lista de (categoria_id|None, tipo, tarifa). La regla con
    categoría gana sobre la general; si no hay ninguna, la línea va exenta.
    """

    def __init__(self, reglas, precios_incluyen_impuesto: bool = True):
        self.por_categoria = {}
        self.general = None
        for categoria_id, tipo, tarifa in reglas:
            if categoria_id is None:
                self.general = (tipo, Decimal(str(tarifa)))
            else:
                self.por_categoria[categoria_id] = (tipo, Decimal(str(tarifa)))
        self.incluidos = precios_incluyen_impuesto

    @classmethod
    def desde_empresa(cls, empresa, impuestos):
        reglas = [(i.categoria_id, i.tipo, i.tarifa) for i in impuestos if i.activo]
        return cls(reglas, empresa.precios_incluyen_impuesto)

    def regla_para(self, categoria_id):
        return self.por_categoria.get(categoria_id) or self.general or ("EXENTO", Decimal("0"))

    def calcular_linea(self, nombre, cantidad, precio_unitario, categoria_id=None, descuento_pct=0):
        cantidad = int(cantidad)
        precio_unitario = Decimal(str(precio_unitario))
        descuento_pct = Decimal(str(descuento_pct or 0))
        tipo, tarifa = self.regla_para(categoria_id)
        bruto = precio_unitario * cantidad
        descuento = _redondear(bruto * descuento_pct / Decimal("100"))
        cobrado = bruto - descuento

        if tarifa == 0 or tipo == "EXENTO":
            base, impuesto, total = _redondear(cobrado), Decimal("0.00"), _redondear(cobrado)
        elif self.incluidos:
            factor = Decimal("1") + (tarifa / Decimal("100"))
            base = _redondear(cobrado / factor)
            total = _redondear(cobrado)
            impuesto = _redondear(total - base)   # así base + impuesto == total, siempre
        else:
            base = _redondear(cobrado)
            impuesto = _redondear(base * tarifa / Decimal("100"))
            total = _redondear(base + impuesto)

        return LineaCalculada(
            nombre=nombre, cantidad=cantidad, precio_unitario=precio_unitario,
            base=base, impuesto_tipo=tipo, impuesto_tarifa=tarifa,
            impuesto_valor=impuesto, total=total,
            descuento_pct=descuento_pct, descuento_valor=descuento,
        )

    def calcular(self, lineas) -> Calculo:
        """`lineas`: iterable de (nombre, cantidad, precio_unitario, categoria_id[, descuento_pct])."""
        calculo = Calculo()
        for nombre, cantidad, precio, categoria_id, *resto in lineas:
            linea = self.calcular_linea(nombre, cantidad, precio, categoria_id, resto[0] if resto else 0)
            calculo.lineas.append(linea)
            calculo.total_base += linea.base
            calculo.total_impuestos += linea.impuesto_valor
            calculo.total_general += linea.total

            if linea.impuesto_valor or linea.impuesto_tipo != "EXENTO":
                acumulado = calculo.detalle.setdefault(
                    linea.impuesto_tipo,
                    {"tarifa": linea.impuesto_tarifa, "base": Decimal("0"), "valor": Decimal("0")},
                )
                acumulado["base"] += linea.base
                acumulado["valor"] += linea.impuesto_valor

        calculo.total_base = _redondear(calculo.total_base)
        calculo.total_impuestos = _redondear(calculo.total_impuestos)
        calculo.total_general = _redondear(calculo.total_general)
        for acumulado in calculo.detalle.values():
            acumulado["base"] = _redondear(acumulado["base"])
            acumulado["valor"] = _redondear(acumulado["valor"])
        return calculo


def lineas_de_sesion(session):
    """Convierte una cuenta de mesa cerrada en líneas para el motor.

    Las líneas anuladas, en cortesía o devueltas no se facturan: no se
    cobraron. El descuento de la cuenta se reparte en todas las líneas con el
    mismo porcentaje, que es como lo espera la factura electrónica.
    """
    from apps.orders.novedades import porcentaje_descuento

    pct = porcentaje_descuento(session)
    lineas = []
    for order in session.orders.exclude(status="cancelled"):
        for item in order.items.all():
            if item.novedad or not item.quantity or not item.unit_price:
                continue
            categoria_id = item.product.category_id if item.product_id else None
            lineas.append((item.product_name, item.quantity, item.unit_price, categoria_id, pct))
    return lineas
