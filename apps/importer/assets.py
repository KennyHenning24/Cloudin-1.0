"""Las fotos de la semilla: rutas relativas a `site/`, desde una carpeta o un zip.

Protecciones: nada de rutas absolutas ni `..` (no se sale de la carpeta), solo
extensiones de imagen, 8 MB por archivo y, en el zip, tope de archivos y de
tamaño descomprimido (contra "bombas" zip).
"""

import hashlib
import zipfile
from pathlib import Path, PurePosixPath

EXTENSIONES = {".webp", ".jpg", ".jpeg", ".png", ".gif", ".svg"}
MAX_ARCHIVO = 8 * 1024 * 1024
MAX_ZIP_ARCHIVOS = 1000
MAX_ZIP_TOTAL = 150 * 1024 * 1024


def _normalizar(ruta: str) -> str | None:
    ruta = str(ruta or "").strip().replace("\\", "/")
    if not ruta or ruta.startswith("/") or ruta.startswith(("http://", "https://")):
        return None
    partes = PurePosixPath(ruta).parts
    if ".." in partes or PurePosixPath(ruta).suffix.lower() not in EXTENSIONES:
        return None
    return str(PurePosixPath(*partes))


def huella(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()[:32]


class SinFotos:
    def leer(self, ruta: str) -> bytes | None:
        return None


class Carpeta:
    """--assets <carpeta>: normalmente la carpeta site/ del proyecto del menú."""

    def __init__(self, raiz):
        self.raiz = Path(raiz).resolve()

    def leer(self, ruta: str) -> bytes | None:
        relativa = _normalizar(ruta)
        if relativa is None:
            return None
        archivo = (self.raiz / relativa).resolve()
        if self.raiz not in archivo.parents or not archivo.is_file() or archivo.stat().st_size > MAX_ARCHIVO:
            return None
        return archivo.read_bytes()


class Zip:
    """assets.zip del endpoint. Acepta el zip de site/ o de su contenido (con o sin «site/»)."""

    def __init__(self, archivo):
        self.zip = zipfile.ZipFile(archivo)
        infos = [i for i in self.zip.infolist() if not i.is_dir()]
        if len(infos) > MAX_ZIP_ARCHIVOS:
            raise ValueError(f"El zip tiene más de {MAX_ZIP_ARCHIVOS} archivos.")
        if sum(i.file_size for i in infos) > MAX_ZIP_TOTAL:
            raise ValueError("El zip descomprimido pesa demasiado (máx. 150 MB).")
        self.indice = {}
        for info in infos:
            nombre = _normalizar(info.filename)
            if nombre is None or info.file_size > MAX_ARCHIVO:
                continue
            self.indice[nombre] = info
            if nombre.startswith("site/"):
                self.indice.setdefault(nombre[5:], info)

    def leer(self, ruta: str) -> bytes | None:
        relativa = _normalizar(ruta)
        info = self.indice.get(relativa) if relativa else None
        return self.zip.read(info) if info else None
