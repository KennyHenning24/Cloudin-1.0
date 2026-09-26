from django import forms

from .models import EmpresaFiscal, ResolucionNumeracion


class EmpresaForm(forms.ModelForm):
    class Meta:
        model = EmpresaFiscal
        fields = [
            "razon_social", "nombre_comercial", "nit", "digito_verificacion",
            "direccion", "ciudad", "departamento", "correo_facturacion", "telefono",
            "regimen", "precios_incluyen_impuesto", "certificado_vence",
        ]
        labels = {
            "digito_verificacion": "DV",
            "correo_facturacion": "Correo para las facturas",
            "precios_incluyen_impuesto": "Los precios del menú ya incluyen impuesto",
            "certificado_vence": "Vencimiento del certificado digital",
        }
        help_texts = {
            "precios_incluyen_impuesto": "Lo normal en restaurantes: el precio de la carta "
                                         "es lo que paga el cliente, impuesto incluido.",
            "certificado_vence": "La fecha que aparece en el certificado que te entregó tu proveedor.",
        }
        widgets = {
            "certificado_vence": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "razon_social": forms.TextInput(attrs={"placeholder": "Como aparece en el RUT"}),
            "nit": forms.TextInput(attrs={"placeholder": "901234567"}),
            "digito_verificacion": forms.TextInput(attrs={"maxlength": 1, "placeholder": "1"}),
        }


class ResolucionForm(forms.ModelForm):
    class Meta:
        model = ResolucionNumeracion
        fields = [
            "tipo_documento", "numero_resolucion", "fecha_expedicion", "fecha_vencimiento",
            "prefijo", "rango_desde", "rango_hasta", "consecutivo_actual", "clave_tecnica",
        ]
        labels = {
            "numero_resolucion": "Número de resolución DIAN",
            "consecutivo_actual": "Último número ya usado",
        }
        help_texts = {
            "consecutivo_actual": "Si es una resolución nueva, déjalo en 0.",
            "clave_tecnica": "Solo para factura electrónica; la entrega la DIAN.",
        }
        widgets = {
            "fecha_expedicion": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "fecha_vencimiento": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "prefijo": forms.TextInput(attrs={"placeholder": "FE"}),
        }

    def clean(self):
        datos = super().clean()
        desde, hasta = datos.get("rango_desde"), datos.get("rango_hasta")
        if desde and hasta and hasta < desde:
            self.add_error("rango_hasta", "El rango final no puede ser menor que el inicial.")
        actual = datos.get("consecutivo_actual")
        if desde and hasta and actual is not None and not (desde - 1 <= actual <= hasta):
            self.add_error("consecutivo_actual", "El consecutivo debe estar dentro del rango.")
        return datos
