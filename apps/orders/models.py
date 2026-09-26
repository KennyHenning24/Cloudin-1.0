from decimal import Decimal

from django.db import models
from django.utils import timezone


class TableSession(models.Model):
    """La cuenta de una mesa: se abre con el primer pedido y se cierra al pagar.

    A una misma sesión se le van agregando pedidos (comandas). El cierre de la
    sesión es lo que en la fase 2 dispara la factura electrónica.
    """

    STATUS_OPEN = "open"
    STATUS_CLOSED = "closed"
    STATUS_CANCELLED = "cancelled"
    STATUS = [
        (STATUS_OPEN, "Abierta"),
        (STATUS_CLOSED, "Cerrada"),
        (STATUS_CANCELLED, "Anulada"),
    ]

    table = models.ForeignKey(
        "dining.Table", on_delete=models.PROTECT, related_name="sessions", verbose_name="Mesa"
    )
    # El turno de caja en el que se abrió. Es lo que hace que al cerrar el turno
    # el panel quede en blanco: las pantallas de operación miran solo el turno
    # abierto, y lo del turno anterior vive en su informe.
    turno = models.ForeignKey(
        "shifts.TurnoCaja", on_delete=models.PROTECT, related_name="sesiones",
        null=True, blank=True, verbose_name="Turno de caja",
    )
    status = models.CharField(max_length=12, choices=STATUS, default=STATUS_OPEN)
    # El mesero que atiende la mesa: el que la abrió. Vacío si llegó por QR.
    mesero = models.ForeignKey(
        "waiters.Mesero", on_delete=models.SET_NULL, related_name="sesiones",
        null=True, blank=True, verbose_name="Mesero",
    )
    customer_name = models.CharField("Nombre del cliente", max_length=80, blank=True)
    guests = models.PositiveIntegerField("Personas", default=1)
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    note = models.TextField("Nota", blank=True)

    # Se congela al cerrar, para no depender de precios que cambien después.
    total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))

    # Descuento sobre toda la cuenta, con su motivo. Quién lo dio y quién lo
    # autorizó queda en NovedadCuenta; Cloudin Control lo vigila.
    descuento = models.DecimalField("Descuento", max_digits=12, decimal_places=2, default=Decimal("0"))
    descuento_motivo = models.CharField("Motivo del descuento", max_length=200, blank=True)

    # La reserva con la que llegó el cliente, si reservó: así la visita queda en
    # su historial y la reserva se completa sola al cerrar la cuenta.
    reserva = models.ForeignKey(
        "reservas.Reserva", on_delete=models.SET_NULL, related_name="cuentas",
        null=True, blank=True, verbose_name="Reserva",
    )

    # Propina voluntaria (Ley 1935 de 2018): no es ingreso del restaurante ni
    # hace parte de la factura. Se anota aparte y se reparte entre el equipo.
    propina = models.DecimalField("Propina", max_digits=12, decimal_places=2, default=Decimal("0"))
    # Cómo la pagó (códigos DIAN, igual que la factura): la de efectivo entra a la caja.
    propina_medio = models.CharField("Medio de pago de la propina", max_length=4, blank=True)

    class Meta:
        verbose_name = "Cuenta de mesa"
        verbose_name_plural = "Cuentas de mesa"
        ordering = ["-opened_at"]

    def __str__(self):
        return f"Cuenta #{self.pk} — {self.table}"

    def subtotal(self) -> Decimal:
        """Lo consumido antes del descuento. Las líneas anuladas, las cortesías y
        las devoluciones ya valen 0, así que no suman."""
        total = Decimal("0")
        for order in self.orders.exclude(status=Order.STATUS_CANCELLED):
            total += order.total()
        return total

    def current_total(self) -> Decimal:
        """Lo que paga el cliente: el consumo menos el descuento de la cuenta."""
        return max(Decimal("0"), self.subtotal() - (self.descuento or Decimal("0")))

    def close(self, total=None):
        self.total = total if total is not None else self.current_total()
        self.status = self.STATUS_CLOSED
        self.closed_at = timezone.now()
        self.save(update_fields=["total", "status", "closed_at"])
        if self.reserva_id:
            # La visita terminó: la reserva pasa al historial del cliente.
            from apps.reservas.services import completar_reserva

            completar_reserva(self.reserva, self)
        return self


class TableDraft(models.Model):
    """El pedido que los comensales de una mesa están armando entre todos.

    Vive en el servidor —y no en el teléfono de cada uno— porque varias
    personas escanean el mismo QR y tienen que ver el mismo carrito. Cuando
    alguien envía, el borrador se convierte en un Order y queda vacío.
    """

    table = models.OneToOneField(
        "dining.Table", on_delete=models.CASCADE, related_name="draft", verbose_name="Mesa"
    )
    # [{"key": "...", "name": "...", "unit_price": 0, "quantity": 1, "note": "", "by": "Ana"}]
    items = models.JSONField(default=list, blank=True)
    # Sube en cada cambio: sirve para que cada teléfono sepa si hay algo nuevo.
    version = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    # Aviso de "voy a enviar", para que nadie mande el pedido dos veces.
    announcing_by = models.CharField(max_length=60, blank=True)
    announcing_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Borrador de mesa"
        verbose_name_plural = "Borradores de mesa"

    def __str__(self):
        return f"Borrador de {self.table}"

    def total(self) -> Decimal:
        return sum(
            (Decimal(str(i["unit_price"])) * int(i.get("quantity", 1)) for i in self.items),
            Decimal("0"),
        )

    def aviso_vigente(self, segundos: int = 20):
        """Quién dijo que iba a enviar, si fue hace poco."""
        if not self.announcing_by or not self.announcing_at:
            return None
        transcurrido = (timezone.now() - self.announcing_at).total_seconds()
        return self.announcing_by if transcurrido < segundos else None

    def limpiar(self):
        self.items = []
        self.version += 1
        self.announcing_by = ""
        self.announcing_at = None
        self.save(update_fields=["items", "version", "announcing_by", "announcing_at"])


class Order(models.Model):
    """Una comanda: el grupo de productos que se manda a cocina de una vez."""

    STATUS_PENDING = "pending"
    STATUS_PREPARING = "preparing"
    STATUS_SERVED = "served"
    STATUS_CANCELLED = "cancelled"
    STATUS = [
        (STATUS_PENDING, "Pendiente"),
        (STATUS_PREPARING, "En preparación"),
        (STATUS_SERVED, "Servido"),
        (STATUS_CANCELLED, "Anulado"),
    ]

    SOURCE_QR = "qr"
    SOURCE_PANEL = "panel"
    SOURCE_MESERO = "mesero"
    SOURCES = [
        (SOURCE_QR, "Cliente (QR)"),
        (SOURCE_PANEL, "Panel"),
        (SOURCE_MESERO, "Mesero (tablet)"),
    ]

    session = models.ForeignKey(
        TableSession, on_delete=models.CASCADE, related_name="orders", verbose_name="Cuenta"
    )
    status = models.CharField(max_length=12, choices=STATUS, default=STATUS_PENDING)
    source = models.CharField(max_length=10, choices=SOURCES, default=SOURCE_QR)
    # Quién tomó la comanda. Null si vino de autoservicio. El nombre se copia
    # aparte para que la cocina y el historial lo sigan mostrando aunque el
    # mesero se borre o cambie de nombre.
    mesero = models.ForeignKey(
        "waiters.Mesero", on_delete=models.SET_NULL, related_name="pedidos",
        null=True, blank=True, verbose_name="Mesero",
    )
    mesero_nombre = models.CharField("Mesero (nombre)", max_length=80, blank=True)
    customer_name = models.CharField("Nombre del cliente", max_length=80, blank=True)
    note = models.TextField("Nota para cocina", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    printed_at = models.DateTimeField(null=True, blank=True)
    # Cuándo empezó a prepararse, cuándo salió a la mesa y cuándo se anuló:
    # de aquí salen los tiempos de cocina que mide Cloudin Control.
    preparando_en = models.DateTimeField(null=True, blank=True)
    servido_en = models.DateTimeField(null=True, blank=True)
    anulado_en = models.DateTimeField(null=True, blank=True)
    # Cuántas veces se imprimió la comanda: el botón pasa a «Imprimido», «Imprimido (1)»…
    impresiones = models.PositiveIntegerField(default=0)
    # Cuándo lo vio el administrador en el panel de mensajes.
    seen_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Pedido"
        verbose_name_plural = "Pedidos"
        ordering = ["created_at"]

    def __str__(self):
        return f"Pedido #{self.pk}"

    def total(self):
        return sum((item.line_total() for item in self.items.all()), Decimal("0"))

    def cambiar_estado(self, nuevo):
        """Pasa la comanda a otro estado y anota la hora del cambio."""
        ahora = timezone.now()
        campos = ["status", "updated_at"]
        if nuevo == self.STATUS_PREPARING and not self.preparando_en:
            self.preparando_en = ahora
            campos.append("preparando_en")
        elif nuevo == self.STATUS_SERVED and not self.servido_en:
            self.servido_en = ahora
            campos.append("servido_en")
            if not self.preparando_en:
                self.preparando_en = ahora
                campos.append("preparando_en")
        elif nuevo == self.STATUS_CANCELLED and not self.anulado_en:
            self.anulado_en = ahora
            campos.append("anulado_en")
        self.status = nuevo
        self.save(update_fields=campos)
        return self

    def minutos_cocina(self):
        """Del pedido a la mesa, en minutos. None si todavía no sale."""
        if not self.servido_en:
            return None
        return round((self.servido_en - self.created_at).total_seconds() / 60, 1)

    def mark_printed(self):
        self.printed_at = timezone.now()
        self.impresiones = (self.impresiones or 0) + 1
        self.save(update_fields=["printed_at", "impresiones"])

    def mark_seen(self):
        if self.seen_at is None:
            self.seen_at = timezone.now()
            self.save(update_fields=["seen_at"])
        return self


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    # Opcional: un pedido puede traer líneas que no son un producto del menú
    # (una combinación con opciones, o algo armado en el sitio del restaurante).
    # En ese caso el nombre y el precio los manda el sitio.
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.PROTECT,
        related_name="order_items",
        null=True,
        blank=True,
    )
    # Copia del nombre y precio al momento del pedido: el menú puede cambiar.
    product_name = models.CharField(max_length=120)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)
    note = models.CharField("Nota", max_length=200, blank=True)
    # Lo que eligió el cliente: [{"grupo": "Elige la carne", "nombre": "Brisket", "precio": 0}].
    # El precio de las opciones ya va sumado en unit_price.
    opciones = models.JSONField(default=list, blank=True)

    # Una línea que no se cobra: anulada, dada en cortesía o devuelta por el
    # cliente. Vale 0 y el precio de carta queda en precio_original.
    ANULADO = "anulado"
    CORTESIA = "cortesia"
    DEVOLUCION = "devolucion"
    NOVEDADES = [(ANULADO, "Anulado"), (CORTESIA, "Cortesía"), (DEVOLUCION, "Devolución")]
    novedad = models.CharField(max_length=12, choices=NOVEDADES, blank=True)
    precio_original = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    class Meta:
        verbose_name = "Ítem"
        verbose_name_plural = "Ítems"

    def __str__(self):
        return f"{self.quantity} x {self.product_name}"

    def save(self, *args, **kwargs):
        if not self.product_name and self.product_id:
            self.product_name = self.product.name
        if self.unit_price is None and self.product_id:
            self.unit_price = self.product.price if self.product.price is not None else Decimal("0")
        super().save(*args, **kwargs)

    def line_total(self) -> Decimal:
        return self.unit_price * self.quantity


class NovedadCuenta(models.Model):
    """Lo que se dejó de cobrar en una cuenta, con quién y por qué.

    Anular un producto, darlo en cortesía, aceptar una devolución o hacer un
    descuento es parte normal del servicio, pero también es por donde se escapa
    la plata sin que nadie lo note. Por eso cada caso queda aquí con motivo,
    quién lo registró y quién lo autorizó. Cloudin Control lee esta tabla.
    """

    ANULACION = "anulacion"
    CORTESIA = "cortesia"
    DEVOLUCION = "devolucion"
    DESCUENTO = "descuento"
    TIPOS = [
        (ANULACION, "Anulación"),
        (CORTESIA, "Cortesía"),
        (DEVOLUCION, "Devolución"),
        (DESCUENTO, "Descuento"),
    ]

    tipo = models.CharField(max_length=12, choices=TIPOS, db_index=True)
    sesion = models.ForeignKey(TableSession, on_delete=models.CASCADE, related_name="novedades")
    pedido = models.ForeignKey(Order, on_delete=models.SET_NULL, null=True, blank=True,
                               related_name="novedades")
    item = models.ForeignKey(OrderItem, on_delete=models.SET_NULL, null=True, blank=True,
                             related_name="novedades")
    turno = models.ForeignKey("shifts.TurnoCaja", on_delete=models.SET_NULL, null=True, blank=True,
                              related_name="novedades")
    producto_nombre = models.CharField(max_length=120, blank=True)
    cantidad = models.PositiveIntegerField(default=1)
    # Lo que se dejó de cobrar, a precio de carta.
    valor = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    # Para los descuentos: el porcentaje sobre el consumo.
    porcentaje = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    motivo = models.CharField(max_length=200)
    registrado_por = models.CharField(max_length=120, blank=True)
    autorizado_por = models.CharField(max_length=120, blank=True)
    mesero_nombre = models.CharField(max_length=80, blank=True)
    # Si la comanda ya estaba en preparación o servida: anular algo que la cocina
    # ya hizo sí cuesta insumos.
    ya_preparado = models.BooleanField(default=False)
    creado = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        verbose_name = "Novedad de cuenta"
        verbose_name_plural = "Novedades de cuenta"
        ordering = ["-creado"]

    def __str__(self):
        return f"{self.get_tipo_display()} · {self.producto_nombre or 'cuenta'} · {self.valor}"
