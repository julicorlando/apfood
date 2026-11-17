import json
from decimal import Decimal

import pytest
from apfood_core.enums import TipoCupom
from django.test import Client
from django.utils import timezone
from rest_framework.test import APIClient

from apps.marketing.models import Cupom


def _dados(html: str) -> dict:
    ini = html.index('id="dados-cardapio"')
    ini = html.index(">", ini) + 1
    return json.loads(html[ini:html.index("</script>", ini)])


def test_pagina_do_cardapio_traz_dados_e_assets(loja, cardapio):
    r = Client().get(f"/{loja.slug}/")
    assert r.status_code == 200
    html = r.content.decode()
    assert "Burger Centro" in html and "vitrine/cardapio.js" in html and "vitrine/carrinho.js" in html
    dados = _dados(html)
    nomes = [p["nome"] for c in dados["categorias"] for p in c["produtos"]]
    assert "X-Burger" in nomes and "Pão" not in nomes  # insumo nunca aparece
    assert dados["loja"]["aberta"] and dados["loja"]["entrega"] and not dados["loja"]["pix_online"]
    pizza = next(c for c in dados["categorias"] if c["nome"] == "Pizzas")
    assert pizza["max_sabores"] == 2 and len(pizza["produtos"][0]["variacoes"]) == 2


def test_loja_bloqueada_ou_inexistente(loja):
    loja.empresa.ativa = False
    loja.empresa.save()
    r = Client().get(f"/{loja.slug}/")
    assert r.status_code == 404 and "indisponível" in r.content.decode()
    assert Client().get("/nao-existe/").status_code == 404


def test_fora_do_horario_mostra_fechada_e_recusa_pedido(loja, cardapio):
    ontem = (timezone.localtime().weekday() - 1) % 7
    loja.horarios = [{"dia_semana": ontem, "abre": "10:00", "fecha": "11:00"}]
    loja.save()
    dados = _dados(Client().get(f"/{loja.slug}/").content.decode())
    assert not dados["loja"]["aberta"] and dados["loja"]["proxima_abertura"]
    r = APIClient().post(f"/api/publico/lojas/{loja.slug}/pedidos/", {
        "tipo_atendimento": "RETIRADA", "nome_cliente": "Ana", "telefone_cliente": "11987654321",
        "forma_pagamento_prevista": "PIX", "itens": [{"produto_id": str(cardapio["lata"].id)}]}, format="json")
    assert r.status_code == 400 and "horário" in r.json()["detail"]


def test_cupom_publico(loja, cardapio):
    Cupom.objects.create(loja=loja, codigo="FRETE", tipo=TipoCupom.FRETE_GRATIS, valor=Decimal("0"))
    Cupom.objects.create(loja=loja, codigo="DEZ", tipo=TipoCupom.PERCENTUAL, valor=Decimal("10"),
                         pedido_minimo_centavos=5000)
    api = APIClient()
    url = f"/api/publico/lojas/{loja.slug}/cupom/"
    r = api.post(url, {"codigo": "frete", "subtotal_centavos": 3000, "taxa_entrega_centavos": 800}, format="json")
    assert r.status_code == 200 and r.json()["desconto_centavos"] == 800
    r = api.post(url, {"codigo": "DEZ", "subtotal_centavos": 3000}, format="json")
    assert r.status_code == 400 and "mínimo" in str(r.json())
    assert api.post(url, {"codigo": "NAOEXISTE"}, format="json").status_code == 400


def test_fluxo_completo_pedido_online_e_acompanhamento(loja, cardapio):
    api = APIClient()
    menu = api.get(f"/api/publico/lojas/{loja.slug}/").json()
    pizza = next(c for c in menu["categorias"] if c["nome"] == "Pizzas")
    cal, por = pizza["produtos"][0], pizza["produtos"][1]
    grande = next(v for v in cal["variacoes"] if v["nome"] == "Grande")
    taxa = api.post(f"/api/publico/lojas/{loja.slug}/taxa-entrega/", {"bairro": "Centro"}, format="json").json()
    assert taxa["taxa_centavos"] == 500
    r = api.post(f"/api/publico/lojas/{loja.slug}/pedidos/", {
        "tipo_atendimento": "ENTREGA", "nome_cliente": "Bia", "telefone_cliente": "(11) 91234-5678",
        "forma_pagamento_prevista": "DINHEIRO", "troco_para_centavos": 10000,
        "endereco": {"logradouro": "Rua A", "numero": "10", "bairro": "Centro"},
        "itens": [{"produto_id": cal["id"], "variacao_id": grande["id"], "sabores": [cal["id"], por["id"]],
                   "observacao": "bem assada"}],
    }, format="json")
    assert r.status_code == 201, r.json()
    corpo = r.json()
    assert corpo["total_centavos"] == 6000 + 500 and corpo["status"] == "PENDENTE"
    pagina = Client().get(f"/pedido/{corpo['token']}/")
    assert pagina.status_code == 200 and "acompanhar.js" in pagina.content.decode()
    st = api.get(f"/api/publico/pedidos/{corpo['token']}/").json()
    assert st["etapa"] == "Recebido" and st["forma_prevista"] == "DINHEIRO" and st["troco_para_centavos"] == 10000
    assert st["loja_slug"] == loja.slug and "Rua A" in st["endereco"]
    assert "1/2" in st["itens"][0]["nome"] and st["itens"][0]["observacao"] == "bem assada"
    assert Client().get("/pedido/token-invalido/").status_code == 404


@pytest.mark.django_db
def test_pagina_inicial_e_o_explorador_e_empresas_tem_o_login(client):
    html = client.get("/").content.decode()
    assert "vitrine/app.js" in html and 'href="/empresas/"' in html
    resposta = client.get("/empresas/")
    assert resposta.status_code == 200
    html = resposta.content.decode()
    assert 'href="/painel/"' in html
    assert "releases/latest" in html


@pytest.mark.django_db
def test_admin_tem_nome_apfood(client):
    resposta = client.get("/admin/login/")
    assert "ApFood" in resposta.content.decode()


def test_app_cliente_lista_lojas_da_regiao(loja):
    from apps.lojas.models import Empresa, Loja

    loja.cidade = "São Paulo"
    loja.save()
    longe = Empresa.objects.create(nome="Longe")
    Loja.objects.create(empresa=longe, nome="Rio Burger", slug="rio-burger", cidade="Rio de Janeiro",
                        latitude=Decimal("-22.90"), longitude=Decimal("-43.20"))
    sem_coord = Empresa.objects.create(nome="Vizinha")
    Loja.objects.create(empresa=sem_coord, nome="Pastel da Vila", slug="pastel-vila", cidade="são paulo")
    oculta = Empresa.objects.create(nome="Oculta")
    Loja.objects.create(empresa=oculta, nome="Escondida", slug="escondida", cidade="São Paulo",
                        latitude=Decimal("-23.55"), longitude=Decimal("-46.63"), aparecer_no_app=False)
    bloqueada = Empresa.objects.create(nome="Bloq", ativa=False)
    Loja.objects.create(empresa=bloqueada, nome="Bloqueada", slug="bloqueada", cidade="São Paulo",
                        latitude=Decimal("-23.55"), longitude=Decimal("-46.63"))

    api = APIClient()
    d = api.get("/api/publico/lojas/", {"lat": "-23.56", "lng": "-46.64"}).json()
    nomes = [x["nome"] for x in d["lojas"]]
    assert nomes[0] == "Burger Centro" and d["lojas"][0]["distancia_km"] < 5
    assert "Pastel da Vila" in nomes  # sem coordenadas, mas da mesma cidade
    assert "Rio Burger" not in nomes and "Escondida" not in nomes and "Bloqueada" not in nomes

    d = api.get("/api/publico/lojas/", {"cidade": "Rio de Janeiro"}).json()
    assert [x["nome"] for x in d["lojas"]] == ["Rio Burger"]
    assert "Rio de Janeiro" in d["cidades"] and "São Paulo" in d["cidades"]
    assert {x["slug"] for x in api.get("/api/publico/lojas/", {"busca": "pastel"}).json()["lojas"]} == {"pastel-vila"}


def test_paginas_do_app(loja):
    c = Client()
    r = c.get("/app/")
    assert r.status_code == 200 and "vitrine/app.js" in r.content.decode()
    assert c.get("/app/manifest.webmanifest").json()["start_url"] == "/app/"
    r = c.get("/app/baixar/cliente/")
    assert r.status_code == 302 and r["Location"].endswith("/ApFood-Cliente.apk")
    assert c.get("/app/baixar/outro/").status_code == 404
    assert "ApFood-Empresa" not in c.get("/empresas/").content.decode()  # só os links /app/baixar/
    assert "/app/baixar/empresa/" in c.get("/empresas/").content.decode()


def test_pagina_do_app_entregador(client):
    r = client.get("/entregador/")
    assert r.status_code == 200 and "vitrine/entregador.js" in r.content.decode()
    assert client.get("/entregador/manifest.webmanifest").json()["start_url"] == "/entregador/"
    assert client.get("/app/baixar/entregador/")["Location"].endswith("/ApFood-Entregador.apk")


def test_cardapio_traz_bairros_cadastrados(loja, cardapio):
    from apps.clientes.models import ZonaEntrega

    ZonaEntrega.objects.create(loja=loja, tipo="BAIRRO", nome="Boa Viagem", taxa_centavos=500)
    ZonaEntrega.objects.create(loja=loja, tipo="BAIRRO", nome="Pina", taxa_centavos=600)
    ZonaEntrega.objects.create(loja=loja, tipo="BAIRRO", nome="Fechado", taxa_centavos=600, ativa=False)
    dados = _dados(Client().get(f"/{loja.slug}/").content.decode())
    assert {"Boa Viagem", "Pina"} <= set(dados["loja"]["bairros"]) and "Fechado" not in dados["loja"]["bairros"]
