"""Relatório de faturamento por data (DD/MM/AAAA) para imprimir, fechamentos de caixa por operador
ou de todos de uma vez, e o ESC/POS para o app Android imprimir na térmica."""

import base64

from apfood_core.enums import CanalVenda, PapelUsuario, StatusPedido, TipoAtendimento
from django.utils import timezone
from rest_framework.test import APIClient

from apps.caixa import services as caixa
from apps.pedidos import services as ps


def painel(u):
    c = APIClient()
    c.force_authenticate(u)
    return c


def venda(loja, cardapio, usuario, forma, qtd=1):
    p = ps.criar_pedido(loja, ps.PedidoIn(canal=CanalVenda.BALCAO, tipo_atendimento=TipoAtendimento.CONSUMO_LOCAL,
                                          itens=[ps.ItemIn(str(cardapio["lata"].id), qtd)]), usuario)
    ps.registrar_pagamento(usuario=usuario, forma=forma, valor_centavos=p.total_centavos, pedido=p)
    ps.transicionar(p, StatusPedido.CONCLUIDO, usuario)
    return p


def test_faturamento_por_data_e_por_operador(loja, cardapio, operador, gerente):
    from apps.contas.models import Usuario

    outro = Usuario.objects.create_user("caixa2", password="x", papel=PapelUsuario.OPERADOR, empresa=loja.empresa,
                                        first_name="Bia")
    outro.lojas.set([loja])
    caixa.abrir_turno(operador, loja, 0)
    caixa.abrir_turno(outro, loja, 0)
    venda(loja, cardapio, operador, "DINHEIRO", 2)   # 1400
    venda(loja, cardapio, operador, "PIX", 1)        # 700
    venda(loja, cardapio, outro, "CARTAO_DEBITO", 3)  # 2100
    hoje = timezone.localdate().strftime("%d/%m/%Y")
    api = painel(gerente)

    r = api.get(f"/api/relatorios/faturamento/?loja={loja.id}&inicio={hoje}&fim={hoje}&largura=32")
    assert r.status_code == 200, r.data
    d = r.data
    assert d["resumo"]["faturamento_centavos"] == 4200 and d["resumo"]["pedidos"] == 3
    assert {f["forma"]: f["bruto_centavos"] for f in d["por_forma"]} == {"DINHEIRO": 1400, "PIX": 700, "CARTAO_DEBITO": 2100}
    assert d["recebido"]["bruto_centavos"] == 4200
    assert {o["operador"]: o["bruto_centavos"] for o in d["por_operador"]} == {"caixa": 2100, "Bia": 2100}
    assert {o["nome"] for o in d["operadores"]} == {"caixa", "Bia"}
    textos = [l["texto"] for l in d["linhas"]]
    assert "RELATÓRIO DE FATURAMENTO" in textos and any(t.startswith(f"Período: {hoje}") for t in textos)
    assert max(len(t) for t in textos) <= 32 and d["linhas"][-1]["corte"]

    r = api.get(f"/api/relatorios/faturamento/?loja={loja.id}&inicio={hoje}&fim={hoje}&operador={outro.id}").data
    assert r["operador"] == "Bia" and r["resumo"]["faturamento_centavos"] == 2100 and r["resumo"]["pedidos"] == 1
    assert [f["forma"] for f in r["por_forma"]] == ["CARTAO_DEBITO"]
    assert any(l["texto"] == "Operador: Bia" for l in r["linhas"])

    assert api.get(f"/api/relatorios/faturamento/?loja={loja.id}&inicio=31/02/2026&fim={hoje}").status_code == 400
    assert painel(operador).get(f"/api/relatorios/faturamento/?loja={loja.id}&data={hoje}").status_code == 403


def test_fechamentos_um_operador_ou_todos_de_uma_vez(loja, cardapio, operador, gerente):
    from apps.contas.models import Usuario

    outro = Usuario.objects.create_user("caixa2", password="x", papel=PapelUsuario.OPERADOR, empresa=loja.empresa,
                                        first_name="Bia")
    outro.lojas.set([loja])
    for u, forma in ((operador, "DINHEIRO"), (outro, "PIX")):
        t = caixa.abrir_turno(u, loja, 1000)
        venda(loja, cardapio, u, forma)
        caixa.fechar_turno(t, u, {"DINHEIRO": 1700 if forma == "DINHEIRO" else 1000, "PIX": 700 if forma == "PIX" else 0})
    hoje = timezone.localdate().strftime("%d/%m/%Y")

    # operador: só o dele
    r = painel(operador).get(f"/api/turnos/fechamentos/?loja={loja.id}&data={hoje}&cupom=1").data
    assert [t["operador"] for t in r["turnos"]] == ["caixa"] and r["operadores"] == []
    assert sum(1 for l in r["linhas"] if l["texto"] == "FECHAMENTO DE CAIXA") == 1
    assert painel(operador).get(f"/api/turnos/fechamentos/?loja={loja.id}&data={hoje}&usuario={outro.id}").data["turnos"][0]["operador"] == "caixa"

    # administrador: todos de uma vez (um cupom atrás do outro) ou um operador
    api = painel(gerente)
    r = api.get(f"/api/turnos/fechamentos/?loja={loja.id}&data={hoje}&cupom=1&largura=32").data
    assert len(r["turnos"]) == 2 and {o["nome"] for o in r["operadores"]} == {"caixa", "Bia"}
    assert sum(1 for l in r["linhas"] if l["texto"] == "FECHAMENTO DE CAIXA") == 2
    assert sum(1 for l in r["linhas"] if l["corte"]) == 2
    assert {l["texto"] for l in r["linhas"]} >= {"Operador: caixa", "Operador: Bia"}
    r = api.get(f"/api/turnos/fechamentos/?loja={loja.id}&data={hoje}&usuario={outro.id}&cupom=1").data
    assert [t["operador"] for t in r["turnos"]] == ["Bia"] and "Operador: Bia" in {l["texto"] for l in r["linhas"]}
    assert api.get(f"/api/turnos/fechamentos/?loja={loja.id}&data=01/01/2020&cupom=1").status_code == 400


def test_escpos_para_o_app_android(operador):
    r = painel(operador).post("/api/impressao/escpos/", {"linhas": [{"texto": "Olá", "negrito": True}, {"corte": True}],
                                                         "gaveta": True}, format="json")
    assert r.status_code == 200
    b = base64.b64decode(r.data["base64"])
    assert b.startswith(b"\x1b@") and b"\x1bp\x00" in b and "Olá".encode("cp860") in b and b"\x1dV" in b
    assert painel(operador).post("/api/impressao/escpos/", {"linhas": []}, format="json").status_code == 400
