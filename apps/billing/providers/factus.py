"""Factus — proveedor tecnológico certificado ante la DIAN (API v2).

Dos piezas, a propósito separadas:

- `ClienteFactus` habla HTTP: pide y renueva el token OAuth, manda peticiones y
  traduce los códigos de respuesta a las excepciones de `base.py`. No sabe nada
  de restaurantes.
- `ProveedorFactus` es el adaptador de Cloudin: arma el JSON de la factura a
  partir del DocumentoFiscal y lee lo que responde Factus.

Referencia: https://developers.factus.com.co (colección v2).

Tres detalles del contrato de Factus que explican buena parte del código:

1. `items.*.price` va **sin impuesto**. La carta de un restaurante trae el INC
   incluido, así que hay que sacar la base por unidad (35.000 / 1,08).
2. La suma de `payment_details` debe igualar el total de la factura. Al sacar la
   base con dos decimales aparecen centavos de diferencia; se concilian con
   `cash_rounding_amount` (pagos − total, máximo ±500).
3. Un rechazo de la DIAN **bloquea** los envíos siguientes hasta que se borre la
   factura no validada. Una demora de la DIAN, en cambio, se resuelve
   reenviando exactamente la misma factura (misma `reference_code`).
"""

from __future__ import annotations

import hashlib
import logging
import re
from decimal import ROUND_HALF_UP, Decimal

import requests
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from .base import ErrorConfiguracionPT, ErrorPT, ErrorTemporalPT, ProveedorTecnologico, RespuestaPT

log = logging.getLogger("cloudin.factus")

CENTAVO = Decimal("0.01")
URL_SANDBOX = "https://api-sandbox.factus.com.co"

# Tablas de referencia de Factus v2 (developers.factus.com.co/tablas-de-referencia).
IMPUESTOS = {"IVA": "01", "INC": "04"}
DOCUMENTOS_IDENTIDAD = {"13": "13", "31": "31", "22": "22", "41": "41"}
CONSUMIDOR_FINAL = "222222222222"
UNIDAD = "94"              # unidad
ESTANDAR = "999"           # estándar de adopción del contribuyente
CONTADO = "1"
MAX_REDONDEO = Decimal("500")


def _dos(valor) -> Decimal:
    return Decimal(str(valor)).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def _texto(valor) -> str:
    return f"{_dos(valor):.2f}"


# ============================================================ cliente HTTP


class ClienteFactus:
    """Wrapper de la API v2 de Factus.

    El token dura una hora. Se guarda en la caché de Django (compartida entre
    procesos si la caché es Redis) y se renueva con el refresh token; si eso
    falla, se vuelve a pedir con usuario y contraseña.
    """

    # Margen para no usar un token a segundos de vencer.
    MARGEN_SEGUNDOS = 120

    def __init__(self, *, url, client_id, client_secret, username, password,
                 timeout=(5, 45), sesion=None):
        self.url = (url or URL_SANDBOX).rstrip("/")
        self.client_id = client_id or ""
        self.client_secret = client_secret or ""
        self.username = username or ""
        self.password = password or ""
        self.timeout = timeout
        self.sesion = sesion or requests.Session()

    @classmethod
    def desde_configuracion(cls, credenciales: dict | None = None, **kwargs):
        """Credenciales propias del restaurante, o las globales del .env."""
        c = credenciales or {}
        return cls(
            url=c.get("url") or getattr(settings, "FACTUS_URL", URL_SANDBOX),
            client_id=c.get("client_id") or getattr(settings, "FACTUS_CLIENT_ID", ""),
            client_secret=c.get("client_secret") or getattr(settings, "FACTUS_CLIENT_SECRET", ""),
            username=c.get("username") or getattr(settings, "FACTUS_USERNAME", ""),
            password=c.get("password") or getattr(settings, "FACTUS_PASSWORD", ""),
            **kwargs,
        )

    @property
    def configurado(self) -> bool:
        return all([self.url, self.client_id, self.client_secret, self.username, self.password])

    @property
    def es_sandbox(self) -> bool:
        return "sandbox" in self.url

    # --------------------------------------------------------------- token

    def _clave_cache(self) -> str:
        huella = hashlib.sha256(f"{self.url}|{self.client_id}|{self.username}".encode()).hexdigest()
        return f"factus:token:{huella[:24]}"

    def _pedir_token(self, datos: dict) -> dict:
        try:
            r = self.sesion.post(
                f"{self.url}/oauth/token",
                data=datos,
                headers={"Accept": "application/json"},
                timeout=self.timeout,
            )
        except requests.RequestException as e:
            raise ErrorTemporalPT(f"No se pudo conectar con Factus: {e}", {"red": str(e)}) from e

        cuerpo = _json(r)
        if r.status_code == 200 and cuerpo.get("access_token"):
            return cuerpo

        codigo = cuerpo.get("error", "")
        if codigo == "invalid_client":
            mensaje = "Factus rechazó el client_id o el client_secret."
        elif codigo == "invalid_grant":
            mensaje = "Factus rechazó el usuario o la contraseña de la API."
        elif r.status_code >= 500:
            raise ErrorTemporalPT("Factus no pudo emitir el token (error del servidor).",
                                  _payload(r, cuerpo))
        else:
            mensaje = f"Factus no entregó el token ({cuerpo.get('message') or r.status_code})."
        raise ErrorConfiguracionPT(mensaje, _payload(r, cuerpo))

    def token(self, forzar: bool = False) -> str:
        if not self.configurado:
            raise ErrorConfiguracionPT(
                "Faltan las credenciales de Factus (FACTUS_* en el .env o las del restaurante)."
            )
        clave = self._clave_cache()
        guardado = None if forzar else cache.get(clave)
        ahora = timezone.now().timestamp()

        if guardado and guardado["vence"] - self.MARGEN_SEGUNDOS > ahora:
            return guardado["access_token"]

        datos_base = {"client_id": self.client_id, "client_secret": self.client_secret}
        cuerpo = None
        if guardado and guardado.get("refresh_token"):
            try:
                cuerpo = self._pedir_token(
                    {**datos_base, "grant_type": "refresh_token",
                     "refresh_token": guardado["refresh_token"]}
                )
            except ErrorConfiguracionPT:
                cuerpo = None      # el refresh venció: se entra de nuevo con usuario
        if cuerpo is None:
            cuerpo = self._pedir_token(
                {**datos_base, "grant_type": "password",
                 "username": self.username, "password": self.password}
            )

        vida = int(cuerpo.get("expires_in") or 3600)
        cache.set(
            clave,
            {
                "access_token": cuerpo["access_token"],
                "refresh_token": cuerpo.get("refresh_token", ""),
                "vence": ahora + vida,
            },
            # El refresh token vive más que el access token; se guarda un día.
            timeout=86400,
        )
        return cuerpo["access_token"]

    def olvidar_token(self):
        cache.delete(self._clave_cache())

    # ------------------------------------------------------------ peticiones

    def peticion(self, metodo: str, ruta: str, *, json=None, params=None,
                 _reintento_auth: bool = True) -> dict:
        """Hace la petición y convierte cualquier falla en ErrorPT o ErrorTemporalPT."""
        encabezados = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.token()}",
        }
        if json is not None:
            encabezados["Content-Type"] = "application/json"

        try:
            r = self.sesion.request(
                metodo, f"{self.url}{ruta}", json=json, params=params,
                headers=encabezados, timeout=self.timeout,
            )
        except requests.Timeout as e:
            raise ErrorTemporalPT("Factus tardó demasiado en responder.", {"red": str(e)}) from e
        except requests.RequestException as e:
            raise ErrorTemporalPT(f"No se pudo conectar con Factus: {e}", {"red": str(e)}) from e

        cuerpo = _json(r)
        estado = r.status_code
        log.info("factus %s %s -> %s", metodo, ruta, estado)

        if 200 <= estado < 300:
            return cuerpo

        payload = _payload(r, cuerpo)
        if estado == 401 and _reintento_auth:
            # El token pudo morir antes de tiempo: uno nuevo y un solo reintento.
            self.olvidar_token()
            return self.peticion(metodo, ruta, json=json, params=params, _reintento_auth=False)
        if estado in (401, 403):
            raise ErrorConfiguracionPT("Factus negó el acceso con estas credenciales.", payload)
        if estado == 402:
            raise ErrorConfiguracionPT(
                "Factus pide pago: el plan no tiene documentos disponibles.", payload
            )
        if estado == 409:
            raise ErrorTemporalPT(
                "Factus tiene una factura pendiente de enviar a la DIAN que bloquea las "
                f"siguientes: {cuerpo.get('message') or 'conflicto'}",
                payload,
            )
        if estado == 422:
            raise ErrorPT("Factus rechazó los datos: " + _errores_validacion(cuerpo), payload)
        if estado == 429:
            espera = r.headers.get("Retry-After", "60")
            raise ErrorTemporalPT(
                f"Se superó el límite de Factus (80 por minuto). Reintentar en {espera} s.",
                payload,
            )
        if estado >= 500:
            raise ErrorTemporalPT(f"Factus falló por su lado (HTTP {estado}).", payload)
        raise ErrorPT(cuerpo.get("message") or f"Factus respondió HTTP {estado}.", payload)

    # ------------------------------------------------------------- endpoints

    def validar_factura(self, cuerpo: dict) -> dict:
        return self.peticion("POST", "/v2/bills/validate", json=cuerpo)

    def ver_factura(self, numero: str) -> dict:
        return self.peticion("GET", f"/v2/bills/{numero}")

    def eliminar_no_validada(self, referencia: str) -> dict:
        return self.peticion("DELETE", f"/v2/bills/destroy/reference/{referencia}")

    def descargar_pdf(self, numero: str) -> dict:
        return self.peticion("GET", f"/v2/bills/{numero}/download-pdf")

    def descargar_xml(self, numero: str) -> dict:
        return self.peticion("GET", f"/v2/bills/{numero}/download-xml")

    def rangos_numeracion(self, *, documento: str = "21", solo_activos: bool = True) -> list:
        params = {"filter[document]": documento}
        if solo_activos:
            params["filter[is_active]"] = 1
        cuerpo = self.peticion("GET", "/v2/numbering-ranges", params=params)
        datos = cuerpo.get("data", cuerpo)
        # Según el endpoint, la lista viene directa o paginada dentro de data.data.
        if isinstance(datos, dict):
            datos = datos.get("data", [])
        return datos if isinstance(datos, list) else []

    def empresa(self) -> dict:
        return self.peticion("GET", "/v2/companies").get("data", {})


def _json(respuesta) -> dict:
    try:
        cuerpo = respuesta.json()
    except ValueError:
        return {"texto": (respuesta.text or "")[:2000]}
    return cuerpo if isinstance(cuerpo, dict) else {"data": cuerpo}


def _payload(respuesta, cuerpo) -> dict:
    return {"http_status": respuesta.status_code, "respuesta": cuerpo}


def _errores_validacion(cuerpo: dict) -> str:
    """Aplana los errores de validación de Factus en una frase legible."""
    fuentes = [cuerpo.get("errors"), (cuerpo.get("data") or {}).get("errors")
               if isinstance(cuerpo.get("data"), dict) else None]
    partes = []
    for errores in fuentes:
        if isinstance(errores, dict):
            for campo, mensajes in errores.items():
                if isinstance(mensajes, (list, tuple)):
                    mensajes = "; ".join(str(m) for m in mensajes)
                partes.append(f"{campo}: {mensajes}")
        elif isinstance(errores, list):
            partes.extend(str(e) for e in errores)
    if not partes and cuerpo.get("message"):
        partes.append(str(cuerpo["message"]))
    return " | ".join(partes)[:900] or "sin detalle"


# ======================================================= armado de la factura


def referencia_de(documento) -> str:
    """El `reference_code` de Factus: único y estable entre reintentos.

    Lleva el restaurante porque varias bases pueden compartir una cuenta de
    Factus (en sandbox, siempre): `CLD-7` de dos restaurantes chocaría.
    """
    if getattr(documento, "referencia_pt", ""):
        return documento.referencia_pt
    base = (documento._state.db or "default").replace("tenant_", "")
    base = re.sub(r"[^A-Za-z0-9]", "", base)[:20].upper()
    return f"CLD-{base}-{documento.pk}"


def _cliente(cliente) -> dict:
    if cliente is None or cliente.tipo_documento == "cf" or not cliente.numero_documento:
        return {
            "identification_document_code": "13",
            "identification": CONSUMIDOR_FINAL,
            "names": "Consumidor Final",
            "legal_organization_code": "2",
            "tribute_code": "ZZ",
        }
    es_nit = cliente.tipo_documento == "31"
    datos = {
        "identification_document_code": DOCUMENTOS_IDENTIDAD.get(cliente.tipo_documento, "13"),
        "identification": re.sub(r"\D", "", cliente.numero_documento.split("-")[0]),
        "legal_organization_code": "1" if es_nit else "2",
        "tribute_code": "ZZ",
    }
    datos["company" if es_nit else "names"] = cliente.nombre
    for campo_factus, valor in (("email", cliente.correo), ("phone", cliente.telefono),
                                ("address", cliente.direccion)):
        if valor:
            datos[campo_factus] = valor
    return datos


def _item(linea: dict, incluye_impuesto: bool) -> tuple[dict, Decimal]:
    """Una línea para Factus y lo que Factus calculará que vale."""
    cantidad = Decimal(str(linea["cantidad"]))
    cobrado_unidad = Decimal(str(linea["precio_unitario"]))
    impuesto = linea.get("impuesto") or {}
    tipo = impuesto.get("tipo", "EXENTO")
    tarifa = Decimal(str(impuesto.get("tarifa") or "0"))
    gravado = tipo in IMPUESTOS and tarifa > 0

    if gravado and incluye_impuesto:
        neto = _dos(cobrado_unidad / (1 + tarifa / 100))
    else:
        neto = _dos(cobrado_unidad)

    descuento_pct = Decimal(str((linea.get("descuento") or {}).get("porcentaje") or "0"))

    nombre = str(linea["nombre"])[:250]
    item = {
        "code_reference": (re.sub(r"[^A-Z0-9]", "", nombre.upper())[:20] or "ITEM"),
        "name": nombre,
        "quantity": _texto(cantidad),
        "discount_rate": _texto(descuento_pct) if descuento_pct else "0.00",
        "price": _texto(neto),
        "unit_measure_code": UNIDAD,
        "standard_code": ESTANDAR,
        "taxes": (
            [{"code": IMPUESTOS[tipo], "rate": _texto(tarifa)}] if gravado
            else [{"is_excluded": True}]
        ),
    }
    # Así redondea la DIAN: primero la base de la línea (menos su descuento),
    # luego su impuesto.
    base_linea = _dos(neto * cantidad)
    base_linea -= _dos(base_linea * descuento_pct / 100)
    valor = base_linea + (_dos(base_linea * tarifa / 100) if gravado else Decimal("0"))
    return item, valor


def construir_factura(documento, empresa, *, observacion: str = "") -> dict:
    """El JSON de `POST /v2/bills/validate` para un DocumentoFiscal ya preparado."""
    items, total_factus = [], Decimal("0")
    for linea in documento.lineas:
        item, valor = _item(linea, empresa.precios_incluyen_impuesto)
        items.append(item)
        total_factus += valor

    cobrado = _dos(documento.total_general)
    redondeo = cobrado - total_factus
    if abs(redondeo) > MAX_REDONDEO:
        raise ErrorPT(
            f"La diferencia entre lo cobrado (${cobrado}) y lo que calcula la factura "
            f"(${total_factus}) es de ${redondeo}; Factus acepta como máximo ±$500.",
            {"cobrado": str(cobrado), "calculado": str(total_factus)},
        )

    cuerpo = {
        "reference_code": referencia_de(documento),
        "document": "01",
        "operation_type": "10",
        "observation": (observacion or "Generada por Cloudin")[:500],
        "send_email": bool(documento.cliente and documento.cliente.correo),
        "payment_details": [{
            "payment_form": CONTADO,
            "payment_method_code": getattr(documento, "medio_pago", "") or "10",
            "amount": _texto(cobrado),
        }],
        "customer": _cliente(documento.cliente),
        "items": items,
    }
    if redondeo:
        cuerpo["cash_rounding_amount"] = _texto(redondeo)
    rango = getattr(documento.resolucion, "id_rango_proveedor", None) if documento.resolucion_id else None
    if rango:
        cuerpo["numbering_range_id"] = rango
    return cuerpo


def es_rechazo(errores) -> bool:
    """La DIAN mezcla notificaciones con rechazos; solo lo que dice «Rechazo»
    tumba la factura (developers.factus.com.co/manejo-errores)."""
    if isinstance(errores, dict):
        textos = errores.values()
    elif isinstance(errores, list):
        textos = errores
    else:
        textos = [errores] if errores else []
    return any("rechazo" in str(t).lower() for t in textos)


# ================================================================ adaptador


class ProveedorFactus(ProveedorTecnologico):
    nombre = "factus"

    def __init__(self, empresa, cliente: ClienteFactus | None = None):
        super().__init__(empresa)
        self.cliente = cliente or ClienteFactus.desde_configuracion(credenciales_de(empresa))

    def emitir(self, documento, payload: dict) -> RespuestaPT:
        if not documento.referencia_pt:
            documento.referencia_pt = referencia_de(documento)
            documento.save(update_fields=["referencia_pt"])
        mesa = payload.get("mesa") or ""
        cuerpo = construir_factura(
            documento, self.empresa,
            observacion=f"Mesa {mesa} · Cloudin" if mesa else "Cloudin",
        )
        respuesta = self.cliente.validar_factura(cuerpo)
        return self._interpretar(respuesta, cuerpo, documento)

    def consultar(self, documento) -> RespuestaPT:
        if not documento.numero_completo:
            raise ErrorPT("El documento no tiene número de Factus para consultar.")
        respuesta = self.cliente.ver_factura(documento.numero_completo)
        return self._interpretar(respuesta, {"reference_code": referencia_de(documento)},
                                 documento, borrar_si_rechazo=False)

    def _interpretar(self, respuesta: dict, cuerpo: dict, documento,
                     borrar_si_rechazo: bool = True) -> RespuestaPT:
        datos = respuesta.get("data") or {}
        bill = datos.get("bill") if isinstance(datos.get("bill"), dict) else datos
        crudo = {"enviado": cuerpo, "respuesta": respuesta}

        if bill.get("is_validated") is True or str(bill.get("status")) == "1":
            enlaces = bill.get("links") or datos.get("links") or {}
            return RespuestaPT(
                cufe=bill.get("cufe", ""),
                numero_completo=bill.get("number", ""),
                pdf_url=enlaces.get("public_url") or bill.get("public_url", ""),
                qr_url=enlaces.get("qr") or bill.get("qr", ""),
                aceptada=True,
                crudo=crudo,
            )

        errores = bill.get("errors") or {}
        if es_rechazo(errores):
            if borrar_si_rechazo:
                # Sin esto Factus no deja emitir la siguiente factura.
                try:
                    crudo["eliminada"] = self.cliente.eliminar_no_validada(cuerpo["reference_code"])
                except (ErrorPT, ErrorTemporalPT) as e:
                    crudo["no_se_pudo_eliminar"] = str(e)
            raise ErrorPT("Rechazada por la DIAN: " + _errores_validacion({"errors": errores}), crudo)

        # Sin rechazo y sin validar: la DIAN está demorada. Se reintenta con los
        # mismos datos y Factus reconoce que es la misma factura.
        raise ErrorTemporalPT(
            "Factus recibió la factura pero la DIAN aún no la valida. Se reintenta sola.", crudo
        )


# ============================================================ credenciales


def nombre_empresa(datos: dict) -> str:
    """Factus trae la razón social en `company` (persona jurídica) o el nombre en
    `names` + `surnames` (persona natural)."""
    nombre = (datos.get("company") or datos.get("trade_name")
              or " ".join(p for p in (datos.get("names"), datos.get("surnames")) if p)
              or datos.get("graphic_representation_name") or "")
    return nombre.strip() or "la empresa"


def credenciales_de(empresa) -> dict:
    """Credenciales propias del restaurante (cifradas), si las tiene."""
    import json

    from apps.tenants.crypto import descifrar

    texto = descifrar(empresa.credenciales_pt or "") if empresa else None
    if not texto:
        return {}
    try:
        datos = json.loads(texto)
    except ValueError:
        return {}
    return datos if isinstance(datos, dict) else {}


def guardar_credenciales(empresa, datos: dict):
    import json

    from apps.tenants.crypto import cifrar

    limpias = {k: (v or "").strip() for k, v in datos.items() if (v or "").strip()}
    url = limpias.get("url")
    if url and not re.match(r"^https://api(-sandbox)?\.factus\.com\.co/?$", url):
        # Solo los servidores de Factus: con otra dirección, Cloudin terminaría
        # mandando las credenciales (o peticiones internas) a quien sea.
        from django.core.exceptions import ValidationError

        raise ValidationError("La dirección de Factus debe ser https://api.factus.com.co o la de sandbox.")
    empresa.credenciales_pt = cifrar(json.dumps(limpias)) if limpias else ""
    empresa.save(update_fields=["credenciales_pt"])


def sincronizar_rangos(empresa, cliente: ClienteFactus | None = None) -> dict:
    """Trae de Factus los rangos de factura activos y los deja como resoluciones.

    El consecutivo real lo lleva Factus; aquí se copia para que el panel muestre
    cuántos números quedan y avise antes de agotarse.
    """
    from datetime import date

    from apps.billing.models import ResolucionNumeracion

    cliente = cliente or ClienteFactus.desde_configuracion(credenciales_de(empresa))
    db = empresa._state.db
    creados = actualizados = 0
    for rango in cliente.rangos_numeracion(documento="21"):
        def fecha(clave, por_defecto):
            valor = rango.get(clave)
            if not valor:
                return por_defecto
            for formato in ("%Y-%m-%d", "%d-%m-%Y"):
                try:
                    return timezone.datetime.strptime(str(valor)[:10], formato).date()
                except ValueError:
                    continue
            return por_defecto

        desde = int(rango.get("from") or 1)
        hasta = int(rango.get("to") or desde)
        siguiente = int(rango.get("current") or desde)
        valores = {
            "empresa": empresa,
            "tipo_documento": ResolucionNumeracion.FACTURA,
            "numero_resolucion": str(rango.get("resolution_number") or rango.get("id")),
            "fecha_expedicion": fecha("start_date", date.today()),
            "fecha_vencimiento": fecha("end_date", date.today()),
            "prefijo": rango.get("prefix") or "",
            "rango_desde": desde,
            "rango_hasta": hasta,
            # Factus da el siguiente número; el modelo guarda el último usado.
            "consecutivo_actual": max(desde - 1, min(siguiente - 1, hasta)),
            "clave_tecnica": rango.get("technical_key") or "",
            "activa": bool(rango.get("is_active", True)) and not bool(rango.get("is_expired")),
        }
        existente = ResolucionNumeracion.objects.using(db).filter(
            empresa=empresa, id_rango_proveedor=rango.get("id")
        ).first()
        if existente:
            for campo, valor in valores.items():
                setattr(existente, campo, valor)
            existente.save()
            actualizados += 1
        else:
            ResolucionNumeracion.objects.using(db).create(
                id_rango_proveedor=rango.get("id"), **valores
            )
            creados += 1
    return {"creados": creados, "actualizados": actualizados}
