"""Seguridad del acceso: intentos de login, modo soporte y redirecciones.

- **Intentos de login.** Cinco contraseñas equivocadas seguidas para el mismo
  usuario (o veinte desde la misma dirección) bloquean el acceso quince minutos.
  Frena a quien intente adivinar claves a fuerza bruta.
- **Modo soporte.** El superusuario de Cloudin puede entrar al panel de cualquier
  restaurante, pero ya no lo hace solo por tener la sesión del panel maestro
  abierta: tiene que confirmar su contraseña, queda un aviso visible de que está
  en modo soporte y el permiso vence a la hora sin actividad.
- **Redirecciones.** Los formularios que devuelven a «donde estaba» solo aceptan
  direcciones de este mismo sitio (nada de mandar a otra página).
"""

import time

from django.contrib import messages
from django.contrib.admin.forms import AdminAuthenticationForm
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, PasswordResetConfirmView, PasswordResetView
from django.core.cache import cache
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from apps.tenants.models import Tenant

INTENTOS_USUARIO = 5
INTENTOS_IP = 20
BLOQUEO_SEGUNDOS = 15 * 60
SOPORTE_SEGUNDOS = 60 * 60          # sin actividad, el modo soporte vence en una hora
SOPORTE_MAXIMO = 8 * 60 * 60        # y nunca dura más de ocho horas seguidas


def ip_de(request) -> str:
    """La IP del cliente, para los topes de intentos y de pedidos.

    Detrás de Cloudflare (el Worker de Cloudflare Containers, y Render, que también
    pasa por Cloudflare) llega en CF-Connecting-IP: la pone Cloudflare y el cliente no
    la puede falsear. Si no está, la primera de X-Forwarded-For (un proxy que la
    reescribe, como el Worker) o REMOTE_ADDR. Render solo *agrega* a X-Forwarded-For,
    así que ahí la primera la podría inventar el cliente."""
    cloudflare = request.META.get("HTTP_CF_CONNECTING_IP", "").strip()
    if cloudflare:
        return cloudflare
    reenviada = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return (reenviada.split(",")[0].strip() if reenviada else "") or request.META.get("REMOTE_ADDR", "")


def volver_seguro(request, destino, defecto):
    """Una dirección a la que se puede volver sin riesgo: solo de este sitio."""
    if destino and url_has_allowed_host_and_scheme(destino, allowed_hosts={request.get_host()},
                                                   require_https=request.is_secure()):
        return destino
    return defecto


# ------------------------------------------------------------------- login


class LimiteDeIntentos:
    """Cuenta los intentos fallidos por usuario y por dirección IP."""

    def _llaves(self, usuario=""):
        ip = ip_de(self.request)
        return f"login:ip:{ip}", f"login:u:{(usuario or '').strip().lower()}"

    def bloqueado(self, usuario=""):
        llave_ip, llave_u = self._llaves(usuario)
        return cache.get(llave_ip, 0) >= INTENTOS_IP or (usuario and cache.get(llave_u, 0) >= INTENTOS_USUARIO)

    def fallo(self, usuario=""):
        for llave in self._llaves(usuario):
            if llave.endswith(":u:"):
                continue
            cache.set(llave, cache.get(llave, 0) + 1, BLOQUEO_SEGUNDOS)

    def limpiar(self, usuario=""):
        cache.delete(self._llaves(usuario)[1])


class LoginSeguro(LimiteDeIntentos, LoginView):
    template_name = "panel/login.html"

    def post(self, request, *args, **kwargs):
        usuario = request.POST.get("username", "")
        if self.bloqueado(usuario):
            form = self.get_form()
            form.is_bound = True
            form._errors = {"__all__": form.error_class([
                "Demasiados intentos fallidos. Por seguridad, espera 15 minutos y vuelve a intentarlo."])}
            return self.render_to_response(self.get_context_data(form=form))
        return super().post(request, *args, **kwargs)

    def form_invalid(self, form):
        self.fallo(self.request.POST.get("username", ""))
        return super().form_invalid(form)

    def form_valid(self, form):
        self.limpiar(form.get_user().username)
        return super().form_valid(form)


class LoginAdminSeguro(LoginSeguro):
    """El login de /admin/ (el del panel maestro) con el mismo límite de intentos."""

    template_name = "admin/login.html"
    authentication_form = AdminAuthenticationForm

    def get_context_data(self, **kwargs):
        from django.contrib import admin

        contexto = super().get_context_data(**kwargs)
        contexto.update(admin.site.each_context(self.request))
        contexto.setdefault("title", "Entrar")
        contexto.setdefault("site_header", admin.site.site_header)
        contexto["app_path"] = self.request.get_full_path()
        return contexto

    def get_success_url(self):
        return volver_seguro(self.request, self.request.POST.get("next") or self.request.GET.get("next"), "/master/")


class RecuperarSeguro(PasswordResetView):
    """Recuperar la contraseña, con un tope por dirección para que no se use para
    llenar de correos a nadie."""

    def form_valid(self, form):
        llave = f"recuperar:{ip_de(self.request)}"
        if cache.get(llave, 0) >= 5:
            form.add_error(None, "Ya pediste varios correos. Espera una hora e inténtalo de nuevo.")
            return self.form_invalid(form)
        cache.set(llave, cache.get(llave, 0) + 1, 3600)
        return super().form_valid(form)


class CrearClave(PasswordResetConfirmView):
    """Crear la contraseña desde un enlace: la invitación del dueño o «Olvidé mi contraseña».

    Deja la sesión iniciada (lo que promete la pantalla) y guarda también la copia
    cifrada que el panel maestro puede mostrar (requisito de Juan, ver crypto.py).
    """

    post_reset_login = True
    post_reset_login_backend = "apps.tenants.auth.UsuarioOCorreo"
    success_url = "/panel/"

    def form_valid(self, form):
        respuesta = super().form_valid(form)
        from django.utils import timezone

        from apps.tenants.crypto import cifrar, hay_llave
        from apps.tenants.models import TenantMembership

        membresia = TenantMembership.objects.filter(user=form.user).first()
        if membresia is not None and hay_llave():
            membresia.password_cifrada = cifrar(form.cleaned_data["new_password1"])
            membresia.password_actualizada = timezone.now()
            membresia.save(update_fields=["password_cifrada", "password_actualizada"])
        return respuesta

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        usuario = getattr(self, "user", None)  # lo deja Django si el enlace es válido
        membresia = getattr(usuario, "tenant_membership", None) if usuario is not None else None
        contexto["restaurante"] = membresia.tenant.name if membresia else ""
        return contexto


# ------------------------------------------------------------ modo soporte


def _llave_soporte(tenant) -> str:
    return f"soporte:{tenant.slug}"


def soporte_vigente(request, tenant) -> bool:
    """Si el superusuario confirmó su clave para este restaurante hace poco."""
    datos = request.session.get(_llave_soporte(tenant))
    if not datos:
        return False
    ahora = time.time()
    if ahora - datos.get("ultimo", 0) > SOPORTE_SEGUNDOS or ahora - datos.get("inicio", 0) > SOPORTE_MAXIMO:
        request.session.pop(_llave_soporte(tenant), None)
        return False
    # Cada pantalla renueva la hora de inactividad (no el máximo).
    if ahora - datos.get("ultimo", 0) > 60:
        datos["ultimo"] = ahora
        request.session[_llave_soporte(tenant)] = datos
    return True


@login_required
def soporte(request):
    """El superusuario confirma su contraseña antes de entrar al panel de un restaurante."""
    if not request.user.is_superuser:
        return redirect("panel:inicio")
    slug = request.GET.get("tenant") or request.POST.get("tenant") or request.session.get("tenant_activo")
    tenant = Tenant.objects.filter(slug=slug, is_active=True).first() if slug else None
    if tenant is None:
        messages.warning(request, "Elige primero un restaurante.")
        return redirect("master:home")
    siguiente = volver_seguro(request, request.GET.get("next") or request.POST.get("next"), "/panel/")
    error = ""
    if request.method == "POST":
        limite = LimiteDeIntentos()
        limite.request = request
        if limite.bloqueado(request.user.username):
            error = "Demasiados intentos. Espera 15 minutos."
        elif request.user.check_password(request.POST.get("clave", "")):
            limite.limpiar(request.user.username)
            ahora = time.time()
            request.session[_llave_soporte(tenant)] = {"inicio": ahora, "ultimo": ahora}
            request.session["tenant_activo"] = tenant.slug
            messages.warning(request, f"Estás en el panel de {tenant.name} en modo soporte de Cloudin.")
            return redirect(siguiente)
        else:
            limite.fallo(request.user.username)
            error = "Esa no es tu contraseña."
    return render(request, "panel/soporte.html", {"t": tenant, "next": siguiente, "error": error})


@login_required
def soporte_salir(request):
    if request.method == "POST":
        for llave in [k for k in request.session.keys() if k.startswith("soporte:")]:
            request.session.pop(llave, None)
        request.session.pop("tenant_activo", None)
        messages.success(request, "Saliste del modo soporte.")
    return redirect("master:home")


def entrar_como_restaurante(request):
    """Cierra la sesión del superusuario y lleva al login del restaurante."""
    slug = request.GET.get("tenant", "")
    if request.method == "POST":
        logout(request)
    return redirect(reverse("panel:login") + (f"?tenant={slug}" if slug else ""))
