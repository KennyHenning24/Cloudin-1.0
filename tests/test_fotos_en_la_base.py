"""Plan gratis (Render sin R2): con FOTOS_EN_LA_BASE las fotos del panel se guardan en
la base de datos y se sirven en /media/. Ver apps/archivos y DESPLIEGUE-GRATIS.md."""

import io
from decimal import Decimal

import pytest
from django.core.files.base import ContentFile
from django.http import Http404
from PIL import Image

from apps.archivos.almacen import AlmacenEnLaBase
from apps.archivos.models import Archivo
from apps.archivos.views import servir
from apps.catalog.models import Category, Menu, Product
from apps.tenants.models import TenantMembership


def foto_png() -> io.BytesIO:
    archivo = io.BytesIO()
    Image.new("RGB", (1200, 900), (200, 80, 40)).save(archivo, "PNG")
    archivo.seek(0)
    archivo.name = "plato.png"
    return archivo


@pytest.mark.django_db
def test_guarda_lee_borra_y_nunca_pisa_un_nombre():
    almacen = AlmacenEnLaBase()
    nombre = almacen.save("productos/limonada.webp", ContentFile(b"primera"))
    assert nombre == "productos/limonada.webp" and almacen.exists(nombre)
    assert almacen.open(nombre).read() == b"primera" and almacen.size(nombre) == 7
    # Un nombre repetido recibe un sufijo: la caché de un año nunca sirve una foto vieja.
    otro = almacen.save("productos/limonada.webp", ContentFile(b"segunda"))
    assert otro != nombre and almacen.open(nombre).read() == b"primera"
    assert almacen.url(nombre) == "/media/productos/limonada.webp"
    almacen.delete(nombre)
    assert not almacen.exists(nombre) and Archivo.objects.count() == 1
    with pytest.raises(FileNotFoundError):
        almacen.open(nombre)


@pytest.mark.django_db
def test_la_foto_se_sirve_con_su_tipo_y_cache_larga(rf):
    AlmacenEnLaBase().save("marca/logo.webp", ContentFile(b"RIFF-webp"))
    r = servir(rf.get("/media/marca/logo.webp"), "marca/logo.webp")
    assert r.status_code == 200 and r.content == b"RIFF-webp"
    assert r["Content-Type"] == "image/webp" and "immutable" in r["Cache-Control"]
    with pytest.raises(Http404):
        servir(rf.get("/media/no/existe.webp"), "no/existe.webp")


@pytest.mark.django_db
def test_la_foto_que_sube_el_dueno_queda_en_la_base(client, settings, crear_restaurante, crear_usuario,
                                                    en_restaurante):
    settings.STORAGES = {**settings.STORAGES, "default": {"BACKEND": "apps.archivos.almacen.AlmacenEnLaBase"}}
    t = crear_restaurante("fotos-gratis")
    dueno = crear_usuario(t, "dueno", rol=TenantMembership.ROLE_OWNER)
    with en_restaurante(t):
        categoria = Category.objects.create(menu=Menu.objects.create(name="Carta"), name="Platos")
        plato = Product.objects.create(category=categoria, name="Bandeja paisa", price=Decimal("25000"))
    client.force_login(dueno)
    r = client.post(f"/api/v1/staff/catalog/products/{plato.uuid}/image/", {"file": foto_png()})
    assert r.status_code == 200, r.content
    with en_restaurante(t):
        nombre = Product.objects.get(pk=plato.pk).imagen.name
    guardada = Archivo.objects.get(nombre=nombre)
    assert guardada.tipo == "image/webp" and bytes(guardada.contenido)[8:12] == b"WEBP"
    assert r.json()["image"].endswith("/media/" + nombre)
