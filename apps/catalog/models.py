"""La carta del restaurante (vive en la base de cada restaurante).

Menú → Categoría → Producto → tamaños (variantes), grupos de adiciones y
etiquetas. Sigue el contrato `cloudin.menu/v1`:

- `uuid`: identificador público; es el `id` que sale en la API.
- `key`: clave estable en kebab-case, única dentro de su padre. Se genera del
  nombre al crear y nunca cambia (la importación la usa para no duplicar).
- `import_snapshot`: los valores que trajo la última importación. Sirve para
  saber si el dueño cambió algo después (entonces se respeta su cambio).

Borrado lógico: un producto vendido no se borra (`eliminado`), y las categorías
y los menús se archivan con `deleted_at`.
"""

import uuid

from django.db import models
from django.db.models import F, Q

from apps.common.history import historial
from apps.common.keys import KEY_MAX, unique_key
from apps.common.models import PublicIdModel

TAX_INC8 = "INC8"
TAX_IVA19 = "IVA19"
TAX_EXENTO = "EXENTO"
TAX_CHOICES = [
    (TAX_INC8, "INC 8 % (impoconsumo)"),
    (TAX_IVA19, "IVA 19 %"),
    (TAX_EXENTO, "Exento"),
]


def _carpeta_restaurante() -> str:
    from apps.tenants.context import get_current_tenant

    tenant = get_current_tenant()
    return tenant.slug if tenant else "sin-restaurante"


def _extension(archivo: str) -> str:
    return (archivo.rsplit(".", 1)[-1] if "." in archivo else "jpg").lower()[:5]


def ruta_foto(instancia, archivo):
    """media/<restaurante>/menu/<aleatorio>.<ext>: nada de fotos mezcladas entre locales."""
    return f"{_carpeta_restaurante()}/menu/{uuid.uuid4().hex[:16]}.{_extension(archivo)}"


def ruta_imagen_categoria(instancia, archivo):
    return f"{_carpeta_restaurante()}/menu/categorias/{uuid.uuid4().hex[:16]}.{_extension(archivo)}"


def _asegurar_clave(obj, **dentro_de) -> None:
    """Si el objeto no tiene clave, la genera del nombre, única dentro de su padre."""
    if obj.key:
        return
    qs = type(obj)._default_manager.filter(**dentro_de)
    if obj.pk:
        qs = qs.exclude(pk=obj.pk)
    obj.key = unique_key(obj.name, lambda k: qs.filter(key=k).exists())


class Tag(PublicIdModel):
    """Etiqueta de un producto: vegetariano, picante, sin gluten, nuevo…"""

    key = models.SlugField("Clave", max_length=KEY_MAX, unique=True)
    name = models.CharField("Nombre", max_length=40)
    position = models.PositiveIntegerField("Orden", default=0)

    class Meta:
        verbose_name = "Etiqueta"
        verbose_name_plural = "Etiquetas"
        ordering = ["position", "name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        _asegurar_clave(self)
        super().save(*args, **kwargs)


class Menu(PublicIdModel):
    """Una carta del restaurante: «Carta», «Desayunos», «Almuerzo»…"""

    key = models.SlugField("Clave", max_length=KEY_MAX, unique=True)
    name = models.CharField("Nombre", max_length=80)
    description = models.TextField("Descripción", blank=True)
    position = models.PositiveIntegerField("Orden", default=0)
    is_active = models.BooleanField("Activo", default=True)
    # Cuándo se ofrece. Días vacíos = todos (0 = lunes … 6 = domingo); sin horas = todo el día.
    available_days = models.JSONField("Días en que se ofrece", default=list, blank=True)
    available_from = models.TimeField("Desde", null=True, blank=True)
    available_to = models.TimeField("Hasta", null=True, blank=True)
    deleted_at = models.DateTimeField("Archivado", null=True, blank=True, db_index=True)
    import_snapshot = models.JSONField(default=dict, blank=True, editable=False)

    history = historial()

    class Meta:
        verbose_name = "Menú"
        verbose_name_plural = "Menús"
        ordering = ["position", "name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        _asegurar_clave(self)
        super().save(*args, **kwargs)

    @classmethod
    def principal(cls) -> "Menu":
        """El primer menú activo; si el restaurante no tiene ninguno, crea «Carta»."""
        menu = cls.objects.filter(deleted_at__isnull=True).order_by("position", "id").first()
        return menu or cls.objects.create(name="Carta")


class Category(PublicIdModel):
    """Categoría del menú: Entradas, Platos fuertes, Bebidas..."""

    menu = models.ForeignKey(Menu, on_delete=models.PROTECT, related_name="categories", verbose_name="Menú")
    key = models.SlugField("Clave", max_length=KEY_MAX)
    name = models.CharField("Nombre", max_length=80)
    description = models.TextField("Descripción", blank=True)
    image = models.ImageField("Imagen", upload_to=ruta_imagen_categoria, blank=True)
    position = models.PositiveIntegerField("Orden", default=0)
    is_active = models.BooleanField("Activa", default=True)
    # En qué carta del sitio aparece, para los sitios con el formato viejo que
    # tienen varias (Almuerzo, Noche, Bebidas). Vacío: en todas.
    secciones = models.JSONField("Cartas donde aparece", default=list, blank=True)
    deleted_at = models.DateTimeField("Archivada", null=True, blank=True, db_index=True)
    import_snapshot = models.JSONField(default=dict, blank=True, editable=False)

    history = historial()

    class Meta:
        verbose_name = "Categoría"
        verbose_name_plural = "Categorías"
        ordering = ["position", "name"]
        constraints = [
            models.UniqueConstraint(fields=["menu", "key"], name="categoria_clave_unica_por_menu"),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # El código de antes (importar la carta vieja, el menú rápido) crea
        # categorías sin menú: van al menú principal.
        if self.menu_id is None:
            self.menu = Menu.principal()
        _asegurar_clave(self, menu_id=self.menu_id)
        super().save(*args, **kwargs)

    @property
    def anchor(self) -> str:
        return f"#cat-{self.key}"


class ModifierGroup(PublicIdModel):
    """Grupo de adiciones u opciones: «Elige tu salsa», «Adiciones»…

    Se puede usar en varios productos. `min_select` ≥ 1 lo vuelve obligatorio;
    `max_select` vacío = sin tope; `max_select` = 1 = se elige solo una.
    """

    key = models.SlugField("Clave", max_length=KEY_MAX, unique=True)
    name = models.CharField("Nombre", max_length=60)
    min_select = models.PositiveSmallIntegerField("Mínimo a elegir", default=0)
    max_select = models.PositiveSmallIntegerField("Máximo a elegir", null=True, blank=True)
    position = models.PositiveIntegerField("Orden", default=0)
    import_snapshot = models.JSONField(default=dict, blank=True, editable=False)

    history = historial()

    class Meta:
        verbose_name = "Grupo de adiciones"
        verbose_name_plural = "Grupos de adiciones"
        ordering = ["position", "name"]
        constraints = [
            models.CheckConstraint(condition=Q(max_select__isnull=True) | Q(max_select__gte=1),
                                   name="grupo_maximo_al_menos_uno"),
            models.CheckConstraint(condition=Q(max_select__isnull=True) | Q(max_select__gte=F("min_select")),
                                   name="grupo_maximo_no_menor_que_minimo"),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        _asegurar_clave(self)
        super().save(*args, **kwargs)

    @property
    def is_required(self) -> bool:
        return self.min_select >= 1


class ModifierOption(PublicIdModel):
    """Una opción del grupo. `price_delta` es lo que SUMA al precio (0 si no cambia)."""

    group = models.ForeignKey(ModifierGroup, on_delete=models.CASCADE, related_name="options",
                              verbose_name="Grupo")
    key = models.SlugField("Clave", max_length=KEY_MAX)
    name = models.CharField("Nombre", max_length=60)
    price_delta = models.DecimalField("Precio extra", max_digits=12, decimal_places=2, default=0)
    position = models.PositiveIntegerField("Orden", default=0)
    import_snapshot = models.JSONField(default=dict, blank=True, editable=False)

    history = historial()

    class Meta:
        verbose_name = "Opción"
        verbose_name_plural = "Opciones"
        ordering = ["position", "id"]
        constraints = [
            models.UniqueConstraint(fields=["group", "key"], name="opcion_clave_unica_por_grupo"),
            models.CheckConstraint(condition=Q(price_delta__gte=0), name="opcion_precio_no_negativo"),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        _asegurar_clave(self, group_id=self.group_id)
        super().save(*args, **kwargs)


class Product(PublicIdModel):
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products",
                                 verbose_name="Categoría")
    key = models.SlugField("Clave", max_length=KEY_MAX)
    name = models.CharField("Nombre", max_length=120)
    description = models.TextField("Descripción", blank=True)
    # Sin precio (null) = todavía no se sabe: el producto no puede estar disponible.
    price = models.DecimalField("Precio", max_digits=12, decimal_places=2, null=True, blank=True)
    image_url = models.URLField("Imagen (URL)", max_length=500, blank=True)
    # Foto subida desde el panel. Si hay las dos, manda la subida.
    imagen = models.ImageField("Foto", upload_to=ruta_foto, blank=True)
    position = models.PositiveIntegerField("Orden", default=0)
    is_available = models.BooleanField("Disponible", default=True)
    is_featured = models.BooleanField("Destacado", default=False)
    sku = models.CharField("Código interno", max_length=40, blank=True)
    prep_minutes = models.PositiveSmallIntegerField("Tiempo de preparación (min)", null=True, blank=True)
    tax_type = models.CharField("Impuesto", max_length=8, choices=TAX_CHOICES, blank=True)
    # Nombre de la presentación base cuando hay tamaños («Personal» frente a «Familiar»).
    base_label = models.CharField("Nombre de la presentación base", max_length=40, blank=True)
    permite_observacion = models.BooleanField(
        "Permitir observación", default=True,
        help_text="Si está activo, el cliente o el mesero pueden escribir «sin cebolla», etc.",
    )
    # Eliminado de la carta por el restaurante. No se borra de verdad: las
    # comandas y facturas viejas lo siguen nombrando.
    eliminado = models.BooleanField(default=False, db_index=True)
    tags = models.ManyToManyField(Tag, blank=True, related_name="products", verbose_name="Etiquetas")
    modifier_groups = models.ManyToManyField(ModifierGroup, through="ProductModifierGroup", blank=True,
                                             related_name="products", verbose_name="Grupos de adiciones")
    import_snapshot = models.JSONField(default=dict, blank=True, editable=False)

    history = historial()

    class Meta:
        verbose_name = "Producto"
        verbose_name_plural = "Productos"
        ordering = ["category__position", "position", "name"]
        constraints = [
            models.UniqueConstraint(fields=["category", "key"], name="producto_clave_unica_por_categoria"),
            models.CheckConstraint(condition=Q(price__isnull=False) | Q(is_available=False),
                                   name="producto_sin_precio_no_disponible"),
            models.CheckConstraint(condition=Q(price__isnull=True) | Q(price__gte=0),
                                   name="producto_precio_no_negativo"),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        _asegurar_clave(self, category_id=self.category_id)
        if self.price is None:
            self.is_available = False
        super().save(*args, **kwargs)

    @property
    def foto(self) -> str:
        """La imagen que se muestra: la subida al panel o, si no, la del sitio."""
        if self.imagen:
            return self.imagen.url
        return self.image_url

    # --- compatibilidad con los pedidos y sitios de antes (ver legacy.py) ---

    @property
    def opciones(self) -> list:
        """Tamaños y adiciones en la forma vieja: lista de grupos por posición."""
        from .legacy import opciones_legacy

        return opciones_legacy(self)

    @property
    def precio_legacy(self):
        """El precio desde el que suman las opciones de la forma vieja."""
        from .legacy import precio_legacy

        return precio_legacy(self)


class ProductVariant(PublicIdModel):
    """Un tamaño o presentación con precio propio («Doble carne», «Familiar»)."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants",
                                verbose_name="Producto")
    key = models.SlugField("Clave", max_length=KEY_MAX)
    name = models.CharField("Nombre", max_length=60)
    price = models.DecimalField("Precio", max_digits=12, decimal_places=2)
    position = models.PositiveIntegerField("Orden", default=0)
    import_snapshot = models.JSONField(default=dict, blank=True, editable=False)

    history = historial()

    class Meta:
        verbose_name = "Tamaño o presentación"
        verbose_name_plural = "Tamaños y presentaciones"
        ordering = ["position", "id"]
        constraints = [
            models.UniqueConstraint(fields=["product", "key"], name="variante_clave_unica_por_producto"),
            models.CheckConstraint(condition=Q(price__gte=0), name="variante_precio_no_negativo"),
        ]

    def __str__(self):
        return f"{self.product.name} · {self.name}"

    def save(self, *args, **kwargs):
        _asegurar_clave(self, product_id=self.product_id)
        super().save(*args, **kwargs)


class ProductModifierGroup(models.Model):
    """Qué grupos de adiciones tiene cada producto, y en qué orden."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="modifier_links")
    group = models.ForeignKey(ModifierGroup, on_delete=models.CASCADE, related_name="product_links")
    position = models.PositiveIntegerField("Orden", default=0)

    class Meta:
        verbose_name = "Grupo de un producto"
        verbose_name_plural = "Grupos de los productos"
        ordering = ["position", "id"]
        constraints = [
            models.UniqueConstraint(fields=["product", "group"], name="grupo_una_vez_por_producto"),
        ]

    def __str__(self):
        return f"{self.product} · {self.group}"
