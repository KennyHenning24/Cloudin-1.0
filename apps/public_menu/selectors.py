"""Consultas del menú público: todo el árbol en un número fijo de consultas (sin N+1).

Solo sale lo que el cliente final puede ver:
- menús y categorías activos y sin archivar;
- productos no eliminados. Los agotados SÍ salen, marcados como no disponibles
  (el sitio decide si los atenúa o los esconde), y también los que aún no tienen
  precio: salen no disponibles y con `price: null`, así lo pre-renderizado desde
  la semilla coincide con lo que llega en vivo;
- categorías sin productos visibles no salen.
"""

from django.db.models import Prefetch

from apps.business.models import OpeningHours, RestaurantSettings
from apps.catalog.models import Category, Menu, ModifierOption, Product, ProductModifierGroup, Tag
from apps.dining.models import Table


def productos_visibles():
    return (Product.objects.filter(eliminado=False)
            .order_by("position", "name")
            .prefetch_related(
                "variants",
                Prefetch("tags", queryset=Tag.objects.order_by("position", "name")),
                Prefetch("modifier_links",
                         queryset=ProductModifierGroup.objects.select_related("group").order_by("position", "id")),
                Prefetch("modifier_links__group__options", queryset=ModifierOption.objects.order_by("position", "id")),
            ))


def menus_publicos():
    categorias = (Category.objects.filter(is_active=True, deleted_at__isnull=True)
                  .order_by("position", "name")
                  .prefetch_related(Prefetch("products", queryset=productos_visibles())))
    return list(Menu.objects.filter(is_active=True, deleted_at__isnull=True)
                .order_by("position", "name")
                .prefetch_related(Prefetch("categories", queryset=categorias)))


def ajustes():
    return RestaurantSettings.load()


def horario():
    return list(OpeningHours.objects.order_by("day", "opens"))


def etiquetas():
    return list(Tag.objects.order_by("position", "name"))


def mesa_por_token_o_numero(valor: str):
    """La mesa del QR. Se acepta el token (lo que imprime Cloudin) o el número."""
    valor = (valor or "").strip()[:64]
    if not valor:
        return None
    mesa = Table.objects.filter(token=valor, is_active=True).first()
    if mesa is None and valor.isdigit():
        mesa = Table.objects.filter(number=int(valor), is_active=True).first()
    return mesa
