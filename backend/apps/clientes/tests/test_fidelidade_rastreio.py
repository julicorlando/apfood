"""Cartão fidelidade com selos e rastreio do entregador para o cliente."""

import json

from apfood_core.enums import CanalVenda, StatusPedido, TipoAtendimento
from django.test import Client

from apps.clientes.models import Cliente, Entregador
from apps.pedidos import services as ps
from apps.pedidos.models import Pedido

TEL = "11999990000"


def concluir(loja, cardapio, u, qtd=1):
    p = ps.criar_pedido(loja, ps.PedidoIn(CanalVenda.BALCAO, TipoAtendimento.RETIRADA,
                                          [ps.ItemIn(str(cardapio["lata"].id), qtd)], telefone_cliente=TEL,
                                          nome_cliente="Ana"), u)
    ps.transicionar(p, StatusPedido.PRONTO, u)
    ps.transicionar(p, StatusPedido.CONCLUIDO, u)
    return p


def test_selos_e_premio(loja, cardapio, operador):
    loja.fidelidade_selos, loja.fidelidade_premio_centavos, loja.fidelidade_pedido_minimo_centavos = 2, 1500, 1000
    loja.save()
    concluir(loja, cardapio, operador, 1)  # 7,00: abaixo do mínimo, sem selo
    assert Cliente.objects.get(telefone=TEL).selos == 0
    concluir(loja, cardapio, operador, 2)
    c = Cliente.objects.get(telefone=TEL)
    assert (c.selos, c.saldo_cashback_centavos) == (1, 0)
    p = concluir(loja, cardapio, operador, 2)
    c.refresh_from_db()
    assert (c.selos, c.saldo_cashback_centavos) == (0, 1500)  # completou: prêmio vira crédito
    d = Client().get(f"/api/publico/pedidos/{p.token_rastreio}/").json()
    assert d["fidelidade"] == {"selos": 0, "meta": 2, "saldo_centavos": 1500}
    assert Client().get(f"/api/publico/lojas/{loja.slug}/").json()["loja"]["fidelidade"]["selos"] == 2


def test_rastreio_do_entregador(loja, cardapio, operador):
    e = Entregador.objects.create(loja=loja, nome="Carlos Silva")
    token = e.gerar_link()
    p = ps.criar_pedido(loja, ps.PedidoIn(
        CanalVenda.DELIVERY, TipoAtendimento.ENTREGA, [ps.ItemIn(str(cardapio["lata"].id), 1)], nome_cliente="Ana",
        telefone_cliente=TEL, taxa_entrega_centavos=0,
        endereco={"logradouro": "Rua A", "numero": "1", "bairro": "Centro", "cidade": "SP",
                  "latitude": "-23.56", "longitude": "-46.64"}), operador)
    url = f"/api/publico/pedidos/{p.token_rastreio}/"
    ps.transicionar(p, StatusPedido.PRONTO, operador)
    ps.transicionar(p, StatusPedido.SAIU_PARA_ENTREGA, operador, entregador_id=e.id)
    assert Client().get(url).json()["rastreio"] is None  # ainda sem posição
    c = Client()
    assert c.post(f"/entrega/{token}/localizacao/", json.dumps({"latitude": 999, "longitude": 0}),
                  content_type="application/json").status_code == 400
    assert c.post("/entrega/" + "x" * 30 + "/localizacao/", json.dumps({"latitude": -23.55, "longitude": -46.63}),
                  content_type="application/json").status_code == 404
    r = c.post(f"/entrega/{token}/localizacao/", json.dumps({"latitude": -23.55, "longitude": -46.63}),
               content_type="application/json")
    assert r.status_code == 200
    rast = Client().get(url).json()["rastreio"]
    assert rast["entregador"] == "Carlos" and 1 < rast["distancia_km"] < 2 and rast["minutos"] >= 1
    Pedido.objects.filter(pk=p.pk).update(status="CONCLUIDO")
    assert Client().get(url).json()["rastreio"] is None
