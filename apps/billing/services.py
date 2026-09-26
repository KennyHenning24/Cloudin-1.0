"""El flujo de facturar: de una cuenta de mesa cerrada a un documento DIAN.

Regla de oro del spec: **la operación del restaurante nunca se detiene**. Si el
proveedor o la DIAN no responden, el documento queda en contingencia y se
reintenta solo; la mesa se cierra y la cocina sigue trabajando igual.
"""

import re
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import ClienteFiscal, DocumentoFiscal, EmpresaFiscal, Impuesto, ResolucionNumeracion
from .providers import ErrorPT, ErrorTemporalPT, obtener_proveedor
from .taxes import MotorTributario, lineas_de_sesion

# Cada reintento espera más que el anterior, hasta una hora.
ESPERAS = [1, 5, 15, 30, 60]


def empresa_actual(db=None) -> EmpresaFiscal | None:
    qs = EmpresaFiscal.objects.using(db) if db else EmpresaFiscal.objects
    return qs.first()


def motor_de(empresa) -> MotorTributario:
    db = empresa._state.db
    impuestos = Impuesto.objects.using(db).filter(activo=True)
    return MotorTributario.desde_empresa(empresa, impuestos)


def _espera(intentos: int) -> timedelta:
    return timedelta(minutes=ESPERAS[min(intentos, len(ESPERAS) - 1)])


def construir_payload(documento, empresa, calculo, cliente) -> dict:
    """El documento en un formato neutro, independiente del PT.

    Cada adaptador lo traduce a lo que pida su API. Así cambiar de proveedor no
    obliga a tocar el cálculo ni el modelo.
    """
    return {
        "tipo": documento.tipo,
        "numero_completo": documento.numero_completo,
        "prefijo": documento.prefijo,
        "consecutivo": documento.consecutivo,
        "fecha": timezone.now().isoformat(timespec="seconds"),
        "emisor": {
            "razon_social": empresa.razon_social,
            "nit": empresa.nit,
            "dv": empresa.digito_verificacion,
            "direccion": empresa.direccion,
            "ciudad": empresa.ciudad,
            "regimen": empresa.regimen,
            "correo": empresa.correo_facturacion,
        },
        "nit_emisor": empresa.nit,
        "cliente": {
            "tipo_documento": cliente.tipo_documento,
            "numero_documento": cliente.numero_documento,
            "nombre": cliente.nombre,
            "correo": cliente.correo,
        },
        "resolucion": (
            {
                "numero": documento.resolucion.numero_resolucion,
                "prefijo": documento.resolucion.prefijo,
                "desde": documento.resolucion.rango_desde,
                "hasta": documento.resolucion.rango_hasta,
                "clave_tecnica": documento.resolucion.clave_tecnica,
            }
            if documento.resolucion
            else None
        ),
        "lineas": calculo.como_dict()["lineas"],
        "total_base": str(calculo.total_base),
        "total_impuestos": str(calculo.total_impuestos),
        "total_general": str(calculo.total_general),
        "impuestos": calculo.como_dict()["detalle"],
        "mesa": documento.sesion.table.number if documento.sesion_id else None,
        "documento_referencia": (
            documento.documento_referencia.numero_completo
            if documento.documento_referencia_id
            else None
        ),
    }


def preparar_documento(session, *, tipo=ResolucionNumeracion.FACTURA, cliente=None,
                       medio_pago=DocumentoFiscal.EFECTIVO):
    """Crea el DocumentoFiscal con sus totales, sin mandarlo todavía."""
    db = session._state.db
    empresa = empresa_actual(db)
    if empresa is None:
        raise ValidationError("El restaurante todavía no tiene datos fiscales cargados.")

    faltantes = [k for k, ok in empresa.requisitos().items() if not ok]
    if faltantes:
        raise ValidationError(
            "Falta completar para poder facturar: " + ", ".join(faltantes).replace("_", " ")
        )

    resolucion = empresa.resolucion_vigente(tipo)
    if resolucion is None:
        raise ValidationError(
            f"No hay resolución de numeración vigente para «{dict(ResolucionNumeracion.TIPOS)[tipo]}»."
        )

    calculo = motor_de(empresa).calcular(lineas_de_sesion(session))
    cliente = cliente or ClienteFiscal.consumidor_final(db)
    if empresa.firma_el_proveedor:
        # Con un PT real el número lo asigna el PT al validar. Reservarlo aquí
        # daba números falsos: si una factura no llegaba al PT (contingencia),
        # su número reservado se lo terminaba dando el PT a la siguiente.
        consecutivo, numero = None, ""
    else:
        consecutivo, numero = resolucion.tomar_consecutivo()

    documento = DocumentoFiscal.objects.using(db).create(
        sesion=session,
        turno=session.turno,
        cliente=cliente,
        resolucion=resolucion,
        tipo=tipo,
        prefijo=resolucion.prefijo,
        consecutivo=consecutivo,
        numero_completo=numero,
        estado=DocumentoFiscal.PENDIENTE,
        medio_pago=medio_pago or DocumentoFiscal.EFECTIVO,
        lineas=calculo.como_dict()["lineas"],
        total_base=calculo.total_base,
        total_impuestos=calculo.total_impuestos,
        impuestos_detalle=calculo.como_dict()["detalle"],
        total_general=calculo.total_general,
    )
    documento.registrar(
        "preparado",
        detalle=f"Numerado como {numero}" if numero
        else f"Listo para enviar; el número lo asigna {empresa.proveedor.capitalize()} al validar",
    )
    return documento, empresa, calculo


def transmitir(documento, empresa=None, calculo=None):
    """Manda el documento al PT y guarda lo que responda, pase lo que pase."""
    db = documento._state.db
    empresa = empresa or empresa_actual(db)
    if calculo is None:
        calculo = motor_de(empresa).calcular(
            [(ln["nombre"], ln["cantidad"], Decimal(ln["precio_unitario"]), None)
             for ln in documento.lineas]
        )

    payload = construir_payload(documento, empresa, calculo, documento.cliente)
    proveedor = obtener_proveedor(empresa)
    documento.intentos += 1

    try:
        respuesta = proveedor.emitir(documento, payload)
    except ErrorTemporalPT as e:
        # No es culpa del documento: se reintenta solo, sin frenar el servicio.
        documento.estado = DocumentoFiscal.CONTINGENCIA
        documento.respuesta_pt = e.payload
        documento.proximo_reintento = timezone.now() + _espera(documento.intentos)
        documento.save(update_fields=["estado", "respuesta_pt", "intentos", "proximo_reintento"])
        documento.registrar("transmision", "contingencia", str(e), e.payload)
        return documento
    except ErrorPT as e:
        # El documento está mal: hay que corregirlo y volver a emitirlo.
        documento.estado = DocumentoFiscal.RECHAZADA
        documento.motivo_rechazo = str(e)
        documento.respuesta_pt = e.payload
        documento.fecha_transmision = timezone.now()
        documento.save(update_fields=[
            "estado", "motivo_rechazo", "respuesta_pt", "intentos", "fecha_transmision",
        ])
        documento.registrar("transmision", "rechazada", str(e), e.payload)
        return documento

    ahora = timezone.now()
    documento.cufe = respuesta.cufe
    # El número oficial es el que asigna el PT (Factus lleva su propio
    # consecutivo); el local era una reserva.
    if respuesta.numero_completo:
        documento.numero_completo = respuesta.numero_completo
        _anotar_consecutivo(documento)
    documento.xml_url = respuesta.xml_url
    documento.pdf_url = respuesta.pdf_url
    documento.qr_url = respuesta.qr_url
    documento.respuesta_pt = respuesta.crudo
    documento.estado = DocumentoFiscal.ACEPTADA if respuesta.aceptada else DocumentoFiscal.ENVIADA
    documento.fecha_transmision = ahora
    documento.fecha_aceptacion = ahora if respuesta.aceptada else None
    documento.motivo_rechazo = ""
    documento.proximo_reintento = None
    documento.save()
    documento.registrar("transmision", "aceptada", f"CUFE {respuesta.cufe[:20]}…", respuesta.crudo)
    return documento


def descontar_inventario(session, usuario=""):
    """Baja del stock lo que consumieron las recetas de esta cuenta.

    Va en un try amplio a propósito: un inventario mal configurado no puede
    impedir que el restaurante facture. Si algo falla, el kardex se queda sin
    ese movimiento y el conteo físico lo corrige.
    """
    try:
        from apps.inventory.services import descontar_sesion

        return descontar_sesion(session, usuario=usuario)
    except Exception:
        return []


def _anotar_consecutivo(documento):
    """Guarda el consecutivo que asignó el PT y lo refleja en la resolución, para
    que el panel siga contando cuántos números quedan."""
    resolucion = documento.resolucion
    if resolucion is None:
        return
    prefijo = resolucion.prefijo or ""
    numero = documento.numero_completo
    resto = numero[len(prefijo):] if prefijo and numero.startswith(prefijo) else numero
    digitos = re.sub(r"\D", "", resto)
    if not digitos:
        return
    documento.prefijo = prefijo
    documento.consecutivo = int(digitos)
    if documento.consecutivo > resolucion.consecutivo_actual:
        type(resolucion).objects.using(documento._state.db).filter(pk=resolucion.pk).update(
            consecutivo_actual=documento.consecutivo
        )


def facturar_sesion(session, *, tipo=ResolucionNumeracion.FACTURA, cliente=None, usuario="",
                    medio_pago=DocumentoFiscal.EFECTIVO):
    """Lo que llama el panel al pulsar «Facturar»."""
    documento, empresa, calculo = preparar_documento(
        session, tipo=tipo, cliente=cliente, medio_pago=medio_pago
    )
    # La comida ya salió de la cocina: el inventario baja aunque la DIAN
    # rechace o el proveedor no responda.
    descontar_inventario(session, usuario)
    return transmitir(documento, empresa, calculo)


def reintentar_pendientes(db=None, limite=50):
    """Cola de contingencia: reenvía lo que quedó esperando. La llama un
    comando programado (más adelante, Celery)."""
    qs = DocumentoFiscal.objects.using(db) if db else DocumentoFiscal.objects
    ahora = timezone.now()
    pendientes = qs.filter(
        estado__in=[DocumentoFiscal.CONTINGENCIA, DocumentoFiscal.PENDIENTE],
        proximo_reintento__lte=ahora,
    )[:limite]
    return [transmitir(doc) for doc in pendientes]


def alertas(db=None) -> list[dict]:
    """Avisos que el panel debe mostrarle al restaurante."""
    empresa = empresa_actual(db)
    if empresa is None:
        return [{"nivel": "alerta", "texto": "Aún no has cargado los datos fiscales."}]

    avisos = []
    for k, ok in empresa.requisitos().items():
        if not ok:
            avisos.append({"nivel": "alerta", "texto": f"Falta: {k.replace('_', ' ')}."})

    for r in empresa.resoluciones.filter(activa=True):
        if r.vencida:
            avisos.append({"nivel": "malo", "texto": f"La resolución {r.numero_resolucion} está vencida."})
        elif r.agotada:
            avisos.append({"nivel": "malo", "texto": f"La resolución {r.numero_resolucion} se agotó."})
        else:
            if r.por_agotarse():
                avisos.append({
                    "nivel": "alerta",
                    "texto": f"Quedan {r.disponibles} números en la resolución {r.numero_resolucion}.",
                })
            if r.por_vencer():
                avisos.append({
                    "nivel": "alerta",
                    "texto": f"La resolución {r.numero_resolucion} vence el "
                             f"{r.fecha_vencimiento:%d/%m/%Y}.",
                })

    qs = DocumentoFiscal.objects.using(db) if db else DocumentoFiscal.objects
    en_contingencia = qs.filter(estado=DocumentoFiscal.CONTINGENCIA).count()
    if en_contingencia:
        avisos.append({
            "nivel": "alerta",
            "texto": f"{en_contingencia} documento(s) esperando reenvío al proveedor.",
        })
    rechazados = qs.filter(estado=DocumentoFiscal.RECHAZADA).count()
    if rechazados:
        avisos.append({"nivel": "malo", "texto": f"{rechazados} documento(s) rechazados por la DIAN."})
    return avisos
