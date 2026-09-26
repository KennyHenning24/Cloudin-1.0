from django.urls import path
from rest_framework.routers import SimpleRouter

from . import avisos, catalogo_views, mesa_views, views

app_name = "api"

# Administración de la carta v1 (panel del dueño). Todo por UUID público.
carta = SimpleRouter()
carta.register("staff/catalog/menus", catalogo_views.MenuViewSet, basename="catalogo-menu")
carta.register("staff/catalog/categories", catalogo_views.CategoryViewSet, basename="catalogo-categoria")
carta.register("staff/catalog/products", catalogo_views.ProductViewSet, basename="catalogo-producto")
carta.register("staff/catalog/modifier-groups", catalogo_views.ModifierGroupViewSet, basename="catalogo-grupo")
carta.register("staff/catalog/tags", catalogo_views.TagViewSet, basename="catalogo-etiqueta")

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
    # Carta v1: orden, acciones masivas, historial, ajustes del negocio, mesas y QR
    path("staff/catalog/reorder/", catalogo_views.ReordenarView.as_view(), name="catalogo-reordenar"),
    path("staff/catalog/bulk/", catalogo_views.AccionesMasivasView.as_view(), name="catalogo-masivo"),
    path("staff/catalog/history/", catalogo_views.HistorialView.as_view(), name="catalogo-historial"),
    path("staff/settings/", catalogo_views.AjustesView.as_view(), name="ajustes"),
    path("staff/settings/logo/", catalogo_views.ImagenDeMarcaView.as_view(campo="logo"), name="ajustes-logo"),
    path("staff/settings/cover/", catalogo_views.ImagenDeMarcaView.as_view(campo="cover"), name="ajustes-portada"),
    path("staff/mesas/", catalogo_views.MesasView.as_view(), name="mesas-qr"),
    path("staff/qr/menu.<str:formato>", catalogo_views.QrView.as_view(), name="qr-menu"),
    path("staff/qr/mesa/<int:mesa_id>.<str:formato>", catalogo_views.QrView.as_view(), name="qr-mesa"),
    path("staff/qr/mesas.pdf", catalogo_views.QrView.as_view(), {"formato": "pdf", "todas": True},
         name="qr-mesas-pdf"),
    *carta.urls,
]
