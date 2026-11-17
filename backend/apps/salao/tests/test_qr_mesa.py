"""Autoatendimento: QR Code da mesa abre o cardápio e o pedido cai na comanda."""

from django.test import Client

from apps.salao import services as salao
from apps.salao.models import Comanda, Mesa


def url(loja, mesa, fim=""):
    return f"/api/publico/lojas/{loja.slug}/mesa/{mesa.token_qr}/{fim}"


def corpo(cardapio, qtd=1):
    return {"nome_cliente": "Ana", "observacao": "sem gelo", "itens": [{"produto_id": str(cardapio["lata"].id), "quantidade": qtd}]}


def test_mesa_ganha_token_e_pagina_abre(loja, cardapio):
    mesa = Mesa.objects.create(loja=loja, nome="Mesa 7")
    assert mesa.token_qr and len(mesa.token_qr) >= 12
    html = Client().get(f"/{loja.slug}/mesa/{mesa.token_qr}/").content.decode()
    assert "Mesa 7" in html
    assert Client().get(f"/{loja.slug}/mesa/errado/").status_code == 404


def test_pedido_pelo_qr_vai_para_a_comanda_da_mesa(loja, cardapio, operador):
    mesa = Mesa.objects.create(loja=loja, nome="Mesa 7")
    c = Client()
    r = c.post(url(loja, mesa, "pedidos/"), corpo(cardapio, 2), content_type="application/json")
    assert r.status_code == 201, r.content
    comanda = Comanda.objects.get(mesa=mesa)
    assert comanda.status == "ABERTA" and comanda.pedidos.count() == 1
    p = comanda.pedidos.get()
    assert p.canal == "MESA" and p.total_centavos == 1400 and "QR" in p.observacao
    # segundo pedido entra na mesma conta
    c.post(url(loja, mesa, "pedidos/"), corpo(cardapio), content_type="application/json")
    assert Comanda.objects.filter(mesa=mesa).count() == 1 and comanda.pedidos.count() == 2
    conta = c.get(url(loja, mesa)).json()
    assert conta["aberta"] and len(conta["itens"]) == 2 and conta["subtotal_centavos"] == 2100
    # conta pedida: não aceita mais pelo QR
    salao.pedir_conta(comanda, operador)
    r = c.post(url(loja, mesa, "pedidos/"), corpo(cardapio), content_type="application/json")
    assert r.status_code == 400 and "garçom" in r.content.decode()


def test_qr_desligado_ou_token_trocado(loja, cardapio, gerente):
    from rest_framework.test import APIClient

    mesa = Mesa.objects.create(loja=loja, nome="Mesa 1")
    antigo = mesa.token_qr
    api = APIClient()
    api.force_authenticate(gerente)
    novo = api.post(f"/api/mesas/{mesa.id}/novo-qr/?loja={loja.id}").data["token_qr"]
    assert novo != antigo
    assert Client().post(f"/api/publico/lojas/{loja.slug}/mesa/{antigo}/pedidos/", corpo(cardapio),
                         content_type="application/json").status_code == 404
    loja.pedido_na_mesa = False
    loja.save()
    mesa.refresh_from_db()
    assert Client().post(url(loja, mesa, "pedidos/"), corpo(cardapio), content_type="application/json").status_code == 404
