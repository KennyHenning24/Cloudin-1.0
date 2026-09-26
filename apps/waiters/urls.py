from django.urls import path

from . import views

app_name = "mesero"

urlpatterns = [
    path("sw.js", views.service_worker, name="sw"),
    path("<slug:slug>/", views.app, name="app"),
    path("<slug:slug>/entrar/", views.entrar, name="entrar"),
    path("<slug:slug>/salir/", views.salir, name="salir"),
    path("<slug:slug>/manifest.webmanifest", views.manifest, name="manifest"),
    path("<slug:slug>/api/mesas/", views.api_mesas, name="api-mesas"),
    path("<slug:slug>/api/menu/", views.api_menu, name="api-menu"),
    path("<slug:slug>/api/mesa/<int:numero>/", views.api_mesa, name="api-mesa"),
    path("<slug:slug>/api/mesa/<int:numero>/pedido/", views.api_pedido, name="api-pedido"),
    path("<slug:slug>/api/pedido/<int:pedido_id>/servido/", views.api_servido, name="api-servido"),
]
