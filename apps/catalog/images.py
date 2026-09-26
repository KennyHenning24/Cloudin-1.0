"""Fotos de la carta: se validan y se guardan en WebP.

- Solo imágenes de verdad (Pillow las abre y las verifica): JPEG, PNG, WebP o GIF.
- Tope de 8 MB y de 40 megapíxeles (protege contra "bombas" de descompresión).
- Se corrige la orientación de la cámara (EXIF) y se reduce al lado mayor pedido.
- WebP calidad 80: una foto de plato de 800 px pesa ~60 KB.

El navegador ya recorta y comprime antes de subir (ver el ImageUploader del
panel); esto es la segunda barrera, la que no se puede saltar.
"""

import io
import uuid

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_BYTES = 8 * 1024 * 1024
MAX_PIXELES = 40_000_000
FORMATOS = {"JPEG", "PNG", "WEBP", "GIF", "MPO"}
LADO_PRODUCTO = 800
LADO_PORTADA = 1600
LADO_LOGO = 512


SVG_PROHIBIDOS = {"script", "foreignobject", "iframe", "object", "embed", "audio", "video", "animate", "set"}


def limpiar_svg(datos: bytes, nombre: str = "logo") -> ContentFile:
    """Un logo SVG sin nada que se pueda ejecutar: sin <script>, sin on*=, sin enlaces
    externos. Un SVG se abre como página: sin limpiarlo podría correr código."""
    import xml.etree.ElementTree as ET

    if len(datos) > 512 * 1024:
        raise ValidationError("El SVG pesa más de 512 KB.")
    try:
        raiz = ET.fromstring(datos)
    except ET.ParseError:
        raise ValidationError("Ese SVG no se pudo leer.")
    if not raiz.tag.lower().endswith("svg"):
        raise ValidationError("Ese archivo no es un SVG.")

    def local(nombre_xml: str) -> str:
        return nombre_xml.rsplit("}", 1)[-1].lower()

    for padre in list(raiz.iter()):
        for hijo in list(padre):
            if local(hijo.tag) in SVG_PROHIBIDOS:
                padre.remove(hijo)
    for el in raiz.iter():
        for attr in list(el.attrib):
            valor = el.attrib[attr].strip().lower()
            if local(attr).startswith("on") or (local(attr) == "href" and not valor.startswith("#")) \
                    or "javascript:" in valor:
                del el.attrib[attr]
    limpio = ET.tostring(raiz, encoding="utf-8", xml_declaration=True)
    return ContentFile(limpio, name=f"{nombre}.svg")


def a_webp(archivo, lado_mayor: int = LADO_PRODUCTO, nombre: str = "") -> ContentFile:
    """Convierte un archivo subido (o bytes) en un WebP listo para guardar."""
    datos = archivo if isinstance(archivo, bytes) else archivo.read()
    if len(datos) > MAX_BYTES:
        raise ValidationError("La foto pesa más de 8 MB. Usa una más liviana.")
    if not datos:
        raise ValidationError("El archivo está vacío.")
    try:
        with Image.open(io.BytesIO(datos)) as prueba:
            if prueba.format not in FORMATOS:
                raise ValidationError("Sube una foto en JPG, PNG o WebP.")
            ancho, alto = prueba.size
            if ancho * alto > MAX_PIXELES:
                raise ValidationError("La foto es demasiado grande. Usa una de menos de 40 megapíxeles.")
            prueba.verify()
        imagen = Image.open(io.BytesIO(datos))
        imagen.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, SyntaxError):
        raise ValidationError("Ese archivo no es una foto válida. Prueba con otra.")

    imagen = ImageOps.exif_transpose(imagen)
    transparente = imagen.mode in ("RGBA", "LA") or (imagen.mode == "P" and "transparency" in imagen.info)
    imagen = imagen.convert("RGBA" if transparente else "RGB")
    imagen.thumbnail((lado_mayor, lado_mayor), Image.Resampling.LANCZOS)
    salida = io.BytesIO()
    imagen.save(salida, "WEBP", quality=80, method=6)
    return ContentFile(salida.getvalue(), name=f"{nombre or uuid.uuid4().hex[:16]}.webp")
