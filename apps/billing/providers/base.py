"""La interfaz que debe cumplir cualquier proveedor tecnológico.

Todo lo que el resto del sistema sabe hacer con un PT está aquí. Integrar
Factus, Alegra o Siigo será escribir una clase que herede de esta.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class ErrorPT(Exception):
    """El PT rechazó el documento. Reintentar igual no sirve: hay que corregir."""

    def __init__(self, mensaje, payload=None):
        super().__init__(mensaje)
        self.payload = payload or {}


class ErrorTemporalPT(Exception):
    """El PT o la DIAN no respondieron. El documento queda en contingencia y
    se reintenta solo; la operación del restaurante no se detiene."""

    def __init__(self, mensaje, payload=None):
        super().__init__(mensaje)
        self.payload = payload or {}


class ErrorConfiguracionPT(ErrorTemporalPT):
    """El PT no nos deja entrar: credenciales rechazadas, plan sin saldo, cuenta
    inactiva. No es culpa del documento, así que queda en contingencia y sale
    solo cuando se arregle la configuración; pero el mensaje lo dice claro para
    que alguien lo arregle."""


@dataclass
class RespuestaPT:
    """Lo que devuelve el PT cuando acepta un documento."""

    cufe: str
    numero_completo: str = ""
    xml_url: str = ""
    pdf_url: str = ""
    qr_url: str = ""
    aceptada: bool = True
    crudo: dict = field(default_factory=dict)


class ProveedorTecnologico(ABC):
    """Contrato común. `empresa` es la EmpresaFiscal del restaurante."""

    nombre = "abstracto"

    def __init__(self, empresa):
        self.empresa = empresa

    @abstractmethod
    def emitir(self, documento, payload: dict) -> RespuestaPT:
        """Manda una factura, nota o documento POS. Devuelve CUFE, XML y PDF."""

    @abstractmethod
    def consultar(self, documento) -> RespuestaPT:
        """Pregunta por el estado de un documento ya enviado."""

    def emitir_nomina(self, payload: dict) -> RespuestaPT:
        """Nómina electrónica. Por ahora solo el simulador la implementa; queda
        declarada aquí para que agregarla después no cambie nada más."""
        raise NotImplementedError(
            f"El proveedor «{self.nombre}» todavía no tiene nómina electrónica."
        )
