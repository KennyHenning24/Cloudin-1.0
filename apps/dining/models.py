import secrets

from django.db import models


def generate_table_token() -> str:
    """Token del QR de la mesa. Corto para que el QR sea fácil de escanear."""
    return secrets.token_urlsafe(9)


class Table(models.Model):
    number = models.PositiveIntegerField("Número de mesa", unique=True)
    seats = models.PositiveIntegerField("Puestos", default=4)
    # Dónde queda (Salón, Patio, Terraza...). Es un dato de la mesa, no su nombre:
    # la mesa se sigue llamando por su número.
    zona = models.CharField("Zona", max_length=40, blank=True)
    # Si se ofrece en las reservas por internet. Las que no, quedan para quien
    # llega sin reservar.
    reservable = models.BooleanField("Se puede reservar", default=True)
    token = models.CharField(
        "Token QR", max_length=32, unique=True, default=generate_table_token, editable=False
    )
    is_active = models.BooleanField("Activa", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Mesa"
        verbose_name_plural = "Mesas"
        ordering = ["number"]

    def __str__(self):
        return f"Mesa {self.number}"

    @property
    def open_session(self):
        """Cuenta abierta de la mesa, si está ocupada."""
        return self.sessions.filter(status="open").order_by("-opened_at").first()

    @property
    def is_occupied(self) -> bool:
        return self.open_session is not None

    def rotate_token(self) -> str:
        self.token = generate_table_token()
        self.save(update_fields=["token"])
        return self.token
