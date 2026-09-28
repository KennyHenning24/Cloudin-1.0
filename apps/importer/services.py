"""Importa una semilla `cloudin.menu/v1` (contrato, sección 8).

Reglas:
- Idempotente por `key`: reimportar actualiza, nunca duplica.
- Merge a 3 vías, campo por campo. `import_snapshot` guarda lo que trajo la
  última importación. Si el valor actual sigue igual a ese, el dueño no lo
  tocó y se actualiza con la semilla nueva. Si es distinto, lo cambió el dueño
  y se respeta (queda en «conservados» del resumen).
- Nunca borra nada, y no revive lo que el dueño borró o archivó.
- Un producto con `price: null` queda NO disponible hasta que el dueño le ponga precio.
- Registra `meta.site_url` como origen permitido y guarda `meta.menu_page`.
- Crea las mesas 1..tables.count que falten, cada una con su token de QR.
- Crea al dueño (si no hay uno) y le envía la invitación por correo.

Con `aplicar=False` (revisar) todo corre dentro de una transacción que se
deshace: el resumen dice qué pasaría, sin cambiar nada y sin subir fotos.
"""

from dataclasses import dataclass, field
from datetime import time
from decimal import Decimal

from django.db import transaction

from apps.business.models import DIAS, OpeningHours, RestaurantSettings
from apps.catalog import images
from apps.catalog.models import Category, Menu, ModifierGroup, ModifierOption, Product, ProductModifierGroup, Tag
from apps.common.keys import unique_key
from apps.dining.qr import asegurar_mesas
from apps.tenants.context import tenant_context
from apps.tenants.models import Tenant, TenantMembership

from .assets import SinFotos, huella
from .semilla import SemillaInvalida, validar

FALTA = object()
NOMBRES_CAMPOS = {
    "name": "nombre", "description": "descripción", "price": "precio", "is_available": "disponible",
    "is_featured": "destacado", "tax_type": "impuesto", "tags": "etiquetas", "position": "orden",
    "min_select": "mínimo", "max_select": "máximo", "price_delta": "precio extra", "hours": "horario",
    "whatsapp": "WhatsApp", "phone": "teléfono", "address": "dirección", "tagline": "frase",
}


@dataclass
class Resumen:
    restaurante: str = ""
    nombre: str = ""
    creado: bool = False
    aplicado: bool = True
    contadores: dict = field(default_factory=dict)
    conservados: list = field(default_factory=list)
    avisos: list = field(default_factory=list)
    fotos: dict = field(default_factory=lambda: {"subidas": 0, "faltantes": []})
    mesas_creadas: int = 0
    invitacion: str = ""
    faltantes_de_la_semilla: list = field(default_factory=list)

    def contar(self, entidad: str, que: str):
        self.contadores.setdefault(entidad, {"creados": 0, "actualizados": 0, "sin_cambios": 0,
                                             "borrados_por_el_dueno": 0})
        self.contadores[entidad][que] += 1

    def como_dict(self) -> dict:
        return {
            "restaurant": self.restaurante, "name": self.nombre, "created": self.creado, "applied": self.aplicado,
            "counts": self.contadores, "kept_owner_changes": self.conservados, "warnings": self.avisos,
            "photos": self.fotos, "tables_created": self.mesas_creadas, "invitation": self.invitacion,
            "missing": self.faltantes_de_la_semilla,
        }


def _normal(valor):
    """Forma comparable: pesos enteros, horas HH:MM, vacío = None."""
    if isinstance(valor, Decimal):
        return int(valor)
    if isinstance(valor, time):
        return valor.strftime("%H:%M")
    if valor == "" or valor == [] or valor == {}:
        return None
    return valor


def _fusionar(obj, nuevos: dict, etiqueta: str, resumen: Resumen) -> bool:
    """Aplica los valores de la semilla respetando lo que cambió el dueño. True si cambió algo."""
    foto = dict(obj.import_snapshot or {})
    cambio = False
    for campo, valor in nuevos.items():
        actual = _normal(getattr(obj, campo))
        nuevo = _normal(valor)
        anterior = foto.get(campo, FALTA)
        if anterior is FALTA:
            # Nunca importado: se llena si el objeto es nuevo o si el campo está vacío.
            puede = obj.pk is None or actual is None
        else:
            puede = actual == anterior  # igual a lo último importado: el dueño no lo tocó
        if actual != nuevo:
            if puede:
                setattr(obj, campo, valor)
                cambio = True
            else:
                resumen.conservados.append(f"{etiqueta} · {NOMBRES_CAMPOS.get(campo, campo)}: "
                                           f"se dejó lo que puso el dueño")
        foto[campo] = nuevo
    if foto != (obj.import_snapshot or {}):
        obj.import_snapshot = foto
        cambio = True
    return cambio


def _guardar(obj, nuevo: bool, cambio: bool, entidad: str, resumen: Resumen):
    if nuevo or cambio:
        obj.save()
    resumen.contar(entidad, "creados" if nuevo else ("actualizados" if cambio else "sin_cambios"))


# ------------------------------------------------------------------ fotos


def _foto(obj, campo_archivo: str, ruta, assets, lado: int, nombre: str, resumen: Resumen, aplicar: bool,
          svg_permitido: bool = False) -> bool:
    """Sube la foto de la semilla si el dueño no puso otra. True si cambió."""
    if not ruta:
        return False
    if ruta.startswith(("http://", "https://")):
        resumen.avisos.append(f"{nombre}: la foto es un enlace externo ({ruta}); súbela en assets/ para que "
                              f"Cloudin la guarde.")
        return False
    datos = assets.leer(ruta)
    if datos is None:
        resumen.fotos["faltantes"].append(ruta)
        return False
    foto = dict(obj.import_snapshot or {})
    firma = huella(datos)
    archivo_actual = getattr(obj, campo_archivo).name or ""
    anterior = foto.get(f"{campo_archivo}_file")
    vacio = not archivo_actual and not getattr(obj, "image_url", "")
    if not vacio and (anterior is None or archivo_actual != anterior):
        return False  # la foto la puso el dueño: se respeta
    if not vacio and foto.get(f"{campo_archivo}_sha") == firma:
        return False  # es la misma foto
    if not aplicar:
        resumen.fotos["subidas"] += 1
        return False
    try:
        if svg_permitido and ruta.lower().endswith(".svg"):
            contenido = images.limpiar_svg(datos, nombre=campo_archivo)
        else:
            contenido = images.a_webp(datos, lado, getattr(obj, "key", "") or campo_archivo)
    except Exception as e:  # una foto dañada no tumba la importación
        resumen.avisos.append(f"{nombre}: la foto {ruta} no se pudo usar ({getattr(e, 'messages', [e])[0]}).")
        return False
    getattr(obj, campo_archivo).save(contenido.name, contenido, save=False)
    foto[f"{campo_archivo}_file"] = getattr(obj, campo_archivo).name
    foto[f"{campo_archivo}_sha"] = firma
    obj.import_snapshot = foto
    resumen.fotos["subidas"] += 1
    return True


# -------------------------------------------------------------- restaurante


def _restaurante(negocio: dict, crear: bool, aplicar: bool, resumen: Resumen):
    tenant = Tenant.objects.filter(slug=negocio["slug"]).first()
    if tenant is not None:
        if not tenant.is_active:
            raise SemillaInvalida([f"El restaurante «{tenant.slug}» está desactivado."])
        return tenant
    if not crear:
        raise SemillaInvalida([f"No existe el restaurante «{negocio['slug']}». Usa --create-tenant para crearlo."])
    resumen.creado = True
    if not aplicar:
        return None
    from apps.tenants.services import aprovisionar, crear_restaurante

    tenant = crear_restaurante(nombre=negocio["name"], slug=negocio["slug"], nit=negocio["nit"],
                               legal_name=negocio["legal_name"], address=negocio["address"],
                               city=negocio["city"], phone=negocio["phone"])
    aprovisionar(tenant)
    return tenant


def _datos_de_control(tenant: Tenant, semilla: dict, resumen: Resumen):
    """Lo que vive en la base de control: datos fiscales vacíos, sitio y orígenes permitidos."""
    negocio, meta = semilla["business"], semilla["meta"]
    campos = []
    for campo in ("nit", "legal_name"):
        if negocio[campo] and not getattr(tenant, campo):
            setattr(tenant, campo, negocio[campo])
            campos.append(campo)
    if meta["site_url"]:
        if not tenant.site_url:
            tenant.site_url = meta["site_url"]
            campos.append("site_url")
        elif meta["site_url"] not in (tenant.allowed_origins or []) and meta["site_url"] != tenant.site_url:
            tenant.allowed_origins = [*(tenant.allowed_origins or []), meta["site_url"]]
            campos.append("allowed_origins")
    if meta["menu_page"]:
        if not tenant.menu_page:
            tenant.menu_page = meta["menu_page"]
            campos.append("menu_page")
        elif tenant.menu_page != meta["menu_page"]:
            resumen.avisos.append(f"La página del menú ya era {tenant.menu_page}; no se cambió a {meta['menu_page']}.")
    if campos:
        tenant.save(update_fields=campos)


def _dueno(tenant: Tenant, negocio: dict, invitar: bool, resumen: Resumen):
    datos = negocio["owner"]
    if not datos["email"]:
        resumen.avisos.append("La semilla no trae el correo del dueño: no se envió invitación.")
        return
    miembros = TenantMembership.objects.filter(tenant=tenant).select_related("user")
    if any(m.role == TenantMembership.ROLE_OWNER for m in miembros):
        resumen.invitacion = "Ya tenía dueño: no se envió otra invitación."
        return
    if any(m.user.email.lower() == datos["email"].lower() for m in miembros):
        resumen.invitacion = f"{datos['email']} ya tiene cuenta en este restaurante."
        return
    from django.contrib.auth.models import User

    from apps.tenants.invitations import enviar_invitacion
    from apps.tenants.services import crear_usuario, nombre_usuario_completo

    usuario = unique_key("dueno", lambda k: User.objects.filter(username=nombre_usuario_completo(tenant, k)).exists())
    user, _ = crear_usuario(tenant, usuario, rol=TenantMembership.ROLE_OWNER, nombre=datos["name"],
                            correo=datos["email"])
    if invitar:
        enviar_invitacion(user, tenant)
        resumen.invitacion = f"Invitación enviada a {datos['email']} (usuario {user.username})."
    else:
        resumen.invitacion = f"Dueño creado ({user.username}) sin enviar la invitación."


# ----------------------------------------------------------------- ajustes


def _ajustes(negocio: dict, assets, aplicar: bool, resumen: Resumen):
    ajustes = RestaurantSettings.load()
    marca = negocio["brand"]
    cambio = _fusionar(ajustes, {
        "tagline": negocio["tagline"], "description": negocio["description"],
        "color_primary": marca["primary"], "color_secondary": marca["secondary"],
        "color_background": marca["background"], "color_text": marca["text"],
        "whatsapp": negocio["whatsapp"], "phone": negocio["phone"], "email": negocio["email"],
        "address": negocio["address"], "city": negocio["city"], "maps_url": negocio["maps_url"],
        "instagram": negocio["instagram"], "facebook": negocio["facebook"], "tiktok": negocio["tiktok"],
        "services": negocio["services"], "payment_methods": negocio["payment_methods"],
    }, "Datos del negocio", resumen)
    cambio |= _foto(ajustes, "logo", negocio["logo"], assets, images.LADO_LOGO, "Logo", resumen, aplicar,
                    svg_permitido=True)
    cambio |= _foto(ajustes, "cover", negocio["cover"], assets, images.LADO_PORTADA, "Portada", resumen, aplicar)
    for campo in ("tagline", "description", "email", "address", "city", "maps_url", "instagram", "facebook",
                  "tiktok", "color_primary", "color_secondary", "color_background", "color_text", "whatsapp",
                  "phone"):
        if getattr(ajustes, campo) is None:
            setattr(ajustes, campo, "")
    if cambio:
        ajustes.save()

    # El horario se trata como un solo valor: si el dueño lo cambió, se respeta entero.
    actual = [{"day": DIAS[h.day], "open": h.opens.strftime("%H:%M"), "close": h.closes.strftime("%H:%M")}
              for h in OpeningHours.objects.order_by("day", "opens")]
    foto = dict(ajustes.import_snapshot or {})
    anterior = foto.get("hours", FALTA)
    if negocio["hours"] != actual:
        if (anterior is FALTA and not actual) or anterior == actual:
            OpeningHours.objects.all().delete()
            for h in negocio["hours"]:
                OpeningHours.objects.create(day=DIAS.index(h["day"]), opens=h["open"], closes=h["close"])
        else:
            resumen.conservados.append("Horario: se dejó el que puso el dueño")
    foto["hours"] = negocio["hours"]
    RestaurantSettings.objects.filter(pk=ajustes.pk).update(import_snapshot=foto)


# -------------------------------------------------------------------- carta


def _etiquetas(claves: list) -> list:
    etiquetas = []
    for clave in claves:
        tag = Tag.objects.filter(key=clave).first()
        if tag is None:
            tag = Tag.objects.create(key=clave, name=clave.replace("-", " ").capitalize())
        etiquetas.append(tag)
    return etiquetas


def _grupos(producto, grupos: list, resumen: Resumen):
    """Los grupos de la semilla viven dentro de cada producto. En Cloudin son
    compartibles: se reconocen por la clave de la semilla dentro del producto."""
    enlaces = {(e.group.import_snapshot or {}).get("seed_key"): e
               for e in producto.modifier_links.select_related("group")}
    for posicion, g in enumerate(grupos):
        enlace = enlaces.get(g["key"])
        nuevo = enlace is None
        grupo = ModifierGroup() if nuevo else enlace.group
        if nuevo:
            grupo.key = unique_key(f"{producto.key}-{g['key']}", lambda k: ModifierGroup.objects.filter(key=k).exists())
            grupo.import_snapshot = {"seed_key": g["key"]}
        cambio = _fusionar(grupo, {"name": g["name"], "min_select": g["min"], "max_select": g["max"]},
                           f"{producto.name} › {g['name']}", resumen)
        _guardar(grupo, nuevo, cambio, "grupos", resumen)
        if nuevo:
            ProductModifierGroup.objects.create(product=producto, group=grupo, position=posicion)
        existentes = {o.key: o for o in grupo.options.all()}
        for j, o in enumerate(g["options"]):
            opcion = existentes.get(o["key"])
            nueva = opcion is None
            if nueva:
                opcion = ModifierOption(group=grupo, key=o["key"])
            cambio = _fusionar(opcion, {"name": o["name"], "price_delta": Decimal(o["price"]), "position": j},
                               f"{producto.name} › {g['name']} › {o['name']}", resumen)
            _guardar(opcion, nueva, cambio, "opciones", resumen)


def _catalogo(semilla: dict, assets, aplicar: bool, resumen: Resumen):
    for mi, m in enumerate(semilla["menus"]):
        menu = Menu.objects.filter(key=m["key"]).first()
        if menu is not None and menu.deleted_at:
            resumen.contar("menus", "borrados_por_el_dueno")
            continue
        nuevo = menu is None
        menu = menu or Menu(key=m["key"])
        cambio = _fusionar(menu, {"name": m["name"], "description": m["description"], "position": mi},
                           m["name"], resumen)
        _guardar(menu, nuevo, cambio, "menus", resumen)

        for ci, c in enumerate(m["categories"]):
            categoria = Category.objects.filter(menu=menu, key=c["key"]).first()
            if categoria is not None and categoria.deleted_at:
                resumen.contar("categorias", "borrados_por_el_dueno")
                continue
            nueva = categoria is None
            categoria = categoria or Category(menu=menu, key=c["key"])
            cambio = _fusionar(categoria, {"name": c["name"], "description": c["description"], "position": ci},
                               c["name"], resumen)
            cambio |= _foto(categoria, "image", c["image"], assets, images.LADO_PRODUCTO, c["name"], resumen,
                            aplicar)
            _guardar(categoria, nueva, cambio, "categorias", resumen)

            for pi, p in enumerate(c["products"]):
                _producto(menu, categoria, p, pi, assets, aplicar, resumen)


def _producto(menu, categoria, p: dict, posicion: int, assets, aplicar: bool, resumen: Resumen):
    # Por clave dentro del menú: si el dueño lo movió de categoría, se sigue reconociendo.
    candidatos = list(Product.objects.filter(category__menu=menu, key=p["key"]))
    producto = next((x for x in candidatos if x.category_id == categoria.pk), candidatos[0] if candidatos else None)
    if producto is not None and producto.eliminado:
        resumen.contar("productos", "borrados_por_el_dueno")
        return
    nuevo = producto is None
    producto = producto or Product(category=categoria, key=p["key"])
    precio = Decimal(p["price"]) if p["price"] is not None else None
    cambio = _fusionar(producto, {
        "name": p["name"], "description": p["description"], "price": precio,
        "is_available": p["available"] and precio is not None, "is_featured": p["featured"],
        "tax_type": p["tax"], "position": posicion,
    }, p["name"], resumen)
    for campo in ("description", "tax_type"):
        if getattr(producto, campo) is None:
            setattr(producto, campo, "")
    if producto.price is None and producto.is_available:
        producto.is_available = False
        cambio = True
    cambio |= _foto(producto, "imagen", p["image"], assets, images.LADO_PRODUCTO, p["name"], resumen, aplicar)
    _guardar(producto, nuevo, cambio, "productos", resumen)
    if precio is None:
        resumen.avisos.append(f"«{p['name']}» no tiene precio: quedó no disponible hasta que el dueño lo complete.")

    # Etiquetas: una lista que se trata como un solo valor.
    actuales = sorted(producto.tags.values_list("key", flat=True))
    foto = dict(producto.import_snapshot or {})
    anterior = foto.get("tags", FALTA)
    deseadas = sorted(p["tags"])
    if deseadas != actuales:
        if nuevo or anterior == actuales or (anterior is FALTA and not actuales):
            producto.tags.set(_etiquetas(p["tags"]))
        else:
            resumen.conservados.append(f"{p['name']} · etiquetas: se dejaron las que puso el dueño")
    foto["tags"] = deseadas
    Product.objects.filter(pk=producto.pk).update(import_snapshot=foto)

    existentes = {v.key: v for v in producto.variants.all()}
    for vi, v in enumerate(p["variants"]):
        variante = existentes.get(v["key"])
        nueva = variante is None
        if nueva:
            variante = producto.variants.model(product=producto, key=v["key"])
        cambio = _fusionar(variante, {"name": v["name"], "price": Decimal(v["price"]), "position": vi},
                           f"{p['name']} › {v['name']}", resumen)
        _guardar(variante, nueva, cambio, "variantes", resumen)
    _grupos(producto, p["modifier_groups"], resumen)


# ---------------------------------------------------------------- entrada


def importar_semilla(datos: dict, assets=None, crear_restaurante: bool = False, aplicar: bool = True,
                     invitar: bool = True) -> Resumen:
    """Importa la semilla. Lanza SemillaInvalida si no se puede (con todos los errores)."""
    semilla, avisos = validar(datos)
    assets = assets or SinFotos()
    negocio = semilla["business"]
    resumen = Resumen(restaurante=negocio["slug"], nombre=negocio["name"], aplicado=aplicar, avisos=list(avisos),
                      faltantes_de_la_semilla=semilla["meta"]["missing"])

    tenant = _restaurante(negocio, crear_restaurante, aplicar, resumen)
    if tenant is None:  # revisión de un restaurante que todavía no existe: todo sería nuevo
        for m in semilla["menus"]:
            resumen.contar("menus", "creados")
            for c in m["categories"]:
                resumen.contar("categorias", "creados")
                for _ in c["products"]:
                    resumen.contar("productos", "creados")
        resumen.mesas_creadas = semilla["tables"]
        return resumen

    with tenant_context(tenant):
        with transaction.atomic(using=tenant.db_alias):
            _ajustes(negocio, assets, aplicar, resumen)
            _catalogo(semilla, assets, aplicar, resumen)
            if semilla["tables"]:
                resumen.mesas_creadas = asegurar_mesas(semilla["tables"])
            if not aplicar:
                transaction.set_rollback(True, using=tenant.db_alias)
    if aplicar:
        _datos_de_control(tenant, semilla, resumen)
        _dueno(tenant, negocio, invitar, resumen)
    resumen.avisos = list(dict.fromkeys(resumen.avisos))
    return resumen
