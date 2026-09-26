"""Proveedor tecnológico simulado.

Imita a un PT real: devuelve CUFE, XML y PDF, y puede rechazar o caerse para
que el manejo de errores y la contingencia se puedan probar hoy, sin depender
de credenciales de nadie.

Cómo forzar cada caso (útil en pruebas y demos):
  - `empresa.credenciales_pt` con "modo=rechazo"    -> siempre rechaza
  - `empresa.credenciales_pt` con "modo=caida"      -> siempre falla temporalmente
  - un cliente llamado "RECHAZAR"                   -> rechaza ese documento
"""

import hashlib
from datetime import datetime

from .base import ErrorPT, ErrorTemporalPT, ProveedorTecnologico, RespuestaPT


class ProveedorSimulado(ProveedorTecnologico):
    nombre = "simulado"

    def _modo(self) -> str:
        cred = (self.empresa.credenciales_pt or "").lower()
        if "modo=rechazo" in cred:
            return "rechazo"
        if "modo=caida" in cred:
            return "caida"
        return "normal"

    def _cufe(self, payload: dict) -> str:
        """Un CUFE real es un SHA-384 de campos de la factura. Aquí se imita
        con la misma forma, para que nada del sistema dependa de su contenido."""
        semilla = "|".join(
            str(payload.get(k, ""))
            for k in ("numero_completo", "fecha", "nit_emisor", "total_general", "cufe_salt")
        )
        return hashlib.sha384(semilla.encode()).hexdigest()

    def emitir(self, documento, payload: dict) -> RespuestaPT:
        modo = self._modo()
        cliente = (payload.get("cliente") or {}).get("nombre", "")

        if modo == "caida":
            raise ErrorTemporalPT(
                "El proveedor no responde (simulado).", {"simulado": True, "modo": modo}
            )
        if modo == "rechazo" or cliente.strip().upper() == "RECHAZAR":
            raise ErrorPT(
                "Rechazado por la DIAN (simulado): el NIT del adquiriente no existe.",
                {"simulado": True, "codigo": "FAD05", "campo": "cliente.numero_documento"},
            )

        cufe = self._cufe(payload)
        numero = payload.get("numero_completo", "")
        return RespuestaPT(
            cufe=cufe,
            numero_completo=numero,
            xml_url=f"https://simulado.cloudin.local/documentos/{cufe[:24]}.xml",
            pdf_url=f"https://simulado.cloudin.local/documentos/{cufe[:24]}.pdf",
            aceptada=True,
            crudo={
                "simulado": True,
                "estado": "aceptada",
                "mensaje": "Documento validado por la DIAN (simulación)",
                "fecha_validacion": datetime.now().isoformat(timespec="seconds"),
                "numero": numero,
                "cufe": cufe,
            },
        )

    def consultar(self, documento) -> RespuestaPT:
        return RespuestaPT(
            cufe=documento.cufe,
            numero_completo=documento.numero_completo,
            xml_url=documento.xml_url,
            pdf_url=documento.pdf_url,
            aceptada=documento.estado == documento.ACEPTADA,
            crudo={"simulado": True, "estado": documento.estado},
        )

    def emitir_nomina(self, payload: dict) -> RespuestaPT:
        """Nómina electrónica simulada, con la misma forma que tendrá la real:
        cuando se contrate el PT, solo se reemplaza esta clase."""
        if self._modo() == "caida":
            raise ErrorTemporalPT("El proveedor no responde (simulado).", {"simulado": True})
        cune = hashlib.sha384(
            f"nomina|{payload.get('periodo')}|{payload.get('nit_empleador')}".encode()
        ).hexdigest()
        return RespuestaPT(
            cufe=cune,   # en nómina se llama CUNE
            numero_completo=str(payload.get("numero", "")),
            xml_url=f"https://simulado.cloudin.local/nomina/{cune[:24]}.xml",
            pdf_url=f"https://simulado.cloudin.local/nomina/{cune[:24]}.pdf",
            crudo={"simulado": True, "tipo": "nomina_individual", "cune": cune},
        )
