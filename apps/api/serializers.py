from rest_framework import serializers

from apps.catalog.legacy import PREFETCH_LEGACY
from apps.catalog.models import Category, Product
from apps.dining.models import Table
from apps.orders.models import Order, OrderItem, TableSession

# Para listar categorías con sus productos sin una consulta por producto.
PREFETCH_PRODUCTOS = ["products", *(f"products__{r}" for r in PREFETCH_LEGACY)]


class ProductSerializer(serializers.ModelSerializer):
    """Producto en la forma de la API v1 vieja: `price` es el precio desde el que
    suman las `opciones` (con tamaños, el del más barato; ver catalog/legacy.py)."""

    foto = serializers.SerializerMethodField()
    price = serializers.DecimalField(source="precio_legacy", max_digits=12, decimal_places=2, read_only=True)
    opciones = serializers.ListField(read_only=True)

    class Meta:
        model = Product
        fields = ["id", "category", "name", "description", "price", "image_url", "foto",
                  "is_available", "opciones", "permite_observacion"]

    def get_foto(self, obj):
        """La imagen lista para usar: absoluta si es una foto subida al panel."""
        foto = obj.foto
        request = self.context.get("request")
        if foto and foto.startswith("/") and request is not None:
            return request.build_absolute_uri(foto)
        return foto


class CategorySerializer(serializers.ModelSerializer):
    products = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ["id", "name", "position", "products"]

    def get_products(self, obj):
        productos = [p for p in obj.products.all() if p.is_available and not p.eliminado]
        return ProductSerializer(productos, many=True, context=self.context).data


class CategoryWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["name", "position", "is_active"]


class ProductWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ["category", "name", "description", "price", "position", "is_available", "eliminado"]

    def validate(self, datos):
        # Restaurar un eliminado lo devuelve a la carta, disponible.
        if datos.get("eliminado") is False:
            datos.setdefault("is_available", True)
        return datos

    def validate_price(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("El precio no puede ser negativo.")
        return value


class MenuCategorySerializer(serializers.ModelSerializer):
    """El menú completo tal como lo edita el restaurante (incluye lo agotado,
    pero no lo eliminado, que va aparte para poder restaurarlo)."""

    products = serializers.SerializerMethodField()
    eliminados = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ["id", "name", "position", "is_active", "products", "eliminados"]

    def get_products(self, obj):
        return ProductSerializer([p for p in obj.products.all() if not p.eliminado], many=True).data

    def get_eliminados(self, obj):
        return [{"id": p.id, "name": p.name} for p in obj.products.all() if p.eliminado]


class OrderItemSerializer(serializers.ModelSerializer):
    line_total = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = ["id", "product", "product_name", "unit_price", "quantity", "note", "line_total",
                  "novedad", "precio_original", "opciones"]

    def get_line_total(self, obj):
        return obj.line_total()


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    total = serializers.SerializerMethodField()
    table_number = serializers.IntegerField(source="session.table.number", read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "session",
            "table_number",
            "status",
            "source",
            "mesero_nombre",
            "customer_name",
            "note",
            "created_at",
            "printed_at",
            "impresiones",
            "seen_at",
            "items",
            "total",
        ]

    def get_total(self, obj):
        return obj.total()


class OrderItemInputSerializer(serializers.Serializer):
    """Una línea del pedido, en cualquiera de sus formas.

    - Con los id de la carta pública (cloudin.menu/v1), la del menú digital:
          {"product": "<uuid>", "variant": "<uuid>" | null, "options": ["<uuid>"], "quantity": 2}
    - Del menú de la API vieja:  {"product_id": 12, "opciones": [{"grupo": 0, "valor": 1}]}
    - Armada en el sitio:        {"name": "Sandwich brisket · 250 g", "unit_price": 42000}

    La última existe para los sitios que ya tienen su propio catálogo con
    opciones y combinaciones, donde el precio final no corresponde a un
    producto suelto del menú. En las dos primeras el precio lo pone el servidor.
    """

    product = serializers.UUIDField(required=False)
    variant = serializers.UUIDField(required=False, allow_null=True)
    options = serializers.ListField(child=serializers.UUIDField(), required=False)
    product_id = serializers.IntegerField(required=False)
    name = serializers.CharField(max_length=120, required=False, allow_blank=True)
    unit_price = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=0, required=False
    )
    quantity = serializers.IntegerField(min_value=1, max_value=99, default=1)
    note = serializers.CharField(max_length=200, required=False, allow_blank=True)
    # Toppings elegidos, por posición: [{"grupo": 0, "valor": 1}]. Solo con product_id.
    opciones = serializers.ListField(child=serializers.DictField(), required=False)

    def validate(self, datos):
        if datos.get("product"):
            from django.core.exceptions import ValidationError as ErrorDjango

            from apps.catalog.legacy import linea_desde_v1

            try:
                return linea_desde_v1(datos)
            except ErrorDjango as e:
                raise serializers.ValidationError(e.messages[0])
        if datos.get("product_id"):
            return datos
        if datos.get("name") and datos.get("unit_price") is not None:
            # Una línea armada en el sitio tiene que ser un plato de la carta y no
            # se cobra por debajo de su precio: el JavaScript del sitio se puede editar.
            from .limites import precio_seguro

            try:
                _, datos["unit_price"] = precio_seguro(datos["name"], datos["unit_price"])
            except ValueError as e:
                raise serializers.ValidationError(str(e))
            return datos
        raise serializers.ValidationError(
            "Cada ítem necesita 'product' (el id de la carta), o 'product_id', o bien 'name' y 'unit_price'."
        )


class OrderCreateSerializer(serializers.Serializer):
    items = OrderItemInputSerializer(many=True)
    note = serializers.CharField(max_length=500, required=False, allow_blank=True)
    guests = serializers.IntegerField(min_value=1, max_value=50, required=False)
    customer_name = serializers.CharField(max_length=80, required=False, allow_blank=True)

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("El pedido no tiene productos.")
        # Solo se verifican contra el menú las líneas que dicen ser del menú.
        ids = [i["product_id"] for i in value if i.get("product_id")]
        if not ids:
            return value
        productos = {p.id: p for p in Product.objects.filter(id__in=ids, is_available=True)}
        faltantes = [i for i in ids if i not in productos]
        if faltantes:
            raise serializers.ValidationError(
                f"Productos no disponibles o inexistentes: {faltantes}"
            )
        # Las opciones se validan aquí para responder 400 con un mensaje claro.
        from django.core.exceptions import ValidationError as ErrorDjango

        from apps.catalog.opciones import aplicar

        for item in value:
            if item.get("product_id"):
                try:
                    aplicar(productos[item["product_id"]], item.get("opciones"), item.get("note", ""))
                except ErrorDjango as e:
                    raise serializers.ValidationError(e.messages[0])
        return value


class TableSessionSerializer(serializers.ModelSerializer):
    orders = OrderSerializer(many=True, read_only=True)
    current_total = serializers.SerializerMethodField()
    subtotal = serializers.SerializerMethodField()
    novedades = serializers.SerializerMethodField()
    table_number = serializers.IntegerField(source="table.number", read_only=True)

    class Meta:
        model = TableSession
        fields = [
            "id",
            "table",
            "table_number",
            "status",
            "customer_name",
            "guests",
            "opened_at",
            "closed_at",
            "total",
            "current_total",
            "subtotal",
            "descuento",
            "descuento_motivo",
            "novedades",
            "orders",
        ]

    def get_current_total(self, obj):
        return obj.current_total()

    def get_subtotal(self, obj):
        return obj.subtotal()

    def get_novedades(self, obj):
        return [
            {"id": n.id, "tipo": n.tipo, "tipo_texto": n.get_tipo_display(), "producto": n.producto_nombre,
             "cantidad": n.cantidad, "valor": n.valor, "motivo": n.motivo, "registrado_por": n.registrado_por,
             "autorizado_por": n.autorizado_por, "creado": n.creado}
            for n in obj.novedades.all()
        ]


class TableWriteSerializer(serializers.ModelSerializer):
    """Alta y edición de mesas desde el panel del restaurante."""

    class Meta:
        model = Table
        fields = ["number", "seats", "is_active", "zona"]

    def validate_number(self, value):
        existentes = Table.objects.filter(number=value)
        if self.instance:
            existentes = existentes.exclude(pk=self.instance.pk)
        if existentes.exists():
            raise serializers.ValidationError(f"Ya existe la mesa {value}.")
        return value


class TableSerializer(serializers.ModelSerializer):
    is_occupied = serializers.BooleanField(read_only=True)
    session_id = serializers.SerializerMethodField()
    session_total = serializers.SerializerMethodField()
    session_customer = serializers.SerializerMethodField()
    pending_orders = serializers.SerializerMethodField()

    class Meta:
        model = Table
        fields = [
            "id",
            "number",
            "seats",
            "zona",
            "is_active",
            "is_occupied",
            "session_id",
            "session_total",
            "session_customer",
            "pending_orders",
        ]

    def get_session_customer(self, obj):
        s = obj.open_session
        return s.customer_name if s else ""

    def get_session_id(self, obj):
        s = obj.open_session
        return s.id if s else None

    def get_session_total(self, obj):
        s = obj.open_session
        return s.current_total() if s else 0

    def get_pending_orders(self, obj):
        s = obj.open_session
        if not s:
            return 0
        return s.orders.filter(status=Order.STATUS_PENDING).count()
