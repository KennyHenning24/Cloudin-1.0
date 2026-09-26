"""Lógica de negocio de la carta.

Las vistas y la API llaman aquí; no cambian modelos por su cuenta. Todo corre
dentro del restaurante activo (`tenant_context` o el middleware).

Cambios de precio y de disponibilidad quedan en el historial (simple-history)
con quién los hizo. Las operaciones masivas no disparan señales, así que suben
la versión del menú a mano (`subir_version_del_menu`).
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Max
from django.utils import timezone
from simple_history.utils import bulk_update_with_history

from apps.common.money import a_pesos, redondear_a


class HaceFaltaConfirmar(ValidationError):
    """La acción borra algo con contenido: la interfaz debe pedir confirmación."""


def _db():
    from apps.tenants.context import get_current_db_alias

    return get_current_db_alias()


def subir_version_del_menu(db: str | None = None) -> None:
    """Marca que el menú cambió: la API pública responde con un ETag nuevo.

    Se llama desde las señales de guardar/borrar y desde las operaciones
    masivas (que no disparan señales). `update()` no dispara señales, así que
    no hay ciclo. Se usa la base del objeto que cambió (`db`), no la del
    restaurante activo: así funciona también en comandos y scripts.
    """
    from apps.business.models import RestaurantSettings

    qs = RestaurantSettings.objects.using(db) if db else RestaurantSettings.objects
    if not qs.filter(pk=1).update(menu_version=F("menu_version") + 1):
        qs.get_or_create(pk=1)


def siguiente_posicion(qs) -> int:
    return (qs.aggregate(m=Max("position"))["m"] or 0) + 1


# ------------------------------------------------------------ disponibilidad


def marcar_disponible(producto, disponible: bool, usuario=None):
    """Agotado ↔ disponible, en un toque. Un producto sin precio no se puede activar."""
    if disponible and producto.price is None:
        raise ValidationError(f"«{producto.name}» todavía no tiene precio. Ponle precio para activarlo.")
    if producto.is_available != disponible:
        producto.is_available = disponible
        producto._history_user = usuario
        producto.save(update_fields=["is_available", "updated_at"])
    return producto


# ------------------------------------------------------- borrar y restaurar


def eliminar_producto(producto, usuario=None):
    """Sale de la carta en todas partes. No se borra: pedidos y facturas lo nombran."""
    producto.eliminado = True
    producto.is_available = False
    producto._history_user = usuario
    producto.save(update_fields=["eliminado", "is_available", "updated_at"])
    return producto


def restaurar_producto(producto, usuario=None):
    producto.eliminado = False
    producto.is_available = producto.price is not None
    producto._history_user = usuario
    producto.save(update_fields=["eliminado", "is_available", "updated_at"])
    return producto


def archivar_categoria(categoria, confirmado: bool = False, usuario=None):
    """Archiva la categoría (desaparece del menú). Si tiene productos, pide confirmación."""
    activos = categoria.products.filter(eliminado=False).count()
    if activos and not confirmado:
        raise HaceFaltaConfirmar(
            f"«{categoria.name}» tiene {activos} producto(s). Si la borras, dejan de verse en el menú.")
    categoria.deleted_at = timezone.now()
    categoria._history_user = usuario
    categoria.save(update_fields=["deleted_at", "updated_at"])
    return categoria


def restaurar_categoria(categoria, usuario=None):
    categoria.deleted_at = None
    categoria._history_user = usuario
    categoria.save(update_fields=["deleted_at", "updated_at"])
    return categoria


def archivar_menu(menu, usuario=None):
    from .models import Menu

    if not Menu.objects.filter(deleted_at__isnull=True).exclude(pk=menu.pk).exists():
        raise ValidationError("Es tu único menú: crea otro antes de borrar este.")
    menu.deleted_at = timezone.now()
    menu._history_user = usuario
    menu.save(update_fields=["deleted_at", "updated_at"])
    return menu


# ------------------------------------------------------------------ orden

TIPOS_ORDEN = {
    "menus": ("Menu", None),
    "categories": ("Category", "menu"),
    "products": ("Product", "category"),
    "modifier-groups": ("ModifierGroup", None),
}


def reordenar(tipo: str, uuids: list) -> int:
    """Guarda el orden de arrastrar y soltar: la posición es el índice en la lista.

    Todos los elementos deben ser del mismo padre (misma categoría, mismo menú).
    """
    from . import models

    if tipo not in TIPOS_ORDEN:
        raise ValidationError("No se puede ordenar eso.")
    nombre, padre = TIPOS_ORDEN[tipo]
    modelo = getattr(models, nombre)
    uuids = [str(u) for u in uuids][:500]
    objetos = {str(o.uuid): o for o in modelo.objects.filter(uuid__in=uuids)}
    if len(objetos) != len(set(uuids)):
        raise ValidationError("Algunos elementos ya no existen. Recarga la pantalla.")
    if padre and len({getattr(o, f"{padre}_id") for o in objetos.values()}) > 1:
        raise ValidationError("Solo se pueden ordenar elementos del mismo grupo.")
    cambiados = []
    for posicion, u in enumerate(uuids):
        o = objetos[u]
        if o.position != posicion:
            o.position = posicion
            cambiados.append(o)
    with transaction.atomic(using=_db()):
        modelo.objects.bulk_update(cambiados, ["position"])
        subir_version_del_menu(_db())
    return len(cambiados)


# ---------------------------------------------------------- acciones masivas

ACCIONES = ("soldout", "available", "price_percent", "set_prices", "move", "delete", "restore")


def acciones_masivas(accion: str, productos: list, valor=None, usuario=None) -> dict:
    """Varias cosas a la vez sobre varios productos. Devuelve cuántos cambiaron y
    lo necesario para «Deshacer» (los valores anteriores)."""
    from .models import Category, Product

    if accion not in ACCIONES:
        raise ValidationError("Acción desconocida.")
    cambiados, deshacer = [], []
    ahora = timezone.now()

    if accion in ("soldout", "available"):
        quiere = accion == "available"
        sin_precio = [p.name for p in productos if quiere and p.price is None]
        if sin_precio:
            raise ValidationError(f"Sin precio no se pueden activar: {', '.join(sin_precio[:5])}.")
        for p in productos:
            if p.is_available != quiere:
                deshacer.append({"id": str(p.uuid), "available": p.is_available})
                p.is_available = quiere
                p.updated_at = ahora
                cambiados.append(p)
        campos = ["is_available", "updated_at"]

    elif accion == "price_percent":
        try:
            porcentaje = Decimal(str(valor))
        except Exception:
            raise ValidationError("Escribe el porcentaje, por ejemplo 5 o -10.")
        if not Decimal("-90") <= porcentaje <= Decimal("300"):
            raise ValidationError("El porcentaje debe estar entre -90 % y 300 %.")
        for p in productos:
            if p.price is None:
                continue
            nuevo = redondear_a(p.price * (1 + porcentaje / 100), 100)
            if nuevo != p.price:
                deshacer.append({"id": str(p.uuid), "price": int(p.price)})
                p.price = nuevo
                p.updated_at = ahora
                cambiados.append(p)
        campos = ["price", "updated_at"]

    elif accion == "set_prices":  # «Deshacer» de un cambio de precios
        precios = {str(i["id"]): a_pesos(i.get("price")) for i in (valor or []) if isinstance(i, dict)}
        for p in productos:
            nuevo = precios.get(str(p.uuid))
            if nuevo is not None and nuevo != p.price:
                deshacer.append({"id": str(p.uuid), "price": int(p.price) if p.price is not None else None})
                p.price = nuevo
                p.updated_at = ahora
                cambiados.append(p)
        campos = ["price", "updated_at"]

    elif accion == "move":
        destino = Category.objects.filter(uuid=valor, deleted_at__isnull=True).first()
        if destino is None:
            raise ValidationError("Elige la categoría a la que los quieres mover.")
        ocupadas = set(Product.objects.filter(category=destino).values_list("key", flat=True))
        choques = [p.name for p in productos if p.category_id != destino.pk and p.key in ocupadas]
        if choques:
            raise ValidationError(f"En «{destino.name}» ya hay productos con la misma clave: {', '.join(choques[:5])}.")
        posicion = siguiente_posicion(Product.objects.filter(category=destino))
        for p in productos:
            if p.category_id != destino.pk:
                deshacer.append({"id": str(p.uuid), "category": str(p.category.uuid)})
                p.category = destino
                p.position = posicion
                posicion += 1
                p.updated_at = ahora
                cambiados.append(p)
        campos = ["category", "position", "updated_at"]

    else:  # delete / restore
        borrar = accion == "delete"
        for p in productos:
            if p.eliminado != borrar:
                deshacer.append({"id": str(p.uuid), "deleted": p.eliminado})
                p.eliminado = borrar
                p.is_available = (not borrar) and p.price is not None
                p.updated_at = ahora
                cambiados.append(p)
        campos = ["eliminado", "is_available", "updated_at"]

    if cambiados:
        with transaction.atomic(using=_db()):
            bulk_update_with_history(cambiados, Product, campos, default_user=usuario, default_date=ahora)
            if usuario is not None:
                # El historial masivo no pasa por la señal que guarda el nombre del autor.
                Product.history.filter(history_date=ahora, history_user_id=usuario.pk).update(
                    history_user_name=(usuario.get_full_name() or usuario.username)[:150])
            subir_version_del_menu(_db())
    return {"changed": len(cambiados), "undo": deshacer}


# ---------------------------------------------------- tamaños y adiciones


def guardar_variantes(producto, variantes: list) -> None:
    """Reemplaza los tamaños del producto con la lista que manda el editor.

    Cada ítem: {"id"?: uuid, "name", "price"}. Los que traen id se actualizan
    (y conservan su clave); los nuevos se crean; los que ya no vienen se borran.
    """
    from .models import ProductVariant

    existentes = {str(v.uuid): v for v in producto.variants.all()}
    vistos = set()
    with transaction.atomic(using=_db()):
        for posicion, item in enumerate(variantes[:30]):
            nombre = str(item.get("name") or "").strip()[:60]
            precio = a_pesos(item.get("price"))
            if not nombre or precio is None or precio < 0:
                raise ValidationError("Cada tamaño necesita nombre y precio.")
            v = existentes.get(str(item.get("id") or ""))
            if v is None:
                v = ProductVariant(product=producto)
            else:
                vistos.add(str(v.uuid))
            v.name, v.price, v.position = nombre, precio, posicion
            v.save()
        for u, v in existentes.items():
            if u not in vistos:
                v.delete()


def guardar_grupos_del_producto(producto, uuids: list) -> None:
    """Qué grupos de adiciones tiene el producto, en ese orden."""
    from .models import ModifierGroup, ProductModifierGroup

    grupos = {str(g.uuid): g for g in ModifierGroup.objects.filter(uuid__in=[str(u) for u in uuids])}
    with transaction.atomic(using=_db()):
        producto.modifier_links.all().delete()
        for posicion, u in enumerate(uuids[:20]):
            g = grupos.get(str(u))
            if g is not None:
                ProductModifierGroup.objects.create(product=producto, group=g, position=posicion)


def guardar_opciones_del_grupo(grupo, opciones: list) -> None:
    """Reemplaza las opciones de un grupo: [{"id"?, "name", "price"}]."""
    from .models import ModifierOption

    existentes = {str(o.uuid): o for o in grupo.options.all()}
    vistos = set()
    with transaction.atomic(using=_db()):
        for posicion, item in enumerate(opciones[:40]):
            nombre = str(item.get("name") or "").strip()[:60]
            precio = a_pesos(item.get("price")) or Decimal("0")
            if not nombre or precio < 0:
                raise ValidationError("Cada opción necesita nombre y un precio extra de 0 o más.")
            o = existentes.get(str(item.get("id") or ""))
            if o is None:
                o = ModifierOption(group=grupo)
            else:
                vistos.add(str(o.uuid))
            o.name, o.price_delta, o.position = nombre, precio, posicion
            o.save()
        for u, o in existentes.items():
            if u not in vistos:
                o.delete()
