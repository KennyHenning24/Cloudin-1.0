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
        fields = ["name", "slug", "plan", "site_url", "legal_name", "nit", "address", "city", "phone"]
        labels = {
            "plan": "Plan",
            "name": "Nombre del restaurante",
            "slug": "Identificador (subdominio)",
            "site_url": "Link del sitio web",
            "legal_name": "Razón social",
            "nit": "NIT",
            "address": "Dirección",
            "city": "Ciudad",
            "phone": "Teléfono",
        }
        help_texts = {
            "plan": "Menú digital: carta, personalización y QR. Completo: además pedidos, turnos, "
            "facturación e inventario.",
            "slug": "Solo minúsculas, números y guiones. Es su subdominio y el nombre de su base de datos.",
            "site_url": "La página desde la que el restaurante enviará los pedidos. "
            "Si todavía no existe, se puede registrar después desde su panel.",
            "nit": "Se usará en la fase de facturación electrónica. Puede quedar vacío.",
        }
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Ej. Cultura Brisket", "autofocus": True}),
            "slug": forms.TextInput(attrs={"placeholder": "culturabrisket"}),
            "site_url": forms.URLInput(attrs={"placeholder": "https://pedidos.mirestaurante.com"}),
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
