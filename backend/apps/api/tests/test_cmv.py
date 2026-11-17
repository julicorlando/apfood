"""CMV teórico pela ficha técnica."""

from apfood_core.enums import CanalVenda, StatusPedido, TipoAtendimento
from rest_framework.test import APIClient

from apps.pedidos import services as ps


def concluir(p, u):
    ps.transicionar(p, StatusPedido.PRONTO, u)
    ps.transicionar(p, StatusPedido.CONCLUIDO, u)


def test_cmv_e_margem(loja, cardapio, operador, gerente):
    c = cardapio
    c["pao"].custo_centavos, c["carne"].custo_centavos = 150, 850  # X-Burger custa 10,00
    c["pao"].save()
    c["carne"].save()
    c["lata"].custo_centavos = 280
    c["lata"].save()
    p = ps.criar_pedido(loja, ps.PedidoIn(CanalVenda.BALCAO, TipoAtendimento.RETIRADA, [
        ps.ItemIn(str(c["x"].id), 2, adicionais=[ps.AdicionalIn(str(c["ao_ponto"].id), 1)]),
        ps.ItemIn(str(c["lata"].id), 1)]), operador)
    concluir(p, operador)
    api = APIClient()
    api.force_authenticate(gerente)
    r = api.get(f"/api/relatorios/cmv/?loja={loja.id}&periodo=dia").data
    assert r["faturamento_centavos"] == 6700 and r["custo_centavos"] == 2280
    assert r["cmv_percentual"] == round(2280 * 100 / 6700, 1)
    x = next(l for l in r["itens"] if l["nome"] == "X-Burger")
    assert x["custo_centavos"] == 2000 and x["margem_percentual"] == 66.7
    card = {l["nome"]: l for l in r["cardapio"]}
    assert card["X-Burger"]["custo_centavos"] == 1000 and card["Lata"]["margem_percentual"] == 60.0
    assert api.get(f"/api/relatorios/cmv/?loja={loja.id}").status_code == 200
    api.force_authenticate(operador)
    assert api.get(f"/api/relatorios/cmv/?loja={loja.id}").status_code == 403


def test_sem_custo_fica_de_fora(loja, cardapio, operador, gerente):
    p = ps.criar_pedido(loja, ps.PedidoIn(CanalVenda.BALCAO, TipoAtendimento.RETIRADA,
                                          [ps.ItemIn(str(cardapio["lata"].id), 1)]), operador)
    concluir(p, operador)
    api = APIClient()
    api.force_authenticate(gerente)
    r = api.get(f"/api/relatorios/cmv/?loja={loja.id}").data
    assert r["faturamento_sem_custo_centavos"] == 700 and r["cmv_percentual"] is None
