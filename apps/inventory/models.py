"""Inventario de Cloudin: insumos, recetas, kardex y compras.

Dos ideas que sostienen todo el módulo y conviene no perder de vista:

1. **Insumo ≠ producto vendible.** El insumo (carne, arroz, empaques) se compra
   y tiene stock físico. El producto del menú no tiene stock propio: su
   disponibilidad y su costo salen de la receta que lo arma.

2. **El stock nunca se edita a mano.** Todo cambio entra como `Movimiento`, con
   fecha, autor, costo del momento y motivo. El saldo es la suma de su historia,
   así que siempre se puede explicar de dónde salió cada gramo.

El costeo es **promedio ponderado** (el estándar que espera un contador en
Colombia): cada compra recalcula el costo promedio del insumo, y las salidas
usan el promedio vigente en ese instante, sin recalcular hacia atrás.
"""

from decimal import Decimal

from django.db import models
from django.utils import timezone

CERO = Decimal("0")


class Bodega(models.Model):
    """Dónde está guardado el inventario: cocina, bodega, barra, otra sede."""

    nombre = models.CharField("Nombre", max_length=80)
    descripcion = models.CharField("Descripción", max_length=200, blank=True)
    principal = models.BooleanField("Es la principal", default=False)
    activa = models.BooleanField("Activa", default=True)
    creada = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Bodega"
        verbose_name_plural = "Bodegas"
        ordering = ["-principal", "nombre"]

    def __str__(self):
        return self.nombre

    @classmethod
    def predeterminada(cls, db=None):
        """La bodega donde cae todo si el restaurante no separó ubicaciones."""
        qs = cls.objects.using(db) if db else cls.objects
        bodega = qs.filter(activa=True).order_by("-principal", "id").first()
        if bodega is None:
            bodega = qs.create(nombre="Cocina", principal=True)
        return bodega

    def valorizacion(self) -> Decimal:
        total = CERO
        for ex in self.existencias.select_related("insumo"):
            total += ex.valor()
        return total.quantize(Decimal("0.01"))


class CategoriaInsumo(models.Model):
    nombre = models.CharField("Nombre", max_length=80)
    posicion = models.PositiveIntegerField("Orden", default=0)

    class Meta:
        verbose_name = "Categoría de insumo"
        verbose_name_plural = "Categorías de insumo"
        ordering = ["posicion", "nombre"]

    def __str__(self):
        return self.nombre


class Proveedor(models.Model):
    nombre = models.CharField("Nombre o razón social", max_length=160)
    nit = models.CharField("NIT / cédula", max_length=30, blank=True)
    contacto = models.CharField("Persona de contacto", max_length=120, blank=True)
    telefono = models.CharField("Teléfono", max_length=40, blank=True)
    correo = models.EmailField("Correo", blank=True)
    direccion = models.CharField("Dirección", max_length=200, blank=True)
    dias_credito = models.PositiveIntegerField("Días de crédito", default=0)
    notas = models.TextField("Notas", blank=True)
    activo = models.BooleanField(default=True)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Proveedor"
        verbose_name_plural = "Proveedores"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Insumo(models.Model):
    """Materia prima: lo que se le compra al proveedor y sí tiene stock real."""

    UNIDADES = [
        ("g", "Gramos (g)"),
        ("kg", "Kilogramos (kg)"),
        ("ml", "Mililitros (ml)"),
        ("l", "Litros (L)"),
        ("und", "Unidades"),
        ("porcion", "Porciones"),
    ]

    codigo = models.CharField("Código de referencia", max_length=30, blank=True, db_index=True)
    nombre = models.CharField("Nombre", max_length=140)
    categoria = models.ForeignKey(
        CategoriaInsumo, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="insumos", verbose_name="Categoría",
    )

    # Se compra por bulto y se consume por gramo: el factor los une.
    unidad_compra = models.CharField("Unidad de compra", max_length=40, default="kg",
                                     help_text="Como se la vende el proveedor: bulto, caja, kg…")
    unidad_consumo = models.CharField("Unidad de consumo", max_length=10, choices=UNIDADES,
                                      default="g", help_text="Como la usa la receta.")
    factor_conversion = models.DecimalField(
        "Unidades de consumo por unidad de compra", max_digits=14, decimal_places=4,
        default=Decimal("1000"),
        help_text="Un bulto de 50 kg que se consume en gramos: 50000.",
    )

    costo_promedio = models.DecimalField(
        "Costo promedio por unidad de consumo", max_digits=14, decimal_places=4, default=CERO
    )
    ultimo_precio_compra = models.DecimalField(
        "Último precio de compra (por unidad de compra)", max_digits=14, decimal_places=2,
        default=CERO,
    )
    ultima_compra = models.DateField("Fecha de la última compra", null=True, blank=True)

    stock_minimo = models.DecimalField(
        "Stock mínimo", max_digits=14, decimal_places=3, default=CERO,
        help_text="Por debajo de esto, el panel avisa que hay que reponer.",
    )
    perecedero = models.BooleanField(
        "Perecedero", default=False, help_text="Si lo es, se controla por lote y vencimiento."
    )
    proveedor = models.ForeignKey(
        Proveedor, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="insumos", verbose_name="Proveedor habitual",
    )
    activo = models.BooleanField(default=True)
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Insumo"
        verbose_name_plural = "Insumos"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre

    # ------------------------------------------------------------ existencias

    @property
    def stock(self) -> Decimal:
        """Cuánto hay, sumando todas las bodegas, en unidad de consumo."""
        total = self.existencias.aggregate(s=models.Sum("cantidad"))["s"] or CERO
        return Decimal(total)

    def stock_en(self, bodega) -> Decimal:
        ex = self.existencias.filter(bodega=bodega).first()
        return ex.cantidad if ex else CERO

    @property
    def valor_stock(self) -> Decimal:
        return (self.stock * self.costo_promedio).quantize(Decimal("0.01"))

    @property
    def bajo_minimo(self) -> bool:
        return self.stock_minimo > 0 and self.stock <= self.stock_minimo

    @property
    def agotado(self) -> bool:
        return self.stock <= 0

    @property
    def costo_unidad_compra(self) -> Decimal:
        """Lo que cuesta, al promedio actual, una unidad de compra completa."""
        return (self.costo_promedio * self.factor_conversion).quantize(Decimal("0.01"))

    def unidad_consumo_texto(self) -> str:
        return dict(self.UNIDADES).get(self.unidad_consumo, self.unidad_consumo)


class Existencia(models.Model):
    """El saldo de un insumo en una bodega. Solo lo escriben los movimientos."""

    insumo = models.ForeignKey(Insumo, on_delete=models.CASCADE, related_name="existencias")
    bodega = models.ForeignKey(Bodega, on_delete=models.CASCADE, related_name="existencias")
    cantidad = models.DecimalField(max_digits=16, decimal_places=3, default=CERO)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Existencia"
        verbose_name_plural = "Existencias"
        unique_together = [("insumo", "bodega")]
        ordering = ["insumo__nombre"]

    def __str__(self):
        return f"{self.insumo.nombre} en {self.bodega.nombre}: {self.cantidad}"

    def valor(self) -> Decimal:
        return (self.cantidad * self.insumo.costo_promedio).quantize(Decimal("0.01"))


class Lote(models.Model):
    """Un lote de un insumo perecedero, con su vencimiento.

    La salida física prioriza el lote que vence primero (PEPS de rotación). El
    costeo sigue siendo promedio ponderado: son dos cosas distintas — se rota
    por antigüedad, se cuesta por promedio.
    """

    insumo = models.ForeignKey(Insumo, on_delete=models.CASCADE, related_name="lotes")
    bodega = models.ForeignKey(Bodega, on_delete=models.CASCADE, related_name="lotes")
    codigo = models.CharField("Lote", max_length=40, blank=True)
    vence = models.DateField("Vence", null=True, blank=True)
    cantidad = models.DecimalField(max_digits=16, decimal_places=3, default=CERO)
    costo_unitario = models.DecimalField(max_digits=14, decimal_places=4, default=CERO)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Lote"
        verbose_name_plural = "Lotes"
        ordering = ["vence", "creado"]

    def __str__(self):
        etiqueta = self.codigo or f"lote {self.pk}"
        return f"{self.insumo.nombre} · {etiqueta}"

    @property
    def dias_para_vencer(self):
        if not self.vence:
            return None
        return (self.vence - timezone.localdate()).days

    @property
    def vencido(self) -> bool:
        dias = self.dias_para_vencer
        return dias is not None and dias < 0


class Receta(models.Model):
    """Lo que consume un plato. O una subreceta, que se usa en varios platos.

    La subreceta («salsa base») se define una vez y los platos la usan como si
    fuera un insumo. Su costo se calcula por porción de rendimiento.
    """

    producto = models.OneToOneField(
        "catalog.Product", on_delete=models.CASCADE, related_name="receta",
        null=True, blank=True, verbose_name="Producto del menú",
    )
    nombre = models.CharField("Nombre", max_length=140, blank=True)
    es_subreceta = models.BooleanField(
        "Es una subreceta (producto intermedio)", default=False,
        help_text="No se vende sola: se usa dentro de otras recetas.",
    )
    rendimiento = models.DecimalField(
        "Rendimiento", max_digits=12, decimal_places=3, default=Decimal("1"),
        help_text="Cuántas porciones o unidades salen de preparar la receta una vez.",
    )
    unidad_rendimiento = models.CharField("Unidad del rendimiento", max_length=20,
                                          default="porcion")
    notas = models.TextField("Preparación / notas", blank=True)
    activa = models.BooleanField(default=True)
    creada = models.DateTimeField(auto_now_add=True)
    actualizada = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Receta"
        verbose_name_plural = "Recetas"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre or (self.producto.name if self.producto_id else f"Receta {self.pk}")

    @property
    def titulo(self) -> str:
        if self.producto_id:
            return self.producto.name
        return self.nombre or f"Receta {self.pk}"

    def costo(self, _visitados=None) -> Decimal:
        """Costo de una porción: suma de sus insumos al promedio de hoy.

        `_visitados` corta las referencias circulares: si alguien hiciera que A
        use B y B use A, el costo sería infinito en vez de un error claro.
        """
        visitados = set(_visitados or ())
        if self.pk in visitados:
            return CERO
        visitados.add(self.pk)

        total = CERO
        for item in self.items.select_related("insumo", "subreceta"):
            total += item.costo(visitados)
        rendimiento = self.rendimiento or Decimal("1")
        return (total / rendimiento).quantize(Decimal("0.01"))

    def falta_stock(self, unidades=Decimal("1")) -> list:
        """Qué insumos no alcanzan para preparar `unidades` porciones."""
        faltantes = []
        for insumo, cantidad in self.explosion(unidades).items():
            if insumo.stock < cantidad:
                faltantes.append({"insumo": insumo, "necesita": cantidad, "hay": insumo.stock})
        return faltantes

    def explosion(self, unidades=Decimal("1"), _visitados=None) -> dict:
        """Los insumos finales y la cantidad total que consume, ya desarmando
        las subrecetas. Es lo que se descuenta del stock al vender."""
        visitados = set(_visitados or ())
        if self.pk in visitados:
            return {}
        visitados.add(self.pk)

        unidades = Decimal(str(unidades))
        factor = unidades / (self.rendimiento or Decimal("1"))
        consumo = {}
        for item in self.items.select_related("insumo", "subreceta"):
            if item.insumo_id:
                consumo[item.insumo] = consumo.get(item.insumo, CERO) + item.cantidad * factor
            elif item.subreceta_id:
                for insumo, cant in item.subreceta.explosion(
                    item.cantidad * factor, visitados
                ).items():
                    consumo[insumo] = consumo.get(insumo, CERO) + cant
        return consumo


class RecetaItem(models.Model):
    """Una línea de la receta: tanto de este insumo, o tanto de esta subreceta."""

    receta = models.ForeignKey(Receta, on_delete=models.CASCADE, related_name="items")
    insumo = models.ForeignKey(
        Insumo, on_delete=models.PROTECT, related_name="en_recetas", null=True, blank=True
    )
    subreceta = models.ForeignKey(
        Receta, on_delete=models.PROTECT, related_name="usada_en", null=True, blank=True
    )
    cantidad = models.DecimalField("Cantidad", max_digits=14, decimal_places=3,
                                   default=Decimal("1"))
    nota = models.CharField("Nota", max_length=160, blank=True)

    class Meta:
        verbose_name = "Ingrediente"
        verbose_name_plural = "Ingredientes"
        ordering = ["id"]

    def __str__(self):
        return f"{self.cantidad} {self.unidad} de {self.que}"

    @property
    def que(self) -> str:
        if self.insumo_id:
            return self.insumo.nombre
        if self.subreceta_id:
            return self.subreceta.titulo
        return "—"

    @property
    def unidad(self) -> str:
        if self.insumo_id:
            return self.insumo.unidad_consumo
        if self.subreceta_id:
            return self.subreceta.unidad_rendimiento
        return ""

    def costo(self, _visitados=None) -> Decimal:
        if self.insumo_id:
            return (self.cantidad * self.insumo.costo_promedio).quantize(Decimal("0.01"))
        if self.subreceta_id:
            return (self.cantidad * self.subreceta.costo(_visitados)).quantize(Decimal("0.01"))
        return CERO


class Compra(models.Model):
    """Una compra de insumos, con el origen del dinero.

    Saber de dónde salió la plata es lo que permite responder después «cuánto
    gastamos en insumos este mes y con qué se pagó».
    """

    EFECTIVO = "caja"
    BANCO = "banco"
    TARJETA = "tarjeta"
    CREDITO = "credito"
    MEDIOS = [
        (EFECTIVO, "Caja / efectivo"),
        (BANCO, "Cuenta bancaria"),
        (TARJETA, "Tarjeta del negocio"),
        (CREDITO, "Crédito con el proveedor"),
    ]

    BORRADOR = "borrador"
    REGISTRADA = "registrada"
    ANULADA = "anulada"
    ESTADOS = [(BORRADOR, "Borrador"), (REGISTRADA, "Registrada"), (ANULADA, "Anulada")]

    proveedor = models.ForeignKey(
        Proveedor, on_delete=models.PROTECT, related_name="compras", verbose_name="Proveedor"
    )
    bodega = models.ForeignKey(
        Bodega, on_delete=models.PROTECT, related_name="compras", verbose_name="Entra a la bodega"
    )
    numero_factura = models.CharField("Factura del proveedor", max_length=40, blank=True)
    fecha = models.DateField("Fecha de la compra", default=timezone.localdate)

    medio_pago = models.CharField("Se pagó con", max_length=10, choices=MEDIOS, default=EFECTIVO)
    cuenta = models.CharField(
        "Cuenta o tarjeta", max_length=80, blank=True,
        help_text="Cuál cuenta bancaria o tarjeta, para poder cruzarlo después.",
    )
    vence = models.DateField("Vence el (si es a crédito)", null=True, blank=True)
    pagada = models.BooleanField("Ya está pagada", default=True)

    total = models.DecimalField(max_digits=14, decimal_places=2, default=CERO)
    estado = models.CharField(max_length=12, choices=ESTADOS, default=BORRADOR, db_index=True)
    notas = models.TextField("Notas", blank=True)
    usuario = models.CharField("Registrada por", max_length=120, blank=True)
    creada = models.DateTimeField(auto_now_add=True)
    registrada_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Compra"
        verbose_name_plural = "Compras"
        ordering = ["-fecha", "-id"]

    def __str__(self):
        return f"Compra {self.numero_factura or self.pk} · {self.proveedor.nombre}"

    def calcular_total(self) -> Decimal:
        return sum((i.subtotal() for i in self.items.all()), CERO)

    @property
    def por_pagar(self) -> bool:
        return self.medio_pago == self.CREDITO and not self.pagada

    @property
    def vencida(self) -> bool:
        return bool(self.por_pagar and self.vence and self.vence < timezone.localdate())


class CompraItem(models.Model):
    compra = models.ForeignKey(Compra, on_delete=models.CASCADE, related_name="items")
    insumo = models.ForeignKey(Insumo, on_delete=models.PROTECT, related_name="compras")
    # Se compra en unidad de compra (bultos, cajas) y el sistema lo convierte.
    cantidad = models.DecimalField("Cantidad (unidad de compra)", max_digits=14, decimal_places=3,
                                   default=Decimal("1"))
    valor_unitario = models.DecimalField("Valor por unidad de compra", max_digits=14,
                                          decimal_places=2, default=CERO)
    lote = models.CharField("Lote", max_length=40, blank=True)
    vence = models.DateField("Vence", null=True, blank=True)

    class Meta:
        verbose_name = "Línea de compra"
        verbose_name_plural = "Líneas de compra"
        ordering = ["id"]

    def __str__(self):
        return f"{self.cantidad} {self.insumo.unidad_compra} de {self.insumo.nombre}"

    def subtotal(self) -> Decimal:
        return (self.cantidad * self.valor_unitario).quantize(Decimal("0.01"))

    def cantidad_consumo(self) -> Decimal:
        """La cantidad traducida a la unidad con la que trabajan las recetas."""
        return self.cantidad * (self.insumo.factor_conversion or Decimal("1"))

    def costo_consumo(self) -> Decimal:
        """Cuánto cuesta cada unidad de consumo en esta compra."""
        unidades = self.cantidad_consumo()
        if not unidades:
            return CERO
        return (self.subtotal() / unidades).quantize(Decimal("0.0001"))


class Movimiento(models.Model):
    """El kardex: una fila por cada cosa que le pasó al inventario.

    Nadie edita el stock: se registra un movimiento y el saldo se mueve con él.
    Cada fila guarda el costo promedio de ese instante, así el kardex valorado
    se puede reconstruir tal como era.
    """

    COMPRA = "compra"
    AJUSTE_POSITIVO = "ajuste_mas"
    DEVOLUCION_CLIENTE = "dev_cliente"
    TRASLADO_ENTRADA = "traslado_in"
    CONTEO_POSITIVO = "conteo_mas"
    PRODUCCION = "produccion"

    VENTA = "venta"
    AJUSTE_NEGATIVO = "ajuste_menos"
    MERMA = "merma"
    DEVOLUCION_PROVEEDOR = "dev_proveedor"
    TRASLADO_SALIDA = "traslado_out"
    CONTEO_NEGATIVO = "conteo_menos"

    TIPOS = [
        (COMPRA, "Compra a proveedor"),
        (AJUSTE_POSITIVO, "Ajuste positivo"),
        (DEVOLUCION_CLIENTE, "Devolución de cliente"),
        (TRASLADO_ENTRADA, "Traslado recibido"),
        (CONTEO_POSITIVO, "Conteo físico (sobrante)"),
        (PRODUCCION, "Producción de subreceta"),
        (VENTA, "Venta (receta)"),
        (AJUSTE_NEGATIVO, "Ajuste negativo"),
        (MERMA, "Merma o desperdicio"),
        (DEVOLUCION_PROVEEDOR, "Devolución a proveedor"),
        (TRASLADO_SALIDA, "Traslado enviado"),
        (CONTEO_NEGATIVO, "Conteo físico (faltante)"),
    ]

    ENTRADAS = [COMPRA, AJUSTE_POSITIVO, DEVOLUCION_CLIENTE, TRASLADO_ENTRADA,
                CONTEO_POSITIVO, PRODUCCION]
    SALIDAS = [VENTA, AJUSTE_NEGATIVO, MERMA, DEVOLUCION_PROVEEDOR, TRASLADO_SALIDA,
               CONTEO_NEGATIVO]
    # Las que no son ni venta ni compra: lo que un conteo físico debería explicar.
    DESCONTROLADAS = [AJUSTE_NEGATIVO, MERMA, CONTEO_NEGATIVO]

    insumo = models.ForeignKey(Insumo, on_delete=models.PROTECT, related_name="movimientos")
    bodega = models.ForeignKey(Bodega, on_delete=models.PROTECT, related_name="movimientos")
    tipo = models.CharField(max_length=16, choices=TIPOS, db_index=True)
    cantidad = models.DecimalField("Cantidad (unidad de consumo)", max_digits=16, decimal_places=3)
    costo_unitario = models.DecimalField(max_digits=14, decimal_places=4, default=CERO)
    valor_total = models.DecimalField(max_digits=16, decimal_places=2, default=CERO)

    # Saldos después del movimiento: el kardex no tiene que recalcularlos.
    saldo_cantidad = models.DecimalField(max_digits=16, decimal_places=3, default=CERO)
    saldo_costo_promedio = models.DecimalField(max_digits=14, decimal_places=4, default=CERO)

    motivo = models.CharField("Motivo", max_length=200, blank=True)
    usuario = models.CharField("Quién lo registró", max_length=120, blank=True)
    momento = models.DateTimeField(default=timezone.now, db_index=True)

    compra = models.ForeignKey(
        Compra, on_delete=models.SET_NULL, null=True, blank=True, related_name="movimientos"
    )
    lote = models.ForeignKey(
        Lote, on_delete=models.SET_NULL, null=True, blank=True, related_name="movimientos"
    )
    orden = models.ForeignKey(
        "orders.Order", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="movimientos_inventario",
    )
    turno = models.ForeignKey(
        "shifts.TurnoCaja", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="movimientos_inventario",
    )
    conteo = models.ForeignKey(
        "inventory.Conteo", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="movimientos",
    )

    class Meta:
        verbose_name = "Movimiento de inventario"
        verbose_name_plural = "Movimientos de inventario"
        ordering = ["-momento", "-id"]

    def __str__(self):
        return f"{self.get_tipo_display()} · {self.cantidad} {self.insumo.unidad_consumo}"

    @property
    def es_entrada(self) -> bool:
        return self.tipo in self.ENTRADAS

    @property
    def signo(self) -> int:
        return 1 if self.es_entrada else -1


class Conteo(models.Model):
    """Un conteo físico: lo que de verdad hay, contra lo que dice el sistema.

    Al aplicarlo, la diferencia de cada insumo entra como ajuste con su motivo,
    para que el faltante quede explicado y no desaparezca en silencio.
    """

    BORRADOR = "borrador"
    APLICADO = "aplicado"
    ESTADOS = [(BORRADOR, "En conteo"), (APLICADO, "Aplicado")]

    bodega = models.ForeignKey(Bodega, on_delete=models.PROTECT, related_name="conteos")
    fecha = models.DateTimeField(default=timezone.now)
    responsable = models.CharField("Quién contó", max_length=120, blank=True)
    notas = models.TextField("Notas", blank=True)
    estado = models.CharField(max_length=10, choices=ESTADOS, default=BORRADOR, db_index=True)
    aplicado_en = models.DateTimeField(null=True, blank=True)
    diferencia_valor = models.DecimalField(max_digits=14, decimal_places=2, default=CERO)

    class Meta:
        verbose_name = "Conteo físico"
        verbose_name_plural = "Conteos físicos"
        ordering = ["-fecha"]

    def __str__(self):
        return f"Conteo {self.pk} · {self.bodega.nombre} · {self.fecha:%d/%m/%Y}"


class ConteoItem(models.Model):
    conteo = models.ForeignKey(Conteo, on_delete=models.CASCADE, related_name="items")
    insumo = models.ForeignKey(Insumo, on_delete=models.PROTECT, related_name="conteos")
    esperado = models.DecimalField(max_digits=16, decimal_places=3, default=CERO)
    contado = models.DecimalField(max_digits=16, decimal_places=3, default=CERO)

    class Meta:
        verbose_name = "Línea de conteo"
        verbose_name_plural = "Líneas de conteo"
        ordering = ["insumo__nombre"]

    def __str__(self):
        return f"{self.insumo.nombre}: {self.contado} (esperado {self.esperado})"

    @property
    def diferencia(self) -> Decimal:
        return self.contado - self.esperado

    @property
    def valor_diferencia(self) -> Decimal:
        return (self.diferencia * self.insumo.costo_promedio).quantize(Decimal("0.01"))
