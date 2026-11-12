from django.urls import path

from . import consumers

websocket_urlpatterns = [
    path("ws/pdv/<str:loja_id>/", consumers.PdvConsumer.as_asgi()),
    path("ws/pedido/<str:token>/", consumers.PedidoClienteConsumer.as_asgi()),
]
