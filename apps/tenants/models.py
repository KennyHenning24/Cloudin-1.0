import secrets

from django.conf import settings
from django.db import models


def generate_api_key() -> str:
    return "ck_" + secrets.token_urlsafe(32)


class Tenant(models.Model):
    """Un restaurante. Vive siempre en la base de control ('default')."""

    name = models.CharField("Nombre", max_length=120)
    slug = models.SlugField(
        "Subdominio",
        max_length=60,
        unique=True,
        help_text="Identificador en el subdominio: lajoya -> lajoya.cloudin.app",
    )
    api_key = models.CharField(max_length=64, unique=True, default=generate_api_key, editable=False)

    # Datos fiscales — se usan en la fase 2 (facturación electrónica).
    nit = models.CharField("NIT", max_length=30, blank=True)
    legal_name = models.CharField("Razón social", max_length=160, blank=True)
    address = models.CharField("Dirección", max_length=200, blank=True)
    phone = models.CharField("Teléfono", max_length=40, blank=True)
    city = models.CharField("Ciudad", max_length=80, blank=True)

    # Sitio web autorizado a mandarle pedidos a este restaurante. Por ahora uno
    # solo: la página desde la que el mesero comanda con la tablet.
    site_url = models.URLField("Sitio web del restaurante", blank=True)
    # De dónde se importa la carta (el archivo cloudin-menu.json del sitio).
    menu_fuente = models.URLField("Archivo de la carta", max_length=500, blank=True)
    # Página del sitio que atiende los QR de mesa. El enlace de cada mesa es
    # site_url + esta ruta + ?m=<token>.
    table_page_path = models.CharField(
        "Página de pedidos en mesa", max_length=120, default="/mesa.html"
    )
    # Última vez que ese sitio llamó a la API: es la señal de "está conectado".
    site_last_seen = models.DateTimeField(null=True, blank=True, editable=False)

    # Cómo se toman los pedidos. Es configuración del restaurante, no un dato de
    # su operación, por eso vive aquí y no en su base.
    AUTOSERVICIO = "autoservicio"
    MESEROS = "meseros"
    MIXTO = "mixto"
    MODOS_SERVICIO = [
        (AUTOSERVICIO, "Autoservicio: el cliente pide desde el QR"),
        (MESEROS, "Meseros: el mesero toma el pedido en la tablet"),
        (MIXTO, "Ambos: QR y meseros a la vez"),
    ]
    modo_servicio = models.CharField(
        "Cómo se toman los pedidos", max_length=14, choices=MODOS_SERVICIO, default=AUTOSERVICIO
    )

    # Qué contrató: solo el menú digital, o Cloudin completo (pedidos, turnos,
    # facturación, inventario…). Define qué secciones ve en su panel.
    PLAN_MENU = "menu"
    PLAN_COMPLETO = "completo"
    PLANES = [
        (PLAN_MENU, "Menú digital"),
        (PLAN_COMPLETO, "Cloudin completo"),
    ]
    plan = models.CharField("Plan", max_length=12, choices=PLANES, default=PLAN_MENU)

    # Página del menú para las mesas (la del QR), p. ej. https://x.pages.dev/menu.html.
    # Si está vacía, el QR lleva al menú de respaldo de Cloudin.
    menu_page = models.URLField("Página del menú (QR)", max_length=500, blank=True)
    # Otros orígenes autorizados además de site_url (dominio propio, pages.dev…).
    allowed_origins = models.JSONField("Otros sitios autorizados", default=list, blank=True)

    # Nombre físico de su base de datos (archivo sqlite o base postgres).
    db_name = models.CharField(max_length=80, blank=True, editable=False)

    is_active = models.BooleanField("Activo", default=True)
    provisioned_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Restaurante"
        verbose_name_plural = "Restaurantes"
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def es_plan_menu(self) -> bool:
        return self.plan == self.PLAN_MENU

    @property
    def origenes_permitidos(self) -> set[str]:
        """site_url + allowed_origins, reducidos a su origen (esquema://host:puerto)."""
        from urllib.parse import urlsplit

        origenes = set()
        for url in [self.site_url, *(self.allowed_origins or [])]:
            partes = urlsplit(str(url or "").strip())
            if partes.scheme in ("http", "https") and partes.netloc:
                origenes.add(f"{partes.scheme}://{partes.netloc}")
        return origenes

    @property
    def usa_meseros(self) -> bool:
        return self.modo_servicio in (self.MESEROS, self.MIXTO)

    @property
    def usa_autoservicio(self) -> bool:
        return self.modo_servicio in (self.AUTOSERVICIO, self.MIXTO)

    def save(self, *args, **kwargs):
        if not self.db_name:
            self.db_name = f"cloudin_{self.slug}"
        super().save(*args, **kwargs)

    @property
    def db_alias(self) -> str:
        return f"tenant_{self.slug}"

    @property
    def domain(self) -> str:
        return f"{self.slug}.{settings.TENANT_BASE_DOMAIN}"

    @property
    def site_origin(self) -> str:
        """El origen (esquema + host + puerto) del sitio, para permitirlo en CORS."""
        if not self.site_url:
            return ""
        from urllib.parse import urlsplit

        partes = urlsplit(self.site_url)
        return f"{partes.scheme}://{partes.netloc}" if partes.scheme and partes.netloc else ""

    def qr_link(self, token: str) -> str:
        """El enlace que lleva el QR de una mesa."""
        if not self.site_url:
            return ""
        ruta = self.table_page_path or "/mesa.html"
        if not ruta.startswith("/"):
            ruta = "/" + ruta
        return f"{self.site_url.rstrip('/')}{ruta}?m={token}"

    def rotate_api_key(self) -> str:
        self.api_key = generate_api_key()
        self.save(update_fields=["api_key"])
        return self.api_key


class TenantMembership(models.Model):
    """Vincula un usuario de Django (base de control) con su restaurante."""

    ROLE_OWNER = "owner"
    ROLE_ADMIN = "admin"
    ROLE_STAFF = "staff"
    ROLES = [
        (ROLE_OWNER, "Dueño del restaurante"),
        (ROLE_ADMIN, "Administrador del restaurante"),
        (ROLE_STAFF, "Mesero / cajero"),
    ]
    # Roles que administran: cambian la carta, los precios, las mesas y los ajustes.
    ROLES_ADMIN = (ROLE_OWNER, ROLE_ADMIN)

    user = models.OneToOneField(
        "auth.User", on_delete=models.CASCADE, related_name="tenant_membership"
    )
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=20, choices=ROLES, default=ROLE_ADMIN)
    created_at = models.DateTimeField(auto_now_add=True)

    # Copia cifrada de la contraseña, para que el panel maestro pueda mostrarla.
    # El login sigue usando el hash de auth_user; esto es solo para consultarla.
    # Se cifra con CREDENTIAL_KEY (.env), que no está en la base ni en el repo.
    password_cifrada = models.TextField(blank=True, editable=False)
    password_actualizada = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        verbose_name = "Usuario de restaurante"
        verbose_name_plural = "Usuarios de restaurante"

    def __str__(self):
        return f"{self.user.username} @ {self.tenant.slug}"

    @property
    def es_admin(self) -> bool:
        """Dueño o administrador: puede cambiar la carta, los precios y los ajustes."""
        return self.role in self.ROLES_ADMIN

    @property
    def es_dueno(self) -> bool:
        return self.role == self.ROLE_OWNER

    @property
    def password_visible(self):
        """La contraseña en claro, o None si no se guardó o la llave cambió."""
        from .crypto import descifrar

        return descifrar(self.password_cifrada)


class AceptacionLegal(models.Model):
    """Constancia de que un usuario aceptó los términos y la política de privacidad.

    Se acepta una sola vez por versión: si Cloudin cambia los documentos (sube
    LEGAL_VERSION en settings), cada usuario los vuelve a ver al entrar. Sin
    aceptarlos no se puede usar el panel.
    """

    user = models.ForeignKey("auth.User", on_delete=models.CASCADE, related_name="aceptaciones_legales")
    version = models.CharField(max_length=20)
    aceptado_en = models.DateTimeField(auto_now_add=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    navegador = models.CharField(max_length=300, blank=True)

    class Meta:
        verbose_name = "Aceptación de términos"
        verbose_name_plural = "Aceptaciones de términos"
        ordering = ["-aceptado_en"]
        constraints = [models.UniqueConstraint(fields=["user", "version"], name="una_aceptacion_por_version")]

    def __str__(self):
        return f"{self.user.username} · versión {self.version}"


class ApiToken(models.Model):
    """Token personal del superadministrador para la API de Cloudin.

    Lo usa, por ejemplo, `POST /api/admin/import-menu/` con
    `Authorization: Bearer <token>`. Solo se guarda su huella (SHA-256): el
    token en claro se muestra una única vez, al crearlo en el panel maestro.
    """

    user = models.ForeignKey("auth.User", on_delete=models.CASCADE, related_name="api_tokens")
    name = models.CharField("Nombre", max_length=80, help_text="Para qué es, p. ej. «Portátil de Juan».")
    prefix = models.CharField(max_length=12, editable=False)
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True, editable=False)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Token de API"
        verbose_name_plural = "Tokens de API"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.prefix}…)"

    @staticmethod
    def huella(token: str) -> str:
        import hashlib

        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @classmethod
    def crear(cls, user, name: str) -> tuple["ApiToken", str]:
        """Crea el token y devuelve (registro, token en claro). El claro no se guarda."""
        token = "cld_" + secrets.token_urlsafe(32)
        registro = cls.objects.create(user=user, name=name[:80], prefix=token[:12], token_hash=cls.huella(token))
        return registro, token

    @classmethod
    def validar(cls, token: str):
        """El registro vigente de ese token (de un superusuario activo), o None."""
        from django.utils import timezone

        if not token:
            return None
        registro = (cls.objects.select_related("user")
                    .filter(token_hash=cls.huella(token), revoked_at__isnull=True,
                            user__is_active=True, user__is_superuser=True)
                    .first())
        if registro is not None:
            cls.objects.filter(pk=registro.pk).update(last_used_at=timezone.now())
        return registro
