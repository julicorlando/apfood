"""Autenticação do WebSocket por JWT (o PDV não tem sessão de navegador).

O cliente conecta em  ws://.../ws/pdv/<loja>/?token=<access JWT>.
Sem token, cai na sessão (admin/navegador)."""

from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware


@database_sync_to_async
def _usuario_do_token(token: str):
    from django.contrib.auth.models import AnonymousUser
    from rest_framework_simplejwt.authentication import JWTAuthentication
    from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

    auth = JWTAuthentication()
    try:
        return auth.get_user(auth.get_validated_token(token))
    except (InvalidToken, TokenError, Exception):  # noqa: BLE001
        return AnonymousUser()


class JWTAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        token = (parse_qs(scope.get("query_string", b"").decode()).get("token") or [None])[0]
        if token:
            scope["user"] = await _usuario_do_token(token)
        return await super().__call__(scope, receive, send)
