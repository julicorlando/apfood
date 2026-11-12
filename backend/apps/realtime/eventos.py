"""Publicação de eventos em tempo real. Sempre após o COMMIT: nunca anunciar
algo que sofreu rollback. Falha no Redis não derruba a operação de negócio."""

import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction

from .grupos import grupo_pdv, grupo_pedido  # noqa: F401 (reexportados)

log = logging.getLogger(__name__)


def _enviar(grupo: str, dados: dict) -> None:
    layer = get_channel_layer()
    if layer is None:
        return
    try:
        async_to_sync(layer.group_send)(grupo, {"type": "evento", "dados": dados})
    except Exception:  # pragma: no cover - infraestrutura
        log.exception("falha ao publicar evento em %s", grupo)


def publicar(grupo: str, tipo: str, dados: dict) -> None:
    payload = {"tipo": tipo, **dados}
    transaction.on_commit(lambda: _enviar(grupo, payload))


def resumo_pedido(pedido) -> dict:
    from apfood_core.enums import StatusPedido
    from apfood_core.pedido_status import ETAPA_CLIENTE

    return {
        "id": str(pedido.id),
        "numero": pedido.numero,
        "codigo_local": pedido.codigo_local,
        "status": pedido.status,
        "etapa": ETAPA_CLIENTE[StatusPedido(pedido.status)],
        "canal": pedido.canal,
        "tipo_atendimento": pedido.tipo_atendimento,
        "nome_cliente": pedido.nome_cliente,
        "total_centavos": pedido.total_centavos,
        "comanda": str(pedido.comanda_id) if pedido.comanda_id else None,
        "atualizado_em": pedido.atualizado_em.isoformat() if pedido.atualizado_em else None,
    }


def pedido_novo(pedido) -> None:
    publicar(grupo_pdv(pedido.loja_id), "pedido.novo", {"pedido": resumo_pedido(pedido)})


def pedido_status(pedido) -> None:
    dados = {"pedido": resumo_pedido(pedido)}
    publicar(grupo_pdv(pedido.loja_id), "pedido.status", dados)
    publicar(grupo_pedido(pedido.token_rastreio), "pedido.status", {
        "status": pedido.status, "etapa": dados["pedido"]["etapa"], "numero": pedido.numero,
    })


def estoque_alerta(produto) -> None:
    publicar(grupo_pdv(produto.loja_id), "estoque.alerta", {
        "produto": {"id": str(produto.id), "nome": produto.nome,
                    "estoque_atual": str(produto.estoque_atual), "estoque_minimo": str(produto.estoque_minimo)},
    })


def catalogo_alterado(loja_id, entidade: str) -> None:
    publicar(grupo_pdv(loja_id), "catalogo.alterado", {"entidade": entidade})
