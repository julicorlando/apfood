import pytest

from apfood_core.caixa import Movimento, calcular_esperado, conferir
from apfood_core.dinheiro import calcular_troco, formatar, reais_para_centavos
from apfood_core.enums import FormaPagamento as F
from apfood_core.enums import StatusPedido as S
from apfood_core.enums import TipoAtendimento
from apfood_core.enums import TipoMovimentacaoCaixa as T
from apfood_core.pedido_status import (
    FINAIS,
    TransicaoInvalida,
    pode_transicionar,
    status_inicial,
    validar_transicao,
)
from apfood_core.totais import (
    AdicionalEscolhido,
    Item,
    RegraGrupo,
    calcular_totais,
    validar_adicionais,
)


# --- dinheiro ---------------------------------------------------------------
@pytest.mark.parametrize(
    "entrada, esperado",
    [("12,50", 1250), ("1.234,56", 123456), ("12.5", 1250), ("R$ 0,99", 99), (12, 1200)],
)
def test_reais_para_centavos(entrada, esperado):
    assert reais_para_centavos(entrada) == esperado


def test_reais_para_centavos_invalido():
    with pytest.raises(ValueError):
        reais_para_centavos("abc")
    with pytest.raises(TypeError):
        reais_para_centavos(True)


def test_formatar():
    assert formatar(1234567) == "R$ 12.345,67"
    assert formatar(5) == "R$ 0,05"
    assert formatar(-150) == "-R$ 1,50"


def test_troco():
    assert calcular_troco(3750, 5000) == 1250
    with pytest.raises(ValueError):
        calcular_troco(5000, 3750)


# --- caixa ------------------------------------------------------------------
def test_esperado_por_forma():
    movs = [
        Movimento(T.VENDA, F.DINHEIRO, 4000),
        Movimento(T.VENDA, F.PIX, 3500),
        Movimento(T.VENDA, F.CARTAO_CREDITO, 6000),
        Movimento(T.SUPRIMENTO, F.DINHEIRO, 5000),
        Movimento(T.SANGRIA, F.DINHEIRO, 2000),
        Movimento(T.DESPESA, F.DINHEIRO, 1500),
        Movimento(T.ESTORNO_VENDA, F.PIX, 500),
    ]
    esp = calcular_esperado(10000, movs)
    assert esp[F.DINHEIRO] == 10000 + 4000 + 5000 - 2000 - 1500
    assert esp[F.PIX] == 3000
    assert esp[F.CARTAO_CREDITO] == 6000
    assert esp[F.CARTAO_DEBITO] == 0


def test_sangria_so_em_dinheiro():
    with pytest.raises(ValueError):
        calcular_esperado(0, [Movimento(T.SANGRIA, F.PIX, 100)])


def test_valor_nao_positivo():
    with pytest.raises(ValueError):
        calcular_esperado(0, [Movimento(T.VENDA, F.PIX, 0)])


def test_conferencia_quebra_e_sobra():
    esp = {F.DINHEIRO: 15500, F.PIX: 3000, F.CARTAO_CREDITO: 6000, F.CARTAO_DEBITO: 0}
    inf = {F.DINHEIRO: 15000, F.PIX: 3000, F.CARTAO_CREDITO: 6100}
    r = conferir(esp, inf)
    linhas = {l.forma: l for l in r.linhas}
    assert linhas[F.DINHEIRO].diferenca_centavos == -500
    assert linhas[F.CARTAO_CREDITO].diferenca_centavos == 100
    assert linhas[F.CARTAO_DEBITO].informado_centavos == 0
    assert r.diferenca_centavos == -400
    assert r.situacao == "QUEBRA"


def test_conferencia_ok():
    esp = calcular_esperado(5000, [])
    assert conferir(esp, {F.DINHEIRO: 5000}).situacao == "OK"


# --- status do pedido -------------------------------------------------------
def test_fluxo_feliz_entrega():
    fluxo = [S.PENDENTE, S.RECEBIDO, S.EM_PREPARO, S.PRONTO, S.SAIU_PARA_ENTREGA, S.CONCLUIDO]
    for de, para in zip(fluxo, fluxo[1:]):
        validar_transicao(de, para, TipoAtendimento.ENTREGA)


def test_retirada_nao_sai_para_entrega():
    assert not pode_transicionar(S.PRONTO, S.SAIU_PARA_ENTREGA, TipoAtendimento.RETIRADA)
    assert pode_transicionar(S.PRONTO, S.CONCLUIDO, TipoAtendimento.RETIRADA)


def test_finais_nao_mudam():
    assert FINAIS == {S.CONCLUIDO, S.CANCELADO, S.RECUSADO}
    with pytest.raises(TransicaoInvalida):
        validar_transicao(S.CONCLUIDO, S.CANCELADO)


def test_status_inicial():
    assert status_inicial(canal_online=True) == S.PENDENTE
    assert status_inicial(canal_online=True, aceite_automatico=True) == S.RECEBIDO
    assert status_inicial(canal_online=False) == S.RECEBIDO


# --- totais -----------------------------------------------------------------
def test_totais_com_adicionais():
    bacon = AdicionalEscolhido("g1", "bacon", 400, quantidade=2)
    itens = [Item(2990, 2, [bacon]), Item(700, 3)]
    t = calcular_totais(itens, taxa_entrega_centavos=600, desconto_centavos=1000)
    assert t.subtotal_centavos == (2990 + 800) * 2 + 2100
    assert t.total_centavos == t.subtotal_centavos + 600 - 1000


def test_total_nunca_negativo():
    assert calcular_totais([Item(500, 1)], desconto_centavos=900).total_centavos == 0


def test_validar_adicionais():
    regras = [RegraGrupo("ponto", "Ponto da carne", 1, 1), RegraGrupo("extras", "Extras", 0, 3)]
    assert validar_adicionais(regras, [AdicionalEscolhido("ponto", "mal", 0)]) == []
    erros = validar_adicionais(regras, [AdicionalEscolhido("extras", "bacon", 400, 4)])
    assert len(erros) == 2  # falta o ponto e excedeu extras
