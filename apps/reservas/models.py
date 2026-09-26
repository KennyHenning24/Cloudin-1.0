"""Cloudin Reservas: quién viene, cuándo, cuántos y a qué mesa.

El recorrido completo de una reserva:

    RESERVA -> LLEGADA -> ASIGNACIÓN DE MESA -> PEDIDO -> FACTURACIÓN -> HISTORIAL

Una reserva nace en el sitio web del restaurante, en el menú de la mesa o en el
panel (cuando alguien llama por teléfono). Si hay cupo, queda confirmada sola y
con mesa asignada. Cuando el cliente llega se le marca la llegada, se sienta en
su mesa (eso abre la cuenta), pide, paga y la visita queda en su historial.

El restaurante decide todo desde el panel: los horarios de cada servicio
(almuerzo, noche, pasadía), qué mesas se ofrecen, con cuánta anticipación, y
los días que no recibe reservas.
"""

import secrets
from datetime import datetime, timedelta
from decimal import Decimal

from django.db import models
from django.utils import timezone

# Sin letras ni números que se confundan al dictarlos por teléfono (0/O, 1/I).
ALFABETO_CODIGO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

DIAS_SEMANA = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]


def nuevo_codigo() -> str:
    return "".join(secrets.choice(ALFABETO_CODIGO) for _ in range(6))


def solo_digitos(telefono: str) -> str:
    return "".join(c for c in str(telefono or "") if c.isdigit())


class Cliente(models.Model):
    """La persona que reserva. Se reconoce por su teléfono.

    No es el cliente fiscal de la factura (ese pide NIT o cédula): es el
    comensal, con su historial de visitas.
    """

    nombre = models.CharField("Nombre", max_length=120)
    telefono = models.CharField("Teléfono", max_length=20, unique=True)
    correo = models.EmailField("Correo", blank=True)
    notas = models.TextField(
        "Notas del cliente", blank=True,
        help_text="Lo que conviene recordar: alergias, mesa preferida, fechas especiales.",
    )
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"
        ordering = ["nombre"]

    def __str__(self):
        return f"{self.nombre} · {self.telefono}"

    @property
    def whatsapp(self) -> str:
        """El número listo para wa.me: con el 57 de Colombia si no lo trae."""
        numero = solo_digitos(self.telefono)
        return numero if len(numero) > 10 else "57" + numero


class AjustesReservas(models.Model):
    """Cómo recibe reservas el restaurante. Una sola fila por restaurante."""

    activo = models.BooleanField(
        "Recibir reservas por internet", default=True,
        help_text="Si lo apagas, el sitio web deja de ofrecer reservas.",
    )
    confirmacion_automatica = models.BooleanField(
        "Confirmar solas si hay cupo", default=True,
        help_text="Si hay mesa libre, la reserva queda confirmada al instante. "
                  "Si lo apagas, cada reserva espera a que alguien la confirme.",
    )
    anticipacion_horas = models.PositiveIntegerField(
        "Horas mínimas de anticipación", default=2,
        help_text="No se puede reservar para dentro de menos de estas horas.",
    )
    dias_maximo = models.PositiveIntegerField(
        "Hasta cuántos días adelante", default=45,
    )
    max_personas = models.PositiveIntegerField(
        "Máximo de personas por reserva en línea", default=12,
        help_text="Los grupos más grandes se atienden por WhatsApp.",
    )
    tolerancia_minutos = models.PositiveIntegerField(
        "Minutos de espera", default=20,
        help_text="Pasado este tiempo sin llegar, la reserva se marca para revisar como no llegó.",
    )
    recordar_horas_antes = models.PositiveIntegerField(
        "Recordar con cuántas horas de anticipación", default=24,
    )
    whatsapp = models.CharField(
        "WhatsApp del restaurante", max_length=20, blank=True,
        help_text="A este número llega el aviso de cada reserva nueva.",
    )
    mensaje_recordatorio = models.TextField(
        "Mensaje del recordatorio", blank=True,
        default=(
            "Hola {nombre}, te esperamos {cuando} en {restaurante} para {personas}. "
            "Tu código de reserva es {codigo}. Si no puedes venir, respóndenos este mensaje. ¡Gracias!"
        ),
        help_text="Puedes usar {nombre}, {cuando}, {restaurante}, {personas} y {codigo}.",
    )
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Ajustes de reservas"
        verbose_name_plural = "Ajustes de reservas"

    def __str__(self):
        return "Ajustes de reservas"

    @classmethod
    def actuales(cls, db=None):
        qs = cls.objects.using(db) if db else cls.objects
        ajustes = qs.first()
        if ajustes is None:
            ajustes = qs.create()
        return ajustes


class ServicioReserva(models.Model):
    """Un horario en el que se reciben reservas: Almuerzo, Noche, Pasadía...

    Dos tipos:
      - «mesa»: por hora, cada reserva ocupa una mesa durante un rato.
      - «dia»: por día, con un cupo de personas (una pasadía, un brunch).
    """

    MESA = "mesa"
    DIA = "dia"
    TIPOS = [(MESA, "Por hora, con mesa"), (DIA, "Por día, con cupo de personas")]

    nombre = models.CharField("Nombre", max_length=60)
    tipo = models.CharField("Cómo se reserva", max_length=6, choices=TIPOS, default=MESA)
    dias = models.JSONField(
        "Días", default=list,
        help_text="0 es lunes y 6 es domingo.",
    )
    abre = models.TimeField("Abre")
    cierra = models.TimeField(
        "Cierra", help_text="Medianoche o después: al día siguiente.",
    )
    intervalo_minutos = models.PositiveIntegerField("Cada cuántos minutos se ofrece una hora", default=30)
    duracion_minutos = models.PositiveIntegerField(
        "Cuánto dura una mesa ocupada", default=120,
        help_text="Una mesa reservada a las 7:00 queda ocupada este tiempo.",
    )
    ultima_llegada_minutos = models.PositiveIntegerField(
        "Última reserva, minutos antes de cerrar", default=60,
    )
    cupo_personas = models.PositiveIntegerField(
        "Cupo de personas", default=0,
        help_text="Por día en los servicios por día. En los de mesa, 0 es sin límite aparte de las mesas.",
    )
    descripcion = models.CharField("Texto para el cliente", max_length=160, blank=True)
    activo = models.BooleanField("Activo", default=True)
    orden = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Servicio de reservas"
        verbose_name_plural = "Servicios de reservas"
        ordering = ["orden", "abre"]

    def __str__(self):
        return self.nombre

    @property
    def por_dia(self) -> bool:
        return self.tipo == self.DIA

    def dias_texto(self) -> str:
        dias = sorted(int(d) for d in (self.dias or []))
        if len(dias) == 7:
            return "Todos los días"
        if not dias:
            return "Ningún día"
        # Días seguidos se leen como rango: «Miércoles a domingo».
        if dias == list(range(dias[0], dias[-1] + 1)) and len(dias) > 2:
            return f"{DIAS_SEMANA[dias[0]]} a {DIAS_SEMANA[dias[-1]].lower()}"
        return ", ".join(DIAS_SEMANA[d] for d in dias)

    def abre_el(self, fecha) -> bool:
        return self.activo and fecha.weekday() in [int(d) for d in (self.dias or [])]

    def minutos_de_servicio(self) -> int:
        inicio = self.abre.hour * 60 + self.abre.minute
        fin = self.cierra.hour * 60 + self.cierra.minute
        if fin <= inicio:
            fin += 24 * 60  # cierra pasada la medianoche
        return fin - inicio

    def horas_del_dia(self, fecha):
        """Las horas que se ofrecen ese día, como datetime con zona horaria."""
        if self.por_dia:
            return []
        inicio = timezone.make_aware(datetime.combine(fecha, self.abre))
        ultima = inicio + timedelta(minutes=max(0, self.minutos_de_servicio() - self.ultima_llegada_minutos))
        paso = timedelta(minutes=max(10, self.intervalo_minutos))
        horas, hora = [], inicio
        while hora <= ultima:
            horas.append(hora)
            hora += paso
        return horas


class BloqueoFecha(models.Model):
    """Un día (o un servicio de un día) en que no se reciben reservas."""

    fecha = models.DateField("Fecha", db_index=True)
    servicio = models.ForeignKey(
        ServicioReserva, on_delete=models.CASCADE, null=True, blank=True,
        related_name="bloqueos", verbose_name="Solo este servicio",
        help_text="Déjalo vacío para cerrar todo el día.",
    )
    motivo = models.CharField("Motivo", max_length=120, blank=True)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Día sin reservas"
        verbose_name_plural = "Días sin reservas"
        ordering = ["fecha"]

    def __str__(self):
        return f"{self.fecha:%d/%m/%Y} · {self.servicio or 'todo el día'}"


class Reserva(models.Model):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    ARRIVED = "arrived"
    SEATED = "seated"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"
    ESTADOS = [
        (PENDING, "Pendiente"),
        (CONFIRMED, "Confirmada"),
        (ARRIVED, "Llegó"),
        (SEATED, "En la mesa"),
        (COMPLETED, "Completada"),
        (CANCELLED, "Cancelada"),
        (NO_SHOW, "No llegó"),
    ]
    # Las que todavía ocupan cupo.
    VIGENTES = [PENDING, CONFIRMED, ARRIVED, SEATED]
    # Las que ya terminaron, para bien o para mal.
    CERRADAS = [COMPLETED, CANCELLED, NO_SHOW]

    SITIO = "sitio"
    MESA_QR = "mesa_qr"
    PANEL = "panel"
    TELEFONO = "telefono"
    WHATSAPP = "whatsapp"
    ORIGENES = [
        (SITIO, "Página web"),
        (MESA_QR, "Menú de la mesa"),
        (PANEL, "Panel"),
        (TELEFONO, "Llamada"),
        (WHATSAPP, "WhatsApp"),
    ]

    codigo = models.CharField("Código", max_length=8, unique=True, default=nuevo_codigo)
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="reservas")
    # Copias: el historial se lee igual aunque el cliente cambie su nombre.
    nombre = models.CharField("Nombre", max_length=120)
    telefono = models.CharField("Teléfono", max_length=20)

    servicio = models.ForeignKey(
        ServicioReserva, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="reservas", verbose_name="Servicio",
    )
    servicio_nombre = models.CharField(max_length=60, blank=True)
    fecha = models.DateField("Fecha", db_index=True)
    hora = models.TimeField("Hora", null=True, blank=True)
    personas = models.PositiveIntegerField("Personas", default=2)
    zona = models.CharField("Zona preferida", max_length=40, blank=True)
    mesa = models.ForeignKey(
        "dining.Table", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="reservas", verbose_name="Mesa",
    )

    estado = models.CharField(max_length=10, choices=ESTADOS, default=PENDING, db_index=True)
    observaciones = models.TextField("Observaciones", blank=True)
    origen = models.CharField(max_length=10, choices=ORIGENES, default=SITIO)
    # Lo que el cliente eligió además (planes de pasadía, ocasión...).
    detalle = models.JSONField(default=dict, blank=True)
    total_estimado = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))

    confirmada_en = models.DateTimeField(null=True, blank=True)
    confirmada_por = models.CharField(max_length=120, blank=True)
    recordatorio_en = models.DateTimeField("Recordatorio enviado", null=True, blank=True)
    llegada_en = models.DateTimeField(null=True, blank=True)
    sentada_en = models.DateTimeField(null=True, blank=True)
    completada_en = models.DateTimeField(null=True, blank=True)
    cancelada_en = models.DateTimeField(null=True, blank=True)
    motivo_cancelacion = models.CharField(max_length=200, blank=True)
    # Cuándo la vio alguien en el panel: de aquí sale el contador de nuevas.
    vista_en = models.DateTimeField(null=True, blank=True)
    # La llave con la que el sitio pide crearla: un reintento no la duplica.
    clave_envio = models.CharField(max_length=64, blank=True, db_index=True)
    creada_por = models.CharField(max_length=120, blank=True)

    creada_en = models.DateTimeField(auto_now_add=True)
    actualizada_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Reserva"
        verbose_name_plural = "Reservas"
        ordering = ["fecha", "hora", "creada_en"]

    def __str__(self):
        return f"{self.codigo} · {self.nombre} · {self.fecha:%d/%m}"

    # ----------------------------------------------------------- tiempo

    @property
    def inicio(self):
        """El momento de la reserva, con zona horaria. Las de día, a la hora de abrir."""
        hora = self.hora or (self.servicio.abre if self.servicio_id else None)
        if hora is None:
            hora = datetime.min.time()
        return timezone.make_aware(datetime.combine(self.fecha, hora))

    @property
    def fin(self):
        duracion = self.servicio.duracion_minutos if self.servicio_id else 120
        return self.inicio + timedelta(minutes=duracion)

    @property
    def vigente(self) -> bool:
        return self.estado in self.VIGENTES

    @property
    def es_hoy(self) -> bool:
        return self.fecha == timezone.localdate()

    def minutos_para(self):
        """Cuánto falta (negativo si ya pasó la hora)."""
        return round((self.inicio - timezone.now()).total_seconds() / 60)

    @property
    def minutos_tarde(self) -> int:
        return max(0, -self.minutos_para())

    @property
    def atrasada(self) -> bool:
        return self.estado in (self.PENDING, self.CONFIRMED) and self.minutos_para() < 0

    def cuando_texto(self) -> str:
        """«el sábado 27 de septiembre a las 7:00 p. m.»"""
        from django.utils.formats import date_format

        dia = date_format(self.fecha, "l j \\d\\e F").lower()
        if self.hora:
            return f"el {dia} a las {self.hora_texto()}"
        return f"el {dia}"

    def hora_texto(self) -> str:
        if not self.hora:
            return "Todo el día"
        h = self.hora
        if h.hour == 12 and h.minute == 0:
            return "12:00 m."
        return f"{h.hour % 12 or 12}:{h.minute:02d} {'a. m.' if h.hour < 12 else 'p. m.'}"

    def personas_texto(self) -> str:
        return "1 persona" if self.personas == 1 else f"{self.personas} personas"
