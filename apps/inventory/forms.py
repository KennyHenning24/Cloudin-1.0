"""Formularios del inventario.

Todos hablan el idioma del restaurante, no el del contador: «como se la vende
el proveedor», «como la usa la receta». La conversión la hace el sistema.
"""

from decimal import Decimal

from django import forms

from .models import (
    Bodega,
    CategoriaInsumo,
    Compra,
    CompraItem,
    Conteo,
    Insumo,
    Proveedor,
    Receta,
    RecetaItem,
)


class InsumoForm(forms.ModelForm):
    class Meta:
        model = Insumo
        fields = [
            "nombre", "codigo", "categoria", "unidad_compra", "unidad_consumo",
            "factor_conversion", "stock_minimo", "perecedero", "proveedor",
        ]
        widgets = {
            "nombre": forms.TextInput(attrs={"placeholder": "Ej. Carne de res (brisket)"}),
            "codigo": forms.TextInput(attrs={"placeholder": "Ej. CAR-001"}),
            "unidad_compra": forms.TextInput(attrs={"placeholder": "kg, bulto de 50 kg, caja×24"}),
        }
        help_texts = {
            "factor_conversion": "Cuántas unidades de consumo trae una unidad de compra. "
                                 "Un bulto de 50 kg consumido en gramos: 50000.",
            "stock_minimo": "En unidad de consumo. Deja 0 si no quieres alertas.",
        }

    def clean_factor_conversion(self):
        factor = self.cleaned_data.get("factor_conversion") or Decimal("0")
        if factor <= 0:
            raise forms.ValidationError("El factor tiene que ser mayor que cero.")
        return factor

    def clean_codigo(self):
        codigo = (self.cleaned_data.get("codigo") or "").strip()
        if not codigo:
            return codigo
        otros = Insumo.objects.filter(codigo=codigo)
        if self.instance.pk:
            otros = otros.exclude(pk=self.instance.pk)
        if otros.exists():
            raise forms.ValidationError("Ya hay un insumo con ese código.")
        return codigo


class ProveedorForm(forms.ModelForm):
    class Meta:
        model = Proveedor
        fields = ["nombre", "nit", "contacto", "telefono", "correo", "direccion",
                  "dias_credito", "notas"]
        widgets = {
            "nombre": forms.TextInput(attrs={"placeholder": "Ej. Distribuidora La 33"}),
            "notas": forms.Textarea(attrs={"rows": 2}),
        }
        help_texts = {"dias_credito": "0 si siempre se le paga de una."}


class CategoriaInsumoForm(forms.ModelForm):
    class Meta:
        model = CategoriaInsumo
        fields = ["nombre", "posicion"]
        widgets = {"nombre": forms.TextInput(attrs={"placeholder": "Carnes, abarrotes, empaques…"})}


class BodegaForm(forms.ModelForm):
    class Meta:
        model = Bodega
        fields = ["nombre", "descripcion", "principal"]
        widgets = {"nombre": forms.TextInput(attrs={"placeholder": "Cocina, bodega, barra…"})}


class CompraForm(forms.ModelForm):
    class Meta:
        model = Compra
        fields = ["proveedor", "bodega", "numero_factura", "fecha", "medio_pago", "cuenta",
                  "vence", "pagada", "notas"]
        widgets = {
            "fecha": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "vence": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "notas": forms.Textarea(attrs={"rows": 2}),
            "numero_factura": forms.TextInput(attrs={"placeholder": "Ej. FV-8821"}),
        }

    def clean(self):
        datos = super().clean()
        if datos.get("medio_pago") == Compra.CREDITO:
            datos["pagada"] = False
            if not datos.get("vence"):
                self.add_error("vence", "Si es a crédito, pon la fecha en que hay que pagarla.")
        if datos.get("medio_pago") in (Compra.BANCO, Compra.TARJETA) and not datos.get("cuenta"):
            self.add_error("cuenta", "Escribe de qué cuenta o tarjeta salió el dinero.")
        return datos


class CompraItemForm(forms.ModelForm):
    class Meta:
        model = CompraItem
        fields = ["insumo", "cantidad", "valor_unitario", "lote", "vence"]
        widgets = {"vence": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["insumo"].queryset = Insumo.objects.filter(activo=True)


# `extra=0` a propósito: las líneas las agrega el navegador con el botón, así la
# pantalla no arranca con filas vacías que confunden.
CompraItemFormSet = forms.inlineformset_factory(
    Compra, CompraItem, form=CompraItemForm, extra=0, min_num=1, validate_min=True,
    can_delete=True,
)


class RecetaForm(forms.ModelForm):
    class Meta:
        model = Receta
        fields = ["nombre", "rendimiento", "unidad_rendimiento", "notas", "activa"]
        widgets = {
            "notas": forms.Textarea(attrs={"rows": 3, "placeholder": "Cómo se prepara…"}),
            "nombre": forms.TextInput(attrs={"placeholder": "Ej. Salsa base de la casa"}),
        }
        help_texts = {
            "rendimiento": "Cuántas porciones salen de preparar la receta una vez.",
        }


class RecetaItemForm(forms.ModelForm):
    class Meta:
        model = RecetaItem
        fields = ["insumo", "subreceta", "cantidad", "nota"]

    def __init__(self, *args, receta=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["insumo"].queryset = Insumo.objects.filter(activo=True)
        self.fields["insumo"].required = False
        subrecetas = Receta.objects.filter(es_subreceta=True, activa=True)
        if receta is not None and receta.pk:
            # Una receta no puede usarse a sí misma.
            subrecetas = subrecetas.exclude(pk=receta.pk)
        self.fields["subreceta"].queryset = subrecetas
        self.fields["subreceta"].required = False
        self.fields["subreceta"].label = "…o esta subreceta"

    def clean(self):
        datos = super().clean()
        if not datos.get("insumo") and not datos.get("subreceta"):
            raise forms.ValidationError("Elige un insumo o una subreceta.")
        if datos.get("insumo") and datos.get("subreceta"):
            raise forms.ValidationError("Una línea es un insumo o una subreceta, no las dos.")
        if (datos.get("cantidad") or 0) <= 0:
            self.add_error("cantidad", "La cantidad tiene que ser mayor que cero.")
        return datos


class MovimientoManualForm(forms.Form):
    """Entradas y salidas a mano: ajustes, mermas, devoluciones.

    El motivo es obligatorio. Un ajuste sin explicación es un agujero en el
    inventario que nadie puede auditar después.
    """

    ENTRADA = "entrada"
    SALIDA = "salida"

    from .models import Movimiento as _M

    OPCIONES = [
        (_M.AJUSTE_POSITIVO, "Ajuste positivo (encontré más de lo que decía)"),
        (_M.DEVOLUCION_CLIENTE, "Devolución de un cliente"),
        (_M.TRASLADO_ENTRADA, "Traslado recibido de otra bodega"),
        (_M.MERMA, "Merma: se dañó, se venció o se botó"),
        (_M.AJUSTE_NEGATIVO, "Ajuste negativo (hay menos de lo que decía)"),
        (_M.DEVOLUCION_PROVEEDOR, "Devolución al proveedor"),
        (_M.TRASLADO_SALIDA, "Traslado enviado a otra bodega"),
    ]

    tipo = forms.ChoiceField(choices=OPCIONES, label="Qué pasó")
    bodega = forms.ModelChoiceField(queryset=Bodega.objects.none(), label="Bodega")
    cantidad = forms.DecimalField(
        min_value=Decimal("0.001"), decimal_places=3, label="Cantidad",
        help_text="En unidad de consumo.",
    )
    costo_unitario = forms.DecimalField(
        required=False, decimal_places=4, label="Costo por unidad (solo entradas)",
        help_text="Déjalo vacío para usar el costo promedio actual.",
    )
    motivo = forms.CharField(
        max_length=200, label="Motivo",
        widget=forms.TextInput(attrs={"placeholder": "Obligatorio: qué pasó exactamente"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["bodega"].queryset = Bodega.objects.filter(activa=True)

    def clean_motivo(self):
        motivo = (self.cleaned_data.get("motivo") or "").strip()
        if len(motivo) < 4:
            raise forms.ValidationError("Escribe el motivo: es lo que permite auditarlo después.")
        return motivo


class ConteoForm(forms.ModelForm):
    solo_con_stock = forms.BooleanField(
        required=False, initial=False, label="Contar solo los insumos que tienen saldo",
    )

    class Meta:
        model = Conteo
        fields = ["bodega", "responsable", "notas"]
        widgets = {"notas": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["bodega"].queryset = Bodega.objects.filter(activa=True)
