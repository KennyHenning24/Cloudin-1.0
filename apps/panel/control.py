"""Cloudin Control en el panel: el detector de fugas y las situaciones a revisar."""

from django import forms
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.control import services as cs
from apps.control.models import AjustesControl, AlertaControl

from .seguridad import volver_seguro
from .views import panel_view

ICONOS_FUGA = {
    "caja": ("durazno", '<rect x="2" y="6" width="20" height="13" rx="2.5"/><circle cx="12" cy="12.5" r="2.6"/>'),
    "inventario": ("lavanda", '<path d="M20 7L12 3 4 7v10l8 4 8-4z"/><path d="M4 7l8 4 8-4M12 11v10"/>'),
    "mermas": ("rosa", '<path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14"/>'),
    "anulaciones": ("amarillo", '<circle cx="12" cy="12" r="9"/><path d="M8.5 8.5l7 7M15.5 8.5l-7 7"/>'),
    "descuentos": ("cielo", '<path d="M19 5L5 19"/><circle cx="7" cy="7" r="2.5"/><circle cx="17" cy="17" r="2.5"/>'),
    "cortesias": ("menta", '<path d="M20 12v9H4v-9M2 7h20v5H2zM12 21V7M12 7H8a2.5 2.5 0 1 1 0-5c3 0 4 5 4 5zM12 7h4a2.5 2.5 0 1 0 0-5c-3 0-4 5-4 5z"/>'),
    "devoluciones": ("durazno", '<path d="M9 14L4 9l5-5"/><path d="M4 9h11a5 5 0 0 1 0 10h-4"/>'),
    "recetas": ("lavanda", '<path d="M4 4h11a3 3 0 0 1 3 3v13H7a3 3 0 0 1-3-3z"/><path d="M8 9h6M8 13h6"/>'),
    "compras": ("cielo", '<circle cx="9" cy="20" r="1.5"/><circle cx="18" cy="20" r="1.5"/><path d="M2 3h3l2.7 12.4a2 2 0 0 0 2 1.6h7.6a2 2 0 0 0 2-1.6L21 7H6"/>'),
    "otras": ("gris", '<circle cx="12" cy="12" r="9"/><path d="M12 8v4M12 16h.01"/>'),
}
COLOR_SEVERIDAD = {"critical": "rosa", "warning": "amarillo", "info": "cielo"}


class AjustesControlForm(forms.ModelForm):
    class Meta:
        model = AjustesControl
        exclude = ["actualizado"]


def _quien(request):
    return request.user.get_full_name() or request.user.username


@panel_view(requiere_turno=False)
def control(request):
    ultimo = cs.analizar_si_hace_falta(_quien(request))
    nombre_periodo = request.GET.get("periodo", "semana")
    desde, hasta, etiqueta = cs.periodo(nombre_periodo)
    fugas = cs.fugas(desde, hasta)
    for c in fugas["categorias"]:
        c["color"], c["icono"] = ICONOS_FUGA.get(c["clave"], ICONOS_FUGA["otras"])

    estado = request.GET.get("estado", "abiertas")
    severidad = request.GET.get("severidad", "")
    tipo = request.GET.get("tipo", "")
    alertas = AlertaControl.objects.all()
    if estado == "abiertas":
        alertas = alertas.filter(estado__in=AlertaControl.ABIERTAS)
    elif estado in dict(AlertaControl.ESTADOS):
        alertas = alertas.filter(estado=estado)
    if severidad:
        alertas = alertas.filter(severidad=severidad)
    if tipo:
        alertas = alertas.filter(tipo=tipo)
    lista = sorted(alertas[:200], key=lambda a: (-a.peso, a.estado != AlertaControl.NEW, -a.detectada_en.timestamp()))
    for a in lista:
        a.color = COLOR_SEVERIDAD.get(a.severidad, "gris")
    tipos_presentes = sorted({a.tipo for a in AlertaControl.objects.filter(estado__in=AlertaControl.ABIERTAS)})
    segundos = (timezone.now() - ultimo.momento).total_seconds()
    revisado = ("hace un momento" if segundos < 60 else
                f"hace {int(segundos // 60)} min" if segundos < 3600 else
                f"el {timezone.localtime(ultimo.momento):%d/%m a las %H:%M}")
    return render(request, "panel/control.html", {
        "seccion": "control",
        "ultimo": ultimo,
        "revisado": revisado,
        "fugas": fugas,
        "periodo": nombre_periodo,
        "etiqueta": etiqueta,
        "periodos": [("hoy", "Hoy"), ("semana", "Esta semana"), ("anterior", "Semana pasada"),
                     ("mes", "Este mes"), ("30", "Últimos 30 días")],
        "resumen": cs.resumen_alertas(),
        "alertas": lista,
        "estado": estado,
        "severidad": severidad,
        "tipo": tipo,
        "tipos": [(t, dict(AlertaControl.TIPOS).get(t, t)) for t in tipos_presentes],
    })


@panel_view(requiere_turno=False)
@require_POST
def control_analizar(request):
    analisis = cs.analizar(_quien(request))
    if analisis.alertas_nuevas:
        messages.success(request, f"Análisis listo: {analisis.alertas_nuevas} situación(es) nueva(s) para revisar.")
    else:
        messages.success(request, "Análisis listo: no apareció nada nuevo.")
    return redirect(volver_seguro(request, request.POST.get("volver"), reverse("panel:control")))


@panel_view(requiere_turno=False)
@require_POST
def control_alerta(request, alerta_id):
    alerta = get_object_or_404(AlertaControl, pk=alerta_id)
    estado = request.POST.get("estado")
    if estado not in dict(AlertaControl.ESTADOS):
        messages.warning(request, "Estado no válido.")
    else:
        cs.cambiar_estado(alerta, estado, _quien(request), request.POST.get("nota", ""))
        textos = {"reviewed": "quedó en revisión", "resolved": "quedó resuelta",
                  "dismissed": "quedó descartada", "new": "volvió a nueva"}
        messages.success(request, f"«{alerta.titulo}» {textos.get(estado, 'actualizada')}.")
    return redirect(volver_seguro(request, request.POST.get("volver"), reverse("panel:control")))


@panel_view(solo_admin=True, requiere_turno=False)
def control_ajustes(request):
    ajustes = AjustesControl.actuales()
    form = AjustesControlForm(request.POST or None, instance=ajustes)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Sensibilidad guardada. El próximo análisis ya la usa.")
        return redirect("panel:control")
    return render(request, "panel/control_ajustes.html", {"seccion": "control", "form": form})
