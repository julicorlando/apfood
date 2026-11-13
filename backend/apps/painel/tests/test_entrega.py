"""Tela do entregador: link secreto, lista as entregas dele e conclui."""

from apfood_core.enums import CanalVenda, StatusPedido, TipoAtendimento
from rest_framework.test import APIClient

from apps.clientes.models import Entregador
from apps.pedidos import services as ps
from apps.pedidos.models import Pedido


def pedido_entrega(loja, cardapio, operador, entregador):
    p = ps.criar_pedido(loja, ps.PedidoIn(
        canal=CanalVenda.DELIVERY, tipo_atendimento=TipoAtendimento.ENTREGA, nome_cliente="Ana", telefone_cliente="11999990000",
        endereco={"logradouro": "Rua A", "numero": "10", "bairro": "Centro", "cidade": "SP"}, taxa_entrega_centavos=500,
        forma_pagamento_prevista="DINHEIRO", troco_para_centavos=5000, itens=[ps.ItemIn(str(cardapio["lata"].id), 2)],
    ), operador)
    ps.transicionar(p, StatusPedido.PRONTO, operador)
    ps.transicionar(p, StatusPedido.SAIU_PARA_ENTREGA, operador, entregador_id=entregador.id)
    return p


def test_gerente_gera_link_e_entregador_conclui(client, loja, cardapio, operador, gerente):
    e = Entregador.objects.create(loja=loja, nome="João", telefone="11988887777")
    api = APIClient()
    api.force_authenticate(gerente)
    r = api.post(f"/api/entregadores/{e.id}/link/?loja={loja.id}")
    assert r.status_code == 200 and "/entrega/" in r.data["url"]
    e.refresh_from_db()
    p = pedido_entrega(loja, cardapio, operador, e)

    html = client.get(f"/entrega/{e.token_acesso}/").content.decode()
    assert f"Pedido #{p.numero}" in html and "Cobrar R$ 19,00" in html and "troco para R$ 50,00" in html

    r = client.post(f"/entrega/{e.token_acesso}/{p.id}/entregue/")
    assert r.status_code == 302
    assert Pedido.objects.get(pk=p.pk).status == StatusPedido.CONCLUIDO
    assert f"Pedido #{p.numero}" not in client.get(f"/entrega/{e.token_acesso}/").content.decode()


def test_operador_nao_gera_link(loja, operador):
    e = Entregador.objects.create(loja=loja, nome="João")
    api = APIClient()
    api.force_authenticate(operador)
    assert api.post(f"/api/entregadores/{e.id}/link/?loja={loja.id}").status_code == 403


def test_link_invalido_ou_antigo_nao_abre(client, loja):
    e = Entregador.objects.create(loja=loja, nome="João")
    antigo = e.gerar_link()
    e.gerar_link()
    assert client.get(f"/entrega/{antigo}/").status_code == 404
    assert client.get("/entrega/curto/").status_code == 404


def test_entregador_nao_conclui_pedido_de_outro(client, loja, cardapio, operador):
    dono = Entregador.objects.create(loja=loja, nome="Dono")
    intruso = Entregador.objects.create(loja=loja, nome="Intruso")
    intruso.gerar_link()
    p = pedido_entrega(loja, cardapio, operador, dono)
    assert client.post(f"/entrega/{intruso.token_acesso}/{p.id}/entregue/").status_code == 404
    assert Pedido.objects.get(pk=p.pk).status == StatusPedido.SAIU_PARA_ENTREGA
