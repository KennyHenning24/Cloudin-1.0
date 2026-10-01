"""El superusuario del panel maestro: se crea en el primer arranque, su clave no se pisa en
cada arranque y se recupera con DJANGO_SUPERUSER_RESET=1 (Render gratis no trae consola).
Y la entrada a /admin/ («datos en crudo»): solo el superusuario, sin distinguir mayúsculas
en el usuario."""

import pytest
from django.contrib.auth import get_user_model

from apps.tenants.management.commands.preparar_servidor import superusuario_inicial

ENTORNO = {"DJANGO_SUPERUSER_USERNAME": "juan", "DJANGO_SUPERUSER_PASSWORD": "clave-nueva-larga-123"}


def _juan():
    return get_user_model().objects.get(username="juan")


@pytest.mark.django_db
def test_se_crea_una_vez_y_otra_clave_en_el_entorno_no_la_pisa():
    nivel, texto = superusuario_inicial(ENTORNO)
    assert nivel == "ok" and "creado" in texto
    assert _juan().is_superuser and _juan().is_staff and _juan().check_password("clave-nueva-larga-123")
    # Otro arranque con otra clave en Render: no la cambia, y el registro dice cómo cambiarla.
    nivel, texto = superusuario_inicial({**ENTORNO, "DJANGO_SUPERUSER_PASSWORD": "otra-clave-456"})
    assert nivel == "info" and "DJANGO_SUPERUSER_RESET=1" in texto
    assert _juan().check_password("clave-nueva-larga-123")


@pytest.mark.django_db
def test_con_reset_la_clave_pasa_a_ser_la_del_entorno():
    superusuario_inicial(ENTORNO)
    nivel, texto = superusuario_inicial({**ENTORNO, "DJANGO_SUPERUSER_PASSWORD": "otra-clave-456",
                                         "DJANGO_SUPERUSER_RESET": "1"})
    assert nivel == "aviso" and "quita DJANGO_SUPERUSER_RESET" in texto
    assert _juan().check_password("otra-clave-456")


@pytest.mark.django_db
def test_reset_no_toca_una_cuenta_de_restaurante(crear_restaurante, crear_usuario):
    dueno = crear_usuario(crear_restaurante("la-casa"), "dueno")
    nivel, texto = superusuario_inicial({"DJANGO_SUPERUSER_USERNAME": dueno.username,
                                         "DJANGO_SUPERUSER_PASSWORD": "otra-clave-456", "DJANGO_SUPERUSER_RESET": "1"})
    dueno.refresh_from_db()
    assert nivel == "aviso" and "no es superusuario" in texto
    assert dueno.check_password("clave-de-prueba-123") and not dueno.is_superuser


@pytest.mark.django_db
def test_sin_las_dos_variables_avisa_y_no_crea_nada():
    assert superusuario_inicial({}) == ("info", "")
    nivel, texto = superusuario_inicial({"DJANGO_SUPERUSER_USERNAME": "juan"})
    assert nivel == "aviso" and "Falta" in texto
    assert not get_user_model().objects.filter(username="juan").exists()


@pytest.mark.django_db
def test_entrar_a_datos_en_crudo(client, crear_restaurante, crear_usuario):
    superusuario_inicial(ENTORNO)
    html = client.get("/admin/login/").content.decode()
    assert "Solo para el administrador de Cloudin" in html and 'href="/panel/login/"' in html
    # El usuario no distingue mayúsculas; la contraseña sí.
    r = client.post("/admin/login/", {"username": "Juan", "password": "clave-nueva-larga-123"})
    assert r.status_code == 302 and r["Location"] == "/master/"
    client.logout()
    r = client.post("/admin/login/", {"username": "juan", "password": "Clave-Nueva-Larga-123"})
    assert r.status_code == 200 and "cuenta de personal" in r.content.decode()
    # Una cuenta de restaurante, con su clave correcta, no entra: lo suyo es /panel/.
    dueno = crear_usuario(crear_restaurante("la-casa"), "dueno")
    r = client.post("/admin/login/", {"username": dueno.username, "password": "clave-de-prueba-123"})
    assert r.status_code == 200 and "_auth_user_id" not in client.session
