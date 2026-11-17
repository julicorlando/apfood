from django.urls import path

from . import views

app_name = "vitrine"

urlpatterns = [
    path("", views.app_cliente, name="inicio"),
    path("empresas/", views.empresas, name="empresas"),
    path("pedido/<str:token>/", views.acompanhar_pedido, name="acompanhar"),
    path("app/", views.app_cliente, name="app_cliente"),
    path("app/manifest.webmanifest", views.app_manifest, name="app_manifest"),
    path("app/baixar/<str:qual>/", views.baixar_app, name="baixar_app"),
    path("entregador/", views.app_entregador, name="app_entregador"),
    path("entregador/manifest.webmanifest", views.app_entregador_manifest, name="app_entregador_manifest"),
    path("<slug:slug>/", views.cardapio, name="cardapio"),
    path("<slug:slug>/mesa/<str:token>/", views.cardapio_mesa, name="cardapio_mesa"),
    path("<slug:slug>/reservar/", views.reservar, name="reservar"),
    path("<slug:slug>/totem/<str:token>/", views.totem, name="totem"),
]
