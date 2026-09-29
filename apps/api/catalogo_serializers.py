"""Serializers de la API de administración de la carta (v1).

Todo se identifica por `id` (el UUID público). La `key` se genera sola al crear
(o se puede mandar una válida) y después no se cambia.
"""

from decimal import Decimal

from rest_framework import serializers

from apps.business.models import DIAS, MEDIOS_DE_PAGO, SERVICIOS, OpeningHours, RestaurantSettings, servicios_de
from apps.catalog.models import Category, Menu, ModifierGroup, Product, Tag
from apps.common.keys import es_clave_valida


def _url(request, campo):
    if not campo:
        return None
    url = campo.url
    return request.build_absolute_uri(url) if request is not None and url.startswith("/") else url


class ClaveMixin(serializers.ModelSerializer):
    """`key` opcional al crear (si viene, debe ser kebab-case); de solo lectura después."""

    def validate_key(self, valor):
        if self.instance is not None and valor != self.instance.key:
            raise serializers.ValidationError("La clave no se cambia: es la que usa la importación.")
        if valor and not es_clave_valida(valor):
            raise serializers.ValidationError("Usa minúsculas, números y guiones (ej. «hamburguesa-clasica»).")
        return valor


class MenuSerializer(ClaveMixin):
    id = serializers.UUIDField(source="uuid", read_only=True)
    key = serializers.CharField(required=False, allow_blank=True, max_length=60)
    categories_count = serializers.IntegerField(source="categorias", read_only=True, default=None)

    class Meta:
        model = Menu
        fields = ["id", "key", "name", "description", "position", "is_active", "available_days",
                  "available_from", "available_to", "categories_count"]
        validators = []

    def validate_available_days(self, dias):
        if not isinstance(dias, list) or any(not isinstance(d, int) or not 0 <= d <= 6 for d in dias):
            raise serializers.ValidationError("Los días van de 0 (lunes) a 6 (domingo).")
        return sorted(set(dias))


class CategorySerializer(ClaveMixin):
    id = serializers.UUIDField(source="uuid", read_only=True)
    key = serializers.CharField(required=False, allow_blank=True, max_length=60)
    menu = serializers.SlugRelatedField(slug_field="uuid", queryset=Menu.objects.filter(deleted_at__isnull=True),
                                        required=False)
    image = serializers.SerializerMethodField()
    products_count = serializers.IntegerField(source="productos", read_only=True, default=None)

    class Meta:
        model = Category
        fields = ["id", "key", "menu", "name", "description", "image", "position", "is_active", "products_count"]
        validators = []

    def get_image(self, obj):
        return _url(self.context.get("request"), obj.image)


class TagSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="uuid", read_only=True)
    key = serializers.CharField(read_only=True)
    products_count = serializers.IntegerField(source="uso", read_only=True, default=None)

    class Meta:
        model = Tag
        fields = ["id", "key", "name", "position", "products_count"]

    def validate_name(self, valor):
        valor = " ".join(valor.split())
        if not valor:
            raise serializers.ValidationError("Escribe el nombre de la etiqueta.")
        otras = Tag.objects.filter(name__iexact=valor)
        if self.instance is not None:
            otras = otras.exclude(pk=self.instance.pk)
        if otras.exists():
            raise serializers.ValidationError(f"Ya existe la etiqueta «{valor}».")
        return valor


class VariantSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="uuid", read_only=True)
    key = serializers.CharField(read_only=True)
    name = serializers.CharField(max_length=60)
    price = serializers.DecimalField(max_digits=12, decimal_places=0, min_value=Decimal("0"))


class OptionSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="uuid", required=False)
    key = serializers.CharField(read_only=True)
    name = serializers.CharField(max_length=60)
    price = serializers.DecimalField(source="price_delta", max_digits=12, decimal_places=0,
                                     min_value=Decimal("0"), default=Decimal("0"))


class ModifierGroupSerializer(ClaveMixin):
    id = serializers.UUIDField(source="uuid", read_only=True)
    key = serializers.CharField(required=False, allow_blank=True, max_length=60)
    min = serializers.IntegerField(source="min_select", min_value=0, max_value=20, default=0)
    max = serializers.IntegerField(source="max_select", min_value=1, max_value=40, allow_null=True, required=False)
    options = OptionSerializer(many=True, required=False)
    products_count = serializers.SerializerMethodField()

    class Meta:
        model = ModifierGroup
        fields = ["id", "key", "name", "min", "max", "options", "products_count"]
        validators = []

    def get_products_count(self, obj):
        return obj.product_links.count()

    def validate(self, datos):
        minimo = datos.get("min_select", getattr(self.instance, "min_select", 0))
        maximo = datos.get("max_select", getattr(self.instance, "max_select", None))
        if maximo is not None and maximo < minimo:
            raise serializers.ValidationError({"max": "El máximo no puede ser menor que el mínimo."})
        return datos

    def _guardar_opciones(self, grupo, opciones):
        from apps.catalog.services import guardar_opciones_del_grupo

        if opciones is not None:
            guardar_opciones_del_grupo(grupo, [
                {"id": o.get("uuid"), "name": o["name"], "price": o.get("price_delta", 0)} for o in opciones])

    def create(self, datos):
        opciones = datos.pop("options", None)
        grupo = super().create(datos)
        self._guardar_opciones(grupo, opciones or [])
        return grupo

    def update(self, grupo, datos):
        opciones = datos.pop("options", None)
        grupo = super().update(grupo, datos)
        self._guardar_opciones(grupo, opciones)
        return grupo


class ProductSerializer(ClaveMixin):
    """El producto como lo edita el panel: todo lo básico y las opciones avanzadas."""

    id = serializers.UUIDField(source="uuid", read_only=True)
    key = serializers.CharField(required=False, allow_blank=True, max_length=60)
    category = serializers.SlugRelatedField(slug_field="uuid",
                                            queryset=Category.objects.filter(deleted_at__isnull=True))
    price = serializers.DecimalField(max_digits=12, decimal_places=0, min_value=Decimal("0"), allow_null=True,
                                     required=False)
    image = serializers.SerializerMethodField()
    tags = serializers.SlugRelatedField(slug_field="key", many=True, queryset=Tag.objects.all(), required=False)
    variants = VariantSerializer(many=True, read_only=True)
    modifier_groups = serializers.SerializerMethodField()
    deleted = serializers.BooleanField(source="eliminado", read_only=True)

    class Meta:
        model = Product
        fields = ["id", "key", "category", "name", "description", "price", "image", "is_available",
                  "is_featured", "sku", "prep_minutes", "tax_type", "base_label", "permite_observacion",
                  "tags", "variants", "modifier_groups", "deleted", "position"]
        extra_kwargs = {"position": {"read_only": True}, "description": {"max_length": 500}}
        validators = []

    def get_image(self, obj):
        foto = obj.foto
        request = self.context.get("request")
        if foto and foto.startswith("/") and request is not None:
            return request.build_absolute_uri(foto)
        return foto or None

    def get_modifier_groups(self, obj):
        return [{"id": str(enlace.group.uuid), "name": enlace.group.name} for enlace in obj.modifier_links.all()]

    def validate(self, datos):
        precio = datos.get("price", getattr(self.instance, "price", None))
        if datos.get("is_available") and precio is None:
            raise serializers.ValidationError({"is_available": "Ponle precio para poder activarlo."})
        return datos

    def create(self, datos):
        from apps.catalog.services import siguiente_posicion

        datos.setdefault("position", siguiente_posicion(Product.objects.filter(category=datos["category"])))
        if datos.get("price") is None:
            datos["is_available"] = False
        return super().create(datos)


# ---------------------------------------------------------------- ajustes


class HorarioSerializer(serializers.Serializer):
    day = serializers.ChoiceField(choices=DIAS)
    open = serializers.TimeField(format="%H:%M", input_formats=["%H:%M"])
    close = serializers.TimeField(format="%H:%M", input_formats=["%H:%M"])

    def validate(self, datos):
        if datos["open"] == datos["close"]:
            raise serializers.ValidationError("La hora de abrir y la de cerrar no pueden ser iguales.")
        return datos


class SettingsSerializer(serializers.ModelSerializer):
    """Datos del negocio y horario. Los colores y el logo son los del MENÚ del restaurante."""

    logo = serializers.SerializerMethodField()
    cover = serializers.SerializerMethodField()
    hours = serializers.SerializerMethodField()
    hours_input = HorarioSerializer(many=True, write_only=True, required=False, source="horas")
    whatsapp = serializers.CharField(required=False, allow_blank=True, max_length=30)
    phone = serializers.CharField(required=False, allow_blank=True, max_length=30)

    class Meta:
        model = RestaurantSettings
        fields = ["logo", "cover", "color_primary", "color_secondary", "color_background", "color_text",
                  "tagline", "description", "welcome_message", "whatsapp", "phone", "email", "address", "city",
                  "maps_url", "instagram", "facebook", "tiktok", "services", "payment_methods",
                  "onboarding_step", "onboarding_done_at", "hours", "hours_input"]
        read_only_fields = ["onboarding_done_at"]

    def to_representation(self, ajustes):
        datos = super().to_representation(ajustes)
        datos["services"] = servicios_de(ajustes)  # los que nunca se tocaron salen encendidos
        return datos

    def get_logo(self, obj):
        return _url(self.context.get("request"), obj.logo)

    def get_cover(self, obj):
        return _url(self.context.get("request"), obj.cover)

    def get_hours(self, obj):
        return [{"day": DIAS[h.day], "open": h.opens.strftime("%H:%M"), "close": h.closes.strftime("%H:%M")}
                for h in OpeningHours.objects.order_by("day", "opens")]

    def validate_whatsapp(self, valor):
        return self._telefono(valor)

    def validate_phone(self, valor):
        return self._telefono(valor)

    def _telefono(self, valor):
        from apps.business.models import normalizar_telefono

        if not valor:
            return ""
        numero = normalizar_telefono(valor)
        if not numero:
            raise serializers.ValidationError("Escribe un celular de 10 dígitos (ej. 300 123 4567).")
        return numero

    def validate_services(self, valor):
        if not isinstance(valor, dict):
            raise serializers.ValidationError("Formato inválido.")
        # El que no viene queda como estaba (encendido si nunca se tocó).
        actuales = servicios_de(self.instance) if self.instance else dict.fromkeys(SERVICIOS, True)
        return {k: bool(valor.get(k, actuales[k])) for k in SERVICIOS}

    def validate_payment_methods(self, valor):
        if not isinstance(valor, list) or any(m not in MEDIOS_DE_PAGO for m in valor):
            raise serializers.ValidationError(f"Medios válidos: {', '.join(MEDIOS_DE_PAGO)}.")
        return list(dict.fromkeys(valor))

    def update(self, ajustes, datos):
        horas = datos.pop("horas", None)
        ajustes = super().update(ajustes, datos)
        if horas is not None:
            OpeningHours.objects.all().delete()
            OpeningHours.objects.bulk_create([
                OpeningHours(day=DIAS.index(h["day"]), opens=h["open"], closes=h["close"]) for h in horas[:40]])
            from apps.catalog.services import subir_version_del_menu

            subir_version_del_menu()
        return ajustes
