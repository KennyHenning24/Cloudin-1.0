"""/panel/design-system/: la guía viva del sistema de diseño (solo con DEBUG=True).

Muestra los tokens tal como están en static/css/cloudin.css (se leen del archivo:
nunca se desincroniza), la relación de contraste de cada par importante en los
dos temas, y todos los componentes con sus estados.
"""

import base64
import re
from pathlib import Path

from django.conf import settings
from django.http import Http404
from django.shortcuts import render

from .iconos import ICONOS

CSS = Path(settings.BASE_DIR) / "static" / "css" / "cloudin.css"

# (qué es, texto, fondo) — deben pasar 4,5:1 (texto normal) o 3:1 (texto grande / controles)
PARES = [
    ("Texto principal sobre el fondo", "text", "bg", 4.5),
    ("Texto principal sobre tarjeta", "text", "surface", 4.5),
    ("Texto secundario sobre tarjeta", "text-2", "surface", 4.5),
    ("Texto suave sobre tarjeta", "text-3", "surface", 4.5),
    ("Texto suave sobre el fondo", "text-3", "bg", 4.5),
    ("Enlace naranja sobre tarjeta", "brand-text", "surface", 4.5),
    ("Texto de «Disponible» sobre su fondo", "ok-text", "ok-soft", 4.5),
    ("Texto de «Agotado» sobre su fondo", "danger-text", "danger-soft", 4.5),
    ("Texto de alerta sobre su fondo", "warn-text", "warn-soft", 4.5),
    ("Texto de información sobre su fondo", "info-text", "info-soft", 4.5),
    ("Anillo de foco sobre tarjeta", "focus", "surface", 3.0),
]
FIJOS = [
    ("Botón naranja: texto ink sobre #F77A27", "#13151C", "#F77A27", 4.5),
    ("Botón naranja al pasar el mouse: ink sobre #E36225", "#13151C", "#E36225", 4.5),
    ("(No usar) blanco sobre #F77A27", "#FFFFFF", "#F77A27", 4.5),
    ("Navegación: nieve sobre ink", "#E9ECF3", "#13151C", 4.5),
    ("Navegación activa: naranja sobre ink", "#F77A27", "#13151C", 4.5),
]


def _bloque(css: str, selector: str) -> dict:
    inicio = css.index(selector + "{") + len(selector) + 1
    cuerpo = css[inicio:css.index("}", inicio)]
    return dict(re.findall(r"--([\w-]+):\s*([^;]+);", cuerpo))


def tokens() -> dict:
    css = CSS.read_text(encoding="utf-8")
    return {
        "marca": _bloque(css, ":root"),
        "claro": _bloque(css, ':root,[data-theme="claro"]'),
        "oscuro": _bloque(css, '[data-theme="oscuro"]'),
    }


def _rgb(color: str):
    color = color.strip()
    if color.startswith("#") and len(color) == 7:
        return tuple(int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)), 1.0
    m = re.match(r"rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?\)", color)
    if m:
        return tuple(float(m.group(i)) / 255 for i in (1, 2, 3)), float(m.group(4) or 1)
    return None, 1.0


def _mezclar(color: str, fondo: str) -> str:
    """Un color con transparencia, sobre su fondo (para medir el contraste real)."""
    (c, a), (f, _) = _rgb(color), _rgb(fondo)
    if c is None or f is None:
        return color
    return "#" + "".join(f"{round((a * x + (1 - a) * y) * 255):02X}" for x, y in zip(c, f, strict=True))


def contraste(texto: str, fondo: str) -> float:
    def lum(hex_color):
        valores = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        valores = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in valores]
        return 0.2126 * valores[0] + 0.7152 * valores[1] + 0.0722 * valores[2]

    a, b = sorted((lum(texto), lum(fondo)), reverse=True)
    return round((a + 0.05) / (b + 0.05), 2)


def tabla_de_contraste(t: dict) -> list:
    filas = []
    for nombre, texto, fondo, minimo in PARES:
        for tema in ("claro", "oscuro"):
            valores = t[tema]
            base = valores.get("surface", "#FFFFFF")
            color_fondo = _mezclar(valores[fondo], base) if fondo in valores else base
            color_texto = _mezclar(valores[texto], color_fondo)
            r = contraste(color_texto, color_fondo)
            filas.append({"nombre": nombre, "tema": tema, "texto": color_texto, "fondo": color_fondo,
                          "ratio": r, "minimo": minimo, "pasa": r >= minimo})
    for nombre, texto, fondo, minimo in FIJOS:
        r = contraste(texto, fondo)
        filas.append({"nombre": nombre, "tema": "los dos", "texto": texto, "fondo": fondo, "ratio": r,
                      "minimo": minimo, "pasa": r >= minimo})
    return filas


def pagina(request):
    if not settings.DEBUG:
        raise Http404
    from apps.dining.qr import png

    t = tokens()
    return render(request, "panel/design_system.html", {
        "t": t,
        "contrastes": tabla_de_contraste(t),
        "iconos": sorted(ICONOS),
        "qr": "data:image/png;base64," + base64.b64encode(png("https://cloudin.example/m/restaurante-ejemplo/", 240)).decode(),
        "escala": [12, 14, 16, 20, 24, 32],
        "espacios": [4, 8, 12, 16, 24, 32, 48],
        "productos_demo": _productos_demo(),
    })


def _productos_demo():
    """Productos de mentira (sin base) para ver la fila en todos sus casos."""
    from decimal import Decimal
    from types import SimpleNamespace
    from uuid import uuid4

    class SinVariantes:
        def all(self):
            return []

    class ConVariantes:
        def all(self):
            return [1]

    def p(nombre, precio, disponible=True, destacado=False, foto="", variantes=False):
        return SimpleNamespace(uuid=uuid4(), name=nombre, price=Decimal(precio) if precio is not None else None,
                               is_available=disponible, is_featured=destacado, foto=foto,
                               variants=ConVariantes() if variantes else SinVariantes())

    return [
        p("Hamburguesa clásica", 24000, destacado=True, variantes=True),
        p("Hamburguesa doble con tocineta ahumada, cebolla caramelizada y salsa de la casa", 32000),
        p("Hamburguesa vegetariana", 26000, disponible=False),
        p("Jugo natural", None, disponible=False),
    ]
