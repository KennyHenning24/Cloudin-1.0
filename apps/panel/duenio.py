"""Panel del dueño: el menú digital (Inicio · Mi menú · Personalizar · Mesas y QR ·
Cuenta). Las pantallas de pedidos, mesas, cocina y meseros están en views.py y
meseros.py. Sigue los wireframes aprobados (docs/wireframes/).

Las pantallas pintan el estado inicial y el JavaScript del panel guarda los
cambios con la API /api/v1/staff/ (apps/api/catalogo_views.py). El asistente de
la primera vez (bienvenida) y la cuenta se guardan con formularios normales.
"""

import json
import re
import time
from datetime import datetime

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.models import User
from django.contrib.staticfiles import finders
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db.models import Max
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.http import require_GET

from apps.business.models import (
    DIAS,
    MEDIOS_DE_PAGO,
    NOMBRES_DIAS,
    SERVICIOS,
    OpeningHours,
    RestaurantSettings,
    normalizar_telefono,
    servicios_de,
)
from apps.catalog import images, selectors
from apps.catalog.models import TAX_CHOICES, Category, Menu, ModifierGroup, Product, Tag
from apps.common.money import a_pesos
from apps.dining import qr
from apps.dining.models import Table
from apps.tenants.models import TenantMembership

from .views import panel_view, resumen_del_servicio

PASOS = ["Logo y colores", "Datos del negocio", "Primera categoría", "Primer producto"]
SUGERENCIAS_CATEGORIA = ["Entradas", "Platos fuertes", "Hamburguesas", "Bebidas", "Postres", "Para compartir"]
ROLES_EQUIPO = {
    TenantMembership.ROLE_OWNER: "Dueño",
    TenantMembership.ROLE_ADMIN: "Administrador",
    TenantMembership.ROLE_STAFF: "Equipo",
}
COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
HORA = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


# ---------------------------------------------------------------- permisos


def _membresia(request):
    return getattr(request.user, "tenant_membership", None)


def es_admin(request) -> bool:
    """Dueño o administrador (o Juan en modo soporte)."""
    if request.user.is_superuser:
        return True
    m = _membresia(request)
    return bool(m and m.es_admin)


def es_dueno(request) -> bool:
    if request.user.is_superuser:
        return True
    m = _membresia(request)
    return bool(m and m.es_dueno)


def _solo_admin(request):
    if not es_admin(request):
        from django.core.exceptions import PermissionDenied

        raise PermissionDenied("Esta sección es solo para el dueño o el administrador del restaurante.")


def _nombre(user) -> str:
    return (user.first_name or user.get_full_name() or user.username.split(".")[-1]).split(" ")[0]


# ------------------------------------------------------------------ Inicio


def _pendientes(ajustes, resumen) -> list[dict]:
    """«Completa tu menú»: cada punto con su acción directa."""
    mi_menu = reverse("panel:mi-menu")
    personalizar = reverse("panel:personalizar")
    sin_foto, sin_precio, total = resumen["sin_foto"], resumen["sin_precio"], resumen["total"]
    return [
        {"texto": "Logo y colores", "hecho": bool(ajustes.logo and ajustes.color_primary),
         "accion": "Agregar", "href": f"{personalizar}#marca"},
        {"texto": "Datos del negocio y horario",
         "hecho": bool((ajustes.address or ajustes.city) and OpeningHours.objects.exists()),
         "accion": "Completar", "href": f"{personalizar}#horario"},
        {"texto": "Primera categoría y producto", "hecho": resumen["categorias"] > 0 and total > 0,
         "accion": "Agregar", "href": reverse("panel:carta-producto-nuevo")},
        {"texto": "WhatsApp", "hecho": bool(ajustes.whatsapp), "accion": "Agregar",
         "href": f"{personalizar}#contacto"},
        {"texto": f"Fotos en {sin_foto} producto{'s' if sin_foto != 1 else ''}" if sin_foto
         else "Fotos en tus productos", "hecho": total > 0 and not sin_foto, "accion": "Agregar",
         "href": f"{mi_menu}?estado=sin_foto"},
        {"texto": f"Precio de {sin_precio} producto{'s' if sin_precio != 1 else ''}" if sin_precio
         else "Precios de tus productos", "hecho": total > 0 and not sin_precio, "accion": "Completar",
         "href": f"{mi_menu}?estado=sin_precio"},
        {"texto": "Mesas y códigos QR", "hecho": Table.objects.filter(is_active=True).exists(),
         "accion": "Crear", "href": reverse("panel:qr")},
    ]


def vista_previa(tenant) -> dict:
    """Lo que necesita la vista previa: la página del menú del restaurante (su diseño,
    con ?cloudin-preview=1) y la API de donde el panel toma los datos guardados.
    Sin página publicada no hay vista previa (Cloudin no tiene un menú propio)."""
    pagina = qr.enlace_del_menu(tenant)
    return {
        "vista_previa": qr.con_parametro(pagina, "cloudin-preview", "1") if pagina else "",
        "api_menu": reverse("public_menu:api", args=[tenant.slug]) + "?vista=panel",
    }


def con_vista_previa(respuesta, tenant):
    """El panel solo deja meter en un iframe su propio origen: se suma el del menú."""
    from urllib.parse import urlsplit

    from config.seguridad import CSP

    partes = urlsplit(tenant.menu_page or "")
    if partes.scheme in ("http", "https") and partes.netloc:
        respuesta["Content-Security-Policy"] = CSP.replace(
            "frame-src 'self'", f"frame-src 'self' {partes.scheme}://{partes.netloc}")
    return respuesta


def _ultimo_cambio():
    fechas = [Product.history.aggregate(u=Max("history_date"))["u"],
              Category.history.aggregate(u=Max("history_date"))["u"]]
    fechas = [f for f in fechas if f]
    return max(fechas) if fechas else None


def inicio_menu(request):
    """Inicio del panel (lo llama views.inicio): el estado del menú, el resumen de
    pedidos y mesas, y el interruptor de los pedidos por QR."""
    tenant = request.tenant
    ajustes = RestaurantSettings.load()
    admin = es_admin(request)
    # La primera vez, el administrador empieza por el asistente (se puede saltar).
    if (admin and not request.user.is_superuser
            and ajustes.onboarding_done_at is None and ajustes.onboarding_step == 0):
        return redirect("panel:bienvenida")

    resumen = selectors.resumen_de_la_carta()
    pendientes = _pendientes(ajustes, resumen) if admin else []
    hechos = sum(1 for p in pendientes if p["hecho"])
    visto = cache.get(f"menu_visto:{tenant.slug}")
    agotados = list(Product.objects.filter(eliminado=False, is_available=False, price__isnull=False,
                                           category__deleted_at__isnull=True)
                    .order_by("category__position", "position")[:8])
    return render(request, "panel/duenio/inicio.html", {
        "seccion": "inicio",
        "nombre": _nombre(request.user),
        "hoy": timezone.localdate(),
        "es_admin": admin,
        "resumen": resumen,
        # En línea = tiene su página publicada y algo que mostrar.
        "publicado": bool(tenant.menu_page),
        "en_linea": bool(tenant.menu_page) and resumen["activos"] > 0,
        "visto": datetime.fromtimestamp(visto, tz=timezone.get_current_timezone()) if visto else None,
        "pendientes": pendientes,
        "hechos": hechos,
        "porcentaje": round(100 * hechos / len(pendientes)) if pendientes else 100,
        "asistente": (ajustes.onboarding_step if admin and ajustes.onboarding_done_at is None else 0),
        "pasos": len(PASOS),
        "agotados": agotados,
        "actividad": selectors.actividad_reciente(5),
        "ultimo_cambio": _ultimo_cambio(),
        "enlace": qr.enlace_del_menu(tenant),
        "menus": Menu.objects.filter(deleted_at__isnull=True).count(),
        "servicio": resumen_del_servicio(),
    })


# ---------------------------------------------------------------- Mi menú


@panel_view()
def mi_menu(request):
    """Categorías y productos del menú elegido. Buscar y filtrar pasa en el
    navegador (instantáneo); guardar, con la API."""
    menus = list(selectors.menus_del_panel())
    if not menus:
        Menu.principal()
        menus = list(selectors.menus_del_panel())
    elegido = request.GET.get("menu", "")
    menu = next((m for m in menus if str(m.uuid) == elegido), menus[0])
    categorias = list(selectors.categorias_del_panel(menu))
    por_categoria = {c.pk: [] for c in categorias}
    for p in selectors.productos_del_panel(menu=menu):
        por_categoria.setdefault(p.category_id, []).append(p)
    nuevo = reverse("panel:carta-producto-nuevo")
    for c in categorias:
        c.lista = por_categoria.get(c.pk, [])
        c.url_nuevo = f"{nuevo}?categoria={c.uuid}"
    productos = [p for c in categorias for p in c.lista]
    cuentas = {
        "todos": len(productos),
        "disponibles": sum(1 for p in productos if p.is_available),
        "agotados": sum(1 for p in productos if not p.is_available and p.price is not None),
        "sin_precio": sum(1 for p in productos if p.price is None),
        "sin_foto": sum(1 for p in productos if not p.foto),
    }
    estado = request.GET.get("estado", "")
    return render(request, "panel/duenio/mi_menu.html", {
        "seccion": "mi-menu",
        "es_admin": es_admin(request),
        "menus": menus,
        "menu": menu,
        "categorias": categorias,
        "todas_las_categorias": list(selectors.categorias_del_panel()),
        "cuentas": cuentas,
        "estado": estado if estado in ("disponibles", "agotados", "sin_precio", "sin_foto") else "",
        "q": request.GET.get("q", "")[:80],
        "enlace": qr.enlace_del_menu(request.tenant),
    })


# -------------------------------------------------------- editor de producto


def _producto_para_editor(producto, request) -> dict | None:
    if producto is None:
        return None
    from apps.api.catalogo_serializers import ProductSerializer

    datos = ProductSerializer(producto, context={"request": request}).data
    datos["variants"] = [{"id": str(v.uuid), "name": v.name, "price": int(v.price)}
                         for v in producto.variants.all()]
    datos["price"] = int(producto.price) if producto.price is not None else None
    return datos


@panel_view()
def producto(request, producto=None):
    """El editor: lo básico arriba, las opciones avanzadas plegadas y la vista previa.

    `?fragmento=1` devuelve solo el formulario, para abrirlo en el cajón lateral
    de la tablet sin salir de Mi menú."""
    _solo_admin(request)
    actual = None
    if producto is not None:
        actual = get_object_or_404(selectors.productos_del_panel(), uuid=producto)
    categorias = list(selectors.categorias_del_panel())
    if not categorias:
        messages.info(request, "Primero crea una categoría (por ejemplo «Platos fuertes») para tu producto.")
        return redirect(reverse("panel:mi-menu") + "?nueva=categoria")
    pedida = request.GET.get("categoria", "")
    categoria = (actual.category if actual else
                 next((c for c in categorias if str(c.uuid) == pedida), categorias[0]))
    grupos = ModifierGroup.objects.prefetch_related("options").order_by("position", "name")
    config = {
        "producto": _producto_para_editor(actual, request),
        "categoria": str(categoria.uuid),
        "categorias": {str(c.uuid): {"key": c.key, "name": c.name, "menu": c.menu.key} for c in categorias},
        "grupos": [{"id": str(g.uuid), "name": g.name, "min": g.min_select, "max": g.max_select,
                    "options": [{"id": str(o.uuid), "name": o.name, "price": int(o.price_delta)}
                                for o in g.options.all()]} for g in grupos],
        "volver": reverse("panel:mi-menu") + f"?menu={categoria.menu.uuid}",
        "editar": reverse("panel:carta-producto", args=["00000000-0000-0000-0000-000000000000"]),
    }
    contexto = {
        "seccion": "mi-menu",
        "p": actual,
        "categoria": categoria,
        "categorias": categorias,
        "etiquetas": Tag.objects.order_by("position", "name"),
        "marcadas": {t.key for t in actual.tags.all()} if actual else set(),
        "impuestos": TAX_CHOICES,
        "config": config,
        **vista_previa(request.tenant),
        "fragmento": request.GET.get("fragmento") == "1",
    }
    plantilla = "panel/duenio/_producto_form.html" if contexto["fragmento"] else "panel/duenio/producto.html"
    return con_vista_previa(render(request, plantilla, contexto), request.tenant)


# ------------------------------------------------------------ Personalizar


def _horario_por_dia() -> list[dict]:
    tramos = {d: [] for d in range(7)}
    for h in OpeningHours.objects.order_by("day", "opens"):
        tramos[h.day].append({"open": h.opens.strftime("%H:%M"), "close": h.closes.strftime("%H:%M")})
    return [{"n": d, "key": DIAS[d], "nombre": NOMBRES_DIAS[d], "corto": NOMBRES_DIAS[d][:3], "tramos": tramos[d]}
            for d in range(7)]


@panel_view()
def personalizar(request):
    """Marca del menú, datos del negocio, contacto, horario, redes y pagos."""
    _solo_admin(request)
    ajustes = RestaurantSettings.load()
    return con_vista_previa(render(request, "panel/duenio/personalizar.html", {
        "seccion": "personalizar",
        "ajustes": ajustes,
        "logo_url": ajustes.logo.url if ajustes.logo else "",
        "portada_url": ajustes.cover.url if ajustes.cover else "",
        "dias": _horario_por_dia(),
        "servicios": [(k, v, servicios_de(ajustes)[k]) for k, v in SERVICIOS.items()],
        "medios": [(k, v, k in (ajustes.payment_methods or [])) for k, v in MEDIOS_DE_PAGO.items()],
        **vista_previa(request.tenant),
        "enlace": qr.enlace_del_menu(request.tenant),
    }), request.tenant)


# ------------------------------------------------------------- Mesas y QR


@panel_view()
def mesas_y_qr(request):
    tenant = request.tenant
    mesas = [{"mesa": m, "enlace": qr.enlace_de_mesa(tenant, m)}
             for m in Table.objects.filter(is_active=True).order_by("number")]
    return render(request, "panel/duenio/mesas_qr.html", {
        "seccion": "qr",
        "es_admin": es_admin(request),
        "mesas": mesas,
        "con_qr": any(m["enlace"] for m in mesas),
        "enlace": qr.enlace_del_menu(tenant),
    })


# ------------------------------------------------------------------ Cuenta


def _usuario_libre(tenant, correo: str) -> str:
    from apps.tenants.services import nombre_usuario_completo

    base = slugify(correo.split("@")[0]).replace("-", "")[:24] or "equipo"
    candidato, n = base, 1
    while User.objects.filter(username=nombre_usuario_completo(tenant, candidato)).exists():
        n += 1
        candidato = f"{base}{n}"
    return candidato


def _guardar_copia_cifrada(user, clave: str) -> None:
    """La copia cifrada de la contraseña que el panel maestro puede mostrar (regla 10)."""
    from apps.tenants.crypto import cifrar, hay_llave

    m = TenantMembership.objects.filter(user=user).first()
    if m is not None:
        m.password_cifrada = cifrar(clave) if hay_llave() else ""
        m.password_actualizada = timezone.now()
        m.save(update_fields=["password_cifrada", "password_actualizada"])


@panel_view()
def cuenta(request):
    """Perfil, contraseña, equipo (según el rol), tema y cerrar sesión."""
    tenant, user = request.tenant, request.user
    soporte = user.is_superuser
    form_clave = PasswordChangeForm(user)
    if request.method == "POST":
        accion = request.POST.get("accion", "")
        if accion == "perfil" and not soporte:
            correo = request.POST.get("email", "").strip().lower()[:254]
            if correo and User.objects.filter(email__iexact=correo).exclude(pk=user.pk).exists():
                messages.warning(request, "Ese correo ya lo usa otra cuenta de Cloudin.")
            else:
                user.first_name = request.POST.get("first_name", "").strip()[:150]
                user.last_name = request.POST.get("last_name", "").strip()[:150]
                user.email = correo
                user.save(update_fields=["first_name", "last_name", "email"])
                messages.success(request, "Tus datos quedaron guardados.")
                return redirect("panel:cuenta")
        elif accion == "clave" and not soporte:
            form_clave = PasswordChangeForm(user, request.POST)
            if form_clave.is_valid():
                form_clave.save()
                _guardar_copia_cifrada(user, form_clave.cleaned_data["new_password1"])
                update_session_auth_hash(request, user)
                messages.success(request, "Listo: tu contraseña cambió. Úsala la próxima vez que entres.")
                return redirect("panel:cuenta")
        elif accion == "invitar" and es_admin(request):
            if _invitar(request, tenant):
                return redirect("panel:cuenta")
        elif accion in ("quitar", "reenviar") and es_admin(request):
            _gestionar_miembro(request, tenant, accion)
            return redirect("panel:cuenta")

    equipo = (TenantMembership.objects.filter(tenant=tenant, user__is_active=True)
              .select_related("user").order_by("role", "user__first_name"))
    return render(request, "panel/duenio/cuenta.html", {
        "seccion": "cuenta",
        "soporte": soporte,
        "es_admin": es_admin(request),
        "es_dueno": es_dueno(request),
        "membresia": _membresia(request),
        "rol": "Soporte de Cloudin" if soporte else ROLES_EQUIPO.get(getattr(_membresia(request), "role", ""), ""),
        "roles": ROLES_EQUIPO,
        "equipo": equipo,
        "form_clave": form_clave,
        "enlace": qr.enlace_del_menu(tenant),
    })


def _invitar(request, tenant) -> bool:
    from apps.tenants.invitations import enviar_invitacion
    from apps.tenants.services import crear_usuario

    nombre = request.POST.get("nombre", "").strip()[:150]
    correo = request.POST.get("correo", "").strip().lower()[:254]
    rol = request.POST.get("rol", TenantMembership.ROLE_STAFF)
    permitidos = [TenantMembership.ROLE_ADMIN, TenantMembership.ROLE_STAFF]
    if rol not in permitidos:
        rol = TenantMembership.ROLE_STAFF
    if not nombre or "@" not in correo:
        messages.warning(request, "Escribe el nombre y el correo de la persona que vas a invitar.")
        return False
    if User.objects.filter(email__iexact=correo).exists():
        messages.warning(request, "Ese correo ya tiene una cuenta en Cloudin.")
        return False
    user, _ = crear_usuario(tenant, _usuario_libre(tenant, correo), rol=rol, nombre=nombre, correo=correo)
    try:
        enviar_invitacion(user, tenant)
    except Exception:  # el correo puede fallar; la cuenta queda y se reenvía desde aquí
        messages.warning(request, f"Creamos la cuenta de {nombre}, pero el correo no salió. Usa «Reenviar».")
        return True
    messages.success(request, f"Le enviamos la invitación a {correo}. Tiene 7 días para crear su contraseña.")
    return True


def _gestionar_miembro(request, tenant, accion: str) -> None:
    from apps.tenants.invitations import enviar_invitacion

    m = (TenantMembership.objects.filter(tenant=tenant, pk=request.POST.get("miembro"), user__is_active=True)
         .select_related("user").first())
    if m is None or m.user_id == request.user.pk or m.role == TenantMembership.ROLE_OWNER:
        messages.warning(request, "Esa persona no se puede cambiar desde aquí.")
        return
    if accion == "reenviar":
        try:
            enviar_invitacion(m.user, tenant)
            messages.success(request, f"Invitación reenviada a {m.user.email}.")
        except Exception:
            messages.warning(request, "El correo no salió. Revisa la dirección e intenta más tarde.")
        return
    if not es_dueno(request):
        messages.warning(request, "Solo el dueño puede sacar a alguien del equipo.")
        return
    m.user.is_active = False
    m.user.save(update_fields=["is_active"])
    messages.success(request, f"{m.user.first_name or m.user.username} ya no tiene acceso al panel.")


# ------------------------------------------------- asistente de la primera vez


def _paso_valido(valor, maximo: int) -> int:
    try:
        return max(1, min(int(valor), maximo))
    except (TypeError, ValueError):
        return 1


@panel_view()
def bienvenida(request):
    """4 pasos y el final. Se puede saltar en cualquier momento y se retoma
    desde el Inicio donde iba (RestaurantSettings.onboarding_step)."""
    _solo_admin(request)
    ajustes = RestaurantSettings.load()
    final = len(PASOS) + 1

    if request.method == "POST":
        if request.POST.get("accion") == "saltar":
            if ajustes.onboarding_step == 0:
                ajustes.onboarding_step = 1
                ajustes.save(update_fields=["onboarding_step", "updated_at"])
            messages.info(request, "Cuando quieras, sigues desde «Completa tu menú» en el Inicio.")
            return redirect("panel:inicio")
        paso = _paso_valido(request.POST.get("paso"), len(PASOS))
        try:
            siguiente = GUARDAR_PASO[paso](request, ajustes)
        except ValidationError as e:
            messages.warning(request, e.messages[0])
            return redirect(f"{reverse('panel:bienvenida')}?paso={paso}")
        ajustes.onboarding_step = max(ajustes.onboarding_step, siguiente)
        campos = ["onboarding_step", "updated_at"]
        if siguiente == final and ajustes.onboarding_done_at is None:
            ajustes.onboarding_done_at = timezone.now()
            campos.append("onboarding_done_at")
        ajustes.save(update_fields=campos)
        return redirect(f"{reverse('panel:bienvenida')}?paso={siguiente}")

    paso = _paso_valido(request.GET.get("paso") or ajustes.onboarding_step or 1, final)
    if ajustes.onboarding_step == 0:
        ajustes.onboarding_step = 1
        ajustes.save(update_fields=["onboarding_step", "updated_at"])
    categorias = list(selectors.categorias_del_panel())
    elegida = request.session.get("bienvenida_categoria", "")
    dias = _horario_por_dia()
    primero = next((d["tramos"][0] for d in dias if d["tramos"]), {"open": "12:00", "close": "21:00"})
    return con_vista_previa(render(request, "panel/duenio/bienvenida.html", {
        "paso": paso,
        "final": final,
        "pasos": PASOS,
        "titulo_paso": PASOS[paso - 1] if paso < final else "Todo listo",
        "ajustes": ajustes,
        "logo_url": ajustes.logo.url if ajustes.logo else "",
        "tenant": request.tenant,
        "dias": dias,
        "hay_horario": any(d["tramos"] for d in dias),
        "abre": primero["open"],
        "cierra": primero["close"],
        "sugerencias": SUGERENCIAS_CATEGORIA,
        "categorias": categorias,
        "categoria_elegida": elegida or (str(categorias[-1].uuid) if categorias else ""),
        "creada_en_paso_3": bool(elegida),
        "enlace": qr.enlace_del_menu(request.tenant),
        **vista_previa(request.tenant),
    }), request.tenant)


def _paso_marca(request, ajustes) -> int:
    cambios = []
    for campo in ("color_primary", "color_secondary", "color_background", "color_text"):
        valor = request.POST.get(campo, "").strip().upper()
        if valor and not COLOR.match(valor):
            raise ValidationError("Usa colores en formato #RRGGBB.")
        if valor and valor != getattr(ajustes, campo):
            setattr(ajustes, campo, valor)
            cambios.append(campo)
    if cambios:
        ajustes.save(update_fields=[*cambios, "updated_at"])
    return 2


def _paso_negocio(request, ajustes) -> int:
    ajustes.tagline = request.POST.get("tagline", "").strip()[:120]
    ajustes.address = request.POST.get("address", "").strip()[:200]
    ajustes.city = request.POST.get("city", "").strip()[:80]
    whatsapp = request.POST.get("whatsapp", "").strip()
    numero = normalizar_telefono(whatsapp)
    if whatsapp and not numero:
        raise ValidationError("Escribe el WhatsApp como un celular de 10 dígitos (ej. 300 123 4567).")
    ajustes.whatsapp = numero
    ajustes.save(update_fields=["tagline", "address", "city", "whatsapp", "updated_at"])

    dias = sorted({int(d) for d in request.POST.getlist("dias") if d.isdigit() and int(d) <= 6})
    abre, cierra = request.POST.get("abre", ""), request.POST.get("cierra", "")
    if dias:
        if not (HORA.match(abre) and HORA.match(cierra)) or abre == cierra:
            raise ValidationError("Revisa el horario: la hora de abrir y la de cerrar deben ser distintas.")
        OpeningHours.objects.all().delete()
        OpeningHours.objects.bulk_create([OpeningHours(day=d, opens=abre, closes=cierra) for d in dias])
        from apps.catalog.services import subir_version_del_menu

        subir_version_del_menu()
    return 3


def _paso_categoria(request, ajustes) -> int:
    nombre = request.POST.get("categoria", "").strip()[:80]
    if not nombre:
        raise ValidationError("Escribe el nombre de tu primera categoría (por ejemplo «Platos fuertes»).")
    menu = Menu.principal()
    categoria = Category.objects.filter(menu=menu, name__iexact=nombre, deleted_at__isnull=True).first()
    if categoria is None:
        from apps.catalog.services import siguiente_posicion

        categoria = Category.objects.create(
            menu=menu, name=nombre, position=siguiente_posicion(Category.objects.filter(menu=menu)))
    request.session["bienvenida_categoria"] = str(categoria.uuid)
    return 4


def _paso_producto(request, ajustes) -> int:
    from apps.catalog.services import siguiente_posicion

    nombre = request.POST.get("name", "").strip()[:120]
    if not nombre:
        raise ValidationError("Escribe el nombre de tu primer producto.")
    precio = a_pesos(re.sub(r"\D", "", request.POST.get("price", "")) or None)
    categoria = Category.objects.filter(uuid=request.POST.get("category") or None, deleted_at__isnull=True).first()
    if categoria is None:
        nueva = request.POST.get("nueva_categoria", "").strip()[:80] or "Platos"
        categoria = Category.objects.create(menu=Menu.principal(), name=nueva)
    producto = Product(category=categoria, name=nombre, price=precio, is_available=precio is not None,
                       position=siguiente_posicion(Product.objects.filter(category=categoria)))
    producto.save()
    foto = request.FILES.get("foto")
    if foto:
        try:
            producto.imagen = images.a_webp(foto, images.LADO_PRODUCTO, producto.key)
            producto.save(update_fields=["imagen", "updated_at"])
        except ValidationError as e:
            messages.warning(request, f"El producto quedó, pero la foto no: {e.messages[0]}")
    request.session.pop("bienvenida_categoria", None)
    return len(PASOS) + 1


GUARDAR_PASO = {1: _paso_marca, 2: _paso_negocio, 3: _paso_categoria, 4: _paso_producto}


# -------------------------------------------------------------------- PWA


@require_GET
def manifest(request):
    """El panel se instala como app en el celular (alcance /panel/)."""
    contenido = {
        "name": "Cloudin · Panel",
        "short_name": "Cloudin",
        "description": "Tu menú digital: precios, agotados, fotos y códigos QR.",
        "lang": "es-CO",
        "start_url": "/panel/",
        "scope": "/panel/",
        "display": "standalone",
        "orientation": "any",
        "background_color": "#13151C",
        "theme_color": "#13151C",
        "icons": [
            {"src": static("img/pwa/cloudin-192.png"), "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": static("img/pwa/cloudin-512.png"), "sizes": "512x512", "type": "image/png", "purpose": "any"},
            {"src": static("img/pwa/cloudin-maskable-512.png"), "sizes": "512x512", "type": "image/png",
             "purpose": "maskable"},
        ],
        "shortcuts": [
            {"name": "Mi menú", "url": "/panel/mi-menu/"},
            {"name": "Agregar producto", "url": "/panel/mi-menu/producto/nuevo/"},
        ],
    }
    return HttpResponse(json.dumps(contenido, ensure_ascii=False), content_type="application/manifest+json")


@require_GET
def service_worker(request):
    """Se sirve desde /panel/ para que su alcance cubra todo el panel."""
    ruta = finders.find("panel/sw.js")
    if not ruta:
        raise Http404
    with open(ruta, encoding="utf-8") as archivo:
        codigo = archivo.read().replace("__VERSION__", _version_estaticos())
    respuesta = HttpResponse(codigo, content_type="application/javascript")
    respuesta["Service-Worker-Allowed"] = "/panel/"
    respuesta["Cache-Control"] = "no-cache"
    return respuesta


def _version_estaticos() -> str:
    """Cambia cuando cambian el CSS o el JS del panel: el service worker renueva su caché."""
    marcas = []
    for ruta in ("css/cloudin.css", "panel/js/ui.js", "panel/js/mi-menu.js", "panel/js/editor-producto.js"):
        archivo = finders.find(ruta)
        if archivo:
            import os

            marcas.append(int(os.path.getmtime(archivo)))
    return str(max(marcas) if marcas else int(time.time()))


@require_GET
def sin_conexion(request):
    """La página que muestra el service worker cuando no hay internet."""
    return render(request, "panel/duenio/sin_conexion.html")
