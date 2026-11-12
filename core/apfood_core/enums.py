"""Enumerações do domínio ApFood.

Fonte única de verdade: o backend Django gera os `choices` dos models a partir
daqui (ver `apps.core.choices`) e o PDV desktop usa as mesmas classes no cache
local. Os valores (strings em MAIÚSCULAS) são o que vai para o banco e para a
API — nunca renomeie um valor existente sem migration de dados.
"""

from enum import StrEnum


class _Rotulado(StrEnum):
    """StrEnum com rótulo legível em português (`.rotulo`)."""

    @property
    def rotulo(self) -> str:
        return _ROTULOS.get((type(self), self.value), self.value.replace("_", " ").capitalize())

    @classmethod
    def choices(cls) -> list[tuple[str, str]]:
        return [(m.value, m.rotulo) for m in cls]


class PapelUsuario(_Rotulado):
    MASTER = "MASTER"  # dono da plataforma: todas as empresas
    ADMIN = "ADMIN"  # administrador de UMA empresa (todas as lojas dela)
    GERENTE = "GERENTE"
    OPERADOR = "OPERADOR"


class CanalVenda(_Rotulado):
    ONLINE = "ONLINE"  # cardápio digital
    BALCAO = "BALCAO"  # consumo no local / retirada no balcão
    DELIVERY = "DELIVERY"  # telefone/WhatsApp lançado pelo atendente


class OrigemContato(_Rotulado):
    TELEFONE = "TELEFONE"
    WHATSAPP = "WHATSAPP"
    PRESENCIAL = "PRESENCIAL"
    SITE = "SITE"


class TipoAtendimento(_Rotulado):
    CONSUMO_LOCAL = "CONSUMO_LOCAL"
    RETIRADA = "RETIRADA"
    ENTREGA = "ENTREGA"


class StatusPedido(_Rotulado):
    PENDENTE = "PENDENTE"  # chegou online, aguardando aceite
    RECEBIDO = "RECEBIDO"  # aceito pelo estabelecimento
    EM_PREPARO = "EM_PREPARO"
    PRONTO = "PRONTO"  # pronto p/ retirada ou aguardando motoboy
    SAIU_PARA_ENTREGA = "SAIU_PARA_ENTREGA"
    CONCLUIDO = "CONCLUIDO"
    CANCELADO = "CANCELADO"
    RECUSADO = "RECUSADO"


class FormaPagamento(_Rotulado):
    DINHEIRO = "DINHEIRO"
    PIX = "PIX"
    CARTAO_CREDITO = "CARTAO_CREDITO"
    CARTAO_DEBITO = "CARTAO_DEBITO"
    VOUCHER = "VOUCHER"
    OUTRO = "OUTRO"


class StatusPagamento(_Rotulado):
    PENDENTE = "PENDENTE"  # ex.: pagar na entrega
    CONFIRMADO = "CONFIRMADO"
    ESTORNADO = "ESTORNADO"


class StatusTurno(_Rotulado):
    ABERTO = "ABERTO"
    FECHADO = "FECHADO"


class TipoConferencia(_Rotulado):
    CEGA = "CEGA"  # operador informa valores sem ver o esperado
    DETALHADA = "DETALHADA"  # operador vê o esperado durante a conferência


class TipoMovimentacaoCaixa(_Rotulado):
    VENDA = "VENDA"
    ESTORNO_VENDA = "ESTORNO_VENDA"
    SUPRIMENTO = "SUPRIMENTO"  # reforço de troco
    SANGRIA = "SANGRIA"  # retirada
    DESPESA = "DESPESA"  # despesa paga com dinheiro do caixa


class TipoProduto(_Rotulado):
    VENDA = "VENDA"  # aparece no cardápio
    INSUMO = "INSUMO"  # matéria-prima / embalagem


class UnidadeMedida(_Rotulado):
    UN = "UN"
    KG = "KG"
    G = "G"
    L = "L"
    ML = "ML"
    CX = "CX"


class TipoMovimentacaoEstoque(_Rotulado):
    ENTRADA = "ENTRADA"
    SAIDA_VENDA = "SAIDA_VENDA"
    ESTORNO_VENDA = "ESTORNO_VENDA"
    AJUSTE = "AJUSTE"
    PERDA = "PERDA"


class MomentoBaixaEstoque(_Rotulado):
    ACEITE = "ACEITE"
    CONCLUSAO = "CONCLUSAO"


class TipoZonaEntrega(_Rotulado):
    BAIRRO = "BAIRRO"
    RAIO_KM = "RAIO_KM"


# Chave (classe, valor): StrEnum compara igual à string, então membros de
# enums diferentes com o mesmo valor colidiriam numa chave simples.
_ROTULOS: dict[tuple[type, str], str] = {
    (m.__class__, m.value): rotulo
    for m, rotulo in [
        (PapelUsuario.MASTER, "Master (plataforma)"),
        (PapelUsuario.ADMIN, "Administrador da empresa"),
        (PapelUsuario.OPERADOR, "Operador de caixa"),
        (CanalVenda.BALCAO, "Balcão"),
        (TipoAtendimento.CONSUMO_LOCAL, "Consumo no local"),
        (StatusPedido.EM_PREPARO, "Em preparo"),
        (StatusPedido.SAIU_PARA_ENTREGA, "Saiu para entrega"),
        (StatusPedido.CONCLUIDO, "Concluído"),
        (FormaPagamento.PIX, "Pix"),
        (FormaPagamento.CARTAO_CREDITO, "Cartão de crédito"),
        (FormaPagamento.CARTAO_DEBITO, "Cartão de débito"),
        (TipoMovimentacaoCaixa.ESTORNO_VENDA, "Estorno de venda"),
        (TipoMovimentacaoEstoque.SAIDA_VENDA, "Saída por venda"),
        (TipoMovimentacaoEstoque.ESTORNO_VENDA, "Estorno de venda"),
        (MomentoBaixaEstoque.CONCLUSAO, "Conclusão"),
        (UnidadeMedida.UN, "Unidade"),
        (UnidadeMedida.CX, "Caixa"),
        (TipoZonaEntrega.RAIO_KM, "Raio (km)"),
    ]
}
