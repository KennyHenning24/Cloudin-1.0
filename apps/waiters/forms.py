import re

from django import forms

from .models import Mesero

USUARIO_VALIDO = re.compile(r"^[a-z0-9._-]{3,40}$")


class MeseroForm(forms.ModelForm):
    """Alta y edición de un mesero. En la edición la contraseña es opcional:
    vacía significa «no la cambies»."""

    clave = forms.CharField(
        label="Contraseña", required=False, strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text="Mínimo 6 caracteres. Se guarda cifrada: puedes volver a verla en la lista de "
                  "meseros escribiendo tu contraseña del panel.",
    )
    clave2 = forms.CharField(
        label="Repite la contraseña", required=False, strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    class Meta:
        model = Mesero
        fields = ["nombre", "usuario", "empleado"]
        widgets = {
            "nombre": forms.TextInput(attrs={"placeholder": "Ej. Laura Gómez"}),
            "usuario": forms.TextInput(attrs={
                "placeholder": "Ej. laura", "autocapitalize": "none", "autocomplete": "off",
            }),
        }
        help_texts = {
            "usuario": "Con esto entra en la tablet. Minúsculas, números, punto o guion.",
            "empleado": "Opcional. Si también marca horario en Cloudin Employees, se cruzan "
                        "sus horas con lo que vendió.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.es_nuevo = self.instance.pk is None
        if self.es_nuevo:
            self.fields["clave"].required = True
            self.fields["clave2"].required = True
        else:
            self.fields["clave"].help_text = "Déjala vacía para no cambiarla."
        from apps.staffing.models import Empleado

        ocupados = Mesero.objects.exclude(pk=self.instance.pk).exclude(empleado__isnull=True)
        self.fields["empleado"].queryset = Empleado.objects.filter(activo=True).exclude(
            pk__in=ocupados.values_list("empleado_id", flat=True)
        )
        self.fields["empleado"].required = False

    def clean_usuario(self):
        usuario = (self.cleaned_data.get("usuario") or "").strip().lower()
        if not USUARIO_VALIDO.match(usuario):
            raise forms.ValidationError(
                "Entre 3 y 40 caracteres: minúsculas, números, punto, guion o guion bajo."
            )
        otros = Mesero.objects.filter(usuario=usuario).exclude(pk=self.instance.pk)
        if otros.exists():
            raise forms.ValidationError("Ya hay un mesero con ese usuario.")
        return usuario

    def clean(self):
        datos = super().clean()
        clave, clave2 = datos.get("clave") or "", datos.get("clave2") or ""
        if clave or clave2 or self.es_nuevo:
            if len(clave) < 6:
                self.add_error("clave", "Mínimo 6 caracteres.")
            elif clave != clave2:
                self.add_error("clave2", "Las dos contraseñas no coinciden.")
            elif clave.lower() == (datos.get("usuario") or "").lower():
                self.add_error("clave", "La contraseña no puede ser igual al usuario.")
        return datos

    def save(self, commit=True):
        mesero = super().save(commit=False)
        if self.cleaned_data.get("clave"):
            mesero.set_password(self.cleaned_data["clave"])
        if commit:
            mesero.save()
        return mesero
