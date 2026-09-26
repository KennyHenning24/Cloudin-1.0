"""El «formato Cloudin» de la carta: cómo un sitio web le entrega su menú al panel.

El sitio del restaurante publica su carta en un archivo JSON (por defecto
`/cloudin-menu.json`) o la incrusta en la página dentro de
`<script type="application/json" id="cloudin-menu">…</script>`. Cloudin la lee
y crea lo que falte. La especificación completa, con ejemplos, está en
`CONECTAR-MENU-A-CLOUDIN.md` en la carpeta del proyecto.

Reglas de la importación (el panel manda):
  - Lo nuevo se crea: categorías y productos que el panel no tenía.
  - Lo que ya existe **no se pisa**: si en el panel se cambió la descripción, la
    foto o los toppings, se respeta. Solo se completan los campos que estén vacíos.
  - Nada se borra: si el sitio quitó un producto, en el panel sigue (se apaga a mano).
  - Lo que el restaurante eliminó en el panel no vuelve, aunque siga en el sitio.
  - Un producto se reconoce por su `id` del sitio (que en Cloudin es su `key`) o,
    si no lo trae, por el nombre dentro de la misma categoría.

Desde la carta v1 las opciones viven en tablas (ver legacy.py); aquí se siguen
leyendo y escribiendo en la forma vieja para los sitios que la usan.
"""

import ipaddress
import json
import re
import socket
from decimal import Decimal, InvalidOperation
from urllib.parse import urljoin, urlsplit

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction

from .legacy import PREFETCH_LEGACY, guardar_opciones_legacy
from .models import Category, Product
from .opciones import limpiar_grupos

VERSION = 1
MAX_BYTES = 2 * 1024 * 1024
SCRIPT_INCRUSTADO = re.compile(
    r'<script[^>]+id=["\']cloudin-menu["\'][^>]*>(.*?)</script>', re.S | re.I
)
# Un id del sitio se guarda tal cual como clave si es un «slug»; si no, se normaliza.
ID_COMO_CLAVE = re.compile(r"^[-a-zA-Z0-9_]{1,60}$")


def _clave_del_sitio(id_sitio: str) -> str:
    from apps.common.keys import key_from

    if not id_sitio:
        return ""
    return id_sitio if ID_COMO_CLAVE.match(id_sitio) else key_from(id_sitio)


# ------------------------------------------------------------------- leer

def _direccion_permitida(url: str):
    """Evita que el panel se use para leer direcciones internas (SSRF).
    En desarrollo se permite localhost, que es donde vive el sitio de pruebas."""
    partes = urlsplit(url)
    if partes.scheme not in ("http", "https") or not partes.hostname:
        raise ValidationError("La dirección debe empezar por http:// o https://")
    if settings.DEBUG:
        return
    try:
        for info in socket.getaddrinfo(partes.hostname, None):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                raise ValidationError("Esa dirección no es pública.")
    except socket.gaierror:
        raise ValidationError("No se encontró ese sitio. Revisa la dirección.")


def extraer(texto: str) -> dict:
    """Saca el JSON de la carta de un archivo .json o de una página HTML."""
    texto = (texto or "").lstrip("﻿").strip()
    if not texto.startswith("{"):
        encontrado = SCRIPT_INCRUSTADO.search(texto)
        if not encontrado:
            raise ValidationError(
                "No encontré la carta. El sitio debe publicar /cloudin-menu.json o incluir "
                '<script type="application/json" id="cloudin-menu"> en la página.'
            )
        texto = encontrado.group(1).strip()
    try:
        datos = json.loads(texto)
    except ValueError as e:
        raise ValidationError(f"La carta no es un JSON válido ({e.msg}, línea {e.lineno}).")
    if not isinstance(datos, dict) or not isinstance(datos.get("categorias"), list):
        raise ValidationError("A la carta le falta la lista «categorias».")
    return datos


def leer_fuente(url: str) -> dict:
    """Descarga la carta desde el sitio del restaurante."""
    import requests

    _direccion_permitida(url)
    try:
        respuesta = requests.get(url, timeout=10, stream=True,
                                 headers={"User-Agent": "Cloudin-Menu/1", "Accept": "application/json,text/html"})
    except requests.RequestException:
        raise ValidationError("No pude conectarme con el sitio. ¿Está publicado y la dirección es correcta?")
    if respuesta.status_code != 200:
        raise ValidationError(f"El sitio respondió {respuesta.status_code}: no encontré la carta en esa dirección.")
    contenido = respuesta.raw.read(MAX_BYTES + 1, decode_content=True)
    if len(contenido) > MAX_BYTES:
        raise ValidationError("La carta pesa más de 2 MB. Usa enlaces a las fotos, no las fotos dentro del archivo.")
    return extraer(contenido.decode(respuesta.encoding or "utf-8", errors="replace"))


# ------------------------------------------------------------ normalizar

def _precio(valor) -> Decimal:
    try:
        precio = Decimal(str(valor))
    except (InvalidOperation, ValueError, TypeError):
        raise ValidationError(f"Precio inválido: {valor!r}")
    if precio < 0:
        raise ValidationError(f"Precio negativo: {valor!r}")
    return precio.quantize(Decimal("1"))


def normalizar(datos: dict, url_base: str = "") -> list:
    """La carta en una forma segura: [{categoria…, productos: […]}]. Los errores
    de un producto no tumban la importación: se reportan y se sigue."""
    base_imagenes = datos.get("base_imagenes") or url_base
    categorias = []
    for ci, c in enumerate(datos["categorias"][:60]):
        if not isinstance(c, dict) or not str(c.get("nombre") or "").strip():
            continue
        productos, errores = [], []
        for p in (c.get("productos") or [])[:300]:
            if not isinstance(p, dict):
                continue
            nombre = str(p.get("nombre") or "").strip()[:120]
            if not nombre:
                continue
            try:
                precio = _precio(p.get("precio"))
                opciones = limpiar_grupos(p.get("opciones"))
            except ValidationError as e:
                errores.append(f"{nombre}: {e.messages[0]}")
                continue
            imagen = str(p.get("imagen") or "").strip()
            if imagen and not imagen.startswith(("http://", "https://")):
                imagen = urljoin(base_imagenes, imagen) if base_imagenes else ""
            productos.append({
                "id": str(p.get("id") or "").strip()[:120],
                "nombre": nombre,
                "precio": precio,
                "descripcion": str(p.get("descripcion") or "").strip()[:2000],
                "imagen": imagen[:500],
                "disponible": p.get("disponible", True) is not False,
                "permite_observacion": p.get("permite_observacion", True) is not False,
                "opciones": opciones,
            })
        secciones = c.get("secciones") if isinstance(c.get("secciones"), list) else []
        categorias.append({
            "id": str(c.get("id") or "").strip()[:120],
            "nombre": str(c["nombre"]).strip()[:80],
            "orden": c.get("orden", ci) if isinstance(c.get("orden", ci), int) else ci,
            # Para sitios con varias cartas (Almuerzo, Noche, Bebidas): en cuáles aparece.
            "secciones": [str(s).strip()[:40] for s in secciones if str(s).strip()][:10],
            "productos": productos,
            "errores": errores,
        })
    return categorias


# ----------------------------------------------------------------- importar

def _buscar_categoria(c):
    clave = _clave_del_sitio(c["id"])
    if clave:
        encontrada = Category.objects.filter(key=clave).first()
        if encontrada:
            return encontrada
    return Category.objects.filter(name__iexact=c["nombre"], deleted_at__isnull=True).first()


def _buscar_producto(p, categoria):
    clave = _clave_del_sitio(p["id"])
    if clave:
        encontrado = Product.objects.filter(key=clave).first()
        if encontrado:
            return encontrado
    if categoria is None:
        return None
    return Product.objects.filter(category=categoria, name__iexact=p["nombre"]).first()


def importar(datos: dict, url_base: str = "", aplicar: bool = True) -> dict:
    """Crea lo nuevo y completa lo vacío. Con `aplicar=False` solo cuenta qué haría."""
    categorias = normalizar(datos, url_base)
    resumen = {"categorias_nuevas": 0, "productos_nuevos": 0, "productos_completados": 0,
               "sin_cambios": 0, "eliminados": 0, "errores": [], "nuevos": []}

    with transaction.atomic(using=Category.objects.db):
        for c in categorias:
            resumen["errores"].extend(c["errores"])
            categoria = _buscar_categoria(c)
            if categoria is not None and categoria.deleted_at is not None:
                # El restaurante archivó la categoría: no se revive ni se le agregan platos.
                resumen["eliminados"] += len(c["productos"])
                continue
            if categoria is None:
                resumen["categorias_nuevas"] += 1
                if aplicar:
                    categoria = Category.objects.create(name=c["nombre"], position=c["orden"],
                                                        key=_clave_del_sitio(c["id"]), secciones=c["secciones"])
            elif aplicar:
                cambios = []
                if c["secciones"] and not categoria.secciones:
                    categoria.secciones = c["secciones"]
                    cambios.append("secciones")
                if cambios:
                    categoria.save(update_fields=cambios)

            for pi, p in enumerate(c["productos"]):
                producto = _buscar_producto(p, categoria)
                if producto is not None and producto.eliminado:
                    # El restaurante lo sacó de la carta: no se revive al reimportar.
                    resumen["eliminados"] += 1
                    continue
                if producto is None:
                    resumen["productos_nuevos"] += 1
                    resumen["nuevos"].append(f"{c['nombre']} · {p['nombre']}")
                    if aplicar:
                        nuevo = Product.objects.create(
                            category=categoria, name=p["nombre"], price=p["precio"],
                            description=p["descripcion"], image_url=p["imagen"], position=pi,
                            is_available=p["disponible"],
                            permite_observacion=p["permite_observacion"], key=_clave_del_sitio(p["id"]),
                        )
                        if p["opciones"]:
                            guardar_opciones_legacy(nuevo, p["opciones"])
                    continue
                # Ya existe: el panel manda. Solo se llena lo que esté vacío.
                cambios = []
                if not producto.description and p["descripcion"]:
                    producto.description = p["descripcion"]
                    cambios.append("description")
                if not producto.image_url and not producto.imagen and p["imagen"]:
                    producto.image_url = p["imagen"]
                    cambios.append("image_url")
                opciones_nuevas = not producto.modifier_links.exists() and p["opciones"]
                if opciones_nuevas:
                    cambios.append("opciones")
                if cambios:
                    resumen["productos_completados"] += 1
                    if aplicar:
                        campos = [c for c in cambios if c != "opciones"]
                        if campos:
                            producto.save(update_fields=campos)
                        if opciones_nuevas:
                            guardar_opciones_legacy(producto, p["opciones"])
                else:
                    resumen["sin_cambios"] += 1
        if not aplicar:
            transaction.set_rollback(True, using=Category.objects.db)
    resumen["total_productos"] = sum(len(c["productos"]) for c in categorias)
    resumen["total_categorias"] = len(categorias)
    return resumen


# ----------------------------------------------------------------- exportar

def exportar(restaurante: str, construir_url=None, solo_disponibles: bool = True) -> dict:
    """La carta del panel en el mismo formato: lo que lee el sitio para pintarse."""
    categorias = []
    prefetch = ["products", *(f"products__{r}" for r in PREFETCH_LEGACY)]
    for c in Category.objects.filter(is_active=True, deleted_at__isnull=True).prefetch_related(*prefetch):
        productos = []
        for p in c.products.all():
            if p.eliminado or p.price is None or (solo_disponibles and not p.is_available):
                continue
            foto = p.foto
            if foto and foto.startswith("/") and construir_url:
                foto = construir_url(foto)
            productos.append({
                "id": p.key,
                "cloudin_id": p.id,
                "nombre": p.name,
                "precio": int(p.precio_legacy),
                "descripcion": p.description,
                "imagen": foto,
                "disponible": p.is_available,
                "permite_observacion": p.permite_observacion,
                "opciones": p.opciones or [],
            })
        if productos or not solo_disponibles:
            categorias.append({"id": c.key, "cloudin_id": c.id,
                               "nombre": c.name, "orden": c.position, "secciones": c.secciones or [],
                               "productos": productos})
    return {"cloudin_menu": VERSION, "restaurante": restaurante, "moneda": "COP",
            "categorias": categorias}
