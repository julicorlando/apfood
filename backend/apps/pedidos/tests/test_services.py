from decimal import Decimal

import pytest
from apfood_core.enums import CanalVenda, FormaPagamento, StatusPedido, TipoAtendimento

from apps.caixa import services as caixa
from apps.cardapio.models import Produto
from apps.core.excecoes import ErroNegocio
from apps.estoque.models import MovimentacaoEstoque
from apps.pedidos import services as ps
from apps.pedidos.models import Pedido

A, I = ps.AdicionalIn, ps.ItemIn


def balcao(itens, **kw):
    return ps.PedidoIn(canal=CanalVenda.BALCAO, tipo_atendimento=TipoAtendimento.RETIRADA, itens=itens, **kw)


def x_burger(c, qtd=1, bacon=0):
    ads = [A(str(c["ao_ponto"].id))] + ([A(str(c["bacon_extra"].id), bacon)] if bacon else [])
    return I(str(c["x"].id), qtd, adicionais=ads)


def saldo(p):
    return Produto.objects.get(pk=p.pk).estoque_atual


def test_totais_adicionais_e_setor(loja, cardapio, operador):
    c = cardapio
    p = ps.criar_pedido(loja, balcao([x_burger(c, 2, bacon=2), I(str(c["lata"].id), 1)]), operador)
    assert p.subtotal_centavos == (3000 + 1000) * 2 + 700
    assert p.total_centavos == p.subtotal_centavos
    assert p.numero == 1 and p.status == StatusPedido.RECEBIDO
    item = p.itens.get(produto=c["x"])
    assert item.setor == c["chapa"] and item.adicionais.count() == 2


def test_grupo_obrigatorio_e_limites(loja, cardapio, operador):
    c = cardapio
    with pytest.raises(ErroNegocio, match="Ponto"):
        ps.criar_pedido(loja, balcao([I(str(c["x"].id))]), operador)
    with pytest.raises(ErroNegocio, match="até 2"):
        ps.criar_pedido(loja, balcao([x_burger(c, bacon=3)]), operador)


def test_pizza_meio_a_meio_preco_maior_e_baixa_proporcional(loja, cardapio, operador):
    (cal, _, cal_g), (por, _, _) = cardapio["sabores"]["Calabresa"], cardapio["sabores"]["Portuguesa"]
    it = I(str(cal.id), 1, variacao_id=str(cal_g.id), sabores=[str(cal.id), str(por.id)])
    p = ps.criar_pedido(loja, balcao([it]), operador)
    assert p.total_centavos == 6000  # regra MAIOR, tamanho Grande
    assert "1/2 Calabresa" in p.itens.get().nome_produto
    ps.transicionar(p, StatusPedido.PRONTO, operador)
    ps.transicionar(p, StatusPedido.CONCLUIDO, operador)
    assert saldo(cardapio["massa"]) == Decimal("20") - Decimal("1.5")  # 2 × (1/2 × 1,5)


def test_tamanho_obrigatorio(loja, cardapio, operador):
    cal = cardapio["sabores"]["Calabresa"][0]
    with pytest.raises(ErroNegocio, match="tamanho"):
        ps.criar_pedido(loja, balcao([I(str(cal.id))]), operador)


def test_idempotente_por_id(loja, cardapio, operador):
    dados = balcao([I(str(cardapio["lata"].id))], id="7d1f0a52-6c1e-4c3a-9b1e-1f2a3b4c5d6e")
    a = ps.criar_pedido(loja, dados, operador)
    b = ps.criar_pedido(loja, dados, operador)
    assert a.pk == b.pk and Pedido.objects.count() == 1


def test_baixa_na_conclusao_e_estorno_no_cancelamento(loja, cardapio, operador, gerente):
    c = cardapio
    p = ps.criar_pedido(loja, balcao([x_burger(c, 2, bacon=1), I(str(c["lata"].id), 2)]), operador)
    assert saldo(c["pao"]) == 50  # padrão: baixa na conclusão
    ps.transicionar(p, StatusPedido.EM_PREPARO, operador)
    ps.transicionar(p, StatusPedido.PRONTO, operador)
    ps.transicionar(p, StatusPedido.CONCLUIDO, operador)
    assert saldo(c["pao"]) == 48 and saldo(c["lata"]) == 8
    assert saldo(c["bacon"]) == Decimal("2") - Decimal("0.060")
    ps.transicionar(p, StatusPedido.CONCLUIDO, operador)  # repetido: nada muda
    assert MovimentacaoEstoque.objects.filter(pedido=p, tipo="SAIDA_VENDA").count() == 4


def test_cancelar_aceito_exige_gerente_e_estorna(loja, cardapio, operador, gerente):
    loja.momento_baixa_estoque = "ACEITE"
    loja.save()
    p = ps.criar_pedido(loja, balcao([I(str(cardapio["lata"].id), 3)]), operador)
    assert saldo(cardapio["lata"]) == 7
    with pytest.raises(ErroNegocio, match="gerente"):
        ps.transicionar(p, StatusPedido.CANCELADO, operador, motivo="cliente desistiu")
    ps.transicionar(p, StatusPedido.CANCELADO, gerente, motivo="cliente desistiu")
    assert saldo(cardapio["lata"]) == 10


def test_transicao_invalida(loja, cardapio, operador):
    p = ps.criar_pedido(loja, balcao([I(str(cardapio["lata"].id))]), operador)
    with pytest.raises(ErroNegocio):
        ps.transicionar(p, StatusPedido.SAIU_PARA_ENTREGA, operador)  # retirada não sai para entrega


def test_online_taxa_por_bairro_minimo_e_pendente(loja, cardapio):
    loja.pedido_minimo_centavos = 1000
    loja.save()
    end = {"logradouro": "Rua A", "numero": "10", "bairro": "centro"}
    dados = ps.PedidoIn(canal=CanalVenda.ONLINE, tipo_atendimento=TipoAtendimento.ENTREGA,
                        itens=[I(str(cardapio["lata"].id), 2)], endereco=end, nome_cliente="Ana",
                        telefone_cliente="(11) 98765-4321", forma_pagamento_prevista="PIX")
    p = ps.criar_pedido(loja, dados)
    assert p.status == StatusPedido.PENDENTE
    assert p.taxa_entrega_centavos == 500 and p.total_centavos == 1900
    assert p.cliente.telefone == "11987654321" and p.cliente.enderecos.count() == 1
    assert p.pagamentos.get().status == "PENDENTE"
    dados.itens = [I(str(cardapio["lata"].id), 1)]
    with pytest.raises(ErroNegocio, match="mínimo"):
        ps.criar_pedido(loja, dados)
    dados.itens = [I(str(cardapio["lata"].id), 2)]
    dados.endereco = {"logradouro": "Rua B", "numero": "1", "bairro": "Longe", "latitude": "-23.80",
                      "longitude": "-46.63"}
    with pytest.raises(ErroNegocio, match="fora da área"):
        ps.criar_pedido(loja, dados)


def test_pagamento_exige_caixa_e_calcula_troco(loja, cardapio, operador):
    p = ps.criar_pedido(loja, balcao([I(str(cardapio["lata"].id), 2)]), operador)
    with pytest.raises(ErroNegocio, match="abra o caixa"):
        ps.registrar_pagamento(usuario=operador, pedido=p, forma=FormaPagamento.DINHEIRO, valor_centavos=1400)
    turno = caixa.abrir_turno(operador, loja, 10000)
    pg = ps.registrar_pagamento(usuario=operador, pedido=p, forma=FormaPagamento.DINHEIRO,
                                valor_centavos=1400, valor_recebido_centavos=2000)
    assert pg.troco_centavos == 600 and pg.turno == turno
    with pytest.raises(ErroNegocio, match="restante"):
        ps.registrar_pagamento(usuario=operador, pedido=p, forma=FormaPagamento.PIX, valor_centavos=1)
    assert caixa.esperado(turno)[FormaPagamento.DINHEIRO] == 11400
