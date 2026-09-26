"""Facturación electrónica: datos fiscales del restaurante y documentos DIAN.

Todo vive en la base del restaurante (no en la de control), igual que el menú y
los pedidos: un restaurante nunca puede ver los documentos de otro.

El flujo es: una cuenta de mesa se cierra -> se construye un DocumentoFiscal ->
se manda al Proveedor Tecnológico (PT) -> el PT lo valida ante la DIAN y
devuelve CUFE, XML y PDF. Cloudin no se certifica ante la DIAN: eso lo hace el
PT, que ya está certificado.
"""

from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone


class EmpresaFiscal(models.Model):
    """Los datos con los que el restaurante factura. Uno solo por restaurante."""

    REGIMEN_IVA = "iva"
    REGIMEN_INC = "inc"
    REGIMEN_NO_RESPONSABLE = "no_responsable"
    REGIMENES = [
        (REGIMEN_IVA, "Responsable de IVA"),
        (REGIMEN_INC, "Responsable de INC (restaurantes)"),
        (REGIMEN_NO_RESPONSABLE, "No responsable"),
    ]

    NO_HABILITADO = "no_habilitado"
    EN_PRUEBAS = "en_pruebas"
    HABILITADO = "habilitado"
    RECHAZADO = "rechazado"
    ESTADOS = [
        (NO_HABILITADO, "No habilitado"),
        (EN_PRUEBAS, "En pruebas con el proveedor"),
        (HABILITADO, "Habilitado"),
        (RECHAZADO, "Rechazado"),
    ]

    razon_social = models.CharField("Razón social", max_length=180)
    nombre_comercial = models.CharField("Nombre comercial", max_length=180, blank=True)
    nit = models.CharField("NIT", max_length=20)
    digito_verificacion = models.CharField("DV", max_length=1, blank=True)
    direccion = models.CharField("Dirección", max_length=200, blank=True)
    ciudad = models.CharField("Ciudad", max_length=80, blank=True)
    departamento = models.CharField("Departamento", max_length=80, blank=True)
    correo_facturacion = models.EmailField("Correo de facturación", blank=True)
    telefono = models.CharField("Teléfono", max_length=40, blank=True)

    regimen = models.CharField("Régimen", max_length=20, choices=REGIMENES, default=REGIMEN_INC)
    # Los precios del menú en un restaurante ya incluyen el impuesto: al
    # facturar hay que sacar la base, no sumarle el impuesto encima.
    precios_incluyen_impuesto = models.BooleanField(
        "Los precios del menú ya incluyen impuesto", default=True
    )

    # Nunca el archivo ni la clave en claro: solo una referencia cifrada.
    certificado_ref = models.TextField("Certificado (referencia cifrada)", blank=True)
    certificado_vence = models.DateField("Vencimiento del certificado", null=True, blank=True)

    proveedor = models.CharField(
        "Proveedor tecnológico", max_length=40, default="simulado",
        help_text="Identificador del PT: 'simulado' mientras no haya uno real.",
    )
    credenciales_pt = models.TextField("Credenciales del PT (cifradas)", blank=True)
    estado_habilitacion = models.CharField(max_length=20, choices=ESTADOS, default=NO_HABILITADO)

    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Datos fiscales"
        verbose_name_plural = "Datos fiscales"

    def __str__(self):
        return self.razon_social or self.nit

    @property
    def certificado_vigente(self) -> bool:
        return bool(self.certificado_vence and self.certificado_vence >= timezone.localdate())

    def resolucion_vigente(self, tipo=None):
        qs = self.resoluciones.filter(activa=True)
        if tipo:
            qs = qs.filter(tipo_documento=tipo)
        if self.firma_el_proveedor:
            # Con un PT real solo sirven los rangos que existen en el PT: los que
            # se trajeron de él tienen su id. Una resolución cargada a mano para
            # el simulado no se puede usar para facturar ante la DIAN.
            qs = qs.filter(id_rango_proveedor__isnull=False)
        return next((r for r in qs.order_by("fecha_vencimiento") if r.utilizable), None)

    @property
    def firma_el_proveedor(self) -> bool:
        """Con un PT real (Factus) el documento lo firma el PT con su propio
        certificado: el restaurante no necesita cargar uno."""
        return (self.proveedor or "simulado") != "simulado"

    def requisitos(self) -> dict:
        """Los tres requisitos para poder facturar de verdad, y si se cumplen."""
        return {
            "datos_empresa": bool(self.razon_social and self.nit),
            "certificado": self.firma_el_proveedor or self.certificado_vigente,
            "resolucion": self.resolucion_vigente() is not None,
        }

    @property
    def puede_facturar(self) -> bool:
        return all(self.requisitos().values()) and self.estado_habilitacion in (
            self.EN_PRUEBAS,
            self.HABILITADO,
        )


class ResolucionNumeracion(models.Model):
    """La autorización de la DIAN para numerar documentos, con su consecutivo."""

    FACTURA = "factura"
    POS = "doc_equivalente_pos"
    NOTA_CREDITO = "nota_credito"
    NOTA_DEBITO = "nota_debito"
    TIPOS = [
        (FACTURA, "Factura electrónica de venta"),
        (POS, "Documento equivalente POS"),
        (NOTA_CREDITO, "Nota crédito"),
        (NOTA_DEBITO, "Nota débito"),
    ]

    empresa = models.ForeignKey(
        EmpresaFiscal, on_delete=models.CASCADE, related_name="resoluciones"
    )
    tipo_documento = models.CharField(max_length=24, choices=TIPOS, default=FACTURA)
    numero_resolucion = models.CharField("Número de resolución", max_length=40)
    fecha_expedicion = models.DateField()
    fecha_vencimiento = models.DateField()
    prefijo = models.CharField(max_length=10, blank=True)
    rango_desde = models.PositiveIntegerField()
    rango_hasta = models.PositiveIntegerField()
    consecutivo_actual = models.PositiveIntegerField(
        help_text="El último número usado. El siguiente documento lleva este + 1."
    )
    clave_tecnica = models.CharField(max_length=120, blank=True)
    # El id del rango en el proveedor tecnológico (numbering_range_id de Factus).
    id_rango_proveedor = models.PositiveIntegerField(null=True, blank=True)
    activa = models.BooleanField(default=True)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Resolución de numeración"
        verbose_name_plural = "Resoluciones de numeración"
        ordering = ["-fecha_vencimiento"]

    def __str__(self):
        return f"{self.prefijo}{self.rango_desde}-{self.rango_hasta} ({self.numero_resolucion})"

    def clean(self):
        if self.rango_hasta < self.rango_desde:
            raise ValidationError({"rango_hasta": "El rango final no puede ser menor que el inicial."})
        if self.consecutivo_actual and not (
            self.rango_desde - 1 <= self.consecutivo_actual <= self.rango_hasta
        ):
            raise ValidationError({"consecutivo_actual": "El consecutivo está fuera del rango."})

    @property
    def vencida(self) -> bool:
        return self.fecha_vencimiento < timezone.localdate()

    @property
    def disponibles(self) -> int:
        return max(0, self.rango_hasta - self.consecutivo_actual)

    @property
    def agotada(self) -> bool:
        return self.disponibles == 0

    @property
    def utilizable(self) -> bool:
        return self.activa and not self.vencida and not self.agotada

    def por_agotarse(self, umbral: int = 50) -> bool:
        return 0 < self.disponibles <= umbral

    def por_vencer(self, dias: int = 30) -> bool:
        limite = timezone.localdate() + timedelta(days=dias)
        return not self.vencida and self.fecha_vencimiento <= limite

    @property
    def estado(self) -> str:
        if self.vencida:
            return "vencida"
        if self.agotada:
            return "agotada"
        if not self.activa:
            return "inactiva"
        return "activa"

    def tomar_consecutivo(self) -> tuple[int, str]:
        """Reserva el siguiente número. Se bloquea la fila para que dos cajas
        simultáneas nunca reciban el mismo consecutivo."""
        with transaction.atomic(using=self._state.db):
            actual = (
                ResolucionNumeracion.objects.using(self._state.db)
                .select_for_update()
                .get(pk=self.pk)
            )
            if not actual.utilizable:
                raise ValidationError(f"La resolución está {actual.estado}.")
            siguiente = max(actual.consecutivo_actual + 1, actual.rango_desde)
            actual.consecutivo_actual = siguiente
            actual.save(update_fields=["consecutivo_actual"])
            self.consecutivo_actual = siguiente
        return siguiente, f"{self.prefijo}{siguiente}"


class ClienteFiscal(models.Model):
    """El comprador. Casi siempre «consumidor final» en un restaurante."""

    CC = "13"
    NIT = "31"
    CE = "22"
    PASAPORTE = "41"
    CONSUMIDOR_FINAL = "cf"
    TIPOS = [
        (CC, "Cédula de ciudadanía"),
        (NIT, "NIT"),
        (CE, "Cédula de extranjería"),
        (PASAPORTE, "Pasaporte"),
        (CONSUMIDOR_FINAL, "Consumidor final"),
    ]

    tipo_documento = models.CharField(max_length=4, choices=TIPOS, default=CONSUMIDOR_FINAL)
    numero_documento = models.CharField(max_length=30, blank=True)
    nombre = models.CharField(max_length=180, default="Consumidor final")
    correo = models.EmailField(blank=True)
    telefono = models.CharField(max_length=40, blank=True)
    direccion = models.CharField(max_length=200, blank=True)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Cliente para facturar"
        verbose_name_plural = "Clientes para facturar"

    def __str__(self):
        return f"{self.nombre} ({self.numero_documento or 'consumidor final'})"

    @classmethod
    def consumidor_final(cls, db=None):
        qs = cls.objects.using(db) if db else cls.objects
        obj, _ = qs.get_or_create(
            tipo_documento=cls.CONSUMIDOR_FINAL,
            numero_documento="222222222222",
            defaults={"nombre": "Consumidor final"},
        )
        return obj


class Impuesto(models.Model):
    """Catálogo tributario del restaurante: qué se cobra y sobre qué."""

    IVA = "IVA"
    INC = "INC"
    EXENTO = "EXENTO"
    TIPOS = [(IVA, "IVA"), (INC, "Impuesto Nacional al Consumo"), (EXENTO, "Exento")]

    tipo = models.CharField(max_length=10, choices=TIPOS, default=INC)
    nombre = models.CharField(max_length=60, blank=True)
    tarifa = models.DecimalField(
        "Tarifa (%)", max_digits=5, decimal_places=2, default=Decimal("8.00")
    )
    # Sin categoría, aplica a todo lo que no tenga una regla más específica.
    categoria = models.ForeignKey(
        "catalog.Category",
        on_delete=models.CASCADE,
        related_name="impuestos",
        null=True,
        blank=True,
        verbose_name="Solo para esta categoría",
    )
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Impuesto"
        verbose_name_plural = "Impuestos"
        ordering = ["categoria__id", "tipo"]

    def __str__(self):
        alcance = self.categoria.name if self.categoria else "todo el menú"
        return f"{self.tipo} {self.tarifa}% · {alcance}"


class DocumentoFiscal(models.Model):
    """Una factura (o nota, o documento POS) y todo su ciclo de vida."""

    TIPOS = ResolucionNumeracion.TIPOS

    # Métodos de pago de la DIAN (tabla de Factus).
    EFECTIVO = "10"
    TARJETA_DEBITO = "49"
    TARJETA_CREDITO = "48"
    TRANSFERENCIA = "47"
    MEDIOS_PAGO = [
        (EFECTIVO, "Efectivo"),
        (TARJETA_DEBITO, "Tarjeta débito"),
        (TARJETA_CREDITO, "Tarjeta crédito"),
        (TRANSFERENCIA, "Transferencia"),
    ]

    PENDIENTE = "pendiente_envio"
    ENVIADA = "enviada"
    ACEPTADA = "aceptada_dian"
    RECHAZADA = "rechazada"
    CONTINGENCIA = "en_contingencia"
    ANULADA = "anulada"
    ESTADOS = [
        (PENDIENTE, "Pendiente de envío"),
        (ENVIADA, "Enviada al proveedor"),
        (ACEPTADA, "Aceptada por la DIAN"),
        (RECHAZADA, "Rechazada"),
        (CONTINGENCIA, "En contingencia"),
        (ANULADA, "Anulada"),
    ]

    # La "cuenta de mesa" cerrada es el pedido que se factura.
    sesion = models.ForeignKey(
        "orders.TableSession",
        on_delete=models.PROTECT,
        related_name="documentos",
        null=True,
        blank=True,
        verbose_name="Cuenta de mesa",
    )
    # El turno de caja en el que se emitió, para el informe de cierre.
    turno = models.ForeignKey(
        "shifts.TurnoCaja", on_delete=models.PROTECT, related_name="documentos",
        null=True, blank=True, verbose_name="Turno de caja",
    )
    cliente = models.ForeignKey(
        ClienteFiscal, on_delete=models.PROTECT, related_name="documentos", null=True, blank=True
    )
    resolucion = models.ForeignKey(
        ResolucionNumeracion, on_delete=models.PROTECT, related_name="documentos",
        null=True, blank=True,
    )
    documento_referencia = models.ForeignKey(
        "self", on_delete=models.PROTECT, related_name="notas", null=True, blank=True,
        help_text="La factura que corrige o anula esta nota.",
    )

    tipo = models.CharField(max_length=24, choices=TIPOS, default=ResolucionNumeracion.FACTURA)
    prefijo = models.CharField(max_length=10, blank=True)
    consecutivo = models.PositiveIntegerField(null=True, blank=True)
    numero_completo = models.CharField(max_length=30, blank=True, db_index=True)
    cufe = models.CharField("CUFE", max_length=120, blank=True, db_index=True)

    estado = models.CharField(max_length=20, choices=ESTADOS, default=PENDIENTE, db_index=True)
    motivo_rechazo = models.TextField(blank=True)
    intentos = models.PositiveIntegerField(default=0)

    medio_pago = models.CharField(
        "Medio de pago", max_length=4, choices=MEDIOS_PAGO, default=EFECTIVO
    )
    # El reference_code con que se mandó al PT: el mismo en cada reintento, para
    # que el PT reconozca que es la misma factura y no cree otra.
    referencia_pt = models.CharField(max_length=60, blank=True, db_index=True)

    xml_url = models.URLField(max_length=500, blank=True)
    pdf_url = models.URLField(max_length=500, blank=True)
    qr_url = models.URLField("Enlace de consulta DIAN", max_length=500, blank=True)
    respuesta_pt = models.JSONField("Respuesta cruda del proveedor", default=dict, blank=True)

    # Congelado al emitir: la factura no puede cambiar si cambia el menú.
    lineas = models.JSONField(default=list, blank=True)
    total_base = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    total_impuestos = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    impuestos_detalle = models.JSONField(default=dict, blank=True)  # {"INC": {"base":…,"valor":…}}
    total_general = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))

    fecha_generacion = models.DateTimeField(auto_now_add=True)
    fecha_transmision = models.DateTimeField(null=True, blank=True)
    fecha_aceptacion = models.DateTimeField(null=True, blank=True)
    proximo_reintento = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Documento fiscal"
        verbose_name_plural = "Documentos fiscales"
        ordering = ["-fecha_generacion"]

    def __str__(self):
        return self.numero_completo or f"Documento #{self.pk} ({self.get_estado_display()})"

    @property
    def es_nota(self) -> bool:
        return self.tipo in (ResolucionNumeracion.NOTA_CREDITO, ResolucionNumeracion.NOTA_DEBITO)

    @property
    def es_simulado(self) -> bool:
        """Emitido por el proveedor simulado: nunca fue a la DIAN y no tiene
        validez. Se marca en todas partes para que nadie lo confunda."""
        return bool((self.respuesta_pt or {}).get("simulado"))

    @property
    def reintentable(self) -> bool:
        return self.estado in (self.CONTINGENCIA, self.PENDIENTE)

    def registrar(self, accion, resultado="ok", detalle="", payload=None):
        """Deja constancia en el log de auditoría."""
        return LogAuditoria.objects.using(self._state.db).create(
            documento=self, accion=accion, resultado=resultado, detalle=detalle,
            payload=payload or {},
        )


class LogAuditoria(models.Model):
    """Todo intento de facturación queda escrito, salga bien o mal."""

    documento = models.ForeignKey(
        DocumentoFiscal, on_delete=models.CASCADE, related_name="auditoria", null=True, blank=True
    )
    accion = models.CharField(max_length=60)
    resultado = models.CharField(max_length=20, default="ok")
    detalle = models.TextField(blank=True)
    payload = models.JSONField(default=dict, blank=True)
    momento = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Registro de auditoría"
        verbose_name_plural = "Registros de auditoría"
        ordering = ["-momento"]

    def __str__(self):
        return f"{self.momento:%d/%m/%Y %H:%M} · {self.accion} · {self.resultado}"
