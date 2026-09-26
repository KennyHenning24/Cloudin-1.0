import uuid

from django.db import models


def ruta_foto(instancia, archivo):
    """media/<restaurante>/menu/<aleatorio>.<ext>: nada de fotos mezcladas entre locales."""
    from apps.tenants.context import get_current_tenant

    tenant = get_current_tenant()
    carpeta = tenant.slug if tenant else "sin-restaurante"
    extension = (archivo.rsplit(".", 1)[-1] if "." in archivo else "jpg").lower()[:5]
    return f"{carpeta}/menu/{uuid.uuid4().hex[:16]}.{extension}"


class Category(models.Model):
    """Categoría del menú: Entradas, Platos fuertes, Bebidas..."""

    name = models.CharField("Nombre", max_length=80)
    position = models.PositiveIntegerField("Orden", default=0)
    is_active = models.BooleanField("Activa", default=True)
    clave_externa = models.CharField(max_length=120, blank=True, db_index=True)
    # En qué carta del sitio aparece, para restaurantes con varias
    # (Almuerzo, Noche, Bebidas). Vacío: en todas o en la única que haya.
    secciones = models.JSONField("Cartas donde aparece", default=list, blank=True)

    class Meta:
        verbose_name = "Categoría"
        verbose_name_plural = "Categorías"
        ordering = ["position", "name"]

    def __str__(self):
        return self.name


class Product(models.Model):
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="products", verbose_name="Categoría"
    )
    name = models.CharField("Nombre", max_length=120)
    description = models.TextField("Descripción", blank=True)
    price = models.DecimalField("Precio", max_digits=12, decimal_places=2)
    image_url = models.URLField("Imagen (URL)", max_length=500, blank=True)
    # Foto subida desde el panel. Si hay las dos, manda la subida.
    imagen = models.ImageField("Foto", upload_to=ruta_foto, blank=True)
    position = models.PositiveIntegerField("Orden", default=0)
    is_available = models.BooleanField("Disponible", default=True)
    # Toppings, adiciones y variantes. Lista de grupos:
    #   [{"nombre": "Elige la carne", "tipo": "uno" | "varios", "obligatorio": true,
    #     "valores": [{"nombre": "Brisket", "precio": 0}, …]}]
    # `precio` es lo que la opción SUMA al precio del producto.
    opciones = models.JSONField("Toppings y opciones", default=list, blank=True)
    permite_observacion = models.BooleanField(
        "Permitir observación", default=True,
        help_text="Si está activo, el cliente o el mesero pueden escribir «sin cebolla», etc.",
    )
    # El identificador que el producto tiene en el sitio web: sirve para volver a
    # importar sin duplicar.
    clave_externa = models.CharField(max_length=120, blank=True, db_index=True)
    # Eliminado de la carta por el restaurante. No se borra de verdad: las
    # comandas y facturas viejas lo siguen nombrando, y así la importación desde
    # el sitio sabe que no debe volver a crearlo.
    eliminado = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Producto"
        verbose_name_plural = "Productos"
        ordering = ["category__position", "position", "name"]

    def __str__(self):
        return self.name

    @property
    def foto(self) -> str:
        """La imagen que se muestra: la subida al panel o, si no, la del sitio."""
        if self.imagen:
            return self.imagen.url
        return self.image_url
