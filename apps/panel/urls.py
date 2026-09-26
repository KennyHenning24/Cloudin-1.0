from django.contrib.auth import views as auth_views
from django.urls import path

from . import control, design_system, duenio, inventario, menu, meseros, propinas, reservas, seguridad, turnos, views

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

    # Panel del dueño: el menú digital (los dos planes; sin turno)
    path("bienvenida/", duenio.bienvenida, name="bienvenida"),
    path("mi-menu/", duenio.mi_menu, name="mi-menu"),
    path("mi-menu/producto/nuevo/", duenio.producto, name="carta-producto-nuevo"),
    path("mi-menu/producto/<uuid:producto>/", duenio.producto, name="carta-producto"),
    path("personalizar/", duenio.personalizar, name="personalizar"),
    path("mesas-y-qr/", duenio.mesas_y_qr, name="qr"),
    path("cuenta/", duenio.cuenta, name="cuenta"),

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
    path("ventas/", views.ventas, name="ventas"),

    # Turno de caja: abrir, cerrar y el informe de cierre
    path("turnos/", turnos.turnos, name="turnos"),
    path("turnos/abrir/", turnos.turno_abrir, name="turno-abrir"),
    path("turnos/cerrar/", turnos.turno_cerrar, name="turno-cerrar"),
    path("turnos/<int:turno_id>/", turnos.turno_detalle, name="turno-detalle"),
    path("turnos/<int:turno_id>/imprimir/", turnos.turno_imprimir, name="turno-imprimir"),

    # Cloudin Reservas: agenda, clientes y horarios
    path("reservas/", reservas.reservas, name="reservas"),
    path("reservas/nueva/", reservas.reserva_nueva, name="reserva-nueva"),
    path("reservas/horas/", reservas.reservas_horas, name="reservas-horas"),
    path("reservas/<int:reserva_id>/", reservas.reserva_detalle, name="reserva"),
    path("reservas/<int:reserva_id>/accion/", reservas.reserva_accion, name="reserva-accion"),
    path("reservas/clientes/", reservas.clientes, name="clientes"),
    path("reservas/clientes/<int:cliente_id>/", reservas.cliente_detalle, name="cliente"),
    path("reservas/horarios/", reservas.reservas_config, name="reservas-config"),

    # Cloudin Control: detector de fugas y situaciones a revisar
    path("control/", control.control, name="control"),
    path("control/analizar/", control.control_analizar, name="control-analizar"),
    path("control/alerta/<int:alerta_id>/", control.control_alerta, name="control-alerta"),
    path("control/ajustes/", control.control_ajustes, name="control-ajustes"),

    # Propinas: registro y reparto entre el equipo
    path("propinas/", propinas.propinas, name="propinas"),
    path("propinas/turno/<int:turno_id>/entregada/", propinas.propinas_pagadas, name="propinas-pagadas"),

    # Cloudin Employees
    path("empleados/", views.empleados, name="empleados"),
    path("empleados/nuevo/", views.empleado_nuevo, name="empleado-nuevo"),
    path("empleados/<int:empleado_id>/editar/", views.empleado_editar, name="empleado-editar"),
    path("empleados/marcar/", views.empleado_marcar, name="empleado-marcar"),
    path("empleados/<int:empleado_id>/activo/", views.empleado_activo, name="empleado-activo"),

    # Cloudin Meseros (la app de la tablet vive en /mesero/<slug>/)
    path("meseros/", meseros.meseros, name="meseros"),
    path("meseros/nuevo/", meseros.mesero_nuevo, name="mesero-nuevo"),
    path("meseros/<int:mesero_id>/editar/", meseros.mesero_editar, name="mesero-editar"),
    path("meseros/<int:mesero_id>/activo/", meseros.mesero_activo, name="mesero-activo"),
    path("meseros/<int:mesero_id>/clave/", meseros.mesero_ver_clave, name="mesero-clave"),

    # Inventario
    path("inventario/", inventario.inventario, name="inventario"),
    path("inventario/insumos/", inventario.insumos, name="insumos"),
    path("inventario/insumos/nuevo/", inventario.insumo_nuevo, name="insumo-nuevo"),
    path("inventario/insumos/<int:insumo_id>/", inventario.insumo_detalle, name="insumo-detalle"),
    path("inventario/insumos/<int:insumo_id>/editar/", inventario.insumo_editar,
         name="insumo-editar"),
    path("inventario/insumos/<int:insumo_id>/activo/", inventario.insumo_activo,
         name="insumo-activo"),
    path("inventario/compras/", inventario.compras, name="compras"),
    path("inventario/compras/nueva/", inventario.compra_nueva, name="compra-nueva"),
    path("inventario/compras/<int:compra_id>/", inventario.compra_detalle, name="compra-detalle"),
    path("inventario/compras/<int:compra_id>/pagar/", inventario.compra_pagar,
         name="compra-pagar"),
    path("inventario/proveedores/", inventario.proveedores, name="proveedores"),
    path("inventario/proveedores/nuevo/", inventario.proveedor_nuevo, name="proveedor-nuevo"),
    path("inventario/proveedores/<int:proveedor_id>/", inventario.proveedor_editar,
         name="proveedor-editar"),
    path("inventario/recetas/", inventario.recetas, name="recetas"),
    path("inventario/recetas/producto/<int:producto_id>/", inventario.receta_editar,
         name="receta-producto"),
    path("inventario/recetas/<int:receta_id>/", inventario.receta_editar, name="receta"),
    path("inventario/subrecetas/nueva/", inventario.subreceta_nueva, name="subreceta-nueva"),
    path("inventario/conteos/", inventario.conteos, name="conteos"),
    path("inventario/conteos/<int:conteo_id>/", inventario.conteo_detalle, name="conteo-detalle"),
    path("inventario/reportes/", inventario.inventario_reportes, name="inventario-reportes"),
    path("inventario/maestros/", inventario.inventario_maestros, name="inventario-maestros"),

    # Facturación electrónica
    path("documento/<int:documento_id>/", views.documento, name="documento"),
    path("documento/<int:documento_id>/reintentar/", views.documento_reintentar,
         name="documento-reintentar"),
    path("cuenta/<int:session_id>/cerrar-y-facturar/", views.cerrar_y_facturar,
         name="cerrar-y-facturar"),
    path("facturacion/", views.facturacion, name="facturacion"),
    path("cuenta/<int:session_id>/facturar/", views.facturar, name="facturar"),

    # Impresión
    path("comanda/<int:order_id>/imprimir/", views.print_order, name="print-order"),
    path("cuenta/<int:session_id>/imprimir/", views.print_bill, name="print-bill"),
    path("documento/<int:documento_id>/recibo/", views.print_factura, name="print-factura"),
]
