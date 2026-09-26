from django import forms

from apps.dining.models import Table

from .models import DIAS_SEMANA, AjustesReservas, BloqueoFecha, ServicioReserva


class AjustesForm(forms.ModelForm):
    class Meta:
        model = AjustesReservas
        fields = ["activo", "confirmacion_automatica", "whatsapp", "anticipacion_horas", "dias_maximo",
                  "max_personas", "tolerancia_minutos", "recordar_horas_antes", "mensaje_recordatorio"]
        widgets = {"mensaje_recordatorio": forms.Textarea(attrs={"rows": 3})}
        labels = {"whatsapp": "WhatsApp donde llegan las reservas"}


class ServicioForm(forms.ModelForm):
    dias = forms.TypedMultipleChoiceField(
        choices=list(enumerate(DIAS_SEMANA)), coerce=int, widget=forms.CheckboxSelectMultiple,
        label="Días que abre",
    )

    class Meta:
        model = ServicioReserva
        fields = ["nombre", "tipo", "dias", "abre", "cierra", "intervalo_minutos", "duracion_minutos",
                  "ultima_llegada_minutos", "cupo_personas", "descripcion", "activo", "orden"]
        widgets = {
            "abre": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "cierra": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
        }

    def clean_dias(self):
        dias = self.cleaned_data.get("dias") or []
        if not dias:
            raise forms.ValidationError("Marca al menos un día.")
        return sorted(set(dias))


class BloqueoForm(forms.ModelForm):
    class Meta:
        model = BloqueoFecha
        fields = ["fecha", "servicio", "motivo"]
        widgets = {"fecha": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}


class ReservaForm(forms.Form):
    """La reserva que el personal toma por teléfono, WhatsApp o en persona."""

    servicio = forms.ModelChoiceField(queryset=ServicioReserva.objects.none(), label="Horario")
    fecha = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    hora = forms.TimeField(required=False, widget=forms.TimeInput(attrs={"type": "time"}, format="%H:%M"))
    personas = forms.IntegerField(min_value=1, max_value=200, initial=2)
    nombre = forms.CharField(max_length=120, label="Nombre de quien reserva")
    telefono = forms.CharField(max_length=20, label="Teléfono (WhatsApp)")
    zona = forms.CharField(max_length=40, required=False, label="Zona preferida")
    mesa = forms.ModelChoiceField(queryset=Table.objects.none(), required=False,
                                  label="Mesa", empty_label="Asignar sola la mejor mesa")
    origen = forms.ChoiceField(choices=[("telefono", "Llamada"), ("whatsapp", "WhatsApp"), ("panel", "En persona")],
                               label="¿Cómo reservó?")
    observaciones = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}),
                                    label="Observaciones (cumpleaños, alergias…)")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["servicio"].queryset = ServicioReserva.objects.filter(activo=True)
        self.fields["mesa"].queryset = Table.objects.filter(is_active=True).order_by("number")
        self.fields["mesa"].label_from_instance = (
            lambda m: f"Mesa {m.number} · {m.seats} puestos" + (f" · {m.zona}" if m.zona else ""))
