"""Arma el JSON `cloudin.menu/v1` que leen los menús digitales.

Tiene la misma forma que `menu.seed.json` del contrato, con dos diferencias:
cada entidad trae además su `id` (UUID) y no salen los datos privados (`owner`,
`nit`, `legal_name`). En la raíz se agrega `tags` (clave → nombre, para que el
runtime pinte el nombre de cada etiqueta) y `meta.version` (el ETag).
"""

from apps.business.models import DIAS, MEDIOS_DE_PAGO, servicios_de
from apps.common.money import a_pesos

SCHEMA = "cloudin.menu/v1"


def _pesos(valor):
    numero = a_pesos(valor)
    return int(numero) if numero is not None else None


def _url(campo, construir_url):
    if not campo:
        return None
    url = campo.url
    return construir_url(url) if construir_url and url.startswith("/") else url


def _hora(t):
    return t.strftime("%H:%M")


def _pagos_en_texto(claves) -> str | None:
    """«Efectivo, Nequi y Tarjeta»: los medios de pago de Personalizar, listos para mostrar."""
    nombres = [nombre for clave, nombre in MEDIOS_DE_PAGO.items() if clave in (claves or [])]
    if len(nombres) > 1:
        return ", ".join(nombres[:-1]) + " y " + nombres[-1]
    return nombres[0] if nombres else None


def horario_del_contrato(tramos) -> list:
    """[{"day": "mon", "closed": true}, {"day": "tue", "open": "12:00", "close": "21:00"}, …]

    Sin ningún tramo se devuelve [] (horario desconocido, no "cerrado toda la semana")."""
    if not tramos:
        return []
    por_dia = {d: [] for d in range(7)}
    for t in tramos:
        por_dia[t.day].append(t)
    salida = []
    for dia in range(7):
        if not por_dia[dia]:
            salida.append({"day": DIAS[dia], "closed": True})
        for t in por_dia[dia]:
            salida.append({"day": DIAS[dia], "open": _hora(t.opens), "close": _hora(t.closes)})
    return salida


def negocio(tenant, ajustes, tramos, construir_url=None) -> dict:
    return {
        "slug": tenant.slug,
        "name": tenant.name,
        "tagline": ajustes.tagline or None,
        "description": ajustes.description or None,
        "welcome_message": ajustes.welcome_message or None,
        "logo": _url(ajustes.logo, construir_url),
        "cover": _url(ajustes.cover, construir_url),
        # Los colores son del diseño de cada menú, no del panel: van vacíos (el campo sigue
        # porque hay menús que lo leen, y con null usan los suyos).
        "brand": {"primary": None, "secondary": None, "background": None, "text": None},
        "contact": {
            "whatsapp": ajustes.whatsapp or None,
            "phone": ajustes.phone or None,
            "email": ajustes.email or None,
            "address": ajustes.address or None,
            "city": ajustes.city or None,
            "maps_url": ajustes.maps_url or None,
        },
        "social": {
            "instagram": ajustes.instagram or None,
            "facebook": ajustes.facebook or None,
            "tiktok": ajustes.tiktok or None,
        },
        "hours": horario_del_contrato(tramos),
        # dine_in queda siempre en true (en la mesa se pide con el QR o el mesero), por los
        # menús que ya lo leen; takeaway y delivery son los interruptores de Personalizar.
        "services": {"dine_in": True, **servicios_de(ajustes)},
        "payment_methods": list(ajustes.payment_methods or []),
        "payment_methods_text": _pagos_en_texto(ajustes.payment_methods),
    }


def producto(p, construir_url=None) -> dict:
    foto = p.foto
    if foto and foto.startswith("/") and construir_url:
        foto = construir_url(foto)
    return {
        "id": str(p.uuid),
        "key": p.key,
        "name": p.name,
        "description": p.description or None,
        "price": _pesos(p.price),
        "image": foto or None,
        "available": p.is_available,
        "featured": p.is_featured,
        "tags": [t.key for t in p.tags.all()],
        "tax": p.tax_type or None,
        "variants": [{"id": str(v.uuid), "key": v.key, "name": v.name, "price": _pesos(v.price)}
                     for v in p.variants.all()],
        "modifier_groups": [
            {
                # Un grupo importado conserva la clave que tenía en la semilla (dentro del producto).
                "id": str(enlace.group.uuid), "key": (enlace.group.import_snapshot or {}).get("seed_key")
                or enlace.group.key, "name": enlace.group.name,
                "min": enlace.group.min_select, "max": enlace.group.max_select,
                "options": [{"id": str(o.uuid), "key": o.key, "name": o.name, "price": _pesos(o.price_delta)}
                            for o in enlace.group.options.all()],
            }
            for enlace in p.modifier_links.all()
        ],
    }


def categoria(c, construir_url=None) -> dict:
    return {
        "id": str(c.uuid),
        "key": c.key,
        "name": c.name,
        "description": c.description or None,
        "image": _url(c.image, construir_url),
        "products": [producto(p, construir_url) for p in c.products.all()],
    }


def menu_publico(tenant, menus, ajustes, tramos, etiquetas, construir_url=None) -> dict:
    salida_menus = []
    for m in menus:
        categorias = [categoria(c, construir_url) for c in m.categories.all()]
        salida_menus.append({
            "id": str(m.uuid),
            "key": m.key,
            "name": m.name,
            "description": m.description or None,
            "availability": {
                "days": [DIAS[d] for d in (m.available_days or []) if isinstance(d, int) and 0 <= d <= 6],
                "from": _hora(m.available_from) if m.available_from else None,
                "to": _hora(m.available_to) if m.available_to else None,
            },
            "categories": [c for c in categorias if c["products"]],
        })
    return {
        "schema": SCHEMA,
        "business": negocio(tenant, ajustes, tramos, construir_url),
        "menus": salida_menus,
        "tags": [{"key": t.key, "name": t.name} for t in etiquetas],
        "meta": {"version": ajustes.menu_version},
    }
