import pytest
from apfood_core.enums import CanalVenda, FormaPagamento, StatusPedido, TipoAtendimento

from apps.caixa import services as caixa
from apps.core.excecoes import ErroNegocio
from apps.pedidos import services as ps
from apps.salao import services as salao
from apps.salao.models import Mesa


def rodada(loja, comanda, cardapio, usuario, qtd):
    return ps.criar_pedido(loja, ps.PedidoIn(CanalVenda.MESA, TipoAtendimento.CONSUMO_LOCAL,
                                             [ps.ItemIn(str(cardapio["lata"].id), qtd)], comanda=comanda), usuario)


def test_comanda_taxa_servico_divisao_e_fechamento(loja, cardapio, operador):
    caixa.abrir_turno(operador, loja, 0)
    mesa = Mesa.objects.create(loja=loja, nome="Mesa 1")
    c = salao.abrir(loja, operador, mesa=mesa, pessoas=3)
    rodada(loja, c, cardapio, operador, 2)
    rodada(loja, c, cardapio, operador, 1)
    c.refresh_from_db()
    assert c.subtotal_centavos == 2100 and c.taxa_servico_centavos == 210 and c.total_centavos == 2310
    assert salao.divisao_sugerida(c) == [770, 770, 770]
    salao.pedir_conta(c, operador)
    with pytest.raises(ErroNegocio, match="em aberto"):
        salao.fechar(c, operador)
    for parte in salao.divisao_sugerida(c):
        ps.registrar_pagamento(usuario=operador, comanda=c, forma=FormaPagamento.PIX, valor_centavos=parte)
    salao.fechar(c, operador)
    c.refresh_from_db()
    assert c.status == "FECHADA"
    assert set(c.pedidos.values_list("status", flat=True)) == {StatusPedido.CONCLUIDO}


def test_juntar_comandas(loja, cardapio, operador):
    a, b = salao.abrir(loja, operador), salao.abrir(loja, operador)
    rodada(loja, a, cardapio, operador, 1)
    rodada(loja, b, cardapio, operador, 2)
    salao.juntar(a, b, operador)
    a.refresh_from_db()
    b.refresh_from_db()
    assert a.status == "CANCELADA" and a.unida_em == b
    assert b.pedidos.count() == 2 and b.subtotal_centavos == 2100
