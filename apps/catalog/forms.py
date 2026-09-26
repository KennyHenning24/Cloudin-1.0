import json

from django import forms
from django.core.exceptions import ValidationError

from .models import Category, Product
from .opciones import limpiar_grupos

MAX_FOTO = 3 * 1024 * 1024


class ProductoForm(forms.ModelForm):
    """Alta y edición de un producto desde el panel.

    El restaurante configura lo que ve el cliente: foto, descripción, toppings y
    si se permite escribir una observación. Nombre y precio se ponen al crear el
    producto; después solo los cambia el administrador de Cloudin (superusuario),
    para que la carta y la facturación no cambien por accidente.
    """

    opciones_json = forms.CharField(widget=forms.HiddenInput, required=False)

    class Meta:
        model = Product
        fields = ["category", "name", "price", "description", "imagen", "image_url",
                  "permite_observacion", "is_available"]
        labels = {
            "category": "Categoría", "name": "Nombre", "price": "Precio",
            "description": "Descripción", "imagen": "Subir foto", "image_url": "…o enlace de la foto",
            "permite_observacion": "Permitir observación (ej. «sin cebolla»)",
            "is_available": "Disponible para pedir",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3, "placeholder": "Qué lleva, tamaño, gramos…"}),
            "name": forms.TextInput(attrs={"placeholder": "Ej. Sandwich 2 Quesos"}),
            "price": forms.NumberInput(attrs={"min": 0, "step": 100, "placeholder": "35000"}),
            "image_url": forms.URLInput(attrs={"placeholder": "https://…/foto.jpg"}),
            "imagen": forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png,image/webp"}),
        }

    def __init__(self, *args, puede_todo=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = Category.objects.all()
        self.fields["opciones_json"].initial = json.dumps(self.instance.opciones or [], ensure_ascii=False)
        self.bloqueados = []
        if self.instance.pk and not puede_todo:
            for campo in ("name", "price", "category"):
                self.fields[campo].disabled = True
                self.bloqueados.append(campo)

    def clean_imagen(self):
        foto = self.cleaned_data.get("imagen")
        if foto and hasattr(foto, "size") and foto.size > MAX_FOTO:
            raise ValidationError("La foto pesa más de 3 MB. Usa una más liviana.")
        return foto

    def clean_price(self):
        precio = self.cleaned_data.get("price")
        if precio is not None and precio < 0:
            raise ValidationError("El precio no puede ser negativo.")
        return precio

    def clean_opciones_json(self):
        texto = self.cleaned_data.get("opciones_json") or "[]"
        try:
            return limpiar_grupos(json.loads(texto))
        except ValueError:
            raise ValidationError("No se pudieron leer los toppings. Vuelve a intentarlo.")

    def save(self, commit=True):
        producto = super().save(commit=False)
        producto.opciones = self.cleaned_data.get("opciones_json") or []
        if commit:
            producto.save()
        return producto
