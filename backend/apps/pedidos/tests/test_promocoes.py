"""Promoções programadas: o servidor aplica no preço; balcão ganha número automático."""

from apfood_core.enums import CanalVenda, TipoAtendimento
from django.utils import timezone
from rest_framework.test import APIClient

from apps.marketing.models import Promocao
from apps.pedidos import services as ps


def api(u):
    c = APIClient()
    c.force_authenticate(u)
    return c


def hoje():
    return timezone.localtime().weekday()


def pedido(loja, cardapio, usuario, canal=CanalVenda.BALCAO, qtd=2, **kw):
    return ps.criar_pedido(loja, ps.PedidoIn(canal, TipoAtendimento.RETIRADA,
                                             [ps.ItemIn(str(cardapio["lata"].id), qtd)], **kw), usuario)


def test_promocao_do_dia_entra_no_preco(loja, cardapio, operador):
    Promocao.objects.create(loja=loja, nome="Bebida em dobro", tipo="PERCENTUAL", valor=50,
                            produtos=[str(cardapio["lata"].id)], dias=[hoje()])
    p = pedido(loja, cardapio, operador)
    item = p.itens.get()
    assert item.preco_unitario_centavos == 350 and item.desconto_promocao_centavos == 350
    assert item.promocao == "Bebida em dobro" and p.total_centavos == 700


def test_promocao_fora_do_dia_canal_ou_inativa_nao_vale(loja, cardapio, operador):
    lata = str(cardapio["lata"].id)
    Promocao.objects.create(loja=loja, nome="Amanhã", tipo="VALOR", valor=100, produtos=[lata], dias=[(hoje() + 1) % 7])
    Promocao.objects.create(loja=loja, nome="Só online", tipo="VALOR", valor=100, produtos=[lata], canais=["ONLINE"])
    Promocao.objects.create(loja=loja, nome="Desligada", tipo="VALOR", valor=100, produtos=[lata], ativa=False)
    assert pedido(loja, cardapio, operador, qtd=1).total_centavos == 700


def test_categoria_e_preco_fixo_e_maior_desconto(loja, cardapio, operador):
    bebidas = cardapio["lata"].categoria_id
    Promocao.objects.create(loja=loja, nome="Categoria", tipo="PERCENTUAL", valor=10, categorias=[str(bebidas)])
    Promocao.objects.create(loja=loja, nome="Fixo", tipo="PRECO_FIXO", valor=500, produtos=[str(cardapio["lata"].id)])
    item = pedido(loja, cardapio, operador, qtd=1).itens.get()
    assert item.preco_unitario_centavos == 500 and item.promocao == "Fixo"


def test_balcao_sem_senha_ganha_numero_do_pedido(loja, cardapio, operador):
    p = pedido(loja, cardapio, operador)
    assert p.senha == f"{p.numero:04d}" and len(p.senha) == 4
    assert pedido(loja, cardapio, operador, senha="A7").senha == "A7"
    d = ps.criar_pedido(loja, ps.PedidoIn(CanalVenda.DELIVERY, TipoAtendimento.ENTREGA,
                                          [ps.ItemIn(str(cardapio["lata"].id), 1)], nome_cliente="Ana",
                                          telefone_cliente="11999990000", taxa_entrega_centavos=0,
                                          endereco={"logradouro": "Rua A", "numero": "1", "bairro": "Centro", "cidade": "SP"}),
                        operador)
    assert d.senha == ""


def test_api_cadastra_valida_e_mostra_promocoes(loja, cardapio, gerente, operador):
    url = f"/api/promocoes/?loja={loja.id}"
    r = api(gerente).post(url, {"nome": "X", "tipo": "PERCENTUAL", "valor": 150}, format="json")
    assert r.status_code == 400 and "valor" in r.data
    r = api(gerente).post(url, {"nome": "X", "tipo": "PERCENTUAL", "valor": 20, "produtos": ["00000000-0000-0000-0000-000000000000"]},
                          format="json")
    assert r.status_code == 400 and "produtos" in r.data
    r = api(gerente).post(url, {"nome": "Terça do burger", "tipo": "PERCENTUAL", "valor": 20, "dias": [hoje()],
                                "produtos": [str(cardapio["x"].id)], "hora_inicio": None}, format="json")
    assert r.status_code == 201, r.data
    assert "20% off" in r.data["resumo"]
    assert api(operador).post(url, {"nome": "Y", "tipo": "VALOR", "valor": 100}, format="json").status_code == 403
    agora = api(operador).get(f"/api/promocoes/agora/?loja={loja.id}").data
    assert agora["BALCAO"][str(cardapio["x"].id)]["nome"] == "Terça do burger"
    assert str(cardapio["lata"].id) not in agora["BALCAO"]
    # vai para o PDV do computador pelo sync
    pull = api(operador).get(f"/api/sync/pull/?loja={loja.id}&entidades=promocoes").data
    assert [x["nome"] for x in pull["entidades"]["promocoes"]["registros"]] == ["Terça do burger"]


def test_cardapio_publico_mostra_promocao(client, loja, cardapio):
    Promocao.objects.create(loja=loja, nome="Lata 5", tipo="PRECO_FIXO", valor=500, produtos=[str(cardapio["lata"].id)])
    Promocao.objects.create(loja=loja, nome="Só no balcão", tipo="VALOR", valor=100, canais=["BALCAO"])
    d = client.get(f"/api/publico/lojas/{loja.slug}/").json()
    lata = next(p for c in d["categorias"] for p in c["produtos"] if p["id"] == str(cardapio["lata"].id))
    assert lata["promocao"]["nome"] == "Lata 5"
    assert [p["nome"] for p in d["promocoes"]] == ["Lata 5"]
