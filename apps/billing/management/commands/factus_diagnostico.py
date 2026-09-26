"""Prueba la conexión con Factus sin tocar ninguna factura.

    python manage.py factus_diagnostico
    python manage.py factus_diagnostico --tenant culturabrisket --sincronizar-rangos

Sin --tenant usa las credenciales globales del .env. Con --tenant usa las del
restaurante si tiene propias, y con --sincronizar-rangos copia sus rangos de
numeración de Factus a las resoluciones de Cloudin.
"""

from django.core.management.base import BaseCommand, CommandError

from apps.billing.providers.base import ErrorPT, ErrorTemporalPT
from apps.billing.providers.factus import (
    ClienteFactus,
    credenciales_de,
    nombre_empresa,
    sincronizar_rangos,
)


class Command(BaseCommand):
    help = "Autentica contra Factus y lista la empresa y los rangos de numeración."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", help="slug del restaurante")
        parser.add_argument("--sincronizar-rangos", action="store_true")

    def handle(self, *args, **opts):
        empresa = None
        contexto = None
        if opts["tenant"]:
            from apps.billing.services import empresa_actual
            from apps.tenants.context import tenant_context
            from apps.tenants.models import Tenant

            tenant = Tenant.objects.filter(slug=opts["tenant"]).first()
            if tenant is None:
                raise CommandError(f"No existe el restaurante «{opts['tenant']}».")
            contexto = tenant_context(tenant)
            contexto.__enter__()
            empresa = empresa_actual()

        try:
            self._diagnosticar(empresa, opts["sincronizar_rangos"])
        finally:
            if contexto:
                contexto.__exit__(None, None, None)

    def _paso(self, texto, ok=True):
        estilo = self.style.SUCCESS if ok else self.style.ERROR
        self.stdout.write(estilo(("  OK   " if ok else "  FALLA ") + texto))

    def _diagnosticar(self, empresa, sincronizar):
        propias = credenciales_de(empresa) if empresa else {}
        cliente = ClienteFactus.desde_configuracion(propias)
        origen = "del restaurante" if propias else "globales (.env)"
        self.stdout.write(f"Factus · {cliente.url} · credenciales {origen}")
        self.stdout.write(f"  ambiente: {'SANDBOX (pruebas)' if cliente.es_sandbox else 'PRODUCCIÓN'}")

        if not cliente.configurado:
            self._paso("faltan credenciales: revisa FACTUS_* en el .env", ok=False)
            return

        try:
            cliente.token(forzar=True)
            self._paso("token OAuth emitido")
        except (ErrorPT, ErrorTemporalPT) as e:
            self._paso(f"autenticación: {e}", ok=False)
            detalle = (e.payload or {}).get("respuesta")
            if detalle:
                self.stdout.write(f"         respuesta de Factus: {detalle}")
            return

        try:
            datos = cliente.empresa()
            nombre = nombre_empresa(datos)
            self._paso(f"empresa: {nombre} · NIT {datos.get('nit', '—')}")
        except (ErrorPT, ErrorTemporalPT) as e:
            self._paso(f"empresa: {e}", ok=False)

        try:
            rangos = cliente.rangos_numeracion()
            self._paso(f"{len(rangos)} rango(s) de factura activos")
            for r in rangos:
                self.stdout.write(
                    f"         id {r.get('id')} · {r.get('prefix', '')} {r.get('from')}–{r.get('to')}"
                    f" · siguiente {r.get('current')} · resolución {r.get('resolution_number')}"
                )
        except (ErrorPT, ErrorTemporalPT) as e:
            self._paso(f"rangos: {e}", ok=False)
            return

        if sincronizar:
            if empresa is None:
                self._paso("para sincronizar rangos hace falta --tenant", ok=False)
                return
            resultado = sincronizar_rangos(empresa, cliente)
            self._paso(
                f"rangos sincronizados: {resultado['creados']} nuevo(s), "
                f"{resultado['actualizados']} actualizado(s)"
            )
