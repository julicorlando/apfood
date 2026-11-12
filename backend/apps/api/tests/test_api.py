import uuid

import pytest
from apfood_core.enums import PapelUsuario
from rest_framework.test import APIClient

from apps.cardapio.models import Categoria, Produto
from apps.contas.models import Usuario
from apps.lojas.models import Empresa, Loja


def cliente_api(usuario):
    c = APIClient()
    c.force_authenticate(usuario)
    return c


@pytest.fixture
def outra_empresa():
    e = Empresa.objects.create(nome="Outra")
    loja = Loja.objects.create(empresa=e, nome="Outra loja", slug="outra")
    u = Usuario.objects.create_user("admin_outra", password="x", papel=PapelUsuario.ADMIN, empresa=e)
    Produto.objects.create(loja=loja, nome="Segredo", preco_centavos=100)
    return {"loja": loja, "admin": u}


def test_isolamento_entre_empresas(loja, cardapio, gerente, outra_empresa):
    api = cliente_api(gerente)
    nomes = {p["nome"] for p in api.get("/api/produtos/").json()["results"]}
    assert "X-Burger" in nomes and "Segredo" not in nomes
    assert api.get(f"/api/produtos/?loja={outra_empresa['loja'].id}").status_code == 403
    r = api.post("/api/pedidos/", {"loja": str(outra_empresa["loja"].id), "canal": "BALCAO",
                                   "tipo_atendimento": "RETIRADA", "itens": []}, format="json")
    assert r.status_code == 403
    # não dá para apontar para categoria de outra loja
    cat_outra = Categoria.objects.create(loja=outra_empresa["loja"], nome="X")
    r = api.post("/api/produtos/", {"nome": "Novo", "categoria": str(cat_outra.id)}, format="json")
    assert r.status_code == 400 and "categoria" in r.json()


def test_operador_nao_altera_cadastro(loja, cardapio, operador):
    api = cliente_api(operador)
    assert api.get("/api/produtos/").status_code == 200
    assert api.post("/api/produtos/", {"nome": "Hack"}, format="json").status_code == 403


def test_empresa_bloqueada_perde_acesso(loja, gerente):
    loja.empresa.ativa = False
    loja.empresa.save()
    assert cliente_api(gerente).get("/api/eu/").status_code == 403


def test_fluxo_balcao_caixa_e_relatorios(loja, cardapio, operador, gerente):
    api = cliente_api(operador)
    assert api.post("/api/turnos/abrir/", {"valor_abertura_centavos": 5000}, format="json").status_code == 201
    r = api.post("/api/pedidos/", {
        "canal": "BALCAO", "tipo_atendimento": "RETIRADA", "nome_cliente": "João",
        "itens": [{"produto_id": str(cardapio["lata"].id), "quantidade": 2}],
    }, format="json")
    assert r.status_code == 201, r.json()
    pedido = r.json()
    assert pedido["total_centavos"] == 1400
    r = api.post(f"/api/pedidos/{pedido['id']}/pagamentos/", {"forma": "DINHEIRO", "valor_centavos": 1400,
                                                              "valor_recebido_centavos": 2000}, format="json")
    assert r.status_code == 201 and r.json()["troco_centavos"] == 600
    for st in ("PRONTO", "CONCLUIDO"):
        assert api.post(f"/api/pedidos/{pedido['id']}/status/", {"status": st}, format="json").status_code == 200

    atual = api.get("/api/turnos/atual/").json()
    assert "esperado" not in atual["resumo"]  # operador: conferência cega
    r = api.post(f"/api/turnos/{atual['id']}/fechar/", {"informado": {"DINHEIRO": 6400}}, format="json")
    assert r.status_code == 200 and r.json()["situacao"] == "OK"

    g = cliente_api(gerente)
    vendas = g.get("/api/relatorios/vendas/").json()
    assert vendas["faturamento_centavos"] == 1400 and vendas["pedidos"] == 1
    assert g.get("/api/relatorios/curva-abc/").json()["itens"][0]["classe"] == "A"
    assert g.get("/api/relatorios/fechamentos/").json()["por_operador"][0]["diferenca_centavos"] == 0
    assert g.get("/api/relatorios/fluxo-caixa/").status_code == 200
    assert api.get("/api/relatorios/vendas/").status_code == 403  # operador não vê relatórios


def test_cardapio_publico_pedido_e_acompanhamento(loja, cardapio):
    anon = APIClient()
    menu = anon.get(f"/api/publico/lojas/{loja.slug}/").json()
    nomes = [p["nome"] for c in menu["categorias"] for p in c["produtos"]]
    assert "X-Burger" in nomes and "Pão" not in nomes  # insumo não aparece
    x = next(p for c in menu["categorias"] for p in c["produtos"] if p["nome"] == "X-Burger")
    ponto = next(g for g in x["grupos"] if g["min"] == 1)
    r = anon.post(f"/api/publico/lojas/{loja.slug}/pedidos/", {
        "tipo_atendimento": "ENTREGA", "nome_cliente": "Ana", "telefone_cliente": "11987654321",
        "forma_pagamento_prevista": "PIX", "desconto_centavos": 99999,  # ignorado no público
        "endereco": {"logradouro": "Rua A", "numero": "1", "bairro": "Centro"},
        "itens": [{"produto_id": x["id"], "adicionais": [{"adicional_id": ponto["opcoes"][0]["id"]}]}],
    }, format="json")
    assert r.status_code == 201, r.json()
    assert r.json()["total_centavos"] == 3000 + 500 and r.json()["status"] == "PENDENTE"
    status = anon.get(f"/api/publico/pedidos/{r.json()['token']}/").json()
    assert status["etapa"] == "Recebido"


def test_sync_push_idempotente_e_pull(loja, cardapio, operador):
    api = cliente_api(operador)
    turno_id, pedido_id, op1, op2 = (str(uuid.uuid4()) for _ in range(4))
    lote = {"operacoes": [
        {"id": op1, "operacao": "caixa.abrir", "payload": {"id": turno_id, "valor_abertura_centavos": 1000}},
        {"id": op2, "operacao": "pedido.criar", "payload": {
            "id": pedido_id, "canal": "BALCAO", "tipo_atendimento": "RETIRADA", "codigo_local": "C1-0001",
            "itens": [{"produto_id": str(cardapio["lata"].id)}]}},
        {"id": str(uuid.uuid4()), "operacao": "pedido.criar", "payload": {"canal": "BALCAO",
            "tipo_atendimento": "RETIRADA", "itens": [{"produto_id": str(uuid.uuid4())}]}},
    ]}
    r1 = api.post("/api/sync/push/", lote, format="json").json()["resultados"]
    assert [x["ok"] for x in r1] == [True, True, False]
    assert "indisponível" in r1[2]["erro"]
    r2 = api.post("/api/sync/push/", lote, format="json").json()["resultados"]
    assert all(x.get("repetida") for x in r2)
    from apps.pedidos.models import Pedido

    assert Pedido.objects.filter(pk=pedido_id).count() == 1

    pull = api.get("/api/sync/pull/?entidades=produtos,mesas").json()["entidades"]
    assert len(pull["produtos"]["registros"]) >= 5 and pull["produtos"]["cursor"]
    vazio = api.get(f"/api/sync/pull/?entidades=produtos&desde={pull['produtos']['cursor']}").json()
    assert vazio["entidades"]["produtos"]["registros"] == []


def test_cozinha_avanca_itens_e_pedido(loja, cardapio, operador):
    api = cliente_api(operador)
    r = api.post("/api/pedidos/", {"canal": "BALCAO", "tipo_atendimento": "CONSUMO_LOCAL", "mesa": "5",
                                   "itens": [{"produto_id": str(cardapio["x"].id),
                                              "adicionais": [{"adicional_id": str(cardapio["ao_ponto"].id)}]}]},
                 format="json")
    fila = api.get(f"/api/cozinha/?setor={cardapio['chapa'].id}").json()
    assert len(fila) == 1 and fila[0]["pedido"]["mesa"] == "5"
    item = fila[0]["id"]
    api.post(f"/api/cozinha/{item}/avancar/")
    api.post(f"/api/cozinha/{item}/avancar/")
    assert api.get(f"/api/pedidos/{r.json()['id']}/").json()["status"] == "PRONTO"
    assert api.get("/api/cozinha/").json() == []
