from urllib.parse import urlsplit

from django import forms
from django.contrib.auth.models import User
from django.utils.text import slugify

from apps.tenants.models import Tenant, TenantMembership
from apps.tenants.services import nombre_usuario_completo

RESERVADOS = {"www", "api", "admin", "app", "master", "panel", "static"}


class RestauranteForm(forms.ModelForm):
    """Alta de un restaurante + su primer usuario administrador."""

    admin_usuario = forms.CharField(
        label="Usuario del administrador",
        max_length=40,
        initial="admin",
        help_text="Se le antepone el nombre del restaurante para que sea único.",
    )
    admin_nombre = forms.CharField(
        label="Nombre de la persona", max_length=80, required=False,
        widget=forms.TextInput(attrs={"placeholder": "Opcional — ej. María Restrepo"}),
    )
    admin_correo = forms.EmailField(
        label="Correo del administrador",
        help_text="Con este correo recupera su contraseña y le llegan los avisos del sistema.",
        widget=forms.EmailInput(attrs={"placeholder": "maria@mirestaurante.com"}),
    )

    class Meta:
        model = Tenant
        fields = ["name", "slug", "menu_page", "legal_name", "nit", "address", "city", "phone"]
        labels = {
            "name": "Nombre del restaurante",
            "slug": "Identificador (subdominio)",
            "menu_page": "Página del menú digital",
            "legal_name": "Razón social",
            "nit": "NIT",
            "address": "Dirección",
            "city": "Ciudad",
            "phone": "Teléfono",
        }
        help_texts = {
            "slug": "Solo minúsculas, números y guiones. Es su subdominio y el nombre de su base de datos.",
            "menu_page": "Donde está publicado su menú (Cloudflare Pages). Con ella salen los QR de "
            "las mesas y ese menú puede enviar pedidos. Si todavía no está publicado, déjala vacía: "
            "se pone después en la ficha del restaurante.",
            "nit": "Dato del negocio. Puede quedar vacío.",
        }
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Ej. Cultura Brisket", "autofocus": True}),
            "slug": forms.TextInput(attrs={"placeholder": "culturabrisket"}),
            "menu_page": forms.URLInput(attrs={"placeholder": "https://culturabrisket.pages.dev/"}),
        }

    def clean_slug(self):
        slug = slugify(self.cleaned_data["slug"])
        if slug in RESERVADOS:
            raise forms.ValidationError("Ese identificador está reservado por el sistema.")
        if Tenant.objects.filter(slug=slug).exists():
            raise forms.ValidationError("Ya hay un restaurante con ese identificador.")
        return slug

    def clean(self):
        datos = super().clean()
        slug, usuario = datos.get("slug"), datos.get("admin_usuario")
        if slug and usuario:
            username = f"{slug}.{usuario.strip().lower()}"
            if User.objects.filter(username=username).exists():
                self.add_error("admin_usuario", f"El usuario '{username}' ya existe.")
        return datos


class EmpleadoForm(forms.Form):
    """Alta de un empleado dentro de un restaurante que ya existe."""

    usuario = forms.CharField(label="Usuario", max_length=40)
    nombre = forms.CharField(label="Nombre de la persona", max_length=80, required=False)
    correo = forms.EmailField(
        label="Correo", required=False,
        help_text="Para que pueda recuperar su contraseña.",
    )
    rol = forms.ChoiceField(label="Rol", choices=TenantMembership.ROLES)

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)

    def clean_usuario(self):
        usuario = self.cleaned_data["usuario"].strip().lower()
        if not usuario.replace(".", "").replace("_", "").replace("-", "").isalnum():
            raise forms.ValidationError("Use solo letras, números, puntos, guiones o guión bajo.")
        username = nombre_usuario_completo(self.tenant, usuario)
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError(f"El usuario '{username}' ya existe.")
        return usuario


def origen(url: str) -> str:
    """https://menu.lacasa.com/carta.html -> https://menu.lacasa.com ("" si no es http/https)."""
    partes = urlsplit((url or "").strip())
    return f"{partes.scheme}://{partes.netloc}" if partes.scheme in ("http", "https") and partes.netloc else ""


class MenuDigitalForm(forms.Form):
    """La página del menú digital de un restaurante: con ella salen los QR y queda
    autorizada para pedir (Tenant.origenes_permitidos)."""

    pagina = forms.URLField(
        label="Página del menú (QR)", required=False, max_length=500,
        widget=forms.URLInput(attrs={"placeholder": "https://culturabrisket.pages.dev/"}),
        help_text="La dirección exacta del menú publicado, sin ?mesa. Vacía: no hay QR ni pedidos.",
    )
    otros = forms.CharField(
        label="Otras direcciones autorizadas", required=False,
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "https://menu.culturabrisket.com"}),
        help_text="Una por línea, solo si el mismo menú también se abre desde otra dirección "
        "(p. ej. su dominio propio).",
    )

    def clean_otros(self):
        salida = []
        for linea in (self.cleaned_data.get("otros") or "").splitlines():
            if not linea.strip():
                continue
            o = origen(linea)
            if not o:
                raise forms.ValidationError(f"«{linea.strip()[:80]}» no es una dirección: debe empezar por https://")
            if o not in salida:
                salida.append(o)
        return salida
