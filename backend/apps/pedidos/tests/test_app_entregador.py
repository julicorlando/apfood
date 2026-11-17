"""App ApFood Entregador: login por telefone + PIN, chamada em fila (30 s cada,
2 min no total), códigos de retirada e de recebimento, ganhos; e avaliação."""

from datetime import timedelta

import pytest
from apfood_core.enums import CanalVenda, StatusPedido, TipoAtendimento
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from apps.clientes.models import Entregador
from apps.pedidos import chamadas
from apps.pedidos import services as ps
from apps.pedidos.models import ChamadaEntrega, Pedido


@pytest.fixture(autouse=True)
def _cache_limpo():
    cache.clear()


def pedido_entrega(loja, cardapio, operador, status=StatusPedido.PRONTO):
    p = ps.criar_pedido(loja, ps.PedidoIn(
        canal=CanalVenda.DELIVERY, tipo_atendimento=TipoAtendimento.ENTREGA, nome_cliente="Ana", telefone_cliente="11999990000",
        endereco={"logradouro": "Rua A", "numero": "10", "bairro": "Centro", "cidade": "SP"}, taxa_entrega_centavos=700,
        forma_pagamento_prevista="DINHEIRO", itens=[ps.ItemIn(str(cardapio["lata"].id), 2)],
    ), operador)
    if status != p.status:
        ps.transicionar(p, status, operador)
    return Pedido.objects.get(pk=p.pk)


def entregador(loja, nome, tel, lat, lng, pin="2580", online=True):
    e = Entregador.objects.create(loja=loja, nome=nome, telefone=tel, latitude=lat, longitude=lng,
                                  online=online, online_em=timezone.now())
    e.definir_pin(pin, trocado=False)
    e.save()
    return e


def app(token=None):
    c = APIClient()
    if token:
        c.credentials(HTTP_AUTHORIZATION=f"Entregador {token}")
    return c


def entrar(tel, pin):
    r = app().post("/api/entregador/entrar/", {"telefone": tel, "pin": pin}, format="json")
    assert r.status_code == 200, r.data
    return r.data["token"]


def test_login_pin_e_troca_de_pin(loja):
    entregador(loja, "João", "11988887777", -23.55, -46.63)
    assert app().post("/api/entregador/entrar/", {"telefone": "11988887777", "pin": "0000"}, format="json").status_code == 400
    r = app().post("/api/entregador/entrar/", {"telefone": "+55 11 98888-7777", "pin": "2580"}, format="json")
    assert r.status_code == 200 and r.data["trocar_pin"] is True and r.data["nome"] == "João"
    tok = r.data["token"]
    assert app(tok).post("/api/entregador/pin/", {"atual": "2580", "novo": "1111"}, format="json").status_code == 400
    r = app(tok).post("/api/entregador/pin/", {"atual": "2580", "novo": "73914"}, format="json")
    assert r.status_code == 200
    assert app(tok).get("/api/entregador/estado/").status_code == 401  # PIN mudou: sessão antiga cai
    assert app(r.data["token"]).get("/api/entregador/estado/").data["trocar_pin"] is False
    assert entrar("11988887777", "73914")


def test_loja_define_pin_no_cadastro(loja, gerente):
    api = APIClient()
    api.force_authenticate(gerente)
    r = api.post(f"/api/entregadores/?loja={loja.id}", {"nome": "Bia", "telefone": "11977776666", "pin": "4826",
                                                       "remuneracao": "FIXO", "valor_por_entrega_centavos": 600}, format="json")
    assert r.status_code == 201 and r.data["tem_pin"] is True and "pin" not in r.data and "pin_hash" not in r.data
    assert entrar("11977776666", "4826")
    assert api.post(f"/api/entregadores/?loja={loja.id}", {"nome": "X", "pin": "12"}, format="json").status_code == 400


def test_chamada_vai_do_mais_perto_ao_proximo_e_aceita(loja, cardapio, operador, gerente):
    perto = entregador(loja, "Perto", "11911111111", -23.5501, -46.6301)
    longe = entregador(loja, "Longe", "11922222222", -23.60, -46.70)
    entregador(loja, "Offline", "11933333333", -23.55, -46.63, online=False)
    p = pedido_entrega(loja, cardapio, operador)
    api = APIClient()
    api.force_authenticate(gerente)
    r = api.post(f"/api/pedidos/{p.id}/chamada/?loja={loja.id}")
    assert r.status_code == 200 and r.data["chamada"]["entregador_atual"] == "Perto" and r.data["disponiveis"] == 2

    t_perto, t_longe = entrar("11911111111", "2580"), entrar("11922222222", "2580")
    oferta = app(t_perto).get("/api/entregador/estado/").data["oferta"]
    assert oferta["numero"] == p.numero and 25 <= oferta["segundos"] <= 30
    assert app(t_longe).get("/api/entregador/estado/").data["oferta"] is None

    # 30 s sem resposta: vai para o próximo
    ChamadaEntrega.objects.update(oferta_ate=timezone.now() - timedelta(seconds=1))
    assert app(t_perto).get("/api/entregador/estado/").data["oferta"] is None
    oferta = app(t_longe).get("/api/entregador/estado/").data["oferta"]
    assert oferta is not None
    r = app(t_longe).post(f"/api/entregador/ofertas/{oferta['chamada']}/aceitar/")
    assert r.status_code == 200
    p.refresh_from_db()
    assert p.entregador == longe
    assert api.get(f"/api/pedidos/{p.id}/chamada/?loja={loja.id}").data["chamada"]["status"] == "ACEITA"
    assert app(t_perto).post(f"/api/entregador/ofertas/{oferta['chamada']}/aceitar/").status_code == 400

    # retirada exige o código da loja; entrega exige o do cliente
    ent = app(t_longe).get("/api/entregador/estado/").data["entregas"][0]
    assert ent["numero"] == p.numero and ent["telefone"] == ""  # telefone do cliente só depois de sair
    assert app(t_longe).post(f"/api/entregador/entregas/{p.id}/retirar/", {"codigo": "9999" if p.codigo_retirada != "9999" else "0000"}).status_code == 400
    assert app(t_longe).post(f"/api/entregador/entregas/{p.id}/entregar/", {"codigo": p.codigo_entrega}).status_code == 400
    assert app(t_longe).post(f"/api/entregador/entregas/{p.id}/retirar/", {"codigo": p.codigo_retirada}).status_code == 200
    assert Pedido.objects.get(pk=p.pk).status == StatusPedido.SAIU_PARA_ENTREGA
    assert app().get(f"/api/publico/pedidos/{p.token_rastreio}/").data["codigo_entrega"] == p.codigo_entrega
    r = app(t_longe).post(f"/api/entregador/entregas/{p.id}/entregar/", {"codigo": p.codigo_entrega})
    assert r.status_code == 400 and "pagamento" in str(r.data)  # cobra antes de concluir
    assert app(t_longe).post(f"/api/entregador/entregas/{p.id}/cobrar/", {"forma": "CARTAO_DEBITO"}).status_code == 200
    assert app(t_longe).post(f"/api/entregador/entregas/{p.id}/entregar/", {"codigo": p.codigo_entrega}).status_code == 200
    assert Pedido.objects.get(pk=p.pk).status == StatusPedido.CONCLUIDO

    g = app(t_longe).get("/api/entregador/estado/").data["ganhos"]
    assert g["hoje"] == {"entregas": 1, "ganhos_centavos": 700} and g["projecao_mes_centavos"] >= 700
    assert perto.pk  # usado


def test_recusa_passa_adiante_e_ninguem_aceita_em_2_min(loja, cardapio, operador, gerente):
    entregador(loja, "Único", "11911111111", -23.55, -46.63)
    p = pedido_entrega(loja, cardapio, operador, StatusPedido.EM_PREPARO)
    ch = chamadas.iniciar(p, gerente)
    tok = entrar("11911111111", "2580")
    oferta = app(tok).get("/api/entregador/estado/").data["oferta"]
    assert app(tok).post(f"/api/entregador/ofertas/{oferta['chamada']}/recusar/").status_code == 200
    ch.refresh_from_db()
    assert ch.status == "PROCURANDO" and ch.entregador_atual is None  # quem recusou não recebe de novo
    ChamadaEntrega.objects.update(expira_em=timezone.now() - timedelta(seconds=1))
    api = APIClient()
    api.force_authenticate(gerente)
    r = api.get(f"/api/pedidos/{p.id}/chamada/?loja={loja.id}")
    assert r.data["chamada"]["status"] == "SEM_RESPOSTA"
    # chamar de novo abre outra chamada; ou escolher o entregador na mão
    assert api.post(f"/api/pedidos/{p.id}/chamada/?loja={loja.id}").data["chamada"]["status"] == "PROCURANDO"
    e2 = Entregador.objects.create(loja=loja, nome="Manual")
    r = api.post(f"/api/pedidos/{p.id}/entregador/?loja={loja.id}", {"entregador_id": str(e2.id)}, format="json")
    assert r.status_code == 200 and str(r.data["entregador"]) == str(e2.id)
    assert ChamadaEntrega.objects.filter(pedido=p, status="PROCURANDO").count() == 0


def test_so_entrega_chama_entregador(loja, cardapio, operador, gerente):
    p = ps.criar_pedido(loja, ps.PedidoIn(canal=CanalVenda.BALCAO, tipo_atendimento=TipoAtendimento.RETIRADA,
                                          itens=[ps.ItemIn(str(cardapio["lata"].id), 1)]), operador)
    api = APIClient()
    api.force_authenticate(gerente)
    assert api.post(f"/api/pedidos/{p.id}/chamada/?loja={loja.id}").status_code == 400


def test_avaliacao_opcional_depois_de_receber(loja, cardapio, operador, gerente):
    p = pedido_entrega(loja, cardapio, operador)
    url = f"/api/publico/pedidos/{p.token_rastreio}/"
    assert app().get(url).data["pode_avaliar"] is False
    assert app().post(url, {"nota": 5}, format="json").status_code == 400  # ainda não recebeu
    ps.transicionar(p, StatusPedido.SAIU_PARA_ENTREGA, operador)
    ps.transicionar(Pedido.objects.get(pk=p.pk), StatusPedido.CONCLUIDO, operador)
    assert app().get(url).data["pode_avaliar"] is True
    assert app().post(url, {"nota": 7}, format="json").status_code == 400
    r = app().post(url, {"nota": 4, "comentario": "Chegou quentinho"}, format="json")
    assert r.status_code == 201
    assert app().post(url, {"nota": 1}, format="json").status_code == 400  # uma vez só
    d = app().get(url).data
    assert d["avaliacao"]["nota"] == 4 and d["pode_avaliar"] is False
    api = APIClient()
    api.force_authenticate(gerente)
    rel = api.get(f"/api/relatorios/avaliacoes/?loja={loja.id}").data
    assert rel["quantidade"] == 1 and rel["media"] == 4 and rel["avaliacoes"][0]["comentario"] == "Chegou quentinho"
