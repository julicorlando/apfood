from django.urls import path

from . import views

app_name = "vitrine"

urlpatterns = [
    path("pedido/<str:token>/", views.acompanhar_pedido, name="acompanhar"),
    path("<slug:slug>/", views.cardapio, name="cardapio"),
]
