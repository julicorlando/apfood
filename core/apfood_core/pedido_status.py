"""Máquina de estados do pedido.

    PENDENTE ─► RECEBIDO ─► EM_PREPARO ─► PRONTO ─► SAIU_PARA_ENTREGA ─► CONCLUIDO
       │            │            │           └──────────────────────────► CONCLUIDO
       └► RECUSADO  └────────────┴──► CANCELADO (qualquer status não final)

Pedidos de balcão/delivery lançados no PDV já nascem RECEBIDO.
"""

from .enums import StatusPedido, TipoAtendimento

S = StatusPedido

TRANSICOES: dict[StatusPedido, frozenset[StatusPedido]] = {
    S.PENDENTE: frozenset({S.RECEBIDO, S.RECUSADO, S.CANCELADO}),
    S.RECEBIDO: frozenset({S.EM_PREPARO, S.PRONTO, S.CANCELADO}),
    S.EM_PREPARO: frozenset({S.PRONTO, S.CANCELADO}),
    S.PRONTO: frozenset({S.SAIU_PARA_ENTREGA, S.CONCLUIDO, S.CANCELADO}),
    S.SAIU_PARA_ENTREGA: frozenset({S.CONCLUIDO, S.CANCELADO}),
    S.CONCLUIDO: frozenset(),
    S.CANCELADO: frozenset(),
    S.RECUSADO: frozenset(),
}

FINAIS = frozenset(s for s, prox in TRANSICOES.items() if not prox)

#: Campo de data/hora do model Pedido preenchido ao entrar em cada status.
CAMPO_TIMESTAMP: dict[StatusPedido, str] = {
    S.RECEBIDO: "aceito_em",
    S.EM_PREPARO: "em_preparo_em",
    S.PRONTO: "pronto_em",
    S.SAIU_PARA_ENTREGA: "saiu_entrega_em",
    S.CONCLUIDO: "concluido_em",
    S.CANCELADO: "cancelado_em",
    S.RECUSADO: "cancelado_em",
}

#: O que o cliente vê no link de acompanhamento (4 etapas do requisito).
ETAPA_CLIENTE: dict[StatusPedido, str] = {
    S.PENDENTE: "Recebido",
    S.RECEBIDO: "Recebido",
    S.EM_PREPARO: "Em preparo",
    S.PRONTO: "Em preparo",
    S.SAIU_PARA_ENTREGA: "Saiu para entrega",
    S.CONCLUIDO: "Concluído",
    S.CANCELADO: "Cancelado",
    S.RECUSADO: "Cancelado",
}


class TransicaoInvalida(ValueError):
    pass


def pode_transicionar(
    de: StatusPedido, para: StatusPedido, atendimento: TipoAtendimento | None = None
) -> bool:
    if para not in TRANSICOES[de]:
        return False
    if para == S.SAIU_PARA_ENTREGA and atendimento not in (None, TipoAtendimento.ENTREGA):
        return False
    return True


def validar_transicao(
    de: StatusPedido, para: StatusPedido, atendimento: TipoAtendimento | None = None
) -> None:
    if not pode_transicionar(de, para, atendimento):
        raise TransicaoInvalida(f"transição inválida: {de} -> {para}")


def status_inicial(canal_online: bool, aceite_automatico: bool = False) -> StatusPedido:
    if canal_online and not aceite_automatico:
        return S.PENDENTE
    return S.RECEBIDO
