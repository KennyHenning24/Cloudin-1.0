from django.contrib.auth import views as auth_views
from django.urls import path

from . import design_system, duenio, menu, meseros, seguridad, views

app_name = "panel"

urlpatterns = [
    path("login/", seguridad.LoginSeguro.as_view(), name="login"),
    # App instalable (PWA): manifiesto, service worker y la página sin conexión.
    path("manifest.webmanifest", duenio.manifest, name="manifest"),
    path("sw.js", duenio.service_worker, name="sw"),
    path("sin-conexion/", duenio.sin_conexion, name="sin-conexion"),
    # Modo soporte: el superusuario confirma su clave antes de entrar a un restaurante.
    path("soporte/", seguridad.soporte, name="soporte"),
    path("soporte/salir/", seguridad.soporte_salir, name="soporte-salir"),
    path("soporte/entrar-como-restaurante/", seguridad.entrar_como_restaurante, name="entrar-como"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),

    # Recuperar la contraseña por correo
    path("recuperar/", seguridad.RecuperarSeguro.as_view(
        template_name="panel/recuperar.html",
        email_template_name="panel/correo_recuperar.txt",
        subject_template_name="panel/correo_recuperar_asunto.txt",
        success_url="/panel/recuperar/enviado/",
    ), name="recuperar"),
    path("recuperar/enviado/", auth_views.PasswordResetDoneView.as_view(
        template_name="panel/recuperar_enviado.html"), name="recuperar-enviado"),
    path("recuperar/<uidb64>/<token>/", seguridad.CrearClave.as_view(
        template_name="panel/recuperar_nueva.html"), name="password_reset_confirm"),
    # Invitación del dueño (llega por correo al importar su menú o al darlo de alta)
    path("invitacion/<uidb64>/<token>/", seguridad.CrearClave.as_view(
        template_name="panel/invitacion.html"), name="invitacion"),
    path("recuperar/listo/", auth_views.PasswordResetCompleteView.as_view(
        template_name="panel/recuperar_listo.html"), name="recuperar-listo"),

    path("", views.inicio, name="inicio"),
    # Guía viva del sistema de diseño (solo con DEBUG=True)
    path("design-system/", design_system.pagina, name="design-system"),

    # Panel del dueño: el menú digital
    path("bienvenida/", duenio.bienvenida, name="bienvenida"),
    path("mi-menu/", duenio.mi_menu, name="mi-menu"),
    path("mi-menu/producto/nuevo/", duenio.producto, name="carta-producto-nuevo"),
    path("mi-menu/producto/<uuid:producto>/", duenio.producto, name="carta-producto"),
    path("personalizar/", duenio.personalizar, name="personalizar"),
    path("mesas-y-qr/", duenio.mesas_y_qr, name="qr"),
    path("cuenta/", duenio.cuenta, name="cuenta"),

    # Pedidos y mesas
    path("mesas/", views.tables, name="tables"),
    path("mesa/<int:table_id>/", views.table_detail, name="table-detail"),
    path("cocina/", views.kitchen, name="kitchen"),
    path("mensajes/", views.mensajes, name="mensajes"),
    path("configuracion/", views.configuracion, name="configuracion"),
    path("mesas/qr/", views.mesas_qr, name="mesas-qr"),
    path("menu/producto/nuevo/", menu.producto_nuevo, name="producto-nuevo"),
    path("menu/producto/<int:producto_id>/", menu.producto_editar, name="producto-editar"),
    path("menu/producto/<int:producto_id>/eliminar/", menu.producto_eliminar, name="producto-eliminar"),
    path("menu/importar/", menu.menu_importar, name="menu-importar"),

    # Cómo se toman los pedidos: el QR de la mesa y Cloudin Meseros (la app de la tablet
    # vive en /mesero/<slug>/)
    path("pedidos-qr/", meseros.pedidos_qr, name="pedidos-qr"),
    path("meseros/", meseros.meseros, name="meseros"),
    path("meseros/nuevo/", meseros.mesero_nuevo, name="mesero-nuevo"),
    path("meseros/<int:mesero_id>/editar/", meseros.mesero_editar, name="mesero-editar"),
    path("meseros/<int:mesero_id>/activo/", meseros.mesero_activo, name="mesero-activo"),
    path("meseros/<int:mesero_id>/clave/", meseros.mesero_ver_clave, name="mesero-clave"),

    # Impresión
    path("comanda/<int:order_id>/imprimir/", views.print_order, name="print-order"),
    path("cuenta/<int:session_id>/imprimir/", views.print_bill, name="print-bill"),
]
