"""Cashback: % do pedido concluído vira saldo do cliente, usado como desconto no PDV."""

from decimal import Decimal

import pytest
from apfood_core.enums import CanalVenda, StatusPedido, TipoAtendimento

from apps.clientes.models import Cliente
from apps.core.excecoes import ErroNegocio
from apps.pedidos import services as ps
from apps.pedidos.models import Pedido

TEL = "11999990000"


def balcao(c, qtd=1, **kw):
    return ps.PedidoIn(canal=CanalVenda.BALCAO, tipo_atendimento=TipoAtendimento.RETIRADA,
                       itens=[ps.ItemIn(str(c["lata"].id), qtd)], telefone_cliente=TEL, nome_cliente="Ana", **kw)


def concluir(p, u):
    ps.transicionar(p, StatusPedido.PRONTO, u)
    ps.transicionar(p, StatusPedido.CONCLUIDO, u)
    return Pedido.objects.get(pk=p.pk)


@pytest.fixture
def com_cashback(loja):
    loja.cashback_percentual = Decimal("10")
    loja.save()
    return loja


def saldo():
    return Cliente.objects.get(telefone=TEL).saldo_cashback_centavos


def test_credita_na_conclusao_uma_vez(com_cashback, cardapio, operador):
    p = ps.criar_pedido(com_cashback, balcao(cardapio, 3), operador)  # 3 × 700
    assert saldo() == 0
    p = concluir(p, operador)
    assert p.cashback_gerado_centavos == 210 and saldo() == 210
    ps.transicionar(p, StatusPedido.CONCLUIDO, operador)  # reenvio idempotente
    assert saldo() == 210


def test_usa_saldo_como_desconto_e_devolve_se_cancelar(com_cashback, cardapio, operador, gerente):
    Cliente.objects.create(loja=com_cashback, nome="Ana", telefone=TEL, saldo_cashback_centavos=500)
    p = ps.criar_pedido(com_cashback, balcao(cardapio, 1, usar_cashback_centavos=9999), operador)
    assert p.cashback_usado_centavos == 500 and p.total_centavos == 200 and saldo() == 0
    ps.transicionar(p, StatusPedido.CANCELADO, gerente, motivo="cliente desistiu")
    assert saldo() == 500


def test_desligado_nao_gera(loja, cardapio, operador):
    concluir(ps.criar_pedido(loja, balcao(cardapio), operador), operador)
    assert saldo() == 0


def test_usar_cashback_exige_telefone(com_cashback, cardapio, operador):
    dados = balcao(cardapio, usar_cashback_centavos=100)
    dados.telefone_cliente = ""
    with pytest.raises(ErroNegocio, match="telefone"):
        ps.criar_pedido(com_cashback, dados, operador)
