"""Valida y normaliza una semilla `cloudin.menu/v1` (sin tocar la base de datos).

Devuelve la semilla en una forma segura y predecible, más una lista de avisos
(cosas que se corrigieron o se ignoraron). Si algo impide importar (esquema,
restaurante, claves repetidas…), lanza `SemillaInvalida` con TODOS los errores
y dónde están, para corregirlos de una vez.
"""

import re
from urllib.parse import urlsplit

from apps.business.models import DIAS, MEDIOS_DE_PAGO, normalizar_telefono
from apps.catalog.models import TAX_CHOICES
from apps.common.keys import es_clave_valida

SCHEMA = "cloudin.menu/v1"
HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
HORA = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
IMPUESTOS = {c for c, _ in TAX_CHOICES}
MAX_PRECIO = 100_000_000


class SemillaInvalida(Exception):
    def __init__(self, errores):
        self.errores = list(errores)
        super().__init__("; ".join(self.errores[:5]))


class _Revisor:
    def __init__(self):
        self.errores, self.avisos = [], []

    def texto(self, valor, donde, largo, obligatorio=False):
        if valor is None or (isinstance(valor, str) and not valor.strip()):
            if obligatorio:
                self.errores.append(f"{donde}: falta.")
            return ""
        if not isinstance(valor, str):
            self.errores.append(f"{donde}: debe ser texto.")
            return ""
        valor = valor.strip()
        if len(valor) > largo:
            self.avisos.append(f"{donde}: tenía más de {largo} caracteres; se recortó.")
        return valor[:largo]

    def clave(self, valor, donde, usadas):
        if not isinstance(valor, str) or not es_clave_valida(valor):
            self.errores.append(f"{donde}: «{valor}» no es una clave válida (kebab-case, máx. 60).")
            return None
        if valor in usadas:
            self.errores.append(f"{donde}: la clave «{valor}» está repetida.")
            return None
        usadas.add(valor)
        return valor

    def precio(self, valor, donde, nulo=True):
        if valor is None and nulo:
            return None
        if isinstance(valor, bool) or not isinstance(valor, (int, float)) or valor != int(valor):
            self.errores.append(f"{donde}: el precio va en pesos enteros (12000), no «{valor}».")
            return None
        if not 0 <= int(valor) <= MAX_PRECIO:
            self.errores.append(f"{donde}: precio fuera de rango.")
            return None
        return int(valor)

    def url(self, valor, donde):
        if not valor:
            return ""
        partes = urlsplit(str(valor).strip())
        if partes.scheme not in ("http", "https") or not partes.netloc:
            self.avisos.append(f"{donde}: «{valor}» no es un enlace http(s); se ignoró.")
            return ""
        return str(valor).strip()[:500]

    def ruta(self, valor, donde):
        if not valor:
            return None
        valor = str(valor).strip().replace("\\", "/")
        if valor.startswith(("http://", "https://")):
            return valor[:500]
        if valor.startswith("/") or ".." in valor.split("/"):
            self.avisos.append(f"{donde}: la ruta «{valor}» debe ser relativa a site/; se ignoró.")
            return None
        return valor[:300]


def validar(datos) -> tuple[dict, list[str]]:
    r = _Revisor()
    if not isinstance(datos, dict):
        raise SemillaInvalida(["La semilla debe ser un objeto JSON."])
    if datos.get("schema") != SCHEMA:
        raise SemillaInvalida([f"schema: debe ser «{SCHEMA}»."])

    b = datos.get("business") if isinstance(datos.get("business"), dict) else {}
    if not b:
        r.errores.append("business: falta.")
    slug = b.get("slug")
    if not isinstance(slug, str) or not es_clave_valida(slug):
        r.errores.append(f"business.slug: «{slug}» no es válido (kebab-case, será la dirección del restaurante).")
    contacto = b.get("contact") if isinstance(b.get("contact"), dict) else {}
    redes = b.get("social") if isinstance(b.get("social"), dict) else {}
    marca = b.get("brand") if isinstance(b.get("brand"), dict) else {}
    dueno = b.get("owner") if isinstance(b.get("owner"), dict) else {}

    def telefono(valor, donde):
        if not valor:
            return ""
        numero = normalizar_telefono(valor)
        if not numero:
            r.avisos.append(f"{donde}: «{valor}» no es un número colombiano válido; se ignoró.")
        return numero

    colores = {}
    for campo in ("primary", "secondary", "background", "text"):
        valor = marca.get(campo)
        if valor and not (isinstance(valor, str) and HEX.match(valor)):
            r.avisos.append(f"business.brand.{campo}: «{valor}» no es un color #RRGGBB; se ignoró.")
            valor = None
        colores[campo] = valor or ""

    horas = []
    for i, h in enumerate(b.get("hours") or []):
        donde = f"business.hours[{i}]"
        if not isinstance(h, dict) or h.get("day") not in DIAS:
            r.errores.append(f"{donde}: «day» debe ser uno de {', '.join(DIAS)}.")
            continue
        if h.get("closed"):
            continue
        abre, cierra = h.get("open"), h.get("close")
        if not (isinstance(abre, str) and HORA.match(abre) and isinstance(cierra, str) and HORA.match(cierra)):
            r.errores.append(f"{donde}: «open» y «close» van en formato HH:MM.")
        elif abre == cierra:
            r.errores.append(f"{donde}: abre y cierra a la misma hora.")
        else:
            horas.append({"day": h["day"], "open": abre, "close": cierra})

    horas.sort(key=lambda h: (DIAS.index(h["day"]), h["open"]))
    servicios = b.get("services") if isinstance(b.get("services"), dict) else {}
    pagos = []
    for m in b.get("payment_methods") or []:
        if m in MEDIOS_DE_PAGO:
            pagos.append(m)
        else:
            r.avisos.append(f"business.payment_methods: «{m}» no es un medio conocido; se ignoró.")

    negocio = {
        "slug": slug,
        "name": r.texto(b.get("name"), "business.name", 120, obligatorio=True),
        "legal_name": r.texto(b.get("legal_name"), "business.legal_name", 160),
        "nit": r.texto(b.get("nit"), "business.nit", 30),
        "tagline": r.texto(b.get("tagline"), "business.tagline", 120),
        "description": r.texto(b.get("description"), "business.description", 2000),
        "logo": r.ruta(b.get("logo"), "business.logo"),
        "cover": r.ruta(b.get("cover"), "business.cover"),
        "brand": colores,
        "whatsapp": telefono(contacto.get("whatsapp"), "business.contact.whatsapp"),
        "phone": telefono(contacto.get("phone"), "business.contact.phone"),
        "email": r.texto(contacto.get("email"), "business.contact.email", 254),
        "address": r.texto(contacto.get("address"), "business.contact.address", 200),
        "city": r.texto(contacto.get("city"), "business.contact.city", 80),
        "maps_url": r.url(contacto.get("maps_url"), "business.contact.maps_url"),
        "instagram": r.url(redes.get("instagram"), "business.social.instagram"),
        "facebook": r.url(redes.get("facebook"), "business.social.facebook"),
        "tiktok": r.url(redes.get("tiktok"), "business.social.tiktok"),
        "hours": horas,
        "services": {k: bool(servicios.get(k)) for k in ("dine_in", "takeaway", "delivery")},
        "payment_methods": pagos,
        "owner": {
            "name": r.texto(dueno.get("name"), "business.owner.name", 150),
            "email": r.texto(dueno.get("email"), "business.owner.email", 254),
            "phone": telefono(dueno.get("phone"), "business.owner.phone"),
        },
    }
    if negocio["owner"]["email"] and "@" not in negocio["owner"]["email"]:
        r.errores.append("business.owner.email: no parece un correo.")

    menus, claves_menu = [], set()
    if not isinstance(datos.get("menus"), list) or not datos["menus"]:
        r.errores.append("menus: debe haber al menos un menú.")
    for mi, m in enumerate(datos.get("menus") or []):
        dm = f"menus[{mi}]"
        if not isinstance(m, dict):
            r.errores.append(f"{dm}: debe ser un objeto.")
            continue
        categorias, claves_cat = [], set()
        for ci, c in enumerate(m.get("categories") or []):
            dc = f"{dm}.categories[{ci}]"
            if not isinstance(c, dict):
                r.errores.append(f"{dc}: debe ser un objeto.")
                continue
            productos, claves_prod = [], set()
            for pi, p in enumerate(c.get("products") or []):
                dp = f"{dc}.products[{pi}]"
                if not isinstance(p, dict):
                    r.errores.append(f"{dp}: debe ser un objeto.")
                    continue
                productos.append(_producto(r, p, dp, claves_prod))
            categorias.append({
                "key": r.clave(c.get("key"), f"{dc}.key", claves_cat),
                "name": r.texto(c.get("name"), f"{dc}.name", 80, obligatorio=True),
                "description": r.texto(c.get("description"), f"{dc}.description", 1000),
                "image": r.ruta(c.get("image"), f"{dc}.image"),
                "products": productos,
            })
        menus.append({
            "key": r.clave(m.get("key"), f"{dm}.key", claves_menu),
            "name": r.texto(m.get("name"), f"{dm}.name", 80, obligatorio=True),
            "description": r.texto(m.get("description"), f"{dm}.description", 1000),
            "categories": categorias,
        })

    mesas = (datos.get("tables") or {}).get("count") if isinstance(datos.get("tables"), dict) else None
    if mesas is not None and (isinstance(mesas, bool) or not isinstance(mesas, int) or not 0 <= mesas <= 200):
        r.errores.append("tables.count: debe ser un número entero de 0 a 200.")
        mesas = None

    meta = datos.get("meta") if isinstance(datos.get("meta"), dict) else {}
    if r.errores:
        raise SemillaInvalida(r.errores)
    return {
        "business": negocio,
        "menus": menus,
        "tables": mesas or 0,
        "meta": {
            "site_url": r.url(meta.get("site_url"), "meta.site_url"),
            "menu_page": r.url(meta.get("menu_page"), "meta.menu_page"),
            "missing": [str(x) for x in (meta.get("missing") or [])][:200],
            "built_with": str(meta.get("built_with") or "")[:40],
        },
    }, r.avisos


def _producto(r: _Revisor, p: dict, dp: str, claves: set) -> dict:
    variantes, claves_var = [], set()
    for vi, v in enumerate(p.get("variants") or []):
        dv = f"{dp}.variants[{vi}]"
        if not isinstance(v, dict):
            r.errores.append(f"{dv}: debe ser un objeto.")
            continue
        variantes.append({"key": r.clave(v.get("key"), f"{dv}.key", claves_var),
                          "name": r.texto(v.get("name"), f"{dv}.name", 60, obligatorio=True),
                          "price": r.precio(v.get("price"), f"{dv}.price", nulo=False)})
    grupos, claves_grupo = [], set()
    for gi, g in enumerate(p.get("modifier_groups") or []):
        dg = f"{dp}.modifier_groups[{gi}]"
        if not isinstance(g, dict):
            r.errores.append(f"{dg}: debe ser un objeto.")
            continue
        opciones, claves_op = [], set()
        for oi, o in enumerate(g.get("options") or []):
            do = f"{dg}.options[{oi}]"
            if not isinstance(o, dict):
                r.errores.append(f"{do}: debe ser un objeto.")
                continue
            opciones.append({"key": r.clave(o.get("key"), f"{do}.key", claves_op),
                             "name": r.texto(o.get("name"), f"{do}.name", 60, obligatorio=True),
                             "price": r.precio(o.get("price", 0), f"{do}.price", nulo=False)})
        minimo, maximo = g.get("min", 0), g.get("max")
        if isinstance(minimo, bool) or not isinstance(minimo, int) or minimo < 0:
            r.errores.append(f"{dg}.min: debe ser un entero de 0 en adelante.")
            minimo = 0
        if maximo is not None and (isinstance(maximo, bool) or not isinstance(maximo, int) or maximo < max(1, minimo)):
            r.errores.append(f"{dg}.max: debe ser vacío o un entero mayor o igual que min (y que 1).")
            maximo = None
        if not opciones:
            r.avisos.append(f"{dg}: el grupo no tiene opciones; se ignoró.")
            continue
        grupos.append({"key": r.clave(g.get("key"), f"{dg}.key", claves_grupo),
                       "name": r.texto(g.get("name"), f"{dg}.name", 60, obligatorio=True),
                       "min": minimo, "max": maximo, "options": opciones})
    etiquetas = []
    for t in p.get("tags") or []:
        if isinstance(t, str) and es_clave_valida(t):
            etiquetas.append(t)
        else:
            r.avisos.append(f"{dp}.tags: «{t}» no es una etiqueta válida; se ignoró.")
    impuesto = p.get("tax")
    if impuesto not in (None, *IMPUESTOS):
        r.avisos.append(f"{dp}.tax: «{impuesto}» no es INC8, IVA19 ni EXENTO; se dejó vacío.")
        impuesto = None
    descripcion = r.texto(p.get("description"), f"{dp}.description", 2000)
    if len(descripcion) > 140:
        r.avisos.append(f"{dp}.description: pasa de 140 caracteres (se ve larga en el menú).")
    return {
        "key": r.clave(p.get("key"), f"{dp}.key", claves),
        "name": r.texto(p.get("name"), f"{dp}.name", 120, obligatorio=True),
        "description": descripcion,
        "price": r.precio(p.get("price"), f"{dp}.price"),
        "image": r.ruta(p.get("image"), f"{dp}.image"),
        "available": p.get("available", True) is not False,
        "featured": bool(p.get("featured")),
        "tags": list(dict.fromkeys(etiquetas)),
        "tax": impuesto or "",
        "variants": variantes,
        "modifier_groups": grupos,
    }
