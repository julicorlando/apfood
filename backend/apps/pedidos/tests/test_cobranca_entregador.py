"""Cobrança na porta pelo app do entregador (dinheiro com troco, cartão, Pix com QR)
e repasse do dinheiro à loja (o entregador informa, a loja confere)."""

import pytest
from apfood_core.enums import StatusPedido
from rest_framework.test import APIClient

from apps.caixa import services as caixa
from apps.caixa.models import MovimentacaoCaixa
from apps.pedidos import acertos
from apps.pedidos import services as ps
from apps.pedidos.models import Pagamento, Pedido, RepasseEntregador

from .test_app_entregador import _cache_limpo, app, entrar, entregador, pedido_entrega  # noqa: F401


def saiu(loja, cardapio, operador, e):
    p = pedido_entrega(loja, cardapio, operador)
    ps.transicionar(p, StatusPedido.SAIU_PARA_ENTREGA, operador, entregador_id=e.id)
    return Pedido.objects.get(pk=p.pk)


def painel(usuario):
    c = APIClient()
    c.force_authenticate(usuario)
    return c


@pytest.fixture
def joao(loja):
    return entregador(loja, "João", "11988887777", -23.55, -46.63)


def test_dinheiro_com_troco_repasse_e_conferencia(loja, cardapio, operador, joao):
    tok = entrar("11988887777", "2580")
    p = saiu(loja, cardapio, operador, joao)
    total = p.total_centavos
    url = f"/api/entregador/entregas/{p.id}/"
    ent = app(tok).get("/api/entregador/estado/").data["entregas"][0]
    assert ent["cobrar_centavos"] == total and ent["forma_prevista"] == "DINHEIRO"

    # a conta precisa fechar: recebido − troco = valor do pedido
    r = app(tok).post(url + "cobrar/", {"forma": "DINHEIRO", "valor_recebido_centavos": total + 5000, "troco_centavos": 100},
                      format="json")
    assert r.status_code == 400 and "conta não fecha" in str(r.data)
    r = app(tok).post(url + "cobrar/", {"forma": "DINHEIRO", "valor_recebido_centavos": total + 5000, "troco_centavos": 5000},
                      format="json")
    assert r.status_code == 200 and r.data["status"] == "PENDENTE"
    pg = p.pagamentos.get()
    assert pg.entregador == joao and pg.cobrado_em and pg.valor_recebido_centavos == total + 5000 and pg.troco_centavos == 5000
    assert ps.total_pago(pedido=p) == total  # conta como pago pelo cliente
    assert app(tok).post(url + "cobrar/", {"forma": "CARTAO_DEBITO"}, format="json").status_code == 400  # já pago
    assert app(tok).post(url + "entregar/", {"codigo": p.codigo_entrega}).status_code == 200

    est = app(tok).get("/api/entregador/estado/").data["repasses"]
    assert est["lojas"][0]["em_maos_centavos"] == total
    assert acertos.resumo(loja)[0]["em_maos_centavos"] == total

    # a loja vê o dinheiro com o entregador; ele informa o repasse
    v = painel(operador).get(f"/api/repasses-entregador/?loja={loja.id}").data
    assert v["com_entregadores"][0]["em_maos_centavos"] == total and not v["aguardando"]
    assert app(tok).post("/api/entregador/repasses/", {"valor_centavos": total}, format="json").status_code == 201
    v = painel(operador).get(f"/api/repasses-entregador/?loja={loja.id}").data
    rep = v["aguardando"][0]
    assert rep["esperado_centavos"] == total and rep["informado_entregador_centavos"] == total and not v["com_entregadores"]

    # a loja confere: precisa de caixa aberto e o dinheiro entra nele
    assert painel(operador).post(f"/api/repasses-entregador/?loja={loja.id}", {"repasse_id": rep["id"], "valor_centavos": total},
                                 format="json").status_code == 400
    turno = caixa.abrir_turno(operador, loja, 0)
    r = painel(operador).post(f"/api/repasses-entregador/?loja={loja.id}", {"repasse_id": rep["id"], "valor_centavos": total},
                              format="json")
    assert r.status_code == 201 and r.data["status"] == "CONFERIDO" and r.data["diferenca_centavos"] == 0
    pg.refresh_from_db()
    assert pg.status == "CONFIRMADO" and pg.turno == turno
    assert caixa.esperado(turno)["DINHEIRO"] == total
    assert acertos.resumo(loja)[0]["em_maos_centavos"] == 0  # já está na loja: não desconta do entregador
    d = acertos.delivery_no_periodo(loja, turno.aberto_em.replace(year=2000), turno.aberto_em.replace(year=2100))
    assert d["na_entrega"]["DINHEIRO"] == total and d["com_entregadores_centavos"] == 0


def test_repasse_com_falta_ajusta_caixa_e_entra_no_acerto(loja, cardapio, operador, gerente, joao):
    tok = entrar("11988887777", "2580")
    p = saiu(loja, cardapio, operador, joao)
    total = p.total_centavos
    app(tok).post(f"/api/entregador/entregas/{p.id}/cobrar/", {"forma": "DINHEIRO", "valor_recebido_centavos": total},
                  format="json")
    app(tok).post(f"/api/entregador/entregas/{p.id}/entregar/", {"codigo": p.codigo_entrega})
    app(tok).post("/api/entregador/repasses/", {"valor_centavos": total}, format="json")
    turno = caixa.abrir_turno(operador, loja, 0)
    rep = RepasseEntregador.objects.get()
    r = painel(operador).post(f"/api/repasses-entregador/?loja={loja.id}", {"repasse_id": str(rep.id), "valor_centavos": total - 300},
                              format="json")
    assert r.data["status"] == "DIVERGENTE" and r.data["diferenca_centavos"] == -300
    assert caixa.esperado(turno)["DINHEIRO"] == total - 300  # a gaveta bate com o que entrou
    assert MovimentacaoCaixa.objects.filter(turno=turno, tipo="SANGRIA", valor_centavos=300).exists()
    linha = acertos.resumo(loja)[0]
    assert linha["em_maos_centavos"] == 300  # a falta é descontada no acerto
    a = acertos.registrar(loja, joao.id, pago_centavos=0, usuario=gerente, gerar_despesa=False)
    assert a.em_maos_centavos == 300
    rep.refresh_from_db()
    assert rep.acerto == a


def test_acerto_desconta_dinheiro_nao_repassado_uma_vez_so(loja, cardapio, operador, gerente, joao):
    tok = entrar("11988887777", "2580")
    p = saiu(loja, cardapio, operador, joao)
    app(tok).post(f"/api/entregador/entregas/{p.id}/cobrar/", {"forma": "DINHEIRO", "valor_recebido_centavos": p.total_centavos},
                  format="json")
    app(tok).post(f"/api/entregador/entregas/{p.id}/entregar/", {"codigo": p.codigo_entrega})
    a = acertos.registrar(loja, joao.id, pago_centavos=0, usuario=gerente, gerar_despesa=False)
    assert a.em_maos_centavos == p.total_centavos
    assert app(tok).get("/api/entregador/estado/").data["repasses"]["lojas"][0]["em_maos_centavos"] == 0
    assert app(tok).post("/api/entregador/repasses/", {"valor_centavos": 100}, format="json").status_code == 400
    assert Pagamento.objects.get(pedido=p).status == "CONFIRMADO"


def test_cartao_marca_pago_e_pdv_nao_apaga_cobranca(loja, cardapio, operador, joao):
    tok = entrar("11988887777", "2580")
    p = saiu(loja, cardapio, operador, joao)
    r = app(tok).post(f"/api/entregador/entregas/{p.id}/cobrar/", {"forma": "CARTAO_CREDITO"}, format="json")
    assert r.status_code == 200 and r.data["status"] == "CONFIRMADO"
    pg = p.pagamentos.get()
    assert pg.forma == "CARTAO_CREDITO" and pg.entregador == joao and pg.turno is None

    # dinheiro com o entregador não some se a loja mexer no pagamento pelo PDV
    q = saiu(loja, cardapio, operador, joao)
    app(tok).post(f"/api/entregador/entregas/{q.id}/cobrar/", {"forma": "DINHEIRO", "valor_recebido_centavos": q.total_centavos},
                  format="json")
    caixa.abrir_turno(operador, loja, 0)
    with pytest.raises(Exception, match="restante"):
        ps.registrar_pagamento(usuario=operador, forma="PIX", valor_centavos=100, pedido=q)
    assert q.pagamentos.filter(cobrado_em__isnull=False).count() == 1


def test_pix_qr_no_app_e_gateway_conclui(loja, cardapio, operador, joao, monkeypatch):
    from apps.integracoes.models import Integracao
    from apps.integracoes.provedores.mercadopago import MercadoPago

    class Integ:
        def obter_credenciais(self):
            return {"access_token": "t"}

        def registrar_erro(self, msg):
            pass

    original = Integracao.ativa.__func__
    monkeypatch.setattr(Integracao, "ativa", classmethod(
        lambda cls, loja, tipo, provedor=None: Integ() if tipo == "PAGAMENTO" else original(cls, loja, tipo, provedor)))
    monkeypatch.setattr(MercadoPago, "criar_pix", lambda self, **kw: {
        "id": "777", "qr_code": "00020126PIX", "qr_code_base64": "iVBOR", "ticket_url": "https://mp.test/t"})
    status = {"s": "pending"}
    monkeypatch.setattr(MercadoPago, "consultar", lambda self, pid: {
        "id": pid, "status": status["s"], "valor_centavos": 10 ** 6, "external_reference": ""})

    tok = entrar("11988887777", "2580")
    p = saiu(loja, cardapio, operador, joao)
    url = f"/api/entregador/entregas/{p.id}/pix/"
    assert app(tok).get("/api/entregador/estado/").data["entregas"][0]["pix_automatico"] is True
    r = app(tok).post(url)
    assert r.status_code == 201 and r.data["qr_code"] == "00020126PIX" and r.data["valor_centavos"] == p.total_centavos
    assert app(tok).post(url).data["qr_code"] == "00020126PIX"  # o mesmo QR, sem gerar outro
    assert Pagamento.objects.filter(pedido=p).count() == 1
    ent = app(tok).get("/api/entregador/estado/").data["entregas"][0]
    assert ent["cobranca"]["pix"]["qr_code"] == "00020126PIX" and ent["cobrar_centavos"] == p.total_centavos

    assert app(tok).get(url).data == {"pago": False, "concluido": False, "falta_centavos": p.total_centavos}
    status["s"] = "approved"
    r = app(tok).get(url)
    assert r.data["pago"] is True and r.data["concluido"] is True  # o gateway confirmou: entrega concluída
    p.refresh_from_db()
    pg = p.pagamentos.get()
    assert p.status == StatusPedido.CONCLUIDO and pg.status == "CONFIRMADO" and pg.entregador == joao and pg.cobrado_em


def test_pix_sem_gateway_marca_pago(loja, cardapio, operador, joao):
    tok = entrar("11988887777", "2580")
    p = saiu(loja, cardapio, operador, joao)
    r = app(tok).post(f"/api/entregador/entregas/{p.id}/pix/")
    assert r.status_code == 400 and "chave Pix" in str(r.data)
    assert app(tok).post(f"/api/entregador/entregas/{p.id}/cobrar/", {"forma": "PIX"}, format="json").data["status"] == "CONFIRMADO"
    assert app(tok).post(f"/api/entregador/entregas/{p.id}/entregar/", {"codigo": p.codigo_entrega}).status_code == 200
