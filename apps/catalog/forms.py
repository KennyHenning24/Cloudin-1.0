import json

from django import forms
from django.core.exceptions import ValidationError

from .legacy import guardar_opciones_legacy, opciones_legacy
from .models import Category, Product
from .opciones import limpiar_grupos

MAX_FOTO = 3 * 1024 * 1024


class ProductoForm(forms.ModelForm):
    """Alta y edición de un producto desde el panel.

    El dueño o el administrador del restaurante cambian todo: nombre, precio,
    categoría, foto, descripción, toppings y observación. Las comandas y facturas
    ya emitidas guardan su propio precio, y cada cambio queda en el historial.
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
        self.fields["category"].queryset = Category.objects.filter(deleted_at__isnull=True)
        # Los tamaños no van aquí: este formulario solo edita las adiciones.
        iniciales = opciones_legacy(self.instance, incluir_variantes=False) if self.instance.pk else []
        self.fields["opciones_json"].initial = json.dumps(iniciales, ensure_ascii=False)
        self.bloqueados = []

    def clean_imagen(self):
        foto = self.cleaned_data.get("imagen")
        if foto and hasattr(foto, "size") and foto.size > MAX_FOTO:
            raise ValidationError("La foto pesa más de 3 MB. Usa una más liviana.")
        return foto

    def clean_price(self):
        precio = self.cleaned_data.get("price")
        if precio is None:
            raise ValidationError("Escribe el precio.")
        if precio < 0:
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
        if commit:
            producto.save()
            guardar_opciones_legacy(producto, self.cleaned_data.get("opciones_json") or [])
        return producto
