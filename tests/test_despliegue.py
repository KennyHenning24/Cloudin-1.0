"""Configuración del servidor: DATABASE_URL y bases de restaurante en Postgres."""

from types import SimpleNamespace

import pytest

from apps.tenants.db import tenant_db_settings
from config.entorno import direccion_publica, es_postgres, lista, postgres_desde_url


def test_database_url_de_neon():
    pg = postgres_desde_url(
        "postgresql://cloudin:cl%40ve%2Fsegura@ep-lago-123.us-east-2.aws.neon.tech/control"
        "?sslmode=require&channel_binding=require")
    assert pg == {
        "NAME": "control",
        "USER": "cloudin",
        "PASSWORD": "cl@ve/segura",  # los caracteres codificados en la URL se decodifican
        "HOST": "ep-lago-123.us-east-2.aws.neon.tech",
        "PORT": "5432",
        "OPTIONS": {"sslmode": "require", "channel_binding": "require"},
    }


def test_database_url_con_puerto_y_sin_base():
    pg = postgres_desde_url("postgres://u:p@db.local:6543")
    assert (pg["HOST"], pg["PORT"], pg["NAME"], pg["OPTIONS"]) == ("db.local", "6543", "postgres", {})


def test_solo_postgres():
    assert es_postgres("postgresql://u@h/b") and es_postgres("postgres://u@h/b")
    assert not es_postgres("") and not es_postgres("sqlite:///control.sqlite3")
    with pytest.raises(ValueError):
        postgres_desde_url("mysql://u:p@h/b")


def test_lista():
    assert lista(" .workers.dev, localhost,,") == [".workers.dev", "localhost"]
    assert lista("") == []


def test_base_de_restaurante_en_postgres_lleva_ssl(settings):
    settings.TENANT_DB_ENGINE = "postgres"
    settings.DB_CONN_MAX_AGE = 60
    settings.TENANT_PG = {"HOST": "h", "PORT": "5432", "USER": "u", "PASSWORD": "p",
                          "OPTIONS": {"sslmode": "require"}, "MAINTENANCE_DB": "control"}
    cfg = tenant_db_settings(SimpleNamespace(db_name="cloudin_lajoya"))
    assert cfg["ENGINE"] == "django.db.backends.postgresql"
    assert (cfg["NAME"], cfg["HOST"], cfg["USER"]) == ("cloudin_lajoya", "h", "u")
    assert cfg["OPTIONS"] == {"sslmode": "require"}
    assert cfg["CONN_MAX_AGE"] == 60 and cfg["CONN_HEALTH_CHECKS"] is True
    # Cada restaurante recibe su propia copia: cambiarla no toca la configuración global.
    cfg["OPTIONS"]["sslmode"] = "disable"
    assert settings.TENANT_PG["OPTIONS"]["sslmode"] == "require"


def test_direccion_publica_en_render(settings):
    """En Render, sin CLOUDIN_PUBLIC_URL, el enlace del panel que entrega el panel maestro
    sale con la dirección del servicio y no con <slug>.localhost."""
    from apps.tenants.services import enlace_panel

    assert direccion_publica("", "cloudin-abcd.onrender.com") == "https://cloudin-abcd.onrender.com"
    assert direccion_publica("https://app.cloudin.co/", "cloudin-abcd.onrender.com") == "https://app.cloudin.co"
    assert direccion_publica("", "") == ""
    settings.CLOUDIN_PUBLIC_URL = direccion_publica("", "cloudin-abcd.onrender.com")
    assert enlace_panel(SimpleNamespace(slug="la-casa")) == "https://cloudin-abcd.onrender.com/panel/login/"


def test_ip_del_cliente_detras_de_cloudflare_y_render():
    """Los topes por IP (pedidos, logins) no se esquivan inventando X-Forwarded-For."""
    from django.test import RequestFactory

    from apps.panel.seguridad import ip_de

    rf = RequestFactory()
    # Render solo agrega a X-Forwarded-For: la primera la puede escribir el cliente.
    # Cloudflare pone CF-Connecting-IP con la IP real y esa es la que vale.
    falsa = rf.get("/", HTTP_X_FORWARDED_FOR="1.2.3.4, 181.50.60.70", HTTP_CF_CONNECTING_IP="181.50.60.70")
    assert ip_de(falsa) == "181.50.60.70"
    # El Worker de Cloudflare Containers reescribe X-Forwarded-For con la IP real.
    assert ip_de(rf.get("/", HTTP_X_FORWARDED_FOR="181.50.60.70")) == "181.50.60.70"
    # Sin proxy (en local): la del socket.
    assert ip_de(rf.get("/", REMOTE_ADDR="127.0.0.1")) == "127.0.0.1"


def test_el_contenedor_escucha_en_el_puerto_que_pide_el_servidor():
    """Render asigna el puerto en PORT (10000); Cloudflare no lo define y usa 8000."""
    from pathlib import Path

    from django.conf import settings

    dockerfile = (Path(settings.BASE_DIR) / "Dockerfile").read_text()
    assert "--bind 0.0.0.0:${PORT:-8000}" in dockerfile
