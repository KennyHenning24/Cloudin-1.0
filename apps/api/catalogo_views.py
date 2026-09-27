"""API de administración de la carta (la usa el panel del dueño). Prefijo /api/v1/staff/.

Sesión de Django + CSRF (el panel vive en el mismo dominio). Permisos:
- leer: todo el equipo del restaurante;
- marcar agotado / disponible: todo el equipo;
- crear, editar, reordenar, borrar, precios, ajustes y mesas: dueño o administrador.
Lo usa el panel del dueño (Mi menú, Personalizar, Mesas y QR).

Todo se identifica por el UUID público (`id`). Borrar es lógico y se puede deshacer.
"""

from django.core.exceptions import ValidationError as ErrorDjango
from django.db import IntegrityError
from django.db.models import Count, Q
from django.http import HttpResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.business.models import RestaurantSettings
from apps.catalog import images, selectors, services
from apps.catalog.models import Category, Menu, ModifierGroup, Product, Tag
from apps.dining.models import Table

from . import catalogo_serializers as s
from .permissions import AdministraLaCarta, LeeLaCarta, PuedeAgotar


def _error(e: ErrorDjango):
    """Un error de negocio como respuesta 400 con un mensaje para mostrar tal cual."""
    return Response({"detail": e.messages[0]}, status=status.HTTP_400_BAD_REQUEST)


class BaseCarta(viewsets.ModelViewSet):
    permission_classes = [AdministraLaCarta]
    lookup_field = "uuid"
    lookup_url_kwarg = "id"
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    def handle_exception(self, exc):
        if isinstance(exc, services.HaceFaltaConfirmar):
            return Response({"detail": exc.messages[0], "code": "confirm"}, status=status.HTTP_409_CONFLICT)
        if isinstance(exc, ErrorDjango):
            return _error(exc)
        if isinstance(exc, IntegrityError):
            return Response({"detail": "Ya existe un elemento con esa clave. Usa otra o déjala vacía."},
                            status=status.HTTP_400_BAD_REQUEST)
        return super().handle_exception(exc)


class MenuViewSet(BaseCarta):
    serializer_class = s.MenuSerializer

    def get_queryset(self):
        return selectors.menus_del_panel()

    def perform_create(self, serializer):
        serializer.save(position=services.siguiente_posicion(Menu.objects.filter(deleted_at__isnull=True)))

    def perform_destroy(self, menu):
        services.archivar_menu(menu, self.request.user)


class CategoryViewSet(BaseCarta):
    serializer_class = s.CategorySerializer

    def get_queryset(self):
        qs = selectors.categorias_del_panel()
        if self.action == "restore":
            return Category.objects.all()
        menu = self.request.query_params.get("menu")
        return qs.filter(menu__uuid=menu) if menu else qs

    def perform_create(self, serializer):
        menu = serializer.validated_data.get("menu") or Menu.principal()
        serializer.save(menu=menu, position=services.siguiente_posicion(
            Category.objects.filter(menu=menu, deleted_at__isnull=True)))

    def destroy(self, request, *args, **kwargs):
        confirmado = request.query_params.get("confirm") in ("1", "true")
        services.archivar_categoria(self.get_object(), confirmado, request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def restore(self, request, id=None):
        categoria = services.restaurar_categoria(self.get_object(), request.user)
        return Response(self.get_serializer(categoria).data)

    @action(detail=True, methods=["post", "delete"], parser_classes=[MultiPartParser])
    def image(self, request, id=None):
        categoria = self.get_object()
        if request.method == "DELETE":
            categoria.image = ""
        else:
            if "file" not in request.FILES:
                return Response({"detail": "Elige una foto."}, status=400)
            categoria.image = images.a_webp(request.FILES["file"], images.LADO_PRODUCTO, categoria.key)
        categoria.save()
        return Response(self.get_serializer(categoria).data)


class ProductViewSet(BaseCarta):
    serializer_class = s.ProductSerializer

    def get_permissions(self):
        if self.action == "availability":
            return [PuedeAgotar()]
        return super().get_permissions()

    def get_queryset(self):
        p = self.request.query_params
        incluir = self.action in ("restore",) or p.get("deleted") in ("1", "true")
        categoria = Category.objects.filter(uuid=p["category"]).first() if p.get("category") else None
        if p.get("category") and categoria is None:
            return Product.objects.none()
        menu = Menu.objects.filter(uuid=p["menu"]).first() if p.get("menu") else None
        qs = selectors.productos_del_panel(categoria=categoria, menu=menu, texto=p.get("q", "").strip()[:80],
                                           estado=p.get("status", ""), incluir_eliminados=incluir)
        if p.get("deleted") in ("1", "true"):
            qs = qs.filter(eliminado=True)
        return qs

    def perform_destroy(self, producto):
        services.eliminar_producto(producto, self.request.user)

    @action(detail=True, methods=["post"])
    def restore(self, request, id=None):
        return Response(self.get_serializer(services.restaurar_producto(self.get_object(), request.user)).data)

    @action(detail=True, methods=["patch"])
    def availability(self, request, id=None):
        disponible = request.data.get("available")
        if not isinstance(disponible, bool):
            return Response({"detail": "Falta decir si está disponible (true o false)."}, status=400)
        producto = services.marcar_disponible(self.get_object(), disponible, request.user)
        return Response({"id": str(producto.uuid), "available": producto.is_available})

    @action(detail=True, methods=["put"])
    def variants(self, request, id=None):
        datos = s.VariantSerializer(data=request.data if isinstance(request.data, list) else [], many=True)
        datos.is_valid(raise_exception=True)
        producto = self.get_object()
        services.guardar_variantes(producto, [
            {"id": (request.data[i] or {}).get("id"), "name": v["name"], "price": v["price"]}
            for i, v in enumerate(datos.validated_data)])
        return Response(self.get_serializer(self.get_queryset().get(pk=producto.pk)).data)

    @action(detail=True, methods=["put"], url_path="modifier-groups")
    def modifier_groups(self, request, id=None):
        if not isinstance(request.data, list):
            return Response({"detail": "Manda la lista de grupos en orden."}, status=400)
        producto = self.get_object()
        services.guardar_grupos_del_producto(producto, request.data)
        return Response(self.get_serializer(self.get_queryset().get(pk=producto.pk)).data)

    @action(detail=True, methods=["post", "delete"], parser_classes=[MultiPartParser])
    def image(self, request, id=None):
        producto = self.get_object()
        if request.method == "DELETE":
            producto.imagen = ""
            producto.image_url = ""
        else:
            if "file" not in request.FILES:
                return Response({"detail": "Elige una foto."}, status=400)
            producto.imagen = images.a_webp(request.FILES["file"], images.LADO_PRODUCTO, producto.key)
        producto.save()
        return Response(self.get_serializer(producto).data)


class ModifierGroupViewSet(BaseCarta):
    serializer_class = s.ModifierGroupSerializer

    def get_queryset(self):
        return ModifierGroup.objects.prefetch_related("options").order_by("position", "name")

    def perform_destroy(self, grupo):
        if grupo.product_links.exists() and self.request.query_params.get("confirm") not in ("1", "true"):
            raise services.HaceFaltaConfirmar(
                f"«{grupo.name}» se usa en {grupo.product_links.count()} producto(s). Si lo borras, se les quita.")
        grupo.delete()


class TagViewSet(BaseCarta):
    serializer_class = s.TagSerializer

    def get_queryset(self):
        return Tag.objects.annotate(uso=Count("products", filter=Q(products__eliminado=False))).order_by(
            "position", "name")


class ReordenarView(APIView):
    """POST {"kind": "categories" | "products" | "menus" | "modifier-groups", "ids": [uuid, …]}"""

    permission_classes = [AdministraLaCarta]

    def post(self, request):
        try:
            cambiados = services.reordenar(request.data.get("kind", ""), request.data.get("ids") or [])
        except ErrorDjango as e:
            return _error(e)
        return Response({"changed": cambiados})


class AccionesMasivasView(APIView):
    """POST {"action": "soldout|available|price_percent|set_prices|move|delete|restore", "ids": [...], "value": …}

    Responde {"changed": n, "undo": [...]}: con eso el panel ofrece «Deshacer»."""

    permission_classes = [AdministraLaCarta]

    def get_permissions(self):
        if isinstance(self.request.data, dict) and self.request.data.get("action") in ("soldout", "available"):
            return [PuedeAgotar()]
        return super().get_permissions()

    def post(self, request):
        ids = [str(i) for i in (request.data.get("ids") or [])][:500]
        productos = list(Product.objects.filter(uuid__in=ids).select_related("category"))
        try:
            resultado = services.acciones_masivas(request.data.get("action", ""), productos,
                                                  request.data.get("value"), request.user)
        except ErrorDjango as e:
            return _error(e)
        return Response(resultado)


class HistorialView(APIView):
    """GET ?product=<uuid> — quién cambió qué y cuándo (o lo último de toda la carta)."""

    permission_classes = [LeeLaCarta]

    def get(self, request):
        producto = None
        if request.query_params.get("product"):
            producto = Product.objects.filter(uuid=request.query_params["product"]).first()
            if producto is None:
                return Response({"detail": "Ese producto no existe."}, status=404)
        return Response(selectors.actividad_reciente(20, producto))


class AjustesView(APIView):
    """GET y PATCH de los datos del negocio (marca del menú, contacto, redes, horario)."""

    permission_classes = [AdministraLaCarta]
    parser_classes = [JSONParser]

    def get(self, request):
        return Response(s.SettingsSerializer(RestaurantSettings.load(), context={"request": request}).data)

    def patch(self, request):
        datos = dict(request.data)
        if "hours" in datos:
            datos["hours_input"] = datos.pop("hours")
        serializer = s.SettingsSerializer(RestaurantSettings.load(), data=datos, partial=True,
                                          context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(s.SettingsSerializer(RestaurantSettings.load(), context={"request": request}).data)


class ImagenDeMarcaView(APIView):
    """POST (multipart `file`) o DELETE del logo o la portada del menú."""

    permission_classes = [AdministraLaCarta]
    parser_classes = [MultiPartParser]
    campo = "logo"

    def post(self, request):
        if "file" not in request.FILES:
            return Response({"detail": "Elige una imagen."}, status=400)
        lado = images.LADO_LOGO if self.campo == "logo" else images.LADO_PORTADA
        try:
            archivo = images.a_webp(request.FILES["file"], lado, self.campo)
        except ErrorDjango as e:
            return _error(e)
        ajustes = RestaurantSettings.load()
        setattr(ajustes, self.campo, archivo)
        ajustes.save()
        return Response(s.SettingsSerializer(ajustes, context={"request": request}).data)

    def delete(self, request):
        ajustes = RestaurantSettings.load()
        setattr(ajustes, self.campo, "")
        ajustes.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------- mesas y QR


class MesasView(APIView):
    """GET: las mesas con su enlace de QR. POST {"count": n}: deja n mesas (crea las que falten)."""

    permission_classes = [AdministraLaCarta]

    def get(self, request):
        from apps.dining.qr import enlace_de_mesa

        mesas = Table.objects.filter(is_active=True).order_by("number")
        return Response([{"id": m.id, "number": m.number, "link": enlace_de_mesa(request.tenant, m)} for m in mesas])

    def post(self, request):
        from apps.dining.qr import asegurar_mesas

        try:
            cantidad = int(request.data.get("count", 0))
        except (TypeError, ValueError):
            cantidad = 0
        if not 1 <= cantidad <= 200:
            return Response({"detail": "Escribe cuántas mesas tienes (de 1 a 200)."}, status=400)
        creadas = asegurar_mesas(cantidad)
        return Response({"created": creadas}, status=201 if creadas else 200)


SIN_PAGINA = ("Tu menú todavía no está publicado: el QR sale cuando tenga su página "
              "(la dirección llega al importar el menú).")


class QrView(APIView):
    """GET staff/qr/menu.(png|svg) · staff/qr/mesa/<id>.(png|svg) · staff/qr/mesas.pdf

    El QR lleva a la página del menú del restaurante (Tenant.menu_page): Cloudin no
    tiene un menú propio. Sin página publicada, responde 404 con la explicación."""

    permission_classes = [LeeLaCarta]

    def get(self, request, formato, mesa_id=None, todas=False):
        from apps.dining import qr

        tenant = request.tenant
        if todas:
            mesas = [m for m in Table.objects.filter(is_active=True).order_by("number") if qr.enlace_de_mesa(tenant, m)]
            if not mesas:
                detalle = SIN_PAGINA if Table.objects.filter(is_active=True).exists() else "Todavía no hay mesas."
                return Response({"detail": detalle}, status=404)
            contenido = qr.pdf_de_mesas(tenant, mesas)
            return _archivo(contenido, "application/pdf", f"qr-mesas-{tenant.slug}.pdf")
        if mesa_id is not None:
            mesa = Table.objects.filter(pk=mesa_id, is_active=True).first()
            if mesa is None:
                return Response({"detail": "Esa mesa no existe."}, status=404)
            enlace, nombre = qr.enlace_de_mesa(tenant, mesa), f"qr-mesa-{mesa.number}-{tenant.slug}"
        else:
            enlace, nombre = qr.enlace_del_menu(tenant), f"qr-menu-{tenant.slug}"
        if not enlace:
            return Response({"detail": SIN_PAGINA}, status=404)
        if formato == "svg":
            return _archivo(qr.svg(enlace), "image/svg+xml", f"{nombre}.svg")
        return _archivo(qr.png(enlace), "image/png", f"{nombre}.png")


def _archivo(contenido, tipo, nombre):
    respuesta = HttpResponse(contenido, content_type=tipo)
    respuesta["Content-Disposition"] = f'inline; filename="{nombre}"'
    respuesta["Cache-Control"] = "private, max-age=300"
    return respuesta
