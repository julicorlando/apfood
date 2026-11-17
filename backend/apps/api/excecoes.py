"""Erros da API sempre em JSON — inclusive falhas ao gravar arquivos (fotos e logos)."""

import logging

from rest_framework.response import Response
from rest_framework.views import exception_handler

log = logging.getLogger("apfood.api")


def tratar(exc, contexto):
    resposta = exception_handler(exc, contexto)
    if resposta is not None:
        return resposta
    if isinstance(exc, OSError):  # PermissionError, disco cheio, pasta inexistente…
        log.exception("falha ao gravar arquivo: %s", exc)
        return Response({"detail": "Não foi possível salvar o arquivo no servidor. Tente de novo em instantes; "
                                   "se continuar, avise o suporte."}, status=503)
    return None
