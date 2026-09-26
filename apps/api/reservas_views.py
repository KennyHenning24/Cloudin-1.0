"""API pública de Cloudin Reservas: lo que usa el sitio web y el menú de la mesa.

Se identifica con la cabecera X-API-Key, igual que el resto de la API pública.
No pide turno abierto: una reserva es para otro momento, y el cliente tiene que
poder reservar a medianoche aunque el local esté cerrado.

    GET  /api/v1/reservas/                   cómo reserva el restaurante (servicios, zonas, límites)
    GET  /api/v1/reservas/dias/?servicio=&personas=&desde=&dias=
    GET  /api/v1/reservas/horas/?servicio=&personas=&fecha=
    GET  /api/v1/reservas/mesas/?servicio=&personas=&fecha=&hora=   el plano de mesas en vivo
    POST /api/v1/reservas/crear/             crea la reserva (confirmada si hay cupo)
    GET  /api/v1/reservas/<codigo>/          en qué va una reserva
    POST /api/v1/reservas/<codigo>/cancelar/ el cliente cancela (con su teléfono)
"""

from datetime import date

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes
from rest_framework.response import Response

from apps.api.limites import permitido
from apps.reservas import services as rs
from apps.reservas.models import AjustesReservas, Reserva, ServicioReserva

# Máximo de reservas nuevas por dirección IP en una hora: frena a quien quiera
# llenar el calendario con reservas falsas.
MAX_POR_HORA = 6
# El plano se refresca solo cada ~15 s mientras el cliente lo mira: 10 minutos
# son ~40 consultas. El tope deja margen y frena a quien lo consulte en bucle.
MAX_PLANO_10_MIN = 180


def _servicio(request, datos=None):
    valor = (datos or request.GET).get("servicio")
    servicio = ServicioReserva.objects.filter(pk=valor, activo=True).first() if str(valor or "").isdigit() else None
    if servicio is None:
        servicio = ServicioReserva.objects.filter(activo=True).order_by("orden", "abre").first()
    return servicio


def _entero(valor, defecto, minimo=1, maximo=100):
    try:
        return max(minimo, min(int(valor), maximo))
    except (TypeError, ValueError):
        return defecto


def _fecha(valor, defecto=None):
    try:
        return date.fromisoformat(str(valor)[:10])
    except (TypeError, ValueError):
        return defecto


def _detalle_limpio(detalle):
    """Solo lo que se usa (los planes de pasadía), con tamaños acotados: nadie puede
    guardar un archivo gigante en la base mandando un «detalle» enorme."""
    if not isinstance(detalle, dict):
        return {}
    planes = []
    for p in (detalle.get("planes") or [])[:10] if isinstance(detalle.get("planes"), list) else []:
        if isinstance(p, dict):
            planes.append({"nombre": str(p.get("nombre", ""))[:80], "cantidad": _entero(p.get("cantidad"), 0, 0, 200),
                           "precio": _entero(p.get("precio"), 0, 0, 10_000_000)})
    return {"planes": planes} if planes else {}


def _servicio_json(s):
    return {
        "id": s.id, "nombre": s.nombre, "tipo": s.tipo, "por_dia": s.por_dia,
        "dias": sorted(int(d) for d in (s.dias or [])), "dias_texto": s.dias_texto(),
        "abre": s.abre.strftime("%H:%M"), "cierra": s.cierra.strftime("%H:%M"),
        "horario": f"{rs._hora_texto(s.abre)} a {rs._hora_texto(s.cierra)}",
        "descripcion": s.descripcion, "cupo_personas": s.cupo_personas or None,
    }


def reserva_json(r, restaurante=""):
    return {
        "codigo": r.codigo,
        "estado": r.estado,
        "estado_texto": r.get_estado_display(),
        "servicio": r.servicio_nombre,
        "fecha": r.fecha.isoformat(),
        "hora": r.hora.strftime("%H:%M") if r.hora else None,
        "cuando": r.cuando_texto(),
        "personas": r.personas,
        "nombre": r.nombre,
        "zona": r.zona,
        "mesa": r.mesa.number if r.mesa_id else None,
        "mesa_zona": r.mesa.zona if r.mesa_id else "",
        "confirmada": r.estado in (Reserva.CONFIRMED, Reserva.ARRIVED, Reserva.SEATED, Reserva.COMPLETED),
        "inicio": r.inicio.isoformat(),
        "fin": r.fin.isoformat(),
        "restaurante": restaurante,
    }


@api_view(["GET"])
@authentication_classes([])
def configuracion(request):
    ajustes = AjustesReservas.actuales()
    tenant = request.tenant
    return Response({
        "restaurante": tenant.name,
        "activo": ajustes.activo,
        "servicios": [_servicio_json(s) for s in rs.servicios_activos()],
        "zonas": rs.zonas(),
        "max_personas": ajustes.max_personas,
        "dias_maximo": ajustes.dias_maximo,
        "anticipacion_horas": ajustes.anticipacion_horas,
        "confirmacion_automatica": ajustes.confirmacion_automatica,
        "whatsapp": ajustes.whatsapp,
        "politica_datos": request.build_absolute_uri(reverse("legal-datos", kwargs={"slug": tenant.slug})),
    })


@api_view(["GET"])
@authentication_classes([])
def dias(request):
    """El calendario: qué días hay cupo para ese servicio y ese número de personas."""
    servicio = _servicio(request)
    if servicio is None:
        return Response({"detail": "El restaurante no tiene horarios de reserva.", "dias": []})
    personas = _entero(request.GET.get("personas"), 2)
    desde = _fecha(request.GET.get("desde"), timezone.localdate())
    cantidad = _entero(request.GET.get("dias"), 35, 1, 62)
    return Response({
        "servicio": _servicio_json(servicio),
        "personas": personas,
        "dias": rs.calendario(servicio, personas, desde, cantidad, request.GET.get("zona", "")),
    })


@api_view(["GET"])
@authentication_classes([])
def horas(request):
    servicio = _servicio(request)
    fecha = _fecha(request.GET.get("fecha"))
    if servicio is None or fecha is None:
        return Response({"detail": "Falta el servicio o la fecha."}, status=status.HTTP_400_BAD_REQUEST)
    personas = _entero(request.GET.get("personas"), 2)
    dia = rs.estado_del_dia(servicio, fecha, personas)
    lista = rs.horas_del_dia(servicio, fecha, personas) if dia["disponible"] else []
    return Response({"servicio": _servicio_json(servicio), "fecha": fecha.isoformat(), "dia": dia,
                     "horas": lista})


@api_view(["GET"])
@authentication_classes([])
def mesas(request):
    """El plano: cada mesa con su estado a esa hora (libre, reservada, ocupada...)."""
    if not permitido(request, "reservas-plano", MAX_PLANO_10_MIN, 600):
        return Response({"detail": "Espera un momento y vuelve a intentarlo.", "codigo": "demasiados"},
                        status=status.HTTP_429_TOO_MANY_REQUESTS)
    servicio = _servicio(request)
    fecha = _fecha(request.GET.get("fecha"))
    if servicio is None or fecha is None:
        return Response({"detail": "Falta el servicio o la fecha."}, status=status.HTTP_400_BAD_REQUEST)
    hora = str(request.GET.get("hora") or "")[:5] or None
    plano = rs.plano_de_mesas(servicio, fecha, _entero(request.GET.get("personas"), 2), hora)
    return Response({"servicio": _servicio_json(servicio), **plano})


@api_view(["POST"])
@authentication_classes([])
def crear(request):
    datos = request.data
    tenant = request.tenant
    if datos.get("acepta_datos") not in (True, "true", "1", 1, "on"):
        return Response(
            {"detail": "Para reservar necesitamos tu autorización para usar tus datos (nombre y teléfono) "
                       "solo para gestionar la reserva.", "codigo": "sin_autorizacion"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    ip = (request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip() or request.META.get("REMOTE_ADDR", ""))
    llave = f"reservas:{tenant.slug}:{ip}"
    if cache.get(llave, 0) >= MAX_POR_HORA:
        return Response({"detail": "Hiciste muchas reservas seguidas. Escríbenos por WhatsApp y te ayudamos.",
                         "codigo": "demasiadas"}, status=status.HTTP_429_TOO_MANY_REQUESTS)

    servicio = _servicio(request, datos)
    fecha = _fecha(datos.get("fecha"))
    if servicio is None or fecha is None:
        return Response({"detail": "Elige el horario y la fecha."}, status=status.HTTP_400_BAD_REQUEST)
    origen = datos.get("origen") if datos.get("origen") in (Reserva.SITIO, Reserva.MESA_QR) else Reserva.SITIO
    detalle = _detalle_limpio(datos.get("detalle"))
    personas = _entero(datos.get("personas"), 0, 0, 1000)
    pedida = _entero(datos.get("mesa"), None, 1, 100_000)
    try:
        # La mesa que tocó en el plano, si sigue libre; si no, Cloudin elige la mejor.
        mesa = rs.mesa_pedida(pedida, servicio, fecha, rs._parse_hora(datos.get("hora")), personas) if pedida else None
        reserva = rs.crear_reserva(
            servicio=servicio, fecha=fecha, hora=datos.get("hora"), personas=datos.get("personas"),
            nombre=datos.get("nombre", ""), telefono=datos.get("telefono", ""), correo=datos.get("correo", ""),
            zona=datos.get("zona", ""), observaciones=datos.get("observaciones", ""), origen=origen,
            detalle={**detalle, "autorizo_datos": timezone.now().isoformat()},
            total_estimado=_entero(datos.get("total_estimado"), 0, 0, 100_000_000), clave_envio=str(datos.get("clave") or ""),
            mesa=mesa,
        )
    except rs.SinCupo as e:
        return Response({"detail": e.messages[0], "codigo": "sin_cupo", "sugerencias": e.sugerencias},
                        status=status.HTTP_409_CONFLICT)
    except ValidationError as e:
        return Response({"detail": e.messages[0], "codigo": "invalida"}, status=status.HTTP_400_BAD_REQUEST)

    cache.set(llave, cache.get(llave, 0) + 1, 3600)
    return Response({
        **reserva_json(reserva, tenant.name),
        "mensaje": ("¡Listo! Tu reserva quedó confirmada." if reserva.estado == Reserva.CONFIRMED
                    else "Recibimos tu reserva. Te confirmamos por WhatsApp muy pronto."),
        "whatsapp_url": rs.enlace_para_restaurante(reserva, tenant.name),
        # Pidió una mesa en el plano y alguien la tomó antes: se le avisa cuál le quedó.
        "mesa_cambiada": bool(pedida and reserva.mesa_id and reserva.mesa.number != pedida),
    }, status=status.HTTP_201_CREATED)


def _por_codigo(codigo):
    return Reserva.objects.filter(codigo=str(codigo).upper()[:8]).select_related("mesa", "servicio").first()


@api_view(["GET"])
@authentication_classes([])
def detalle(request, codigo):
    reserva = _por_codigo(codigo)
    telefono = rs.solo_digitos(request.GET.get("telefono", ""))
    # Con el código solo no basta: también el teléfono, para que nadie vea reservas ajenas.
    if reserva is None or len(telefono) < 7 or not reserva.telefono.endswith(telefono[-7:]):
        return Response({"detail": "No encontramos una reserva con ese código y teléfono."},
                        status=status.HTTP_404_NOT_FOUND)
    return Response(reserva_json(reserva, request.tenant.name))


@api_view(["POST"])
@authentication_classes([])
def cancelar(request, codigo):
    reserva = _por_codigo(codigo)
    telefono = rs.solo_digitos(request.data.get("telefono", ""))
    if reserva is None or not telefono or not reserva.telefono.endswith(telefono[-7:]):
        return Response({"detail": "No encontramos una reserva con ese código y teléfono."},
                        status=status.HTTP_404_NOT_FOUND)
    try:
        rs.cancelar(reserva, "El cliente", "Cancelada por el cliente desde el sitio")
    except ValidationError as e:
        return Response({"detail": e.messages[0]}, status=status.HTTP_400_BAD_REQUEST)
    return Response(reserva_json(reserva, request.tenant.name))
