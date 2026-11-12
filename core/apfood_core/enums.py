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
    MESA = "MESA"  # comanda/mesa no salão
    MARKETPLACE = "MARKETPLACE"  # iFood, 99Food, Rappi...


class Marketplace(_Rotulado):
    IFOOD = "IFOOD"
    NOVENTA_E_NOVE_FOOD = "99FOOD"
    RAPPI = "RAPPI"
    OUTRO = "OUTRO"


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
    VOUCHER = "VOUCHER"  # vale-refeição/alimentação
    MARKETPLACE = "MARKETPLACE"  # pago no app do marketplace
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


class StatusComanda(_Rotulado):
    ABERTA = "ABERTA"
    FECHANDO = "FECHANDO"  # conta pedida, aguardando pagamento
    FECHADA = "FECHADA"
    CANCELADA = "CANCELADA"


class StatusProducao(_Rotulado):
    """Status de cada item na cozinha (KDS / setores de produção)."""

    AGUARDANDO = "AGUARDANDO"
    EM_PREPARO = "EM_PREPARO"
    PRONTO = "PRONTO"
    ENTREGUE = "ENTREGUE"


class RegraPrecoSabores(_Rotulado):
    """Preço de item com vários sabores (pizza meio a meio)."""

    MAIOR = "MAIOR"  # cobra o sabor mais caro
    MEDIA = "MEDIA"  # média dos sabores


class RegimeTributario(_Rotulado):
    MEI = "MEI"
    SIMPLES_NACIONAL = "SIMPLES_NACIONAL"
    SIMPLES_EXCESSO = "SIMPLES_EXCESSO"  # excesso de sublimite
    NORMAL = "NORMAL"  # lucro presumido / real


class AmbienteFiscal(_Rotulado):
    HOMOLOGACAO = "HOMOLOGACAO"
    PRODUCAO = "PRODUCAO"


class ModeloDocumentoFiscal(_Rotulado):
    NFCE = "NFCE"  # modelo 65
    SAT = "SAT"  # CF-e SAT (SP)
    NFE = "NFE"  # modelo 55


class StatusNotaFiscal(_Rotulado):
    PENDENTE = "PENDENTE"
    PROCESSANDO = "PROCESSANDO"
    AUTORIZADA = "AUTORIZADA"
    REJEITADA = "REJEITADA"
    CONTINGENCIA = "CONTINGENCIA"  # emitida offline, aguardando transmissão
    CANCELADA = "CANCELADA"


class StatusCompra(_Rotulado):
    RASCUNHO = "RASCUNHO"
    LANCADA = "LANCADA"  # deu entrada no estoque
    CANCELADA = "CANCELADA"


class TipoCupom(_Rotulado):
    PERCENTUAL = "PERCENTUAL"
    VALOR_FIXO = "VALOR_FIXO"
    FRETE_GRATIS = "FRETE_GRATIS"


class StatusAssinatura(_Rotulado):
    TRIAL = "TRIAL"
    ATIVA = "ATIVA"
    INADIMPLENTE = "INADIMPLENTE"
    CANCELADA = "CANCELADA"


class StatusFatura(_Rotulado):
    ABERTA = "ABERTA"
    PAGA = "PAGA"
    CANCELADA = "CANCELADA"


class TipoIntegracao(_Rotulado):
    MARKETPLACE = "MARKETPLACE"
    PAGAMENTO = "PAGAMENTO"  # Pix dinâmico / link de pagamento
    FISCAL = "FISCAL"  # emissor de NFC-e/SAT
    WHATSAPP = "WHATSAPP"
    MAPAS = "MAPAS"  # geocodificação / distância


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
        (Marketplace.NOVENTA_E_NOVE_FOOD, "99Food"),
        (Marketplace.IFOOD, "iFood"),
        (FormaPagamento.MARKETPLACE, "Pago no marketplace"),
        (FormaPagamento.VOUCHER, "Vale-refeição"),
        (CanalVenda.MARKETPLACE, "Marketplace"),
        (StatusProducao.EM_PREPARO, "Em preparo"),
        (RegraPrecoSabores.MAIOR, "Sabor mais caro"),
        (RegraPrecoSabores.MEDIA, "Média dos sabores"),
        (RegimeTributario.SIMPLES_EXCESSO, "Simples (excesso de sublimite)"),
        (RegimeTributario.NORMAL, "Regime normal"),
        (AmbienteFiscal.HOMOLOGACAO, "Homologação"),
        (AmbienteFiscal.PRODUCAO, "Produção"),
        (ModeloDocumentoFiscal.NFCE, "NFC-e"),
        (ModeloDocumentoFiscal.SAT, "CF-e SAT"),
        (ModeloDocumentoFiscal.NFE, "NF-e"),
        (StatusNotaFiscal.CONTINGENCIA, "Contingência"),
        (StatusCompra.LANCADA, "Lançada"),
        (TipoCupom.VALOR_FIXO, "Valor fixo"),
        (TipoCupom.FRETE_GRATIS, "Frete grátis"),
        (TipoIntegracao.MAPAS, "Mapas"),
    ]
}
