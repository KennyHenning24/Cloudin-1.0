"""Consultas de la carta para el panel (listas con filtros, historial reciente)."""

from django.db.models import Count, Prefetch, Q

from apps.common.money import formato_cop

from .models import Category, Menu, ModifierOption, Product, ProductModifierGroup, ProductVariant


def menus_del_panel():
    return (Menu.objects.filter(deleted_at__isnull=True).order_by("position", "name")
            .annotate(categorias=Count("categories", filter=Q(categories__deleted_at__isnull=True))))


def categorias_del_panel(menu=None):
    qs = Category.objects.filter(deleted_at__isnull=True).select_related("menu").order_by("position", "name")
    if menu is not None:
        qs = qs.filter(menu=menu)
    return qs.annotate(productos=Count("products", filter=Q(products__eliminado=False)))


def productos_del_panel(categoria=None, menu=None, texto="", estado="", incluir_eliminados=False):
    """Productos para Mi menú, con todo lo que la lista y el editor necesitan."""
    qs = (Product.objects.select_related("category", "category__menu")
          .prefetch_related(
              "tags",
              Prefetch("variants", queryset=ProductVariant.objects.order_by("position", "id")),
              Prefetch("modifier_links", queryset=ProductModifierGroup.objects.select_related("group")
                       .order_by("position", "id")),
              Prefetch("modifier_links__group__options", queryset=ModifierOption.objects.order_by("position", "id")),
          )
          .filter(category__deleted_at__isnull=True)
          .order_by("category__position", "position", "name"))
    if not incluir_eliminados:
        qs = qs.filter(eliminado=False)
    if categoria is not None:
        qs = qs.filter(category=categoria)
    if menu is not None:
        qs = qs.filter(category__menu=menu)
    if texto:
        qs = qs.filter(Q(name__icontains=texto) | Q(description__icontains=texto) | Q(sku__iexact=texto))
    if estado == "available":
        qs = qs.filter(is_available=True)
    elif estado == "soldout":
        qs = qs.filter(is_available=False)
    elif estado == "no_price":
        qs = qs.filter(price__isnull=True)
    return qs


def resumen_de_la_carta() -> dict:
    """Los números del Inicio: activos, agotados, sin foto, sin precio."""
    base = Product.objects.filter(eliminado=False, category__deleted_at__isnull=True)
    return {
        "activos": base.filter(is_available=True).count(),
        "agotados": base.filter(is_available=False, price__isnull=False).count(),
        "sin_foto": base.filter(imagen="", image_url="").count(),
        "sin_precio": base.filter(price__isnull=True).count(),
        "total": base.count(),
        "categorias": Category.objects.filter(deleted_at__isnull=True).count(),
    }


def _texto_de_cambio(registro) -> str | None:
    """Una frase para la «Actividad reciente» a partir de un registro del historial."""
    nombre = getattr(registro, "name", "") or ""
    if registro.history_type == "+":
        return f"agregó {nombre}"
    if registro.history_type == "-":
        return f"borró {nombre}"
    anterior = registro.prev_record
    if anterior is None:
        return None
    cambios = registro.diff_against(anterior).changes
    frases = []
    for c in cambios:
        if c.field == "price":
            frases.append(f"cambió el precio de {nombre}: {formato_cop(c.old) or 'sin precio'} → "
                          f"{formato_cop(c.new) or 'sin precio'}")
        elif c.field == "is_available":
            frases.append(f"marcó {nombre} como {'disponible' if c.new else 'agotado'}")
        elif c.field == "eliminado":
            frases.append(f"{'sacó' if c.new else 'devolvió'} {nombre} {'de' if c.new else 'a'} la carta")
        elif c.field == "deleted_at":
            frases.append(f"{'borró' if c.new else 'restauró'} {nombre}")
        elif c.field == "name":
            frases.append(f"renombró {c.old} como {c.new}")
    return frases[0] if frases else f"editó {nombre}"


def actividad_reciente(limite: int = 10, producto=None) -> list[dict]:
    """Quién cambió qué y cuándo (productos y categorías)."""
    historial = Product.history.all() if producto is None else Product.history.filter(id=producto.pk)
    registros = list(historial.order_by("-history_date")[: limite * 2])
    if producto is None:
        registros += list(Category.history.order_by("-history_date")[:limite])
        registros.sort(key=lambda r: r.history_date, reverse=True)
    salida = []
    for r in registros:
        texto = _texto_de_cambio(r)
        if texto:
            salida.append({"when": r.history_date, "who": r.history_user_name or "Cloudin", "text": texto})
        if len(salida) >= limite:
            break
    return salida
