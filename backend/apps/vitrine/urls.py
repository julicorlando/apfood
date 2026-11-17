from django.urls import path

from . import views

app_name = "vitrine"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("pedido/<str:token>/", views.acompanhar_pedido, name="acompanhar"),
    path("app/", views.app_cliente, name="app_cliente"),
    path("app/manifest.webmanifest", views.app_manifest, name="app_manifest"),
    path("app/baixar/<str:qual>/", views.baixar_app, name="baixar_app"),
    path("<slug:slug>/", views.cardapio, name="cardapio"),
    path("<slug:slug>/mesa/<str:token>/", views.cardapio_mesa, name="cardapio_mesa"),
]
