"""Panel del restaurante: mesas, mensajes, cocina, configuración e impresión."""

from decimal import Decimal
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.validators import URLValidator, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_POST

from apps.catalog.models import Category
from apps.dining.models import Table
from apps.orders.models import Order, TableSession


def panel_view(solo_admin=False, requiere_turno=True, menu=False):
    """Resuelve el restaurante de la petición y controla quién puede entrar.

    En vez de un 404 seco, cada caso tiene su salida:
      - superusuario sin restaurante elegido -> lo mandamos al panel maestro,
      - usuario de otro restaurante o sin permiso -> página de "sin acceso",
      - plan «Menú digital» en una pantalla del plan completo -> al Inicio,
      - sin turno abierto -> a la pantalla de turnos, a abrirlo. Nada de la
        plataforma funciona hasta que alguien abre el turno de caja; solo las
        pantallas marcadas con `requiere_turno=False` quedan disponibles.

    `menu=True` marca las pantallas del menú digital (Mi menú, Personalizar,
    Mesas y QR, Cuenta): existen en los dos planes y nunca exigen turno.
    """
    if menu:
        requiere_turno = False

    def decorador(vista):
        @wraps(vista)
        @login_required
        def envoltura(request, *args, **kwargs):
            tenant = getattr(request, "tenant", None)

            if tenant is None:
                if request.user.is_superuser:
                    messages.warning(request, "Elige primero un restaurante.")
                    return redirect("master:home")
                raise PermissionDenied("No se identificó el restaurante de esta dirección.")

            if not request.user.is_superuser:
                membership = getattr(request.user, "tenant_membership", None)
                if membership is None or membership.tenant_id != tenant.id:
                    raise PermissionDenied("No tienes acceso a este restaurante.")
                if solo_admin and not membership.es_admin:
                    raise PermissionDenied(
                        "Esta sección es solo para el administrador del restaurante. "
                        "Pídele a quien administra el local que haga este cambio."
                    )

            request.tenant = tenant

            # El plan «Menú digital» solo tiene las pantallas del menú: lo demás
            # (caja, cocina, facturación…) lleva al Inicio.
            if tenant.es_plan_menu and not menu:
                return redirect("panel:inicio")

            # Los términos y la política se aceptan una vez; sin eso no se entra.
            from .legal import ya_acepto

            if not ya_acepto(request):
                from urllib.parse import quote

                return redirect(f"{reverse('legal-aceptar')}?next={quote(request.get_full_path())}")

            # El superusuario no entra a un restaurante solo por tener la sesión
            # del panel maestro abierta: confirma su clave (modo soporte).
            if request.user.is_superuser:
                from urllib.parse import quote

                from .seguridad import soporte_vigente

                if not soporte_vigente(request, tenant):
                    return redirect(f"{reverse('panel:soporte')}?tenant={tenant.slug}&next={quote(request.get_full_path())}")
                request.modo_soporte = True

            if requiere_turno and not tenant.es_plan_menu:
                from apps.shifts.services import MENSAJE_SIN_TURNO, turno_actual

                if turno_actual() is None:
                    messages.warning(request, MENSAJE_SIN_TURNO)
                    return redirect("panel:turnos")

            return vista(request, *args, **kwargs)

        return envoltura

    return decorador


@panel_view()
def tables(request):
    return render(request, "panel/tables.html",
                  {"mesas": Table.objects.filter(is_active=True), "seccion": "mesas"})


@panel_view()
def table_detail(request, table_id):
    from apps.orders.novedades import es_admin

    table = get_object_or_404(Table, pk=table_id, is_active=True)
    categorias = Category.objects.filter(is_active=True).prefetch_related("products")
    return render(
        request,
        "panel/table_detail.html",
        {
            "mesa": table,
            "cuenta": table.open_session,
            "categorias": categorias,
            "seccion": "mesas",
            # Un cajero necesita la clave del admin para anular, dar cortesías o descuentos.
            "es_admin": es_admin(request.user),
            # Lo que el JS necesita para elegir toppings al agregar.
            "productos_js": {
                p.id: {"nombre": p.name, "precio": float(p.precio_legacy), "opciones": p.opciones or [],
                       "observacion": p.permite_observacion, "foto": p.foto}
                for c in categorias for p in c.products.all() if p.is_available
            },
        },
    )


@panel_view()
def kitchen(request):
    return render(request, "panel/kitchen.html", {"seccion": "cocina"})


@panel_view()
def mensajes(request):
    """Bandeja de pedidos que llegan del sitio web, por mesa y cliente."""
    return render(request, "panel/mensajes.html", {"seccion": "mensajes"})


@panel_view(solo_admin=True)
def configuracion(request):
    """Mesas, menú y conexión con el sitio web del restaurante."""
    tenant = request.tenant

    if request.method == "POST":
        url = (request.POST.get("site_url") or "").strip()
        if url:
            try:
                URLValidator(schemes=["http", "https"])(url)
            except ValidationError:
                messages.warning(
                    request, "Esa dirección no es válida. Debe empezar por https:// o http://"
                )
                return redirect("panel:configuracion")
        ruta = (request.POST.get("table_page_path") or "/mesa.html").strip()
        if not ruta.startswith("/"):
            ruta = "/" + ruta
        tenant.table_page_path = ruta[:120]
        tenant.site_url = url
        if not url:
            tenant.site_last_seen = None
        tenant.save(update_fields=["site_url", "site_last_seen", "table_page_path"])
        messages.success(
            request,
            f"Sitio web autorizado: {tenant.site_origin}" if url else "Sitio web desconectado.",
        )
        return redirect("panel:configuracion")

    return render(request, "panel/configuracion.html", {"seccion": "config"})


@panel_view(menu=True)
def inicio(request):
    """La portada del panel. Con el plan «Menú digital», el Inicio del menú
    (apps/panel/duenio.py); con el completo, cómo va el negocio de un vistazo,
    qué viene hoy y qué conviene revisar (y eso sí exige turno abierto)."""
    if request.tenant.es_plan_menu:
        from .duenio import inicio_menu

        return inicio_menu(request)

    from apps.shifts.services import MENSAJE_SIN_TURNO, turno_actual

    if turno_actual() is None:
        messages.warning(request, MENSAJE_SIN_TURNO)
        return redirect("panel:turnos")
    return _inicio_completo(request)


def _inicio_completo(request):
    from apps.control import services as cs
    from apps.control.recomendaciones import recomendaciones
    from apps.reservas import services as rs
    from apps.reservas.models import Reserva

    from .reservas import _decorar

    usuario = request.user.get_full_name() or request.user.username
    cs.analizar_si_hace_falta(usuario)
    desde, hasta, _ = cs.periodo("semana")
    tarjetas, datos = recomendaciones(limite=3)
    hoy = [_decorar(r, request.tenant.name) for r in
           Reserva.objects.filter(fecha=timezone.localdate(),
                                  estado__in=[Reserva.PENDING, Reserva.CONFIRMED, Reserva.ARRIVED, Reserva.SEATED])
           .select_related("mesa").order_by("hora")[:6]]
    return render(request, "panel/inicio.html", {
        "seccion": "inicio",
        "hoy": timezone.localdate(),
        "recomendaciones": tarjetas,
        "top": datos["filas"][:5],
        "fugas": cs.fugas(desde, hasta),
        "alertas": cs.resumen_alertas(),
        "reservas_hoy": hoy,
        "reservas_resumen": rs.resumen(),
    })


@panel_view(requiere_turno=False)  # solo consulta: el informe de un turno cerrado enlaza aquí
def documento(request, documento_id):
    """El comprobante de una factura: qué se envió, qué respondió la DIAN y cuándo."""
    import json

    from apps.billing.models import DocumentoFiscal
    from apps.billing.services import empresa_actual

    doc = get_object_or_404(
        DocumentoFiscal.objects.select_related("cliente", "resolucion", "sesion__table"),
        pk=documento_id,
    )
    return render(
        request,
        "panel/documento.html",
        {
            "seccion": "facturacion",
            "d": doc,
            "empresa": empresa_actual(),
            "auditoria": doc.auditoria.all(),
            "respuesta_pt": json.dumps(doc.respuesta_pt, indent=2, ensure_ascii=False),
        },
    )


@panel_view()
@require_POST
def documento_reintentar(request, documento_id):
    """Vuelve a mandar al proveedor un documento que quedó en contingencia."""
    from apps.billing.models import DocumentoFiscal
    from apps.billing.services import transmitir

    doc = get_object_or_404(DocumentoFiscal, pk=documento_id)
    if not doc.reintentable:
        messages.warning(request, "Ese documento no está pendiente de envío.")
    else:
        doc = transmitir(doc)
        if doc.estado == doc.ACEPTADA:
            messages.success(request, f"Enviada y aceptada: {doc.numero_completo}.")
        elif doc.estado == doc.CONTINGENCIA:
            messages.warning(request, "El proveedor sigue sin responder. Se reintentará solo.")
        else:
            messages.warning(request, f"Rechazada: {doc.motivo_rechazo}")
    return redirect("panel:documento", documento_id=doc.id)


def _medio_pago(request) -> str:
    from apps.billing.models import DocumentoFiscal

    elegido = request.POST.get("medio_pago", DocumentoFiscal.EFECTIVO)
    validos = dict(DocumentoFiscal.MEDIOS_PAGO)
    return elegido if elegido in validos else DocumentoFiscal.EFECTIVO


@panel_view()
@require_POST
def cerrar_y_facturar(request, session_id):
    """Cierra la mesa y emite su factura, en un solo movimiento.

    La regla de oro: la mesa se cierra pase lo que pase con la facturación. Si
    el proveedor falla, el documento queda en contingencia y el restaurante
    sigue trabajando.
    """
    from django.core.exceptions import ValidationError as VE

    from apps.billing.services import facturar_sesion
    from apps.shifts.propinas import registrar_propina

    from .turnos import _plata

    session = get_object_or_404(TableSession, pk=session_id)
    if session.status == TableSession.STATUS_OPEN:
        session.close()

    medio = _medio_pago(request)
    try:
        registrar_propina(session, _plata(request.POST.get("propina"), 0), medio)
    except VE as e:
        messages.warning(request, f"No se anotó la propina: {e.messages[0]}")

    try:
        documento = facturar_sesion(session, medio_pago=medio)
    except VE as e:
        messages.warning(
            request,
            f"La mesa quedó cerrada y la venta registrada, pero no se pudo facturar: {e.messages[0]}",
        )
        return redirect("panel:facturacion")

    # Aterriza en el comprobante e imprime la factura del cliente.
    return redirect(reverse("panel:documento", kwargs={"documento_id": documento.id}) + "?imprimir=1")


@panel_view(solo_admin=True)
def empleado_nuevo(request):
    """El alta va en su propia pantalla.

    Antes el formulario completo vivía debajo del reloj y la pantalla se veía
    cargada. Ahora la lista solo tiene un botón, y los campos se llenan aquí.
    """
    from apps.staffing.forms import EmpleadoForm

    form = EmpleadoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        empleado = form.save()
        messages.success(
            request,
            f"{empleado.nombre} quedó registrado"
            + (f" con el código {empleado.codigo}." if empleado.codigo else "."),
        )
        return redirect("panel:empleados")
    return render(
        request,
        "panel/empleado_form.html",
        {"seccion": "empleados", "form": form, "es_nuevo": True},
    )


@panel_view(solo_admin=True)
def empleado_editar(request, empleado_id):
    from apps.staffing.forms import EmpleadoForm
    from apps.staffing.models import Empleado

    empleado = get_object_or_404(Empleado, pk=empleado_id)
    form = EmpleadoForm(request.POST or None, instance=empleado)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"{empleado.nombre} actualizado.")
        return redirect("panel:empleados")
    return render(
        request,
        "panel/empleado_form.html",
        {"seccion": "empleados", "form": form, "empleado": empleado},
    )


@panel_view(solo_admin=True)
def empleados(request):
    """Cloudin Employees: quién trabaja, cuántas horas lleva y cuánto cuesta."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.staffing.models import Empleado, Turno

    hoy = timezone.localdate()
    lunes = hoy - timedelta(days=hoy.weekday())
    inicio_semana = timezone.make_aware(
        timezone.datetime.combine(lunes, timezone.datetime.min.time())
    )
    inicio_dia = timezone.make_aware(
        timezone.datetime.combine(hoy, timezone.datetime.min.time())
    )

    gente = []
    for e in Empleado.objects.filter(activo=True):
        horas_hoy = e.horas_entre(inicio_dia, timezone.now())
        horas_semana = e.horas_entre(inicio_semana, timezone.now())
        gente.append({
            "e": e,
            "trabajando": e.esta_trabajando,
            "turno": e.turno_abierto,
            "horas_hoy": horas_hoy,
            "horas_semana": horas_semana,
            "costo_semana": (horas_semana * e.costo_hora()).quantize(Decimal("0.01")),
        })

    return render(
        request,
        "panel/empleados.html",
        {
            "seccion": "empleados",
            "gente": gente,
            "trabajando_ahora": sum(1 for g in gente if g["trabajando"]),
            "horas_hoy": sum((g["horas_hoy"] for g in gente), Decimal("0")),
            "horas_semana": sum((g["horas_semana"] for g in gente), Decimal("0")),
            "costo_semana": sum((g["costo_semana"] for g in gente), Decimal("0")),
            "turnos": Turno.objects.select_related("empleado")[:25],
            "inactivos": Empleado.objects.filter(activo=False).count(),
        },
    )


@panel_view()
@require_POST
def empleado_marcar(request):
    """El reloj: la persona teclea su código y el sistema decide si entra o sale."""
    from apps.staffing.models import Empleado

    codigo = (request.POST.get("codigo") or "").strip()
    empleado = Empleado.objects.filter(codigo=codigo, activo=True).first() if codigo else None
    if empleado is None:
        empleado = Empleado.objects.filter(pk=request.POST.get("empleado_id"), activo=True).first()

    if empleado is None:
        messages.warning(request, "No encontramos a nadie con ese código.")
        return redirect("panel:empleados")

    from django.utils import timezone

    turno, que = empleado.marcar()
    # timezone.localtime: las horas se guardan en UTC, pero se muestran en la
    # hora de Colombia, igual que en el resto del panel.
    if que == "entrada":
        hora = timezone.localtime(turno.entrada)
        messages.success(request, f"{empleado.nombre} entró a las {hora:%H:%M}.")
    else:
        hora = timezone.localtime(turno.salida)
        messages.success(
            request,
            f"{empleado.nombre} salió a las {hora:%H:%M} · {turno.horas()} h trabajadas.",
        )
    return redirect("panel:empleados")


@panel_view(solo_admin=True)
@require_POST
def empleado_activo(request, empleado_id):
    from apps.staffing.models import Empleado

    empleado = get_object_or_404(Empleado, pk=empleado_id)
    empleado.activo = not empleado.activo
    empleado.save(update_fields=["activo"])
    messages.success(
        request, f"{empleado.nombre} quedó {'activo' if empleado.activo else 'inactivo'}."
    )
    return redirect("panel:empleados")


@panel_view(solo_admin=True)
def ventas(request):
    """Tablero de ventas: gráficas, los platos que más venden y qué hacer con cada uno."""
    from datetime import timedelta

    from apps.control import recomendaciones as rc

    try:
        dias = max(7, min(int(request.GET.get("dias", 30)), 180))
    except ValueError:
        dias = 30
    hasta = timezone.localdate()
    desde = hasta - timedelta(days=dias - 1)
    tarjetas, datos = rc.recomendaciones(desde, hasta, limite=8)
    return render(request, "panel/ventas.html", {
        "seccion": "ventas",
        "dias": dias,
        "recomendaciones": tarjetas,
        "productos": datos["filas"],
        "total_productos": datos["total"],
        "matriz": rc.matriz(datos["filas"]),
        "pares": rc.pares(desde, hasta)[:5],
    })


@panel_view(solo_admin=True)
def facturacion(request):
    """Habilitación para facturar y documentos emitidos."""
    from apps.billing.forms import EmpresaForm, ResolucionForm
    from apps.billing.models import DocumentoFiscal, EmpresaFiscal, Impuesto
    from apps.billing.services import alertas, empresa_actual

    empresa = empresa_actual()
    accion = request.POST.get("accion") if request.method == "POST" else None

    form_empresa = EmpresaForm(instance=empresa)
    form_resolucion = ResolucionForm()

    if accion == "empresa":
        form_empresa = EmpresaForm(request.POST, instance=empresa)
        if form_empresa.is_valid():
            empresa = form_empresa.save()
            if not Impuesto.objects.exists():
                # Restaurantes: INC del 8% sobre todo el menú, hasta que se
                # configure otra cosa.
                Impuesto.objects.create(tipo=Impuesto.INC, tarifa=8)
            messages.success(request, "Datos fiscales guardados.")
            return redirect("panel:facturacion")

    elif accion == "resolucion" and empresa:
        form_resolucion = ResolucionForm(request.POST)
        if form_resolucion.is_valid():
            resolucion = form_resolucion.save(commit=False)
            resolucion.empresa = empresa
            resolucion.save()
            messages.success(request, f"Resolución {resolucion.numero_resolucion} registrada.")
            return redirect("panel:facturacion")

    elif accion == "proveedor" and empresa:
        elegido = request.POST.get("proveedor")
        if elegido in ("simulado", "factus"):
            empresa.proveedor = elegido
            empresa.save(update_fields=["proveedor"])
            messages.success(request, f"Proveedor tecnológico: {elegido.capitalize()}.")
        return redirect(reverse("panel:facturacion") + "#proveedor")

    elif accion in ("factus_probar", "factus_rangos", "factus_credenciales") and empresa:
        return _acciones_factus(request, empresa, accion)

    elif accion == "certificado" and empresa:
        # Todavía no se sube el archivo: se guarda la constancia de que existe.
        empresa.certificado_ref = (request.POST.get("certificado_ref") or "").strip()[:200]
        empresa.save(update_fields=["certificado_ref"])
        messages.success(request, "Certificado registrado.")
        return redirect("panel:facturacion")

    # Con los tres requisitos listos, el restaurante pasa solo a «en pruebas»:
    # ya puede emitir contra el proveedor. El salto a «habilitado» lo da el PT
    # cuando termina el set de pruebas de la DIAN.
    if empresa and empresa.estado_habilitacion == EmpresaFiscal.NO_HABILITADO:
        if all(empresa.requisitos().values()):
            empresa.estado_habilitacion = EmpresaFiscal.EN_PRUEBAS
            empresa.save(update_fields=["estado_habilitacion"])

    documentos = (
        DocumentoFiscal.objects.select_related("cliente", "sesion__table")[:40] if empresa else []
    )
    from apps.billing.providers.factus import ClienteFactus, credenciales_de

    propias = credenciales_de(empresa) if empresa else {}
    cliente_factus = ClienteFactus.desde_configuracion(propias)
    return render(
        request,
        "panel/facturacion.html",
        {
            "seccion": "facturacion",
            "empresa": empresa,
            "form_empresa": form_empresa,
            "form_resolucion": form_resolucion,
            "resoluciones": empresa.resoluciones.all() if empresa else [],
            "documentos": documentos,
            "alertas": alertas(),
            "requisitos": empresa.requisitos() if empresa else {},
            "ESTADOS": EmpresaFiscal.ESTADOS,
            "factus": {
                "propias": bool(propias),
                "configurado": cliente_factus.configurado,
                "sandbox": cliente_factus.es_sandbox,
            },
        },
    )


def _acciones_factus(request, empresa, accion):
    """Probar la conexión, traer rangos y guardar credenciales propias."""
    from apps.billing.providers.base import ErrorPT, ErrorTemporalPT
    from apps.billing.providers.factus import (
        ClienteFactus,
        credenciales_de,
        guardar_credenciales,
        nombre_empresa,
        sincronizar_rangos,
    )

    volver = reverse("panel:facturacion") + "#proveedor"

    if accion == "factus_credenciales":
        if request.POST.get("borrar"):
            guardar_credenciales(empresa, {})
            messages.success(request, "Se volverán a usar las credenciales de Cloudin.")
        else:
            from django.core.exceptions import ValidationError as VE

            campos = ("url", "client_id", "client_secret", "username", "password")
            try:
                guardar_credenciales(empresa, {c: request.POST.get(c, "") for c in campos})
            except VE as e:
                messages.warning(request, e.messages[0])
                return redirect(volver)
            messages.success(request, "Credenciales de Factus guardadas (cifradas).")
        return redirect(volver)

    cliente = ClienteFactus.desde_configuracion(credenciales_de(empresa))
    try:
        if accion == "factus_probar":
            cliente.token(forzar=True)
            datos = cliente.empresa()
            rangos = cliente.rangos_numeracion()
            nombre = nombre_empresa(datos)
            ambiente = "sandbox" if cliente.es_sandbox else "producción"
            messages.success(
                request,
                f"Conectado a Factus ({ambiente}): {nombre}, "
                f"{len(rangos)} rango(s) de factura activos.",
            )
        else:
            resultado = sincronizar_rangos(empresa, cliente)
            messages.success(
                request,
                f"Rangos traídos de Factus: {resultado['creados']} nuevo(s), "
                f"{resultado['actualizados']} actualizado(s).",
            )
    except (ErrorPT, ErrorTemporalPT) as e:
        messages.warning(request, f"Factus: {e}")
    return redirect(volver)


@panel_view()
@require_POST
def facturar(request, session_id):
    """Convierte una cuenta de mesa en documento fiscal."""
    from django.core.exceptions import ValidationError as VE

    from apps.billing.services import facturar_sesion

    session = get_object_or_404(TableSession, pk=session_id)
    try:
        documento = facturar_sesion(session, medio_pago=_medio_pago(request))
    except VE as e:
        messages.warning(request, e.messages[0])
        return redirect("panel:facturacion")

    if documento.estado == documento.ACEPTADA:
        messages.success(request, f"Factura {documento.numero_completo} aceptada por la DIAN.")
    elif documento.estado == documento.CONTINGENCIA:
        messages.warning(
            request,
            "El proveedor no respondió. La factura quedó en contingencia y se reintenta sola; "
            "la mesa queda cerrada igual.",
        )
    else:
        messages.warning(request, f"Rechazada: {documento.motivo_rechazo}")
    return redirect("panel:facturacion")


def _qr_data_uri(texto: str) -> str:
    """El QR como imagen incrustada, para que la hoja se imprima sin pedir nada."""
    import base64
    import io

    import qrcode

    qr = qrcode.QRCode(box_size=10, border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(texto)
    qr.make(fit=True)
    buffer = io.BytesIO()
    qr.make_image(fill_color="black", back_color="white").save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


@panel_view(solo_admin=True)
def mesas_qr(request):
    """Hoja imprimible con un QR por mesa, para pegar en cada una."""
    tenant = request.tenant
    mesas = []
    for mesa in Table.objects.filter(is_active=True):
        enlace = tenant.qr_link(mesa.token)
        mesas.append({"mesa": mesa, "enlace": enlace, "qr": _qr_data_uri(enlace) if enlace else ""})
    return render(request, "panel/mesas_qr.html", {"mesas": mesas, "seccion": "config"})


@panel_view()
@xframe_options_sameorigin
def print_order(request, order_id):
    """Comanda en formato tirilla — dispara el diálogo de impresión del navegador."""
    order = get_object_or_404(Order, pk=order_id)
    return render(request, "panel/print_order.html", {"pedido": order})


@panel_view()
@xframe_options_sameorigin
def print_bill(request, session_id):
    """Precuenta de la mesa, o el comprobante de una mesa cerrada sin facturar.
    No es factura electrónica: lo dice impreso."""
    session = get_object_or_404(TableSession, pk=session_id)
    lineas = []
    for order in session.orders.exclude(status=Order.STATUS_CANCELLED):
        lineas.extend(order.items.all())
    total = session.current_total()
    return render(
        request,
        "panel/print_bill.html",
        {"cuenta": session, "lineas": lineas, "total": total,
         "propina": session.propina, "total_con_propina": total + (session.propina or 0)},
    )


@panel_view(requiere_turno=False)  # reimprimir la factura de ayer no mueve la operación
@xframe_options_sameorigin
def print_factura(request, documento_id):
    """La factura del cliente: la representación gráfica, con resolución, CUFE y QR."""
    from apps.billing.models import DocumentoFiscal
    from apps.billing.services import empresa_actual

    doc = get_object_or_404(
        DocumentoFiscal.objects.select_related("cliente", "resolucion", "sesion__table", "sesion__mesero"),
        pk=documento_id,
    )
    propina = doc.sesion.propina if doc.sesion_id else 0
    return render(request, "panel/print_factura.html", {
        "d": doc,
        "empresa": empresa_actual(),
        "qr": _qr_data_uri(doc.qr_url) if doc.qr_url else "",
        "propina": propina,
        "total_con_propina": doc.total_general + (propina or 0),
    })
