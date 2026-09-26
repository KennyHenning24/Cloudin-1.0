"""Sistema de diseño: tokens, contraste y la guía viva."""

from pathlib import Path

import pytest
from django.template import Context, Template

from apps.panel.design_system import contraste, tabla_de_contraste, tokens

CSS = Path(__file__).resolve().parent.parent / "static" / "css" / "cloudin.css"


def test_la_paleta_oficial_esta_en_los_tokens():
    t = tokens()
    assert t["marca"]["color-ink"] == "#13151C"
    assert t["marca"]["color-brand"] == "#F77A27"
    assert t["marca"]["color-brand-start"] == "#EF7026" and t["marca"]["color-brand-end"] == "#E36225"
    assert t["marca"]["color-snow"] == "#E9ECF3"
    assert t["marca"]["on-brand"] == "#13151C"  # texto de los botones naranjas


def test_contrastes_verificados_del_prompt():
    assert contraste("#FFFFFF", "#F77A27") == pytest.approx(2.7, abs=0.05)   # blanco sobre naranja: NO
    assert contraste("#13151C", "#F77A27") == pytest.approx(6.74, abs=0.05)
    assert contraste("#E9ECF3", "#13151C") == pytest.approx(15.4, abs=0.1)
    assert contraste("#C2410C", "#FFFFFF") == pytest.approx(5.18, abs=0.05)


def test_todos_los_pares_del_tema_pasan_aa():
    no_pasan = [f for f in tabla_de_contraste(tokens()) if not f["pasa"] and not f["nombre"].startswith("(No usar)")]
    assert no_pasan == []


def test_sin_texto_blanco_sobre_naranja_en_las_plantillas():
    import re

    plantillas = Path(__file__).resolve().parent.parent / "templates"
    malas = [str(p) for p in plantillas.rglob("*.html")
             if re.search(r"brand(-grad)?\);\s*color:#fff", p.read_text(encoding="utf-8"))]
    assert malas == []
    assert not re.search(r"brand(-grad)?\);\s*color:#fff", CSS.read_text(encoding="utf-8"))


def test_la_fuente_se_sirve_desde_cloudin():
    base = (Path(__file__).resolve().parent.parent / "templates" / "base.html").read_text(encoding="utf-8")
    assert "fonts.googleapis" not in base and "css/cloudin.css" in base
    assert (CSS.parent.parent / "fonts" / "plus-jakarta-sans-latin.woff2").stat().st_size > 10_000


def test_iconos_accesibles():
    html = Template('{% load cloudin %}{% icono "agotado" %}|{% icono "x" "ico" "Cerrar" %}').render(Context())
    decorativo, con_nombre = html.split("|")
    assert 'aria-hidden="true"' in decorativo
    assert 'role="img"' in con_nombre and 'aria-label="Cerrar"' in con_nombre


def test_pesos_con_el_formato_del_contrato():
    html = Template("{% load cloudin %}{{ a|cop }}|{{ b|cop }}").render(Context({"a": 24000, "b": None}))
    assert html == "$ 24.000|"


@pytest.mark.django_db
def test_guia_viva_solo_con_debug(client, settings):
    settings.DEBUG = False
    assert client.get("/panel/design-system/").status_code == 404
    settings.DEBUG = True
    r = client.get("/panel/design-system/")
    assert r.status_code == 200
    html = r.content.decode()
    for componente in ('class="btn', 'data-precio', 'role="switch"', 'class="chip agotado"', 'class="producto"',
                       'dialog', 'role="tablist"', 'data-subir-foto', 'class="color"', "qr-card", "vacio-amable"):
        assert componente in html, componente
