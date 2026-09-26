"""Proveedores tecnológicos de facturación electrónica.

Cloudin no habla con la DIAN: habla con un PT certificado. Cambiar de PT debe
ser escribir una clase nueva aquí, sin tocar el resto del sistema.
"""

from .base import (  # noqa: F401
    ErrorConfiguracionPT,
    ErrorPT,
    ErrorTemporalPT,
    ProveedorTecnologico,
    RespuestaPT,
)
from .factus import ProveedorFactus  # noqa: F401
from .simulado import ProveedorSimulado  # noqa: F401

PROVEEDORES = {
    "simulado": ProveedorSimulado,
    "factus": ProveedorFactus,
}


def obtener_proveedor(empresa) -> ProveedorTecnologico:
    """Devuelve el adaptador configurado para ese restaurante."""
    clase = PROVEEDORES.get(empresa.proveedor or "simulado", ProveedorSimulado)
    return clase(empresa)
