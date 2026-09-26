"""El turno de caja: la jornada de trabajo del local, de apertura a cierre.

No confundir con `staffing.Turno`, que es la jornada de una persona. Este es el
turno del negocio: se abre al empezar el día (o el relevo), todo lo que pasa
—mesas, pedidos, facturas, consumo de inventario— queda colgado de él, y al
cerrarlo se congela el resultado en un informe que ya no cambia.

Cerrar el turno es lo que deja el panel en blanco: las mesas quedan libres, la
bandeja de mensajes vacía y la cocina sin comandas, porque todas esas pantallas
muestran solo el turno abierto. Lo del turno anterior no se borra: se queda
guardado en su informe.
"""

from decimal import Decimal

from django.db import models
from django.utils import timezone


class TurnoCaja(models.Model):
    ABIERTO = "abierto"
    CERRADO = "cerrado"
    ESTADOS = [(ABIERTO, "Abierto"), (CERRADO, "Cerrado")]

    numero = models.PositiveIntegerField("Turno n.º", default=1, db_index=True)
    estado = models.CharField(max_length=10, choices=ESTADOS, default=ABIERTO, db_index=True)

    abierto_en = models.DateTimeField("Apertura", default=timezone.now)
    abierto_por = models.CharField("Abierto por", max_length=120, blank=True)
    base_inicial = models.DecimalField(
        "Base inicial de caja", max_digits=12, decimal_places=2, default=Decimal("0"),
        help_text="El efectivo con el que arranca la caja.",
    )

    cerrado_en = models.DateTimeField("Cierre", null=True, blank=True)
    cerrado_por = models.CharField("Cerrado por", max_length=120, blank=True)
    efectivo_contado = models.DecimalField(
        "Efectivo contado al cerrar", max_digits=12, decimal_places=2, null=True, blank=True
    )
    diferencia = models.DecimalField(
        "Diferencia de caja", max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Contado menos lo que debería haber. Negativo es faltante.",
    )
    notas = models.TextField("Notas del cierre", blank=True)

    # --- Congelado al cerrar: el informe no puede cambiar después. ---
    total_ventas = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    total_pedidos = models.PositiveIntegerField(default=0)
    total_mesas = models.PositiveIntegerField(default=0)
    total_comensales = models.PositiveIntegerField(default=0)
    total_facturado = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    total_base = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    total_impuestos = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    docs_aceptados = models.PositiveIntegerField(default=0)
    docs_pendientes = models.PositiveIntegerField(default=0)
    docs_rechazados = models.PositiveIntegerField(default=0)
    costo_inventario = models.DecimalField(
        "Costo del inventario consumido", max_digits=14, decimal_places=2, default=Decimal("0")
    )
    # Todo el detalle del turno: productos, mesas, documentos, gente, insumos.
    resumen = models.JSONField(default=dict, blank=True)

    # Cuándo se le entregó al equipo la propina de este turno.
    propinas_pagadas_en = models.DateTimeField(null=True, blank=True)
    propinas_pagadas_por = models.CharField(max_length=120, blank=True)

    class Meta:
        verbose_name = "Turno de caja"
        verbose_name_plural = "Turnos de caja"
        ordering = ["-abierto_en"]

    def __str__(self):
        return f"Turno {self.numero} · {timezone.localtime(self.abierto_en):%d/%m/%Y %H:%M}"

    # ------------------------------------------------------------- consultas

    @classmethod
    def abierto_actual(cls, db=None):
        qs = cls.objects.using(db) if db else cls.objects
        return qs.filter(estado=cls.ABIERTO).order_by("-abierto_en").first()

    @classmethod
    def siguiente_numero(cls, db=None) -> int:
        qs = cls.objects.using(db) if db else cls.objects
        ultimo = qs.order_by("-numero").values_list("numero", flat=True).first()
        return (ultimo or 0) + 1

    @property
    def abierto(self) -> bool:
        return self.estado == self.ABIERTO

    @property
    def fin_efectivo(self):
        return self.cerrado_en or timezone.now()

    def horas(self) -> Decimal:
        segundos = (self.fin_efectivo - self.abierto_en).total_seconds()
        return (Decimal(max(0, segundos)) / Decimal("3600")).quantize(Decimal("0.1"))

    @property
    def ventas_efectivo(self) -> Decimal:
        """Lo vendido que sí entró a la caja (sin tarjetas ni transferencias)."""
        valor = (self.resumen or {}).get("ventas_efectivo")
        if valor is None:
            return self.total_ventas or Decimal("0")
        return Decimal(str(valor))

    @property
    def propinas_efectivo(self) -> Decimal:
        """Propina que se pagó en billetes: está en la caja, pero es del equipo."""
        valor = ((self.resumen or {}).get("propinas") or {}).get("efectivo")
        return Decimal(str(valor)) if valor else Decimal("0")

    @property
    def efectivo_esperado(self) -> Decimal:
        """Lo que debería haber en la caja: la base, lo cobrado en efectivo y la
        propina que dejaron en efectivo (que luego se le entrega al equipo)."""
        return (self.base_inicial or Decimal("0")) + self.ventas_efectivo + self.propinas_efectivo

    @property
    def ticket_promedio(self) -> Decimal:
        if not self.total_mesas:
            return Decimal("0")
        return (self.total_ventas / self.total_mesas).quantize(Decimal("0.01"))
