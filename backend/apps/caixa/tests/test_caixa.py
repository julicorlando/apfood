import pytest
from apfood_core.enums import CanalVenda, FormaPagamento, TipoAtendimento
from apfood_core.enums import TipoMovimentacaoCaixa as T

from apps.caixa import services as caixa
from apps.core.excecoes import ErroNegocio
from apps.pedidos import services as ps


def test_ciclo_completo_com_quebra(loja, cardapio, operador):
    t = caixa.abrir_turno(operador, loja, 10000)
    with pytest.raises(ErroNegocio, match="já tem um caixa"):
        caixa.abrir_turno(operador, loja, 5000)
    p = ps.criar_pedido(loja, ps.PedidoIn(CanalVenda.BALCAO, TipoAtendimento.RETIRADA,
                                          [ps.ItemIn(str(cardapio["lata"].id), 5)]), operador)
    ps.registrar_pagamento(usuario=operador, pedido=p, forma=FormaPagamento.DINHEIRO, valor_centavos=2000)
    ps.registrar_pagamento(usuario=operador, pedido=p, forma=FormaPagamento.PIX, valor_centavos=1500)
    caixa.movimentar(t, T.SUPRIMENTO, 5000, operador)
    caixa.movimentar(t, T.SANGRIA, 3000, operador, motivo="cofre")
    caixa.pagar_despesa(t, operador, descricao="gás", valor_centavos=1000)
    with pytest.raises(ErroNegocio, match="maior que o dinheiro"):
        caixa.movimentar(t, T.SANGRIA, 999999, operador, motivo="x")

    resumo = caixa.resumo(t, mostrar_esperado=False)
    assert "esperado" not in resumo  # conferência cega
    r = caixa.fechar_turno(t, operador, {"DINHEIRO": 12500, "PIX": 1500})
    # esperado dinheiro = 10000 + 2000 + 5000 - 3000 - 1000 = 13000
    assert r.diferenca_centavos == -500 and r.situacao == "QUEBRA"
    t.refresh_from_db()
    assert t.status == "FECHADO" and t.conferencias.count() == 4 and t.diferenca_centavos == -500
    with pytest.raises(ErroNegocio, match="fechado"):
        caixa.movimentar(t, T.SUPRIMENTO, 100, operador)
