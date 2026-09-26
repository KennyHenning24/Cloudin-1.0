from django.urls import path

from . import analitica, avisos, mesa_views, reservas_views, views

app_name = "api"

urlpatterns = [
    path("ping/", views.ping, name="ping"),
    # Web del cliente (QR) — se autentica con X-API-Key + token de mesa
    path("menu/", views.menu, name="menu"),
    path("tables/<str:token>/", views.table_detail, name="table-detail"),
    path("tables/<str:token>/orders/", views.table_create_order, name="table-create-order"),
    # Mesa con QR: carrito compartido y estado en vivo. El token va en la URL.
    path("mesa/<str:token>/", mesa_views.mesa_inicio, name="mesa-inicio"),
    path("mesa/<str:token>/estado/", mesa_views.mesa_estado, name="mesa-estado"),
    path("mesa/<str:token>/borrador/", mesa_views.mesa_borrador, name="mesa-borrador"),
    path("mesa/<str:token>/aviso/", mesa_views.mesa_aviso, name="mesa-aviso"),
    path("mesa/<str:token>/enviar/", mesa_views.mesa_enviar, name="mesa-enviar"),
    # Reservas: el sitio web y el menú de la mesa (X-API-Key, sin turno)
    path("reservas/", reservas_views.configuracion, name="reservas"),
    path("reservas/dias/", reservas_views.dias, name="reservas-dias"),
    path("reservas/horas/", reservas_views.horas, name="reservas-horas"),
    path("reservas/mesas/", reservas_views.mesas, name="reservas-mesas"),
    path("reservas/crear/", reservas_views.crear, name="reservas-crear"),
    path("reservas/<str:codigo>/", reservas_views.detalle, name="reservas-detalle"),
    path("reservas/<str:codigo>/cancelar/", reservas_views.cancelar, name="reservas-cancelar"),
    # Sitio web del restaurante (la tablet del mesero)
    path("site/info/", views.site_info, name="site-info"),
    path("site/tables/", views.site_tables, name="site-tables"),
    path("site/tables/<int:numero>/orders/", views.site_table_orders, name="site-table-orders"),
    path("site/orders/", views.site_create_order, name="site-create-order"),
    # Panel del restaurante
    path("staff/avisos/", avisos.staff_avisos, name="staff-avisos"),
    path("staff/items/<int:item_id>/novedad/", avisos.staff_item_novedad, name="staff-item-novedad"),
    path("staff/sessions/<int:session_id>/descuento/", avisos.staff_session_descuento, name="staff-descuento"),
    path("staff/tables/", views.staff_tables, name="staff-tables"),
    path("staff/tables/<int:table_id>/", views.staff_table_detail, name="staff-table-detail"),
    path("staff/site/status/", views.staff_site_status, name="staff-site-status"),
    path("staff/analitica/", analitica.staff_analitica, name="staff-analitica"),
    path("staff/menu/", views.staff_menu, name="staff-menu"),
    path("staff/menu/categories/", views.staff_categories, name="staff-categories"),
    path("staff/menu/categories/<int:category_id>/", views.staff_category_detail, name="staff-category"),
    path("staff/menu/products/", views.staff_products, name="staff-products"),
    path("staff/menu/products/<int:product_id>/", views.staff_product_detail, name="staff-product"),
    path("staff/messages/", views.staff_messages, name="staff-messages"),
    path("staff/orders/<int:order_id>/visto/", views.staff_order_seen, name="staff-order-seen"),
    path("staff/orders/<int:order_id>/impreso/", views.staff_order_printed, name="staff-order-printed"),
    path("staff/tables/<int:table_id>/open/", views.staff_open_table, name="staff-open-table"),
    path("staff/tables/<int:table_id>/orders/", views.staff_create_order, name="staff-create-order"),
    path("staff/orders/<int:order_id>/status/", views.staff_order_status, name="staff-order-status"),
    path("staff/kitchen/", views.staff_kitchen, name="staff-kitchen"),
    path("staff/sessions/<int:session_id>/", views.staff_session, name="staff-session"),
    path("staff/sessions/<int:session_id>/close/", views.staff_close_session, name="staff-close"),
]
