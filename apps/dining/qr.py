"""Códigos QR del menú y de cada mesa (PNG, SVG y un PDF con todas las mesas).

Cloudin no tiene un menú propio: el QR lleva a la página del menú del restaurante
(`Tenant.menu_page`, la que llega con la importación). Para una mesa:
1. `menu_page` + `?mesa=<token>` (el runtime lo lee y muestra «Mesa 5»).
2. Si el restaurante pide por QR desde su sitio (`site_url`), el enlace de siempre
   (`mesa.html?m=<token>`): así no hay que reimprimir.
3. Si todavía no hay página publicada, no hay QR (enlace vacío).

El token (no el número) va en el QR: así nadie puede pedir para otra mesa
cambiando un número en la dirección.
"""

import io
from urllib.parse import urlsplit, urlunsplit

import qrcode
import qrcode.image.svg
from PIL import Image, ImageDraw, ImageFont

from .models import Table


def con_parametro(url: str, clave: str, valor: str) -> str:
    partes = urlsplit(url)
    consulta = f"{partes.query}&" if partes.query else ""
    return urlunsplit(partes._replace(query=f"{consulta}{clave}={valor}"))


def enlace_del_menu(tenant) -> str:
    """La página del menú del restaurante, o "" si todavía no está publicada."""
    return tenant.menu_page or ""


def enlace_de_mesa(tenant, mesa) -> str:
    if tenant.menu_page:
        return con_parametro(tenant.menu_page, "mesa", mesa.token)
    if tenant.site_url:
        return tenant.qr_link(mesa.token)
    return ""


def asegurar_mesas(cantidad: int) -> int:
    """Deja las mesas 1..cantidad activas (crea las que falten). Nunca borra ninguna."""
    existentes = {m.number: m for m in Table.objects.filter(number__lte=cantidad)}
    creadas = 0
    for numero in range(1, cantidad + 1):
        mesa = existentes.get(numero)
        if mesa is None:
            Table.objects.create(number=numero)
            creadas += 1
        elif not mesa.is_active:
            mesa.is_active = True
            mesa.save(update_fields=["is_active"])
    return creadas


def _qr(texto: str) -> qrcode.QRCode:
    codigo = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=2)
    codigo.add_data(texto)
    codigo.make(fit=True)
    return codigo


def png(texto: str, lado: int = 1000) -> bytes:
    imagen = _qr(texto).make_image(fill_color="#13151C", back_color="white").convert("RGB")
    imagen = imagen.resize((lado, lado), Image.Resampling.NEAREST)
    salida = io.BytesIO()
    imagen.save(salida, "PNG", optimize=True)
    return salida.getvalue()


def svg(texto: str) -> bytes:
    imagen = _qr(texto).make_image(image_factory=qrcode.image.svg.SvgPathImage)
    salida = io.BytesIO()
    imagen.save(salida)
    return salida.getvalue()


def _fuente(tamano: int):
    try:
        return ImageFont.load_default(size=tamano)
    except TypeError:  # Pillow viejo, sin FreeType
        return ImageFont.load_default()


def pdf_de_mesas(tenant, mesas: list) -> bytes:
    """Un PDF tamaño carta con 4 QR por hoja (2 × 2), listos para recortar."""
    dpi = 150
    ancho, alto = int(8.5 * dpi), int(11 * dpi)
    celda_w, celda_h = ancho // 2, alto // 2
    lado_qr = int(celda_w * 0.62)
    titulo, texto, pie = _fuente(44), _fuente(28), _fuente(22)
    paginas = []
    for inicio in range(0, len(mesas), 4):
        hoja = Image.new("RGB", (ancho, alto), "white")
        dibujo = ImageDraw.Draw(hoja)
        for i, mesa in enumerate(mesas[inicio:inicio + 4]):
            x0, y0 = (i % 2) * celda_w, (i // 2) * celda_h
            dibujo.rectangle([x0 + 12, y0 + 12, x0 + celda_w - 12, y0 + celda_h - 12], outline="#D9DCE5", width=2)
            imagen_qr = Image.open(io.BytesIO(png(enlace_de_mesa(tenant, mesa), lado_qr)))
            hoja.paste(imagen_qr, (x0 + (celda_w - lado_qr) // 2, y0 + 150))
            dibujo.text((x0 + celda_w // 2, y0 + 70), tenant.name, fill="#13151C", font=texto, anchor="mm")
            dibujo.text((x0 + celda_w // 2, y0 + 118), f"Mesa {mesa.number}", fill="#13151C", font=titulo, anchor="mm")
            dibujo.text((x0 + celda_w // 2, y0 + 150 + lado_qr + 45), "Escanea para ver el menú",
                        fill="#5F6679", font=pie, anchor="mm")
        paginas.append(hoja)
    salida = io.BytesIO()
    paginas[0].save(salida, "PDF", resolution=dpi, save_all=True, append_images=paginas[1:])
    return salida.getvalue()
