from django import forms

from .models import Empleado


class EmpleadoForm(forms.ModelForm):
    class Meta:
        model = Empleado
        fields = [
            "nombre", "tipo_documento", "documento", "cargo", "telefono", "correo",
            "forma_pago", "valor_hora", "salario_mensual", "codigo", "ingreso",
        ]
        widgets = {
            "ingreso": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "nombre": forms.TextInput(attrs={"placeholder": "Ej. Carlos Mesa"}),
            "cargo": forms.TextInput(attrs={"placeholder": "Mesero, cocina, caja…"}),
            "codigo": forms.TextInput(attrs={"placeholder": "Ej. 101"}),
        }
        help_texts = {
            "codigo": "Un número corto que la persona teclea en el reloj para marcar.",
            "valor_hora": "Solo si se le paga por hora.",
            "salario_mensual": "Solo si tiene salario fijo; la hora se estima sobre 240 h al mes.",
        }

    def clean(self):
        datos = super().clean()
        if datos.get("forma_pago") == Empleado.POR_HORA and not datos.get("valor_hora"):
            self.add_error("valor_hora", "Escribe cuánto vale la hora.")
        if datos.get("forma_pago") == Empleado.MENSUAL and not datos.get("salario_mensual"):
            self.add_error("salario_mensual", "Escribe el salario mensual.")
        return datos

    def clean_codigo(self):
        codigo = (self.cleaned_data.get("codigo") or "").strip()
        if not codigo:
            return codigo
        otros = Empleado.objects.filter(codigo=codigo)
        if self.instance.pk:
            otros = otros.exclude(pk=self.instance.pk)
        if otros.exists():
            raise forms.ValidationError("Ya hay alguien con ese código.")
        return codigo
