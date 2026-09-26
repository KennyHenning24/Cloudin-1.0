"""Cloudin Reservas en el panel: la agenda del día, el recorrido de cada reserva,
los clientes con su historial y los horarios que se ofrecen.

No pide turno abierto: revisar la agenda de mañana o confirmar una reserva no
mueve la caja. Sentar a alguien en su mesa sí lo pide, porque abre la cuenta.
"""

from datetime import date, timedelta

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count, Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.dining.models import Table
from apps.orders.models import TableSession
from apps.reservas import services as rs
from apps.reservas.forms import AjustesForm, BloqueoForm, ReservaForm, ServicioForm
from apps.reservas.models import AjustesReservas, BloqueoFecha, Cliente, Reserva, ServicioReserva

from .views import panel_view

COLOR_ESTADO = {
    Reserva.PENDING: "amarillo", Reserva.CONFIRMED: "cielo", Reserva.ARRIVED: "lavanda",
    Reserva.SEATED: "durazno", Reserva.COMPLETED: "menta", Reserva.CANCELLED: "gris", Reserva.NO_SHOW: "rosa",
}


def _quien(request):
    return request.user.get_full_name() or request.user.username


def _fecha(valor, defecto):
    try:
        return date.fromisoformat(valor)
    except (TypeError, ValueError):
        return defecto


def _decorar(reserva, restaurante):
    reserva.color = COLOR_ESTADO.get(reserva.estado, "gris")
    reserva.whatsapp_recordatorio = rs.enlace_recordatorio(reserva, restaurante)
    return reserva


@panel_view(requiere_turno=False)
def reservas(request):
    hoy = timezone.localdate()
    dia = _fecha(request.GET.get("fecha"), hoy)
    restaurante = request.tenant.name

    del_dia = [_decorar(r, restaurante) for r in
               Reserva.objects.filter(fecha=dia).select_related("mesa", "servicio", "cliente")
               .order_by("hora", "creada_en")]
    vigentes = [r for r in del_dia if r.estado != Reserva.CANCELLED]

    # La tira de días: cuántas reservas y personas trae cada uno.
    inicio = min(dia, hoy) if dia >= hoy - timedelta(days=3) else dia
    conteos = {
        f["fecha"]: f for f in Reserva.objects.filter(fecha__gte=inicio, fecha__lte=inicio + timedelta(days=13))
        .exclude(estado=Reserva.CANCELLED).values("fecha").annotate(n=Count("id"), p=Sum("personas"))
    }
    dias = []
    for i in range(14):
        f = inicio + timedelta(days=i)
        c = conteos.get(f, {})
        dias.append({"fecha": f, "n": c.get("n", 0), "p": c.get("p", 0) or 0, "hoy": f == hoy, "on": f == dia})

    # Por servicio, como se piensa el día en un restaurante: almuerzo, noche…
    grupos = {}
    for r in del_dia:
        grupos.setdefault(r.servicio_nombre or "Reservas", []).append(r)

    ocupadas = set(TableSession.objects.filter(status=TableSession.STATUS_OPEN).values_list("table_id", flat=True))
    mesas_libres = [m for m in Table.objects.filter(is_active=True).order_by("number") if m.id not in ocupadas]

    return render(request, "panel/reservas.html", {
        "seccion": "reservas",
        "sub": "agenda",
        "dia": dia,
        "hoy": hoy,
        "dias": dias,
        "grupos": grupos,
        "vigentes": vigentes,
        "resumen": rs.resumen(dia),
        "recordar": [_decorar(r, restaurante) for r in rs.pendientes_de_recordar()],
        "atrasadas": rs.atrasadas(),
        "pendientes": Reserva.objects.filter(estado=Reserva.PENDING, fecha__gte=hoy).select_related("mesa")[:10],
        "proxima": rs.proxima(),
        "mesas_libres": mesas_libres,
        "servicios": ServicioReserva.objects.filter(activo=True).exists(),
        "anterior": dia - timedelta(days=1),
        "siguiente": dia + timedelta(days=1),
        "ajustes": AjustesReservas.actuales(),
    })


@panel_view(requiere_turno=False)
def reserva_nueva(request):
    inicial = {"fecha": _fecha(request.GET.get("fecha"), timezone.localdate()), "origen": "telefono"}
    form = ReservaForm(request.POST or None, initial=inicial)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        try:
            reserva = rs.crear_reserva(
                servicio=d["servicio"], fecha=d["fecha"], hora=d["hora"], personas=d["personas"],
                nombre=d["nombre"], telefono=d["telefono"], zona=d["zona"], observaciones=d["observaciones"],
                origen=d["origen"], mesa=d["mesa"], usuario=_quien(request), desde_panel=True,
            )
        except ValidationError as e:
            messages.warning(request, e.messages[0])
        else:
            messages.success(request, f"Reserva {reserva.codigo} para {reserva.nombre}, {reserva.cuando_texto()}"
                                      + (f", mesa {reserva.mesa.number}." if reserva.mesa_id else "."))
            return redirect(reverse("panel:reservas") + f"?fecha={reserva.fecha.isoformat()}")
    return render(request, "panel/reserva_form.html", {"seccion": "reservas", "form": form})


@panel_view(requiere_turno=False)
def reservas_horas(request):
    """Horas disponibles para el formulario del panel (JSON)."""
    servicio = ServicioReserva.objects.filter(pk=request.GET.get("servicio")).first()
    fecha = _fecha(request.GET.get("fecha"), None)
    if servicio is None or fecha is None:
        return JsonResponse({"horas": [], "por_dia": False})
    try:
        personas = max(1, int(request.GET.get("personas") or 2))
    except ValueError:
        personas = 2
    dia = rs.estado_del_dia(servicio, fecha, personas, sin_limites=True)
    return JsonResponse({
        "por_dia": servicio.por_dia, "dia": dia,
        "horas": rs.horas_del_dia(servicio, fecha, personas, sin_limites=True),
    })


@panel_view(requiere_turno=False)
def reserva_detalle(request, reserva_id):
    reserva = get_object_or_404(Reserva.objects.select_related("mesa", "servicio", "cliente"), pk=reserva_id)
    if reserva.vista_en is None:
        reserva.vista_en = timezone.now()
        reserva.save(update_fields=["vista_en"])
    if request.method == "POST":
        try:
            personas = int(request.POST.get("personas") or reserva.personas)
        except ValueError:
            personas = reserva.personas
        mesa = Table.objects.filter(pk=request.POST.get("mesa")).first() if request.POST.get("mesa") else None
        if mesa and reserva.hora:
            choca = Reserva.objects.filter(fecha=reserva.fecha, mesa=mesa, estado__in=Reserva.VIGENTES) \
                .exclude(pk=reserva.pk)
            if any(r.inicio < reserva.fin and reserva.inicio < r.fin for r in choca):
                messages.warning(request, f"La mesa {mesa.number} ya está reservada en ese horario.")
                return redirect("panel:reserva", reserva_id=reserva.id)
        reserva.personas = max(1, personas)
        reserva.mesa = mesa
        reserva.zona = (request.POST.get("zona") or "")[:40]
        reserva.observaciones = (request.POST.get("observaciones") or "")[:1000]
        reserva.save()
        messages.success(request, "Reserva actualizada.")
        return redirect("panel:reserva", reserva_id=reserva.id)
    return render(request, "panel/reserva_detalle.html", {
        "seccion": "reservas",
        "r": _decorar(reserva, request.tenant.name),
        "mesas": Table.objects.filter(is_active=True).order_by("number"),
        "historial": rs.historial_cliente(reserva.cliente),
        "cuenta": reserva.cuentas.order_by("-opened_at").first(),
    })


@panel_view(requiere_turno=False)
@require_POST
def reserva_accion(request, reserva_id):
    reserva = get_object_or_404(Reserva, pk=reserva_id)
    accion = request.POST.get("accion")
    quien = _quien(request)
    from .seguridad import volver_seguro

    volver = volver_seguro(request, request.POST.get("volver"),
                           reverse("panel:reservas") + f"?fecha={reserva.fecha.isoformat()}")
    try:
        if accion == "confirmar":
            rs.confirmar(reserva, quien)
            messages.success(request, f"Reserva de {reserva.nombre} confirmada.")
        elif accion == "llego":
            rs.marcar_llegada(reserva, quien)
            texto = f"{reserva.nombre} llegó."
            texto += (f" Su mesa es la {reserva.mesa.number}: toca «Sentar» para abrir la cuenta."
                      if reserva.mesa_id else " Elige una mesa para sentarlo.")
            messages.success(request, texto)
        elif accion == "sentar":
            mesa = get_object_or_404(Table, pk=request.POST.get("mesa") or reserva.mesa_id)
            cuenta = rs.sentar(reserva, mesa, quien)
            messages.success(request, f"{reserva.nombre} quedó en la mesa {mesa.number}. Ya puedes tomar su pedido.")
            return redirect("panel:table-detail", table_id=cuenta.table_id)
        elif accion == "no_llego":
            rs.no_llego(reserva, quien)
            messages.success(request, f"Marcada: {reserva.nombre} no llegó.")
        elif accion == "cancelar":
            rs.cancelar(reserva, quien, request.POST.get("motivo", ""))
            messages.success(request, f"Reserva de {reserva.nombre} cancelada.")
        elif accion == "recordatorio":
            reserva.recordatorio_en = timezone.now()
            reserva.save(update_fields=["recordatorio_en", "actualizada_en"])
            if request.headers.get("x-requested-with") == "fetch":
                return JsonResponse({"ok": True})
            messages.success(request, f"Recordatorio enviado a {reserva.nombre}.")
        else:
            messages.warning(request, "Acción no reconocida.")
    except ValidationError as e:
        messages.warning(request, e.messages[0])
    return redirect(volver)


# ------------------------------------------------------------------ clientes


@panel_view(requiere_turno=False)
def clientes(request):
    q = (request.GET.get("q") or "").strip()
    qs = Cliente.objects.annotate(
        n_reservas=Count("reservas", distinct=True),
        visitas=Count("reservas__cuentas", filter=Q(reservas__cuentas__status="closed"), distinct=True),
        no_llego=Count("reservas", filter=Q(reservas__estado=Reserva.NO_SHOW), distinct=True),
        gasto=Sum("reservas__cuentas__total", filter=Q(reservas__cuentas__status="closed")),
    ).order_by("-visitas", "nombre")
    if q:
        qs = qs.filter(Q(nombre__icontains=q) | Q(telefono__icontains=q))
    return render(request, "panel/clientes.html", {
        "seccion": "reservas", "sub": "clientes", "clientes": qs[:200], "q": q,
        "frecuentes": rs.clientes_frecuentes(), "total": Cliente.objects.count(),
    })


@panel_view(requiere_turno=False)
def cliente_detalle(request, cliente_id):
    cliente = get_object_or_404(Cliente, pk=cliente_id)
    if request.method == "POST":
        cliente.nombre = (request.POST.get("nombre") or cliente.nombre)[:120]
        cliente.correo = (request.POST.get("correo") or "")[:254]
        cliente.notas = (request.POST.get("notas") or "")[:2000]
        cliente.save()
        messages.success(request, "Cliente actualizado.")
        return redirect("panel:cliente", cliente_id=cliente.id)
    historial = rs.historial_cliente(cliente)
    for r in historial["reservas"]:
        _decorar(r, request.tenant.name)
    return render(request, "panel/cliente_detalle.html", {
        "seccion": "reservas", "sub": "clientes", "c": cliente, "h": historial,
        "whatsapp": f"https://wa.me/{cliente.whatsapp}",
    })


# ------------------------------------------------------------------ horarios


@panel_view(solo_admin=True, requiere_turno=False)
def reservas_config(request):
    ajustes = AjustesReservas.actuales()
    accion = request.POST.get("accion") if request.method == "POST" else None
    form_ajustes = AjustesForm(instance=ajustes)
    servicio_editar = None
    if request.GET.get("servicio"):
        servicio_editar = ServicioReserva.objects.filter(pk=request.GET["servicio"]).first()
    form_servicio = ServicioForm(instance=servicio_editar) if servicio_editar else ServicioForm(
        initial={"dias": list(range(7)), "intervalo_minutos": 30, "duracion_minutos": 120,
                 "ultima_llegada_minutos": 60})
    form_bloqueo = BloqueoForm()
    form_bloqueo.fields["servicio"].queryset = ServicioReserva.objects.all()
    form_bloqueo.fields["servicio"].empty_label = "Todo el día"

    if accion == "ajustes":
        form_ajustes = AjustesForm(request.POST, instance=ajustes)
        if form_ajustes.is_valid():
            form_ajustes.save()
            messages.success(request, "Ajustes de reservas guardados.")
            return redirect("panel:reservas-config")
    elif accion == "servicio":
        instancia = ServicioReserva.objects.filter(pk=request.POST.get("id")).first()
        form_servicio = ServicioForm(request.POST, instance=instancia)
        if form_servicio.is_valid():
            s = form_servicio.save()
            messages.success(request, f"Horario «{s.nombre}» guardado: {s.dias_texto()}.")
            return redirect(reverse("panel:reservas-config") + "#horarios")
        servicio_editar = instancia
    elif accion == "borrar_servicio":
        s = get_object_or_404(ServicioReserva, pk=request.POST.get("id"))
        if s.reservas.exists():
            s.activo = False
            s.save(update_fields=["activo"])
            messages.success(request, f"«{s.nombre}» ya tenía reservas: quedó desactivado en vez de borrarse.")
        else:
            s.delete()
            messages.success(request, "Horario eliminado.")
        return redirect(reverse("panel:reservas-config") + "#horarios")
    elif accion == "bloqueo":
        form_bloqueo = BloqueoForm(request.POST)
        form_bloqueo.fields["servicio"].queryset = ServicioReserva.objects.all()
        if form_bloqueo.is_valid():
            b = form_bloqueo.save()
            messages.success(request, f"El {b.fecha:%d/%m/%Y} no se recibirán reservas"
                                      + (f" de {b.servicio.nombre}." if b.servicio_id else "."))
            return redirect(reverse("panel:reservas-config") + "#bloqueos")
    elif accion == "quitar_bloqueo":
        BloqueoFecha.objects.filter(pk=request.POST.get("id")).delete()
        messages.success(request, "Ese día vuelve a recibir reservas.")
        return redirect(reverse("panel:reservas-config") + "#bloqueos")
    elif accion == "mesas":
        cambiadas = 0
        for mesa in Table.objects.filter(is_active=True):
            puestos = request.POST.get(f"puestos_{mesa.id}")
            zona = (request.POST.get(f"zona_{mesa.id}") or "").strip()[:40]
            reservable = request.POST.get(f"reservable_{mesa.id}") == "1"
            try:
                puestos = max(1, min(int(puestos), 40))
            except (TypeError, ValueError):
                puestos = mesa.seats
            if (puestos, zona, reservable) != (mesa.seats, mesa.zona, mesa.reservable):
                mesa.seats, mesa.zona, mesa.reservable = puestos, zona, reservable
                mesa.save(update_fields=["seats", "zona", "reservable"])
                cambiadas += 1
        messages.success(request, f"Mesas actualizadas ({cambiadas} con cambios).")
        return redirect(reverse("panel:reservas-config") + "#mesas")

    return render(request, "panel/reservas_config.html", {
        "seccion": "reservas", "sub": "config", "ajustes": ajustes, "form_ajustes": form_ajustes,
        "form_servicio": form_servicio, "servicio_editar": servicio_editar, "form_bloqueo": form_bloqueo,
        "servicios": ServicioReserva.objects.all(),
        "bloqueos": BloqueoFecha.objects.filter(fecha__gte=timezone.localdate()).select_related("servicio"),
        "mesas": Table.objects.filter(is_active=True).order_by("number"),
        "zonas": sorted({m.zona for m in Table.objects.exclude(zona="")}),
        "politica": request.build_absolute_uri(reverse("legal-datos", kwargs={"slug": request.tenant.slug})),
    })
