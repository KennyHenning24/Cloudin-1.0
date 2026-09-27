"""Cloudin Meseros: quién toma los pedidos desde la tablet.

El mesero vive en la base **de su restaurante**, no en la de control. Eso hace
que pertenecer a un restaurante no sea un campo que alguien pueda cambiar: un
mesero de Cultura Brisket físicamente no existe en la base de otro local.

Tampoco es un usuario de Django. Tiene su propio usuario y contraseña, su propia
sesión y su propia pantalla: entrar como mesero no abre el panel del
administrador, y el administrador no necesita darle su clave a nadie.
"""

from django.contrib.auth.hashers import check_password, identify_hasher, make_password
from django.db import models
from django.utils import timezone


class Mesero(models.Model):
    nombre = models.CharField("Nombre", max_length=80)
    usuario = models.CharField(
        "Usuario", max_length=40, unique=True,
        help_text="Con esto entra en la tablet. Sin espacios; no distingue mayúsculas.",
    )
    # Hash, igual que Django: la contraseña en claro no se guarda en ninguna parte.
    password = models.CharField(max_length=128)
    # Copia cifrada (Fernet, llave CREDENTIAL_KEY del .env) para que el
    # administrador pueda volver a verla con su propia contraseña del panel.
    clave_cifrada = models.TextField(blank=True, editable=False)
    activo = models.BooleanField("Activo", default=True)
    ultimo_ingreso = models.DateTimeField(null=True, blank=True)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Mesero"
        verbose_name_plural = "Meseros"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        self.usuario = (self.usuario or "").strip().lower()
        super().save(*args, **kwargs)

    # ------------------------------------------------------------ contraseña

    def set_password(self, clave: str):
        from apps.tenants.crypto import cifrar, hay_llave

        self.password = make_password(clave)
        self.clave_cifrada = cifrar(clave) if hay_llave() else ""

    def clave_visible(self) -> str | None:
        """La contraseña en claro, si se guardó cifrada. None si no se puede."""
        from apps.tenants.crypto import descifrar

        return descifrar(self.clave_cifrada) if self.clave_cifrada else None

    def check_password(self, clave: str) -> bool:
        if not self.password:
            return False
        try:
            identify_hasher(self.password)
        except ValueError:
            return False
        return check_password(clave, self.password)

    def registrar_ingreso(self):
        self.ultimo_ingreso = timezone.now()
        self.save(update_fields=["ultimo_ingreso"])

    @property
    def iniciales(self) -> str:
        partes = [p for p in self.nombre.split() if p]
        return "".join(p[0] for p in partes[:2]).upper() or "M"
