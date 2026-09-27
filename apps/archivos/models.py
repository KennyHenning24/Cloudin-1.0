from django.db import models


class Archivo(models.Model):
    """Un archivo subido (las fotos del panel) guardado en la base de control.

    Solo se usa con FOTOS_EN_LA_BASE (ver almacen.py). Las fotos de todos los
    restaurantes van aquí: son públicas (salen en su menú) y así se sirven sin saber de
    qué restaurante es la petición."""

    nombre = models.CharField(max_length=255, unique=True)
    contenido = models.BinaryField()
    tipo = models.CharField("Tipo de contenido", max_length=100, blank=True)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Archivo"
        verbose_name_plural = "Archivos"

    def __str__(self):
        return self.nombre
