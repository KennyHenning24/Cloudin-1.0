from django.urls import path

from . import views

app_name = "master"

urlpatterns = [
    path("", views.home, name="home"),
    path("nuevo/", views.restaurante_nuevo, name="restaurante-nuevo"),
    path("r/<slug:slug>/", views.restaurante, name="restaurante"),
    path("r/<slug:slug>/usuarios/nuevo/", views.empleado_nuevo, name="empleado-nuevo"),
    path("r/<slug:slug>/usuarios/<int:user_id>/clave/", views.empleado_password, name="empleado-clave"),
    path("r/<slug:slug>/usuarios/<int:user_id>/eliminar/", views.empleado_eliminar, name="empleado-eliminar"),
    path("r/<slug:slug>/activo/", views.restaurante_activo, name="restaurante-activo"),
    path("r/<slug:slug>/api-key/", views.restaurante_api_key, name="restaurante-api-key"),
]
