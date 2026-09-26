"""La inteligencia de las reservas: qué días y horas hay cupo, a qué mesa va
cada quien y el recorrido reserva → llegada → mesa → cuenta → historial.

La disponibilidad se calcula con lo que el restaurante configuró en el panel:
los horarios de cada servicio, las mesas que se ofrecen (y sus puestos), los
días bloqueados y la anticipación mínima. Nada está escrito a mano en el sitio
web: el sitio pregunta aquí y muestra lo que hay.
"""

from datetime import datetime, timedelta
from decimal import Decimal
from urllib.parse import quote

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone

from apps.dining.models import Table

from .models import AjustesReservas, BloqueoFecha, Cliente, Reserva, ServicioReserva, solo_digitos

# Por debajo de esta proporción de horas libres, el día se muestra con «pocos cupos».
POCOS_CUPOS = 0.34


class SinCupo(ValidationError):
    """No hay mesa o cupo para lo que se pidió. Lleva sugerencias para ofrecer."""

    def __init__(self, mensaje, sugerencias=None):
        super().__init__(mensaje)
        self.sugerencias = sugerencias or {}


# ------------------------------------------------------------------ clientes


def normalizar_telefono(telefono: str) -> str:
    numero = solo_digitos(telefono)
    # +57 300 123 4567 y 300 123 4567 son el mismo cliente.
    if len(numero) == 12 and numero.startswith("57"):
        numero = numero[2:]
    if not 7 <= len(numero) <= 15:
        raise ValidationError("Escribe un teléfono válido, con WhatsApp si es posible.")
    return numero


def cliente_por_telefono(nombre: str, telefono: str, correo: str = "") -> Cliente:
    numero = normalizar_telefono(telefono)
    nombre = (nombre or "").strip()[:120]
    cliente, creado = Cliente.objects.get_or_create(telefono=numero, defaults={"nombre": nombre or "Cliente"})
    cambios = []
    if not creado and nombre and cliente.nombre in ("", "Cliente"):
        cliente.nombre = nombre
        cambios.append("nombre")
    if correo and not cliente.correo:
        cliente.correo = correo[:254]
        cambios.append("correo")
    if cambios:
        cliente.save(update_fields=cambios + ["actualizado"])
    return cliente


# ------------------------------------------------------------ disponibilidad


def _limites():
    """Desde cuándo y hasta qué día se puede reservar por internet."""
    ajustes = AjustesReservas.actuales()
    primero = timezone.now() + timedelta(hours=ajustes.anticipacion_horas)
    ultimo_dia = timezone.localdate() + timedelta(days=ajustes.dias_maximo)
    return ajustes, primero, ultimo_dia


def bloqueo_de(servicio, fecha):
    return (
        BloqueoFecha.objects.filter(fecha=fecha)
        .filter(Q(servicio__isnull=True) | Q(servicio=servicio))
        .first()
    )


def mesas_candidatas(personas: int, zona: str = "", solo_reservables=True):
    """Las mesas donde cabe el grupo, de la más justa a la más grande."""
    qs = Table.objects.filter(is_active=True, seats__gte=max(1, personas))
    if solo_reservables:
        qs = qs.filter(reservable=True)
    if zona:
        qs = qs.filter(zona__iexact=zona)
    return list(qs.order_by("seats", "number"))


def _ocupaciones(fecha, excluir=None):
    """Qué mesas están reservadas ese día y en qué horario."""
    qs = (
        Reserva.objects.filter(fecha=fecha, estado__in=Reserva.VIGENTES, mesa__isnull=False)
        .select_related("servicio")
    )
    if excluir is not None:
        qs = qs.exclude(pk=excluir.pk)
    return [(r.mesa_id, r.inicio, r.fin) for r in qs]


def _mesas_ocupadas_ahora():
    from apps.orders.models import TableSession

    return set(TableSession.objects.filter(status=TableSession.STATUS_OPEN).values_list("table_id", flat=True))


def mesa_libre(personas, inicio, fin, zona="", ocupaciones=None, solo_reservables=True, excluir=None):
    """La mesa más justa que está libre en ese horario, o None."""
    if ocupaciones is None:
        ocupaciones = _ocupaciones(timezone.localtime(inicio).date(), excluir=excluir)
    # Si la reserva es para ya, una mesa con cuenta abierta tampoco sirve.
    ahora = timezone.now()
    ocupadas_ya = _mesas_ocupadas_ahora() if inicio <= ahora + timedelta(minutes=90) else set()
    for mesa in mesas_candidatas(personas, zona, solo_reservables):
        if mesa.id in ocupadas_ya:
            continue
        choca = any(m == mesa.id and ini < fin and inicio < f for m, ini, f in ocupaciones)
        if not choca:
            return mesa
    return None


def _personas_en(servicio, fecha, inicio=None, fin=None, excluir=None):
    qs = Reserva.objects.filter(servicio=servicio, fecha=fecha, estado__in=Reserva.VIGENTES)
    if excluir is not None:
        qs = qs.exclude(pk=excluir.pk)
    if inicio is None:
        return qs.aggregate(n=Sum("personas"))["n"] or 0
    return sum(r.personas for r in qs if r.inicio < fin and inicio < r.fin)


def horas_del_dia(servicio, fecha, personas, zona="", excluir=None, sin_limites=False):
    """Las horas de ese día con su disponibilidad: [{hora, texto, libre, mesas}]."""
    if servicio.por_dia:
        return []
    _, primero, _ = _limites()
    ocupaciones = _ocupaciones(fecha, excluir=excluir)
    candidatas = mesas_candidatas(personas, zona)
    duracion = timedelta(minutes=servicio.duracion_minutos)
    horas = []
    for inicio in servicio.horas_del_dia(fecha):
        if not sin_limites and inicio < primero:
            continue
        fin = inicio + duracion
        libres = [m for m in candidatas
                  if not any(o == m.id and ini < fin and inicio < f for o, ini, f in ocupaciones)]
        libre = bool(libres)
        if libre and servicio.cupo_personas:
            libre = _personas_en(servicio, fecha, inicio, fin, excluir) + personas <= servicio.cupo_personas
        local = timezone.localtime(inicio)
        horas.append({
            "hora": local.strftime("%H:%M"),
            "texto": _hora_texto(local),
            "libre": libre,
            "mesas": len(libres),
        })
    return horas


def _hora_texto(momento) -> str:
    if momento.hour == 12 and momento.minute == 0:
        return "12:00 m."  # el mediodía en Colombia
    return f"{momento.hour % 12 or 12}:{momento.minute:02d} {'a. m.' if momento.hour < 12 else 'p. m.'}"


def estado_del_dia(servicio, fecha, personas, zona="", sin_limites=False):
    """Si se puede reservar ese día, y si no, por qué (para explicárselo al cliente)."""
    _, primero, ultimo_dia = _limites()
    dia = {"fecha": fecha.isoformat(), "disponible": False, "motivo": "", "texto": "",
           "horas_libres": 0, "pocos": False, "cupo_restante": None}

    if not sin_limites and (fecha < timezone.localtime(primero).date() or fecha > ultimo_dia):
        dia.update(motivo="fuera_de_rango", texto="No disponible")
        return dia
    if not servicio.abre_el(fecha):
        dia.update(motivo="cerrado", texto=f"{servicio.nombre}: no hay servicio este día")
        return dia
    bloqueo = bloqueo_de(servicio, fecha)
    if bloqueo:
        dia.update(motivo="bloqueado", texto=bloqueo.motivo or "No recibimos reservas este día")
        return dia

    if servicio.por_dia:
        usados = _personas_en(servicio, fecha)
        restante = max(0, (servicio.cupo_personas or 0) - usados) if servicio.cupo_personas else None
        libre = restante is None or restante >= personas
        dia.update(disponible=libre, cupo_restante=restante,
                   pocos=bool(restante is not None and servicio.cupo_personas
                              and restante < servicio.cupo_personas * POCOS_CUPOS),
                   motivo="" if libre else "lleno",
                   texto="" if libre else "Cupo completo")
        return dia

    if not mesas_candidatas(personas, zona):
        dia.update(motivo="grupo_grande", texto="Para un grupo así, escríbenos")
        return dia
    horas = horas_del_dia(servicio, fecha, personas, zona, sin_limites=sin_limites)
    libres = sum(1 for h in horas if h["libre"])
    dia.update(disponible=libres > 0, horas_libres=libres,
               pocos=0 < libres < max(1, len(horas)) * POCOS_CUPOS,
               motivo="" if libres else ("sin_horas" if not horas else "lleno"),
               texto="" if libres else "Sin mesas libres")
    return dia


def calendario(servicio, personas, desde=None, dias=31, zona=""):
    """Un día tras otro, para pintar el calendario del sitio."""
    ajustes, _, _ = _limites()
    hoy = timezone.localdate()
    desde = max(desde or hoy, hoy)
    dias = max(1, min(int(dias or 31), ajustes.dias_maximo + 1, 62))
    return [estado_del_dia(servicio, desde + timedelta(days=i), personas, zona) for i in range(dias)]


def sugerencias(servicio, fecha, personas, zona="", hora=None):
    """Si lo pedido no se puede: horas cercanas ese mismo día y los próximos días con cupo."""
    horas = [h for h in horas_del_dia(servicio, fecha, personas, zona) if h["libre"]]
    if hora:
        objetivo = hora.hour * 60 + hora.minute
        horas.sort(key=lambda h: abs(int(h["hora"][:2]) * 60 + int(h["hora"][3:]) - objetivo))
    proximos = [d for d in calendario(servicio, personas, fecha + timedelta(days=1), 21, zona)
                if d["disponible"]][:3]
    return {"horas": horas[:4], "dias": proximos}


def servicios_activos():
    return list(ServicioReserva.objects.filter(activo=True).order_by("orden", "abre"))


def zonas():
    return sorted({z for z in Table.objects.filter(is_active=True, reservable=True)
                   .exclude(zona="").values_list("zona", flat=True)})


# ------------------------------------------------------------ plano de mesas


# Lo que el cliente ve en cada mesa del plano.
ESTADOS_PLANO = {
    "libre": "Libre",
    "reservada": "Reservada",
    "ocupada": "Ocupada ahora",
    "no_alcanza": "Para {puestos}",
    "sin_reserva": "Sin reserva",
    "cerrada": "No disponible",
}


def _inicio_de(servicio, fecha, hora: str):
    """El momento exacto de una hora ofrecida («19:00»), sacado de los horarios del
    servicio: así una hora después de medianoche cae en el día que corresponde."""
    for inicio in servicio.horas_del_dia(fecha):
        if timezone.localtime(inicio).strftime("%H:%M") == hora:
            return inicio
    return None


def plano_de_mesas(servicio, fecha, personas, hora=None):
    """Las mesas del local con su estado a esa hora, para pintar el plano en el sitio.

    Sin datos de nadie: solo número, zona, puestos y si se puede reservar. Si no
    llega hora, se muestra la primera hora con mesa libre de ese día (vista previa).
    """
    dia = estado_del_dia(servicio, fecha, personas)
    base = {"fecha": fecha.isoformat(), "personas": personas, "dia": dia, "zonas": [],
            "hora": None, "hora_texto": "", "vista_previa": False, "hora_disponible": False,
            "libres": 0, "total": 0, "en_vivo": fecha == timezone.localdate(),
            "actualizado": timezone.now().isoformat(), "mensaje": ""}
    if servicio.por_dia:
        base["mensaje"] = "Este plan no se reserva por mesa."
        return base

    horas = horas_del_dia(servicio, fecha, personas)
    elegida = next((h for h in horas if h["hora"] == hora), None) if hora else None
    if elegida is None:
        elegida = next((h for h in horas if h["libre"]), None) or (horas[0] if horas else None)
        base["vista_previa"] = True
    inicio = _inicio_de(servicio, fecha, elegida["hora"]) if elegida else None
    if inicio is None:
        base["mensaje"] = dia["texto"] or "Ese día no hay horas para reservar."
        return base

    fin = inicio + timedelta(minutes=servicio.duracion_minutos)
    ocupaciones = _ocupaciones(fecha)
    ocupadas_ya = _mesas_ocupadas_ahora() if inicio <= timezone.now() + timedelta(minutes=90) else set()
    hora_libre = bool(elegida["libre"])

    grupos = {}
    for mesa in Table.objects.filter(is_active=True).order_by("number"):
        if not mesa.reservable:
            estado = "sin_reserva"
        elif mesa.id in ocupadas_ya:
            estado = "ocupada"
        elif any(m == mesa.id and ini < fin and inicio < f for m, ini, f in ocupaciones):
            estado = "reservada"
        elif mesa.seats < personas:
            estado = "no_alcanza"
        elif not hora_libre:
            estado = "cerrada"  # hay mesa, pero el horario llegó a su cupo de personas
        else:
            estado = "libre"
        grupos.setdefault(mesa.zona.strip() or "Mesas", []).append({
            "numero": mesa.number,
            "puestos": mesa.seats,
            "estado": estado,
            "texto": ESTADOS_PLANO[estado].format(puestos=mesa.seats),
        })

    libres = sum(1 for g in grupos.values() for m in g if m["estado"] == "libre")
    total = sum(1 for g in grupos.values() for m in g if m["estado"] != "sin_reserva")
    texto_hora = _hora_texto(timezone.localtime(inicio))
    quien = f"{personas} persona{'' if personas == 1 else 's'}"
    if libres:
        mensaje = (f"A las {texto_hora} hay {libres} mesa{'' if libres == 1 else 's'} "
                   f"libre{'' if libres == 1 else 's'} para {quien}. Toca una si quieres pedirla.")
    elif not hora_libre and any(m["estado"] == "cerrada" for g in grupos.values() for m in g):
        mensaje = f"A las {texto_hora} ya se completó el cupo. Prueba otra hora."
    else:
        mensaje = f"A las {texto_hora} no quedan mesas para {quien}. Prueba otra hora."
    base.update(
        hora=elegida["hora"], hora_texto=texto_hora, hora_disponible=hora_libre and libres > 0,
        libres=libres, total=total, mensaje=mensaje,
        # Las zonas en el orden de sus mesas: la de la mesa 1 primero.
        zonas=[{"nombre": nombre, "libres": sum(1 for m in mesas if m["estado"] == "libre"), "mesas": mesas}
               for nombre, mesas in sorted(grupos.items(), key=lambda g: g[1][0]["numero"])],
    )
    return base


def mesa_pedida(numero, servicio, fecha, hora, personas):
    """La mesa que el cliente tocó en el plano, si todavía le sirve; si no, None y
    Cloudin le asigna la mejor libre (el restaurante siempre puede cambiarla)."""
    if not numero or servicio.por_dia or not hora:
        return None
    mesa = Table.objects.filter(number=numero, is_active=True, reservable=True, seats__gte=personas).first()
    inicio = _inicio_de(servicio, fecha, hora.strftime("%H:%M") if hasattr(hora, "hour") else str(hora)[:5])
    if mesa is None or inicio is None:
        return None
    fin = inicio + timedelta(minutes=servicio.duracion_minutos)
    if inicio <= timezone.now() + timedelta(minutes=90) and mesa.id in _mesas_ocupadas_ahora():
        return None
    if any(m == mesa.id and ini < fin and inicio < f for m, ini, f in _ocupaciones(fecha)):
        return None
    return mesa


# --------------------------------------------------------------------- crear


def _parse_hora(valor):
    if not valor:
        return None
    if hasattr(valor, "hour"):
        return valor
    try:
        return datetime.strptime(str(valor)[:5], "%H:%M").time()
    except ValueError:
        raise ValidationError("La hora no es válida.")


@transaction.atomic
def crear_reserva(*, servicio, fecha, personas, nombre, telefono, hora=None, correo="", zona="",
                  observaciones="", origen=Reserva.SITIO, detalle=None, total_estimado=0,
                  clave_envio="", usuario="", mesa=None, desde_panel=False):
    """Crea la reserva si hay cupo; si no, lanza SinCupo con alternativas.

    Desde el panel (`desde_panel`) el personal puede saltarse la anticipación y
    el máximo de personas, y elegir la mesa a mano: es una decisión del local.
    """
    ajustes = AjustesReservas.actuales()
    hora = _parse_hora(hora)
    nombre = (nombre or "").strip()
    if not nombre:
        raise ValidationError("Escribe el nombre de quien reserva.")
    try:
        personas = int(personas)
    except (TypeError, ValueError):
        raise ValidationError("Indica cuántas personas vienen.")
    if personas < 1:
        raise ValidationError("Indica cuántas personas vienen.")

    if clave_envio:
        ya = Reserva.objects.filter(clave_envio=clave_envio[:64]).first()
        if ya:
            return ya  # el sitio reintentó: no se duplica

    if not desde_panel:
        if not ajustes.activo:
            raise ValidationError("En este momento no estamos recibiendo reservas por internet.")
        if personas > ajustes.max_personas:
            raise SinCupo(
                f"Para grupos de más de {ajustes.max_personas} personas escríbenos por WhatsApp "
                "y lo organizamos contigo.")
        if not servicio.activo:
            raise ValidationError("Ese horario ya no recibe reservas.")

    dia = estado_del_dia(servicio, fecha, personas, "", sin_limites=desde_panel)
    if not dia["disponible"] and not (desde_panel and dia["motivo"] in ("lleno", "sin_horas", "grupo_grande")):
        raise SinCupo(dia["texto"] or "Ese día no está disponible.",
                      sugerencias(servicio, fecha, personas, "", hora))

    cliente = cliente_por_telefono(nombre, telefono, correo)
    asignada = mesa
    if not servicio.por_dia:
        if hora is None:
            raise ValidationError("Elige una hora.")
        # La zona es una preferencia: la disponibilidad se mira en todo el local.
        ofrecidas = {h["hora"]: h for h in horas_del_dia(servicio, fecha, personas,
                                                         sin_limites=desde_panel)}
        clave = hora.strftime("%H:%M")
        if not desde_panel and (clave not in ofrecidas or not ofrecidas[clave]["libre"]):
            raise SinCupo("Esa hora acaba de llenarse. Mira estas otras opciones.",
                          sugerencias(servicio, fecha, personas, "", hora))
        if asignada is None:
            inicio = timezone.make_aware(datetime.combine(fecha, hora))
            fin = inicio + timedelta(minutes=servicio.duracion_minutos)
            asignada = mesa_libre(personas, inicio, fin, zona) or (
                mesa_libre(personas, inicio, fin) if zona else None)
            if asignada is None and desde_panel:
                asignada = mesa_libre(personas, inicio, fin, solo_reservables=False)
    else:
        hora = hora or None

    automatica = ajustes.confirmacion_automatica or desde_panel
    estado = Reserva.CONFIRMED if automatica else Reserva.PENDING
    ahora = timezone.now()
    reserva = Reserva.objects.create(
        cliente=cliente, nombre=nombre[:120], telefono=cliente.telefono,
        servicio=servicio, servicio_nombre=servicio.nombre, fecha=fecha, hora=hora,
        personas=personas, zona=(zona or "")[:40], mesa=asignada,
        estado=estado, observaciones=(observaciones or "")[:1000], origen=origen,
        detalle=detalle or {}, total_estimado=Decimal(str(total_estimado or 0)),
        confirmada_en=ahora if automatica else None,
        confirmada_por=(usuario or "Panel") if desde_panel else ("Confirmación automática" if automatica else ""),
        clave_envio=(clave_envio or "")[:64], creada_por=usuario or "",
        # Lo que se crea en el panel ya lo vio alguien.
        vista_en=ahora if desde_panel else None,
    )
    return reserva


# ------------------------------------------------------------ el recorrido


def confirmar(reserva, usuario=""):
    if reserva.estado != Reserva.PENDING:
        raise ValidationError("Solo se confirma una reserva pendiente.")
    if reserva.mesa_id is None and reserva.servicio_id and not reserva.servicio.por_dia:
        reserva.mesa = mesa_libre(reserva.personas, reserva.inicio, reserva.fin, reserva.zona,
                                  excluir=reserva) or mesa_libre(
            reserva.personas, reserva.inicio, reserva.fin, solo_reservables=False, excluir=reserva)
    reserva.estado = Reserva.CONFIRMED
    reserva.confirmada_en = timezone.now()
    reserva.confirmada_por = usuario
    reserva.save()
    return reserva


def cancelar(reserva, usuario="", motivo=""):
    if reserva.estado in Reserva.CERRADAS or reserva.estado == Reserva.SEATED:
        raise ValidationError("Esa reserva ya no se puede cancelar.")
    reserva.estado = Reserva.CANCELLED
    reserva.cancelada_en = timezone.now()
    reserva.motivo_cancelacion = (motivo or f"Cancelada por {usuario or 'el restaurante'}")[:200]
    reserva.save()
    return reserva


def marcar_llegada(reserva, usuario=""):
    if reserva.estado not in (Reserva.PENDING, Reserva.CONFIRMED):
        raise ValidationError("Esa reserva ya no está esperando al cliente.")
    reserva.estado = Reserva.ARRIVED
    reserva.llegada_en = timezone.now()
    if reserva.mesa_id and reserva.mesa.is_occupied:
        # Su mesa todavía tiene gente: se le busca otra libre en este momento.
        reserva.mesa = None
    if reserva.mesa_id is None:
        ahora = timezone.now()
        reserva.mesa = mesa_libre(reserva.personas, ahora, ahora + timedelta(minutes=90),
                                  reserva.zona, solo_reservables=False, excluir=reserva)
    reserva.save()
    return reserva


def sentar(reserva, mesa, usuario=""):
    """Asigna la mesa y abre la cuenta. Desde aquí los pedidos quedan a su nombre."""
    from apps.orders.models import TableSession
    from apps.shifts.services import exigir_turno

    if reserva.estado not in (Reserva.PENDING, Reserva.CONFIRMED, Reserva.ARRIVED):
        raise ValidationError("Esa reserva ya no está esperando mesa.")
    if mesa is None:
        raise ValidationError("Elige la mesa.")
    turno = exigir_turno()
    cuenta = mesa.open_session
    if cuenta and cuenta.reserva_id != reserva.id:
        raise ValidationError(f"La mesa {mesa.number} está ocupada. Elige otra.")
    if cuenta is None:
        cuenta = TableSession.objects.create(
            table=mesa, guests=reserva.personas, customer_name=reserva.nombre[:80],
            turno=turno, reserva=reserva,
            note=f"Reserva {reserva.codigo}" + (f" · {reserva.observaciones[:120]}" if reserva.observaciones else ""),
        )
    ahora = timezone.now()
    reserva.mesa = mesa
    reserva.estado = Reserva.SEATED
    reserva.llegada_en = reserva.llegada_en or ahora
    reserva.sentada_en = ahora
    reserva.save()
    return cuenta


def completar_reserva(reserva, cuenta=None):
    if reserva.estado in (Reserva.COMPLETED, Reserva.CANCELLED):
        return reserva
    reserva.estado = Reserva.COMPLETED
    reserva.completada_en = timezone.now()
    reserva.save(update_fields=["estado", "completada_en", "actualizada_en"])
    return reserva


def no_llego(reserva, usuario=""):
    if reserva.estado not in (Reserva.PENDING, Reserva.CONFIRMED):
        raise ValidationError("Solo se marca «no llegó» a una reserva que estaba esperando.")
    reserva.estado = Reserva.NO_SHOW
    reserva.save()
    return reserva


# ---------------------------------------------------------------- WhatsApp


def _numero_whatsapp(numero: str) -> str:
    numero = solo_digitos(numero)
    return numero if len(numero) > 10 else ("57" + numero if numero else "")


def mensaje_recordatorio(reserva, restaurante: str) -> str:
    ajustes = AjustesReservas.actuales()
    plantilla = ajustes.mensaje_recordatorio or AjustesReservas._meta.get_field("mensaje_recordatorio").default
    try:
        return plantilla.format(
            nombre=reserva.nombre.split(" ")[0], cuando=reserva.cuando_texto(), restaurante=restaurante,
            personas=reserva.personas_texto(), codigo=reserva.codigo,
        )
    except (KeyError, IndexError, ValueError):
        return plantilla


def enlace_recordatorio(reserva, restaurante: str) -> str:
    return f"https://wa.me/{reserva.cliente.whatsapp}?text={quote(mensaje_recordatorio(reserva, restaurante))}"


def mensaje_para_restaurante(reserva, restaurante: str) -> str:
    """El aviso que el cliente le manda al restaurante por WhatsApp al reservar."""
    partes = [
        f"Hola {restaurante}, acabo de reservar.",
        f"Código: {reserva.codigo}",
        f"{reserva.servicio_nombre}: {reserva.cuando_texto()}",
        f"Personas: {reserva.personas}",
        f"A nombre de: {reserva.nombre}",
        f"Teléfono: {reserva.telefono}",
    ]
    if reserva.zona:
        partes.append(f"Zona: {reserva.zona}")
    for plan in (reserva.detalle or {}).get("planes", []):
        partes.append(f"· {plan.get('cantidad')} × {plan.get('nombre')}")
    if reserva.observaciones:
        partes.append(f"Nota: {reserva.observaciones}")
    partes.append("Estado: " + ("confirmada" if reserva.estado == Reserva.CONFIRMED else "por confirmar"))
    return "\n".join(partes)


def enlace_para_restaurante(reserva, restaurante: str) -> str:
    numero = _numero_whatsapp(AjustesReservas.actuales().whatsapp)
    if not numero:
        return ""
    return f"https://wa.me/{numero}?text={quote(mensaje_para_restaurante(reserva, restaurante))}"


# ---------------------------------------------------------------- consultas


def pendientes_de_recordar():
    """Reservas que vienen pronto y a las que todavía no se les recordó."""
    ajustes = AjustesReservas.actuales()
    ahora = timezone.now()
    limite = ahora + timedelta(hours=ajustes.recordar_horas_antes)
    qs = Reserva.objects.filter(
        estado__in=[Reserva.PENDING, Reserva.CONFIRMED], recordatorio_en__isnull=True,
        fecha__gte=timezone.localdate(), fecha__lte=timezone.localtime(limite).date(),
    ).select_related("servicio", "cliente", "mesa")
    return [r for r in qs if ahora < r.inicio <= limite]


def atrasadas():
    """Pasó la hora más la tolerancia y el cliente no ha llegado."""
    ajustes = AjustesReservas.actuales()
    hoy = timezone.localdate()
    qs = Reserva.objects.filter(estado__in=[Reserva.PENDING, Reserva.CONFIRMED],
                                fecha__gte=hoy - timedelta(days=1), fecha__lte=hoy).select_related("servicio", "mesa")
    return [r for r in qs if r.minutos_para() < -ajustes.tolerancia_minutos]


def resumen(fecha=None):
    fecha = fecha or timezone.localdate()
    del_dia = Reserva.objects.filter(fecha=fecha).exclude(estado=Reserva.CANCELLED)
    return {
        "reservas": del_dia.count(),
        "personas": del_dia.aggregate(n=Sum("personas"))["n"] or 0,
        "por_llegar": del_dia.filter(estado__in=[Reserva.PENDING, Reserva.CONFIRMED]).count(),
        "llegaron": del_dia.filter(estado__in=[Reserva.ARRIVED, Reserva.SEATED, Reserva.COMPLETED]).count(),
        "no_llegaron": del_dia.filter(estado=Reserva.NO_SHOW).count(),
        "por_confirmar": Reserva.objects.filter(estado=Reserva.PENDING, fecha__gte=timezone.localdate()).count(),
        "nuevas": Reserva.objects.filter(vista_en__isnull=True).exclude(estado=Reserva.CANCELLED).count(),
    }


def proxima():
    ahora = timezone.now()
    for r in (Reserva.objects.filter(estado__in=[Reserva.PENDING, Reserva.CONFIRMED],
                                     fecha__gte=timezone.localdate())
              .select_related("servicio", "mesa").order_by("fecha", "hora")[:30]):
        if r.inicio >= ahora - timedelta(minutes=30):
            return r
    return None


def historial_cliente(cliente):
    """Todo lo que se sabe de un cliente: visitas, gasto, lo que más pide."""
    from apps.orders.models import OrderItem, TableSession

    reservas = list(cliente.reservas.select_related("mesa", "servicio").order_by("-fecha", "-hora"))
    cuentas = TableSession.objects.filter(reserva__cliente=cliente, status=TableSession.STATUS_CLOSED)
    gasto = cuentas.aggregate(t=Sum("total"))["t"] or Decimal("0")
    visitas = cuentas.count()
    favoritos = (
        OrderItem.objects.filter(order__session__in=cuentas, novedad="")
        .values("product_name").annotate(veces=Sum("quantity")).order_by("-veces")[:5]
    )
    conteo = {e: 0 for e, _ in Reserva.ESTADOS}
    for r in reservas:
        conteo[r.estado] += 1
    ultima = cuentas.order_by("-closed_at").first()
    return {
        "reservas": reservas,
        "visitas": visitas,
        "gasto": gasto,
        "ticket": (gasto / visitas).quantize(Decimal("1")) if visitas else Decimal("0"),
        "favoritos": list(favoritos),
        "no_llego": conteo[Reserva.NO_SHOW],
        "canceladas": conteo[Reserva.CANCELLED],
        "ultima_visita": ultima.closed_at if ultima else None,
        "cumplimiento": round(100 * visitas / max(1, visitas + conteo[Reserva.NO_SHOW])),
    }


def clientes_frecuentes(limite=8):
    from apps.orders.models import TableSession

    filas = (
        TableSession.objects.filter(status=TableSession.STATUS_CLOSED, reserva__isnull=False)
        .values("reserva__cliente").annotate(visitas=Count("id"), gasto=Sum("total"))
        .order_by("-visitas", "-gasto")[:limite]
    )
    por_id = Cliente.objects.in_bulk([f["reserva__cliente"] for f in filas])
    return [{"cliente": por_id[f["reserva__cliente"]], "visitas": f["visitas"], "gasto": f["gasto"]}
            for f in filas if f["reserva__cliente"] in por_id]
