"""Datos públicos del negocio (viven en la base de cada restaurante).

Es todo lo de `business` del contrato `cloudin.menu/v1`, menos lo privado
(razón social y NIT viven en `Tenant`, en la base de control, y nunca salen en
la API pública; los datos del dueño son su usuario).

Estos colores y el logo son los del MENÚ PÚBLICO del restaurante. El panel usa
siempre la identidad de Cloudin.
"""

import uuid

from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q

from apps.common.history import historial
from apps.common.models import TimeStampedModel

color_hex = RegexValidator(r"^#[0-9A-Fa-f]{6}$", "Usa un color en formato #RRGGBB.")
telefono_co = RegexValidator(r"^\+57\d{10}$", "Escribe el número con +57 y 10 dígitos (ej. +573001234567).")

DIAS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
NOMBRES_DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]

# Cómo más se puede pedir, además de en la mesa (la mesa la manejan los pedidos por QR y los
# meseros). Los dos vienen encendidos; el restaurante los apaga en Personalizar y su menú digital
# esconde esa opción (business.takeaway / business.delivery en el runtime).
SERVICIOS = {"takeaway": "Recoger", "delivery": "Domicilio"}
MEDIOS_DE_PAGO = {
    "efectivo": "Efectivo", "nequi": "Nequi", "daviplata": "Daviplata", "tarjeta": "Tarjeta",
    "transferencia": "Transferencia",
}


def ruta_marca(instancia, archivo):
    from apps.tenants.context import get_current_tenant

    tenant = get_current_tenant()
    carpeta = tenant.slug if tenant else "sin-restaurante"
    extension = (archivo.rsplit(".", 1)[-1] if "." in archivo else "png").lower()[:5]
    return f"{carpeta}/marca/{uuid.uuid4().hex[:16]}.{extension}"


class RestaurantSettings(TimeStampedModel):
    """Una sola fila por restaurante (`load()` la crea si no existe)."""

    # Marca del menú público
    logo = models.ImageField("Logo", upload_to=ruta_marca, blank=True)
    cover = models.ImageField("Portada", upload_to=ruta_marca, blank=True)
    color_primary = models.CharField("Color principal", max_length=7, blank=True, validators=[color_hex])
    color_secondary = models.CharField("Color secundario", max_length=7, blank=True, validators=[color_hex])
    color_background = models.CharField("Color de fondo", max_length=7, blank=True, validators=[color_hex])
    color_text = models.CharField("Color del texto", max_length=7, blank=True, validators=[color_hex])

    # Textos
    tagline = models.CharField("Frase corta", max_length=120, blank=True)
    description = models.TextField("Descripción", blank=True)
    welcome_message = models.CharField("Mensaje de bienvenida", max_length=200, blank=True)

    # Contacto y ubicación
    whatsapp = models.CharField("WhatsApp", max_length=13, blank=True, validators=[telefono_co])
    phone = models.CharField("Teléfono", max_length=13, blank=True, validators=[telefono_co])
    email = models.EmailField("Correo", blank=True)
    address = models.CharField("Dirección", max_length=200, blank=True)
    city = models.CharField("Ciudad", max_length=80, blank=True)
    maps_url = models.URLField("Enlace de Google Maps", max_length=500, blank=True)

    # Redes
    instagram = models.URLField("Instagram", max_length=300, blank=True)
    facebook = models.URLField("Facebook", max_length=300, blank=True)
    tiktok = models.URLField("TikTok", max_length=300, blank=True)

    # Servicios {"takeaway": true, "delivery": false} (si falta, encendido: servicios_de) y
    # medios de pago ["efectivo", …]
    services = models.JSONField("Servicios", default=dict, blank=True)
    payment_methods = models.JSONField("Medios de pago", default=list, blank=True)

    # Sube con cada cambio del menú o de estos datos: es el ETag de la API pública.
    menu_version = models.PositiveBigIntegerField(default=1, editable=False)

    # Asistente de la primera vez
    onboarding_step = models.PositiveSmallIntegerField("Paso del asistente", default=0)
    onboarding_done_at = models.DateTimeField("Asistente terminado", null=True, blank=True)

    import_snapshot = models.JSONField(default=dict, blank=True, editable=False)

    history = historial(excluded_fields=["menu_version", "onboarding_step", "onboarding_done_at"])

    class Meta:
        verbose_name = "Datos del negocio"
        verbose_name_plural = "Datos del negocio"

    def __str__(self):
        return "Datos del negocio"

    @classmethod
    def load(cls):
        """La fila del restaurante activo. La primera vez se crea con lo que ya se
        sabe de él en la base de control (dirección, teléfono y ciudad)."""
        ajustes = cls.objects.filter(pk=1).first()
        if ajustes is not None:
            return ajustes
        from apps.tenants.context import get_current_tenant

        tenant = get_current_tenant()
        datos = {}
        if tenant is not None:
            datos = {"address": tenant.address[:200], "city": tenant.city[:80]}
            telefono = normalizar_telefono(tenant.phone)
            if telefono:
                datos["phone"] = telefono
        ajustes, _ = cls.objects.get_or_create(pk=1, defaults=datos)
        return ajustes


class OpeningHours(TimeStampedModel):
    """Un tramo del horario. Varias filas el mismo día = horario partido.

    Un día sin filas está cerrado. Si `closes` es menor que `opens`, el tramo
    pasa la medianoche (ej. 18:00 – 02:00).
    """

    day = models.PositiveSmallIntegerField("Día", choices=list(enumerate(NOMBRES_DIAS)))
    opens = models.TimeField("Abre")
    closes = models.TimeField("Cierra")

    history = historial()

    class Meta:
        verbose_name = "Horario"
        verbose_name_plural = "Horarios"
        ordering = ["day", "opens"]
        constraints = [
            models.CheckConstraint(condition=Q(day__lte=6), name="horario_dia_valido"),
            models.CheckConstraint(condition=~Q(opens=models.F("closes")), name="horario_abre_distinto_de_cierra"),
        ]

    def __str__(self):
        return f"{NOMBRES_DIAS[self.day]} {self.opens:%H:%M}–{self.closes:%H:%M}"


def servicios_de(ajustes) -> dict:
    """{"takeaway": bool, "delivery": bool}: encendidos salvo que el restaurante los apague."""
    guardados = ajustes.services or {}
    return {k: bool(guardados.get(k, True)) for k in SERVICIOS}


def normalizar_telefono(texto: str) -> str:
    """«300 123 4567», «(+57) 300-123-4567» -> «+573001234567». Vacío si no se entiende."""
    digitos = "".join(ch for ch in str(texto or "") if ch.isdigit())
    if len(digitos) == 12 and digitos.startswith("57"):
        digitos = digitos[2:]
    if len(digitos) == 10 and digitos[0] in "36":
        return "+57" + digitos
    return ""
