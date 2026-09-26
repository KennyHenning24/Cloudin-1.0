from django.urls import path

from . import views

app_name = "public_menu"

urlpatterns = [
    path("api/public/<slug:slug>/menu/", views.menu_api, name="api"),
    path("api/public/menu/", views.menu_api, name="api-subdominio"),
]
