"""Pruebas del cliente y el adaptador de Factus, sin red.

Una sesión HTTP falsa responde lo que documenta Factus v2
(developers.factus.com.co), así se prueba el contrato completo —token, errores,
armado de la factura y lectura de la respuesta— sin depender del sandbox.

    python manage.py test apps.billing.tests.test_factus
"""

from decimal import Decimal
from types import SimpleNamespace

import requests
from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from apps.billing.providers.base import ErrorConfiguracionPT, ErrorPT, ErrorTemporalPT
from apps.billing.providers.factus import (
    ClienteFactus,
    ProveedorFactus,
    construir_factura,
    es_rechazo,
    referencia_de,
)

CACHE_LOCAL = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


# ----------------------------------------------------------------- dobles


class Respuesta:
    def __init__(self, status=200, cuerpo=None, headers=None):
        self.status_code = status
        self._cuerpo = cuerpo if cuerpo is not None else {}
        self.headers = headers or {}
        self.text = str(self._cuerpo)

    def json(self):
        if isinstance(self._cuerpo, Exception):
            raise self._cuerpo
        return self._cuerpo


class SesionFalsa:
    """Guarda cada petición y responde de una cola, en orden."""

    def __init__(self, *respuestas):
        self.cola = list(respuestas)
        self.llamadas = []

    def _siguiente(self):
        r = self.cola.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    def post(self, url, data=None, headers=None, timeout=None):
        self.llamadas.append(("POST", url, data, None, headers))
        return self._siguiente()

    def request(self, metodo, url, json=None, params=None, headers=None, timeout=None):
        self.llamadas.append((metodo, url, json or params, None, headers))
        return self._siguiente()


def token(access="tok-1", refresh="ref-1", vida=3600):
    return Respuesta(200, {"token_type": "Bearer", "expires_in": vida,
                           "access_token": access, "refresh_token": refresh})


def cliente(sesion):
    return ClienteFactus(url="https://api-sandbox.factus.com.co", client_id="id",
                         client_secret="secreto", username="u@x.co", password="clave",
                         sesion=sesion)


def linea(nombre, cantidad, precio, tipo="INC", tarifa="8"):
    return {"nombre": nombre, "cantidad": cantidad, "precio_unitario": str(precio),
            "impuesto": {"tipo": tipo, "tarifa": tarifa, "valor": "0"}}


def documento(lineas, total, *, pk=7, medio="10", cliente_fiscal=None, rango=None):
    doc = SimpleNamespace(
        pk=pk, lineas=lineas, total_general=Decimal(str(total)), medio_pago=medio,
        referencia_pt="", cliente=cliente_fiscal, resolucion_id=1 if rango else None,
        resolucion=SimpleNamespace(id_rango_proveedor=rango) if rango else None,
        numero_completo="",
    )
    doc._state = SimpleNamespace(db="tenant_culturabrisket")
    return doc


EMPRESA = SimpleNamespace(precios_incluyen_impuesto=True, credenciales_pt="")


# ----------------------------------------------------------------- token


@override_settings(CACHES=CACHE_LOCAL)
class TokenTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_pide_token_con_password_y_lo_reutiliza(self):
        sesion = SesionFalsa(token())
        c = cliente(sesion)
        self.assertEqual(c.token(), "tok-1")
        self.assertEqual(c.token(), "tok-1")
        self.assertEqual(len(sesion.llamadas), 1, "el segundo token debe salir de la caché")
        _, url, datos, _, _ = sesion.llamadas[0]
        self.assertTrue(url.endswith("/oauth/token"))
        self.assertEqual(datos["grant_type"], "password")
        self.assertEqual(datos["username"], "u@x.co")

    def test_token_vencido_se_renueva_con_refresh_token(self):
        sesion = SesionFalsa(token(vida=60), token(access="tok-2"))
        c = cliente(sesion)
        c.token()                      # vida 60 s < margen de 120 s: nace «vencido»
        self.assertEqual(c.token(), "tok-2")
        self.assertEqual(sesion.llamadas[1][2]["grant_type"], "refresh_token")
        self.assertEqual(sesion.llamadas[1][2]["refresh_token"], "ref-1")

    def test_credenciales_rechazadas_son_error_de_configuracion(self):
        sesion = SesionFalsa(Respuesta(400, {
            "error": "invalid_grant",
            "message": "The user credentials were incorrect.",
        }))
        with self.assertRaises(ErrorConfiguracionPT) as ctx:
            cliente(sesion).token()
        self.assertIn("usuario o la contraseña", str(ctx.exception))
        # Es temporal a propósito: la factura queda en contingencia, no se pierde.
        self.assertIsInstance(ctx.exception, ErrorTemporalPT)

    def test_sin_credenciales_no_llama_a_la_red(self):
        sesion = SesionFalsa()
        c = ClienteFactus(url="x", client_id="", client_secret="", username="", password="",
                          sesion=sesion)
        with self.assertRaises(ErrorConfiguracionPT):
            c.token()
        self.assertEqual(sesion.llamadas, [])


# ------------------------------------------------------------- peticiones


@override_settings(CACHES=CACHE_LOCAL)
class PeticionTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_401_renueva_el_token_y_reintenta_una_vez(self):
        sesion = SesionFalsa(token(), Respuesta(401, {"message": "Unauthenticated."}),
                             token(access="tok-2"), Respuesta(200, {"data": {"ok": 1}}))
        r = cliente(sesion).peticion("GET", "/v2/companies")
        self.assertEqual(r["data"]["ok"], 1)
        self.assertEqual(sesion.llamadas[-1][4]["Authorization"], "Bearer tok-2")

    def test_422_es_rechazo_con_los_campos_explicados(self):
        sesion = SesionFalsa(token(), Respuesta(422, {
            "status": "Validation error",
            "message": "Error de validación",
            "data": {"errors": {"customer.identification": ["El campo es obligatorio."]}},
        }))
        with self.assertRaises(ErrorPT) as ctx:
            cliente(sesion).validar_factura({})
        self.assertNotIsInstance(ctx.exception, ErrorTemporalPT)
        self.assertIn("customer.identification", str(ctx.exception))
        self.assertEqual(ctx.exception.payload["http_status"], 422)

    def test_409_factura_pendiente_bloquea_pero_es_temporal(self):
        sesion = SesionFalsa(token(), Respuesta(409, {
            "message": "Se encontró una factura pendiente por enviar a la DIAN"}))
        with self.assertRaises(ErrorTemporalPT) as ctx:
            cliente(sesion).validar_factura({})
        self.assertIn("pendiente", str(ctx.exception))

    def test_429_informa_la_espera(self):
        sesion = SesionFalsa(token(), Respuesta(429, {}, headers={"Retry-After": "37"}))
        with self.assertRaises(ErrorTemporalPT) as ctx:
            cliente(sesion).rangos_numeracion()
        self.assertIn("37", str(ctx.exception))

    def test_caidas_de_red_y_500_son_temporales(self):
        for falla in (Respuesta(503, {"message": "mantenimiento"}),
                      requests.Timeout("lento"), requests.ConnectionError("sin red")):
            cache.clear()
            sesion = SesionFalsa(token(), falla)
            with self.assertRaises(ErrorTemporalPT):
                cliente(sesion).validar_factura({})

    def test_402_plan_sin_documentos(self):
        sesion = SesionFalsa(token(), Respuesta(402, {"message": "Payment required"}))
        with self.assertRaises(ErrorConfiguracionPT):
            cliente(sesion).validar_factura({})

    def test_rangos_lee_lista_directa_o_paginada(self):
        rangos = [{"id": 8, "prefix": "SETP", "from": 990000000, "to": 995000000}]
        for cuerpo in ({"data": rangos}, {"data": {"data": rangos, "pagination": {}}}):
            cache.clear()
            sesion = SesionFalsa(token(), Respuesta(200, cuerpo))
            self.assertEqual(cliente(sesion).rangos_numeracion()[0]["id"], 8)
        self.assertEqual(sesion.llamadas[-1][2]["filter[document]"], "21")


# ------------------------------------------------------- armado del JSON


class ConstruirFacturaTests(SimpleTestCase):
    def test_la_base_sale_del_precio_con_inc_incluido(self):
        doc = documento([linea("Brisket", 1, 35000)], 35000)
        cuerpo = construir_factura(doc, EMPRESA)
        item = cuerpo["items"][0]
        self.assertEqual(item["price"], "32407.41")               # 35.000 / 1,08
        self.assertEqual(item["taxes"], [{"code": "04", "rate": "8.00"}])
        self.assertEqual(item["quantity"], "1.00")
        self.assertEqual(item["unit_measure_code"], "94")
        self.assertEqual(cuerpo["payment_details"][0]["amount"], "35000.00")
        self.assertNotIn("cash_rounding_amount", cuerpo)          # 32407.41 + 2592.59 = 35.000

    def test_reproduce_el_ejemplo_de_redondeo_de_la_documentacion(self):
        # Mismas líneas del ejemplo «Redondeo en medios de pago» de Factus, donde
        # el total de la factura es 260.564,81.
        lineas = [linea("BOTELLA AGUA", 1, 190000), linea("Energizante", 2, 16000),
                  linea("MANZANA VERDE", 1, "38564.82", tipo="IVA", tarifa="19")]
        cuerpo = construir_factura(documento(lineas, "260550"), EMPRESA)
        precios = [i["price"] for i in cuerpo["items"]]
        self.assertEqual(precios, ["175925.93", "14814.81", "32407.41"])
        # Pagos 260.550 − total 260.564,81 = −14,81, igual que en la documentación.
        self.assertEqual(cuerpo["cash_rounding_amount"], "-14.81")

    def test_consumidor_final_y_medio_de_pago(self):
        cuerpo = construir_factura(documento([linea("Té", 1, 5000)], 5000, medio="48"), EMPRESA)
        self.assertEqual(cuerpo["customer"]["identification"], "222222222222")
        self.assertEqual(cuerpo["customer"]["identification_document_code"], "13")
        self.assertEqual(cuerpo["customer"]["legal_organization_code"], "2")
        self.assertEqual(cuerpo["payment_details"][0]["payment_method_code"], "48")
        self.assertFalse(cuerpo["send_email"])

    def test_cliente_con_nit_es_persona_juridica(self):
        empresa_cliente = SimpleNamespace(tipo_documento="31", numero_documento="900123456-7",
                                          nombre="ACME SAS", correo="f@acme.co", telefono="",
                                          direccion="")
        doc = documento([linea("Té", 1, 5000)], 5000, cliente_fiscal=empresa_cliente)
        cuerpo = construir_factura(doc, EMPRESA)
        self.assertEqual(cuerpo["customer"]["identification"], "900123456")   # sin DV
        self.assertEqual(cuerpo["customer"]["company"], "ACME SAS")
        self.assertEqual(cuerpo["customer"]["legal_organization_code"], "1")
        self.assertTrue(cuerpo["send_email"])

    def test_producto_exento_va_excluido(self):
        cuerpo = construir_factura(documento([linea("Agua", 2, 3000, tipo="EXENTO", tarifa="0")],
                                             6000), EMPRESA)
        self.assertEqual(cuerpo["items"][0]["price"], "3000.00")
        self.assertEqual(cuerpo["items"][0]["taxes"], [{"is_excluded": True}])

    def test_rango_y_referencia(self):
        cuerpo = construir_factura(documento([linea("Té", 1, 5000)], 5000, rango=389), EMPRESA)
        self.assertEqual(cuerpo["numbering_range_id"], 389)
        self.assertEqual(cuerpo["reference_code"], "CLD-CULTURABRISKET-7")

    def test_diferencia_absurda_no_se_manda(self):
        with self.assertRaises(ErrorPT):
            construir_factura(documento([linea("Té", 1, 5000)], 9000), EMPRESA)


# ------------------------------------------------------ lectura de respuesta


@override_settings(CACHES=CACHE_LOCAL)
class InterpretarTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def _proveedor(self, *respuestas):
        sesion = SesionFalsa(token(), *respuestas)
        return ProveedorFactus(EMPRESA, cliente=cliente(sesion)), sesion

    def _doc(self):
        doc = documento([linea("Brisket", 1, 35000)], 35000)
        doc.save = lambda **kw: None
        return doc

    def test_validada_por_la_dian(self):
        proveedor, _ = self._proveedor(Respuesta(201, {
            "status": "Created",
            "data": {"number": "SETP990000550", "is_validated": True, "cufe": "abc123",
                     "errors": {"FAJ44b": "Regla: FAJ44b, Notificación: nombre distinto"},
                     "links": {"qr": "https://catalogo-vpfe.dian.gov.co/document/searchqr?x",
                               "public_url": "https://factus.com.co/p/abc"}},
        }))
        r = proveedor.emitir(self._doc(), {"mesa": 4})
        self.assertTrue(r.aceptada)
        self.assertEqual(r.numero_completo, "SETP990000550")
        self.assertEqual(r.cufe, "abc123")
        self.assertIn("dian.gov.co", r.qr_url)
        self.assertEqual(r.crudo["enviado"]["observation"], "Mesa 4 · Cloudin")

    def test_rechazo_borra_la_factura_para_no_bloquear(self):
        proveedor, sesion = self._proveedor(
            Respuesta(201, {"data": {"is_validated": False,
                                     "errors": {"FAJ43b": "Regla: FAJ43b, Rechazo: NIT errado"}}}),
            Respuesta(200, {"message": "eliminada"}),
        )
        with self.assertRaises(ErrorPT) as ctx:
            proveedor.emitir(self._doc(), {})
        self.assertNotIsInstance(ctx.exception, ErrorTemporalPT)
        self.assertIn("Rechazo", str(ctx.exception))
        metodo, url, *_ = sesion.llamadas[-1]
        self.assertEqual(metodo, "DELETE")
        self.assertTrue(url.endswith("/v2/bills/destroy/reference/CLD-CULTURABRISKET-7"))

    def test_dian_demorada_se_reintenta_sin_borrar(self):
        proveedor, sesion = self._proveedor(Respuesta(201, {"data": {
            "is_validated": False,
            "errors": {"RUT01": "Regla: RUT01, Notificación: se validará después"},
        }}))
        with self.assertRaises(ErrorTemporalPT):
            proveedor.emitir(self._doc(), {})
        self.assertNotIn("DELETE", [ll[0] for ll in sesion.llamadas])

    def test_es_rechazo_distingue_notificaciones(self):
        self.assertFalse(es_rechazo({"FAJ44b": "Regla: FAJ44b, Notificación"}))
        self.assertTrue(es_rechazo({"FAJ43b": "Regla: FAJ43b, Rechazo: x"}))
        self.assertFalse(es_rechazo({}))

    def test_referencia_estable(self):
        doc = self._doc()
        self.assertEqual(referencia_de(doc), referencia_de(doc))
        doc.referencia_pt = "CLD-GUARDADA-1"
        self.assertEqual(referencia_de(doc), "CLD-GUARDADA-1")


@override_settings(CACHES=CACHE_LOCAL)
class DescuentoTests(SimpleTestCase):
    """El descuento de la cuenta viaja a la factura como discount_rate por línea."""

    def test_descuento_se_reparte_y_factus_lo_recibe(self):
        from apps.billing.taxes import MotorTributario

        motor = MotorTributario([(None, "INC", 8)])
        calculo = motor.calcular([("Brisket", 2, Decimal("35000"), None, Decimal("10"))])
        self.assertEqual(calculo.total_general, Decimal("63000.00"))       # 70.000 − 10 %
        detalle = calculo.como_dict()["lineas"][0]
        self.assertEqual(detalle["descuento"]["valor"], "7000.00")
        cuerpo = construir_factura(documento([detalle], calculo.total_general), EMPRESA)
        item = cuerpo["items"][0]
        self.assertEqual(item["discount_rate"], "10.00")
        self.assertEqual(item["price"], "32407.41")                         # el precio va sin descuento
        self.assertLessEqual(abs(Decimal(cuerpo.get("cash_rounding_amount", "0"))), Decimal("1"))

    def test_sin_descuento_no_cambia_nada(self):
        from apps.billing.taxes import MotorTributario

        calculo = MotorTributario([(None, "INC", 8)]).calcular([("Brisket", 1, Decimal("35000"), None)])
        self.assertEqual(calculo.total_general, Decimal("35000.00"))
        cuerpo = construir_factura(documento(calculo.como_dict()["lineas"], "35000"), EMPRESA)
        self.assertEqual(cuerpo["items"][0]["discount_rate"], "0.00")
