"""Cloudin Employees — quién trabaja, cuánto tiempo y cuánto cuesta.

Un módulo aparte dentro del mismo sistema: el restaurante lo enciende si lo
necesita. Registra a la gente, marca entradas y salidas, suma las horas y
calcula el costo. No da acceso al panel: ser empleado aquí y tener usuario en
Cloudin son dos cosas distintas (el usuario se crea desde el panel maestro).

La nómina electrónica todavía no se emite; el modelo ya guarda lo que esa
emisión va a necesitar: horas del período y valor devengado.
"""

from datetime import timedelta
from decimal import Decimal

from django.db import models
from django.utils import timezone


class Empleado(models.Model):
    CC = "CC"
    CE = "CE"
    PAS = "PAS"
    DOCUMENTOS = [(CC, "Cédula de ciudadanía"), (CE, "Cédula de extranjería"), (PAS, "Pasaporte")]

    POR_HORA = "hora"
    MENSUAL = "mes"
    PAGOS = [(POR_HORA, "Por hora"), (MENSUAL, "Salario mensual")]

    nombre = models.CharField("Nombre completo", max_length=120)
    documento = models.CharField("Documento", max_length=30, blank=True)
    tipo_documento = models.CharField(max_length=4, choices=DOCUMENTOS, default=CC)
    cargo = models.CharField("Cargo", max_length=80, blank=True)
    telefono = models.CharField("Teléfono", max_length=40, blank=True)
    correo = models.EmailField("Correo", blank=True)

    forma_pago = models.CharField("Forma de pago", max_length=10, choices=PAGOS, default=POR_HORA)
    valor_hora = models.DecimalField(
        "Valor de la hora", max_digits=12, decimal_places=2, default=Decimal("0"),
        help_text="Lo que cuesta una hora de esta persona. Sirve para estimar el costo del turno.",
    )
    salario_mensual = models.DecimalField(
        "Salario mensual", max_digits=12, decimal_places=2, default=Decimal("0")
    )

    # Código corto para marcar en el reloj sin buscar en la lista.
    codigo = models.CharField("Código para marcar", max_length=8, blank=True)
    activo = models.BooleanField("Activo", default=True)
    ingreso = models.DateField("Fecha de ingreso", null=True, blank=True)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Empleado"
        verbose_name_plural = "Empleados"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre

    @property
    def turno_abierto(self):
        return self.turnos.filter(salida__isnull=True).order_by("-entrada").first()

    @property
    def esta_trabajando(self) -> bool:
        return self.turno_abierto is not None

    def costo_hora(self) -> Decimal:
        """Cuánto vale una hora suya. Del salario mensual se estima con 240 h,
        que es la jornada mensual completa en Colombia."""
        if self.forma_pago == self.POR_HORA:
            return self.valor_hora
        return (self.salario_mensual / Decimal("240")) if self.salario_mensual else Decimal("0")

    def horas_entre(self, desde, hasta) -> Decimal:
        total = Decimal("0")
        for t in self.turnos.filter(entrada__gte=desde, entrada__lte=hasta):
            total += t.horas()
        return total

    def marcar(self, nota: str = ""):
        """Entra si estaba afuera; sale si estaba adentro."""
        abierto = self.turno_abierto
        if abierto:
            abierto.cerrar(nota)
            return abierto, "salida"
        return Turno.objects.create(empleado=self, nota=nota), "entrada"


class Turno(models.Model):
    """Una jornada: desde que marcó entrada hasta que marcó salida."""

    # Un turno que nadie cerró no puede crecer para siempre.
    MAX_HORAS = 16

    empleado = models.ForeignKey(Empleado, on_delete=models.CASCADE, related_name="turnos")
    entrada = models.DateTimeField(default=timezone.now)
    salida = models.DateTimeField(null=True, blank=True)
    nota = models.CharField(max_length=200, blank=True)
    cerrado_automatico = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Turno"
        verbose_name_plural = "Turnos"
        ordering = ["-entrada"]

    def __str__(self):
        return f"{self.empleado.nombre} · {self.entrada:%d/%m %H:%M}"

    @property
    def abierto(self) -> bool:
        return self.salida is None

    def fin_efectivo(self):
        """Para un turno abierto, 'hasta ahora'; y nunca más del tope."""
        if self.salida:
            return self.salida
        tope = self.entrada + timedelta(hours=self.MAX_HORAS)
        return min(timezone.now(), tope)

    def horas(self) -> Decimal:
        segundos = (self.fin_efectivo() - self.entrada).total_seconds()
        return (Decimal(max(0, segundos)) / Decimal("3600")).quantize(Decimal("0.01"))

    def costo(self) -> Decimal:
        return (self.horas() * self.empleado.costo_hora()).quantize(Decimal("0.01"))

    def cerrar(self, nota: str = ""):
        self.salida = timezone.now()
        if nota:
            self.nota = nota
        self.save(update_fields=["salida", "nota"])
        return self
