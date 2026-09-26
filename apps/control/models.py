"""Cloudin Control: detecta, explica y ayuda a corregir lo que afecta la rentabilidad.

    REGISTRAR -> CONECTAR -> MEDIR -> DETECTAR -> EXPLICAR -> RECOMENDAR -> MEJORAR

Los módulos de siempre registran (pedidos, caja, inventario, compras, gente).
Control los cruza, mide contra lo esperado y cuando algo se sale de lo normal
deja una alerta que explica qué pasó, cuánto podría costar y qué revisar.

Regla de lenguaje, sin excepciones: una alerta nunca acusa. Se habla de
«diferencia», «posible fuga», «situación a revisar» o «variación detectada»,
jamás de robo. Hay muchas explicaciones honestas para una diferencia.

`AlertaControl` es la entidad `control_alert` de la especificación. El
«restaurant_id» no hace falta como columna: cada restaurante tiene su propia
base de datos, así que todas las alertas de una base son de ese restaurante.
"""

from decimal import Decimal

from django.db import models
from django.utils import timezone


class AlertaControl(models.Model):
    # severity
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    SEVERIDADES = [(INFO, "Para tener en cuenta"), (WARNING, "Revisar pronto"), (CRITICAL, "Revisar hoy")]

    # status
    NEW = "new"
    REVIEWED = "reviewed"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"
    ESTADOS = [(NEW, "Nueva"), (REVIEWED, "En revisión"), (RESOLVED, "Resuelta"), (DISMISSED, "Descartada")]
    ABIERTAS = [NEW, REVIEWED]

    # type: de qué parte del negocio viene
    TIPOS = [
        ("inventario", "Inventario"),
        ("ventas", "Ventas"),
        ("caja", "Caja"),
        ("anulaciones", "Anulaciones"),
        ("descuentos", "Descuentos"),
        ("cortesias", "Cortesías"),
        ("devoluciones", "Devoluciones"),
        ("mermas", "Mermas"),
        ("recetas", "Recetas"),
        ("compras", "Compras"),
        ("costos", "Costos"),
        ("empleados", "Empleados"),
        ("turnos", "Turnos"),
        ("pedidos", "Pedidos"),
        ("cocina", "Tiempos de cocina"),
        ("reservas", "Reservas"),
    ]

    # Las categorías del Detector de fugas. Vacío: la alerta no es de plata.
    FUGAS = [
        ("caja", "Diferencias de caja"),
        ("inventario", "Inventario real vs. teórico"),
        ("mermas", "Mermas"),
        ("anulaciones", "Anulaciones"),
        ("descuentos", "Descuentos excepcionales"),
        ("cortesias", "Cortesías"),
        ("devoluciones", "Devoluciones"),
        ("recetas", "Diferencias de receta"),
        ("compras", "Compras más caras"),
        ("otras", "Otras diferencias"),
    ]

    tipo = models.CharField("Tipo", max_length=16, choices=TIPOS, db_index=True)
    severidad = models.CharField("Severidad", max_length=10, choices=SEVERIDADES, default=INFO, db_index=True)
    titulo = models.CharField("Título", max_length=200)
    descripcion = models.TextField("Qué pasó")
    recomendacion = models.TextField("Qué revisar", blank=True)
    impacto_estimado = models.DecimalField(
        "Impacto estimado", max_digits=14, decimal_places=2, default=Decimal("0"),
        help_text="Cuánta plata podría estar en juego. Es una estimación, no una pérdida confirmada.",
    )
    categoria_fuga = models.CharField(max_length=14, choices=FUGAS, blank=True, db_index=True)

    # A qué se refiere: un turno, un insumo, un producto, una compra...
    entidad_tipo = models.CharField(max_length=30, blank=True)
    entidad_id = models.CharField(max_length=40, blank=True)
    enlace = models.CharField("Dónde verlo", max_length=200, blank=True)

    # El período que miró el detector.
    periodo_desde = models.DateField(null=True, blank=True, db_index=True)
    periodo_hasta = models.DateField(null=True, blank=True)

    estado = models.CharField("Estado", max_length=10, choices=ESTADOS, default=NEW, db_index=True)
    detectada_en = models.DateTimeField(default=timezone.now, db_index=True)
    resuelta_en = models.DateTimeField(null=True, blank=True)
    revisada_por = models.CharField(max_length=120, blank=True)
    nota = models.TextField("Nota de quien la revisó", blank=True)

    # Los números detrás de la alerta, para mostrarlos y para no repetirla.
    metadata = models.JSONField(default=dict, blank=True)
    # La misma situación siempre da la misma huella: al volver a analizar se
    # actualiza la alerta en vez de crear otra igual.
    huella = models.CharField(max_length=160, unique=True)

    creada_en = models.DateTimeField(auto_now_add=True)
    actualizada_en = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "control_alert"
        verbose_name = "Alerta de control"
        verbose_name_plural = "Alertas de control"
        ordering = ["-detectada_en"]

    def __str__(self):
        return self.titulo

    @property
    def abierta(self) -> bool:
        return self.estado in self.ABIERTAS

    @property
    def peso(self) -> int:
        return {self.CRITICAL: 3, self.WARNING: 2, self.INFO: 1}.get(self.severidad, 0)


class AjustesControl(models.Model):
    """Qué tan sensible es cada detector. El restaurante lo ajusta a su realidad."""

    tolerancia_caja = models.DecimalField(
        "Diferencia de caja que no se reporta", max_digits=12, decimal_places=2, default=Decimal("2000"),
        help_text="Diferencias menores a esto se consideran vueltas y redondeos.",
    )
    inventario_pct = models.DecimalField(
        "Consumo real sobre el teórico que se reporta (%)", max_digits=5, decimal_places=2,
        default=Decimal("8"),
    )
    anulaciones_por_turno = models.PositiveIntegerField("Anulaciones por turno que se reportan", default=5)
    descuento_pct = models.DecimalField(
        "Descuento excepcional desde (%)", max_digits=5, decimal_places=2, default=Decimal("15"),
    )
    cortesias_pct = models.DecimalField(
        "Cortesías sobre ventas que se reportan (%)", max_digits=5, decimal_places=2, default=Decimal("3"),
    )
    compra_alza_pct = models.DecimalField(
        "Alza de precio de compra que se reporta (%)", max_digits=5, decimal_places=2, default=Decimal("10"),
    )
    food_cost_objetivo = models.DecimalField(
        "Food cost objetivo (%)", max_digits=5, decimal_places=2, default=Decimal("35"),
    )
    margen_caida_puntos = models.DecimalField(
        "Caída de margen que se reporta (puntos)", max_digits=5, decimal_places=2, default=Decimal("3"),
    )
    cocina_minutos = models.PositiveIntegerField("Minutos de cocina que se consideran demora", default=25)
    turno_horas = models.PositiveIntegerField("Horas de turno abierto que se reportan", default=16)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Ajustes de Cloudin Control"
        verbose_name_plural = "Ajustes de Cloudin Control"

    def __str__(self):
        return "Ajustes de Cloudin Control"

    @classmethod
    def actuales(cls, db=None):
        qs = cls.objects.using(db) if db else cls.objects
        ajustes = qs.first()
        if ajustes is None:
            ajustes = qs.create()
        return ajustes


class Analisis(models.Model):
    """Cada vez que Control revisa el negocio: cuándo, qué tan largo y qué encontró."""

    momento = models.DateTimeField(default=timezone.now, db_index=True)
    desde = models.DateField()
    hasta = models.DateField()
    duracion_ms = models.PositiveIntegerField(default=0)
    alertas_nuevas = models.PositiveIntegerField(default=0)
    alertas_actualizadas = models.PositiveIntegerField(default=0)
    por_detector = models.JSONField(default=dict, blank=True)
    usuario = models.CharField(max_length=120, blank=True)

    class Meta:
        verbose_name = "Análisis de control"
        verbose_name_plural = "Análisis de control"
        ordering = ["-momento"]

    def __str__(self):
        return f"Análisis {timezone.localtime(self.momento):%d/%m %H:%M}"
