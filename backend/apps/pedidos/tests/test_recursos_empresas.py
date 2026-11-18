"""Push, acerto com entregadores, cartão online, agendamento, reservas, indicação,
totem, rede e delivery no fechamento de caixa."""

from datetime import timedelta
from decimal import Decimal

import pytest
from apfood_core.enums import CanalVenda, StatusPedido, TipoAtendimento
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from apps.clientes.models import Entregador
from apps.contas.models import Usuario
from apps.pedidos import services as ps
from apps.pedidos.models import AcertoEntregador, Pedido
from apps.core.testes import quitar  # noqa: E402


@pytest.fixture(autouse=True)
def _cache_limpo():
    cache.clear()


def cliente_api(u):
    api = APIClient()
    api.force_authenticate(u)
    return api


def entregue(loja, cardapio, operador, entregador, *, dinheiro=True):
    p = ps.criar_pedido(loja, ps.PedidoIn(
        canal=CanalVenda.DELIVERY, tipo_atendimento=TipoAtendimento.ENTREGA, nome_cliente="Ana", telefone_cliente="11999990000",
        endereco={"logradouro": "Rua A", "numero": "10", "bairro": "Centro", "cidade": "SP"}, taxa_entrega_centavos=700,
        forma_pagamento_prevista="DINHEIRO" if dinheiro else "PIX", itens=[ps.ItemIn(str(cardapio["lata"].id), 2)],
    ), operador)
    ps.transicionar(p, StatusPedido.PRONTO, operador)
    ps.transicionar(Pedido.objects.get(pk=p.pk), StatusPedido.SAIU_PARA_ENTREGA, operador, entregador_id=entregador.id)
    quitar(p, "DINHEIRO" if dinheiro else "PIX")
    ps.transicionar(Pedido.objects.get(pk=p.pk), StatusPedido.CONCLUIDO, operador)
    return Pedido.objects.get(pk=p.pk)


# ----------------------------------------------------------------------------- 1. push
def test_registro_de_push(loja, gerente):
    from apps.integracoes.models import DispositivoPush

    r = cliente_api(gerente).post("/api/push/", {"token": "x" * 40}, format="json")
    assert r.status_code == 200 and r.data["ativo"] is False  # sem credenciais do Firebase: registra, não envia
    assert DispositivoPush.objects.get(token="x" * 40).usuario == gerente


# ----------------------------------------------------------------------------- 2. acerto
def test_acerto_com_entregador(loja, cardapio, operador, gerente):
    e = Entregador.objects.create(loja=loja, nome="Rui", telefone="11911112222", remuneracao="FIXO", valor_por_entrega_centavos=800)
    entregue(loja, cardapio, operador, e)
    entregue(loja, cardapio, operador, e)
    api = cliente_api(gerente)
    r = api.get(f"/api/acertos-entregador/?loja={loja.id}").data
    pend = r["pendentes"][0]
    assert pend["entregas"] == 2 and pend["ganhos_centavos"] == 1600 and pend["taxas_centavos"] == 1400
    r = api.post(f"/api/acertos-entregador/?loja={loja.id}", {"entregador_id": str(e.id), "pago_centavos": 1600,
                                                              "gerar_despesa": True}, format="json")
    assert r.status_code == 201 and any("RECIBO" in l["texto"] for l in r.data["linhas"])
    a = AcertoEntregador.objects.get()
    assert a.entregas == 2 and a.despesa.valor_centavos == 1600 and a.despesa.data_pagamento
    assert api.get(f"/api/acertos-entregador/?loja={loja.id}").data["pendentes"] == []
    assert api.post(f"/api/acertos-entregador/?loja={loja.id}", {"entregador_id": str(e.id), "pago_centavos": 0},
                    format="json").status_code == 400
    assert api.get(f"/api/acertos-entregador/{a.id}/recibo/?loja={loja.id}").status_code == 200


def test_operador_nao_ve_acerto(loja, operador):
    assert cliente_api(operador).get(f"/api/acertos-entregador/?loja={loja.id}").status_code == 403


# ----------------------------------------------------------------------------- 3. cartão online
def test_cartao_online_gera_checkout(loja, cardapio, monkeypatch):
    from apps.integracoes.models import Integracao
    from apps.integracoes.provedores.mercadopago import MercadoPago

    class Integ:
        def obter_credenciais(self):
            return {"access_token": "t"}

        def registrar_erro(self, msg):
            pass

    monkeypatch.setattr(Integracao, "ativa", classmethod(lambda cls, *a, **k: Integ()))
    monkeypatch.setattr(MercadoPago, "criar_preferencia", lambda self, **kw: {"id": "pref1", "init_point": "https://mp.test/pagar"})
    r = APIClient().post(f"/api/publico/lojas/{loja.slug}/pedidos/", {
        "tipo_atendimento": "RETIRADA", "nome_cliente": "Ana", "telefone_cliente": "11987654321",
        "forma_pagamento_prevista": "CARTAO_CREDITO", "pagar_cartao_agora": True,
        "itens": [{"produto_id": str(cardapio["lata"].id)}]}, format="json")
    assert r.status_code == 201 and r.data["cartao_url"] == "https://mp.test/pagar"
    pg = Pedido.objects.get(token_rastreio=r.data["token"]).pagamentos.get()
    assert pg.status == "PENDENTE" and pg.pago_online and pg.referencia_externa == "pref:pref1"
    assert APIClient().get(f"/api/publico/pedidos/{r.data['token']}/").data["cartao_url"] == "https://mp.test/pagar"


# ----------------------------------------------------------------------------- 4. agendamento
def test_pedido_agendado_com_loja_fechada(loja, cardapio):
    from apps.pedidos import agendados

    amanha = (timezone.localtime() + timedelta(days=1)).weekday()
    loja.horarios = [{"dia_semana": amanha, "abre": "11:00", "fecha": "14:00"}]
    loja.aceita_agendamento = True
    loja.save()
    dias = agendados.horarios_disponiveis(loja)
    assert dias and dias[0]["horarios"][0] == "11:00" and "13:45" in dias[0]["horarios"] and "14:00" not in dias[0]["horarios"]
    quando = timezone.make_aware(timezone.datetime.combine(timezone.localdate() + timedelta(days=1),
                                                           timezone.datetime.min.time().replace(hour=12)))
    corpo = {"tipo_atendimento": "RETIRADA", "nome_cliente": "Ana", "telefone_cliente": "11987654321",
             "forma_pagamento_prevista": "PIX", "itens": [{"produto_id": str(cardapio["lata"].id)}]}
    api = APIClient()
    assert api.post(f"/api/publico/lojas/{loja.slug}/pedidos/", corpo, format="json").status_code == 400  # fechada agora
    r = api.post(f"/api/publico/lojas/{loja.slug}/pedidos/", {**corpo, "agendado_para": quando.isoformat()}, format="json")
    assert r.status_code == 201, r.data
    assert Pedido.objects.get(token_rastreio=r.data["token"]).agendado_para == quando
    fora = quando.replace(hour=20)
    assert api.post(f"/api/publico/lojas/{loja.slug}/pedidos/", {**corpo, "agendado_para": fora.isoformat()},
                    format="json").status_code == 400
    loja.aceita_agendamento = False
    loja.save()
    assert api.post(f"/api/publico/lojas/{loja.slug}/pedidos/", {**corpo, "agendado_para": quando.isoformat()},
                    format="json").status_code == 400


# ----------------------------------------------------------------------------- 6. reservas
def test_reserva_pelo_site_e_confirmacao(loja, gerente):
    loja.aceita_reservas = True
    loja.save()
    quando = timezone.localtime() + timedelta(days=2)
    api = APIClient()
    r = api.post(f"/api/publico/lojas/{loja.slug}/reservas/", {"nome": "Bia", "telefone": "(11) 98888-7777", "pessoas": 4,
                                                               "data_hora": quando.isoformat()}, format="json")
    assert r.status_code == 201 and r.data["status"] == "PENDENTE"
    g = cliente_api(gerente)
    lista = g.get(f"/api/reservas/?loja={loja.id}&data={quando.date()}").data
    itens = lista["results"] if isinstance(lista, dict) else lista
    assert itens[0]["nome"] == "Bia" and itens[0]["telefone"] == "11988887777"
    r = g.post(f"/api/reservas/{itens[0]['id']}/status/?loja={loja.id}", {"status": "CONFIRMADA"}, format="json")
    assert r.status_code == 200 and r.data["status"] == "CONFIRMADA"
    passado = timezone.localtime() - timedelta(hours=1)
    assert api.post(f"/api/publico/lojas/{loja.slug}/reservas/", {"nome": "X", "telefone": "11988887777", "pessoas": 2,
                                                                  "data_hora": passado.isoformat()}, format="json").status_code == 400


# ----------------------------------------------------------------------------- 5. indicação
def test_indicacao_da_cashback_a_quem_indicou(loja, cardapio, operador):
    from apps.clientes.models import Cliente
    from apps.marketing.reconquista import codigo_indicacao

    loja.indicacao_ativa, loja.indicacao_desconto_centavos, loja.indicacao_premio_centavos = True, 500, 1000
    loja.save()
    ana = Cliente.objects.create(loja=loja, nome="Ana Souza", telefone="11911110000")
    codigo = codigo_indicacao(ana)
    assert codigo.startswith("ANA") and codigo_indicacao(ana) == codigo
    p = ps.criar_pedido(loja, ps.PedidoIn(canal=CanalVenda.BALCAO, tipo_atendimento=TipoAtendimento.RETIRADA,
                                          nome_cliente="Caio", telefone_cliente="11922220000", cupom_codigo=codigo,
                                          itens=[ps.ItemIn(str(cardapio["lata"].id), 2)]), operador)
    assert p.desconto_centavos == 500
    ps.transicionar(p, StatusPedido.PRONTO, operador)
    quitar(p)
    ps.transicionar(Pedido.objects.get(pk=p.pk), StatusPedido.CONCLUIDO, operador)
    ana.refresh_from_db()
    assert ana.saldo_cashback_centavos >= 1000
    assert Cliente.objects.get(telefone="11922220000").indicado_por == ana


# ----------------------------------------------------------------------------- 8. totem
def test_totem_link_e_pedido(loja, cardapio, gerente, operador):
    g = cliente_api(gerente)
    url = g.post(f"/api/lojas/{loja.id}/totem/?loja={loja.id}").data["url"]
    assert f"/{loja.slug}/totem/" in url
    token = url.rstrip("/").rsplit("/", 1)[1]
    assert cliente_api(operador).post(f"/api/lojas/{loja.id}/totem/?loja={loja.id}").status_code == 403
    html = APIClient().get(f"/{loja.slug}/totem/{token}/").content.decode()
    assert '"totem"' in html
    assert APIClient().get(f"/{loja.slug}/totem/errado/").status_code == 404
    r = APIClient().post(f"/api/publico/lojas/{loja.slug}/totem/{token}/pedidos/", {
        "tipo_atendimento": "CONSUMO_LOCAL", "nome_cliente": "Léo", "itens": [{"produto_id": str(cardapio["lata"].id), "quantidade": 1}]},
        format="json")
    assert r.status_code == 201 and len(r.data["senha"]) == 4
    p = Pedido.objects.get(token_rastreio=r.data["token"])
    assert p.canal == "BALCAO" and p.atendente_id is None and "[Totem]" in p.observacao
    assert APIClient().post(f"/api/publico/lojas/{loja.slug}/totem/errado/pedidos/", {
        "tipo_atendimento": "RETIRADA", "itens": [{"produto_id": str(cardapio["lata"].id)}]}, format="json").status_code == 404
    g.delete(f"/api/lojas/{loja.id}/totem/?loja={loja.id}")
    assert APIClient().get(f"/{loja.slug}/totem/{token}/").status_code == 404


# ----------------------------------------------------------------------------- 7. rede
def test_visao_da_rede_e_replicar_cardapio(loja, cardapio):
    from apps.cardapio.models import Produto
    from apps.lojas.models import Loja

    filial = Loja.objects.create(empresa=loja.empresa, nome="Burger Sul", slug="burger-sul")
    admin = Usuario.objects.create_user("dono", password="x", papel="ADMIN", empresa=loja.empresa)
    api = cliente_api(admin)
    r = api.get("/api/rede/")
    assert r.status_code == 200 and {l["loja"] for l in r.data["lojas"]} == {"Burger Centro", "Burger Sul"}
    r = api.post("/api/rede/replicar/", {"origem": str(loja.id), "destinos": [str(filial.id)]}, format="json")
    assert r.status_code == 200 and r.data["resultado"]["Burger Sul"]["produtos_novos"] >= 2
    xb = Produto.objects.get(loja=filial, nome="X-Burger")
    assert xb.categoria.loja == filial and xb.grupos_adicionais.exists()
    original = Produto.objects.get(loja=loja, nome="X-Burger")
    original.preco_centavos = 4321
    original.save()
    api.post("/api/rede/replicar/", {"origem": str(loja.id), "destinos": [str(filial.id)], "somente_precos": True}, format="json")
    xb.refresh_from_db()
    assert xb.preco_centavos == 4321
    assert Produto.objects.filter(loja=filial, nome="X-Burger").count() == 1


# ----------------------------------------------------------------------------- delivery no fechamento
def test_delivery_no_fechamento_de_caixa(loja, cardapio, operador, gerente):
    from apps.caixa import services as caixa

    t = caixa.abrir_turno(gerente, loja, 10000)
    e = Entregador.objects.create(loja=loja, nome="Rui")
    entregue(loja, cardapio, operador, e)
    api = cliente_api(gerente)
    r = api.get(f"/api/turnos/{t.id}/resumo/?loja={loja.id}").data
    assert r["delivery"]["pedidos"] == 1 and r["delivery"]["por_entregador"][0]["entregador"] == "Rui"
    assert "delivery" not in cliente_api(operador).get(f"/api/turnos/{t.id}/resumo/?loja={loja.id}").data
    hoje = timezone.localdate()
    d = api.get(f"/api/relatorios/fechamentos/?loja={loja.id}&inicio={hoje}&fim={hoje}").data["delivery"]
    assert d["pedidos"] == 1 and d["taxas_centavos"] == 700 and d["a_receber_centavos"] + d["na_entrega_centavos"] == d["total_centavos"]
    assert Decimal(d["total_centavos"]) > 0
