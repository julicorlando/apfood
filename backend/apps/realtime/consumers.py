"""Consumers WebSocket. Esqueleto — implementação completa no Passo 2."""

from channels.generic.websocket import AsyncJsonWebsocketConsumer

from .grupos import grupo_pedido, grupo_pdv


class PdvConsumer(AsyncJsonWebsocketConsumer):
    """ws/pdv/<loja_id>/ — fila de pedidos em tempo real no PDV."""

    async def connect(self):
        user = self.scope.get("user")
        loja_id = self.scope["url_route"]["kwargs"]["loja_id"]
        if not user or not user.is_authenticated or str(user.loja_id) != loja_id:
            await self.close(code=4401)
            return
        self.grupo = grupo_pdv(loja_id)
        await self.channel_layer.group_add(self.grupo, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if hasattr(self, "grupo"):
            await self.channel_layer.group_discard(self.grupo, self.channel_name)

    async def evento(self, message):  # type: "evento" enviado via group_send
        await self.send_json(message["dados"])


class PedidoClienteConsumer(AsyncJsonWebsocketConsumer):
    """ws/pedido/<token>/ — acompanhamento público do pedido pelo cliente."""

    async def connect(self):
        self.grupo = grupo_pedido(self.scope["url_route"]["kwargs"]["token"])
        await self.channel_layer.group_add(self.grupo, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        await self.channel_layer.group_discard(self.grupo, self.channel_name)

    async def evento(self, message):
        await self.send_json(message["dados"])
