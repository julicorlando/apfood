"""Previsão de chegada, pedir de novo, combos, cardápio por horário, tela da cozinha, várias entregas
por viagem, foto na entrega, carrinho abandonado, resumo do dia, lista de compras, importar cardápio
e tempo por etapa."""

import io
from datetime import datetime, timedelta
from decimal import Decimal

from apfood_core.enums import CanalVenda, StatusPedido, TipoAtendimento
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from apps.integracoes.models import Integracao, Tarefa
from apps.pedidos import services as ps
from apps.pedidos.models import Pedido

from .test_app_entregador import _cache_limpo, app, entrar, entregador, pedido_entrega  # noqa: F401


def painel(u):
    c = APIClient()
    c.force_authenticate(u)
    return c


def png(nome="foto.png"):
    b = io.BytesIO()
    Image.new("RGB", (40, 30), (200, 100, 50)).save(b, "PNG")
    b.seek(0)
    b.name = nome
    return b


# ----------------------------------------------------------------------------- previsão e pedir de novo
def test_previsao_de_chegada_e_pedir_de_novo(loja, cardapio, operador):
    p = pedido_entrega(loja, cardapio, operador, StatusPedido.RECEBIDO)
    v = app().get(f"/api/publico/pedidos/{p.token_rastreio}/").data["previsao"]
    assert v["tipo"] == "chegada" and v["base"] == "estimativa" and 45 <= v["minutos"] <= 51  # 30 de preparo + ~20 de trajeto

    e = entregador(loja, "João", "11988887777", -23.55, -46.63)
    Pedido.objects.filter(pk=p.pk).update(entrega_latitude=Decimal("-23.56"), entrega_longitude=Decimal("-46.64"))
    ps.transicionar(Pedido.objects.get(pk=p.pk), StatusPedido.PRONTO, operador)
    ps.transicionar(Pedido.objects.get(pk=p.pk), StatusPedido.SAIU_PARA_ENTREGA, operador, entregador_id=e.id)
    type(e).objects.filter(pk=e.pk).update(localizacao_em=timezone.now())
    v = app().get(f"/api/publico/pedidos/{p.token_rastreio}/").data["previsao"]
    assert v["base"] == "entregador" and 3 <= v["minutos"] <= 15

    ps.transicionar(Pedido.objects.get(pk=p.pk), StatusPedido.CONCLUIDO, operador)
    d = app().get(f"/api/publico/pedidos/{p.token_rastreio}/").data
    assert d["previsao"] is None
    assert d["repetir"] == [{"produto_id": str(cardapio["lata"].id), "quantidade": 2, "variacao_id": None, "sabores": [],
                             "adicionais": [], "observacao": ""}]


# ----------------------------------------------------------------------------- combos
def test_combo_no_cardapio_e_no_estoque(loja, cardapio, gerente, operador):
    from apps.estoque import services as estoque

    api = painel(gerente)
    x, lata = cardapio["x"], cardapio["lata"]
    assert api.post(f"/api/combos/?loja={loja.id}", {"nome": "Só um", "preco_centavos": 100,
                                                     "itens": [{"produto_id": str(lata.id)}]}, format="json").status_code == 400
    r = api.post(f"/api/combos/?loja={loja.id}", {"nome": "Combo X", "preco_centavos": 3300, "itens": [
        {"produto_id": str(x.id), "quantidade": 1}, {"produto_id": str(lata.id), "quantidade": 1}]}, format="json")
    assert r.status_code == 201 and r.data["de_centavos"] == 3700 and r.data["economia_centavos"] == 400
    assert r.data["categoria"] == "Combos"
    combo_id = r.data["id"]
    assert api.get(f"/api/combos/?loja={loja.id}").data[0]["id"] == combo_id

    cat = app().get(f"/api/publico/lojas/{loja.slug}/").data["categorias"]
    combo = next(p for c in cat for p in c["produtos"] if p["id"] == combo_id)
    assert combo["combo"]["itens"] == ["1x X-Burger", "1x Lata"] and combo["combo"]["economia_centavos"] == 400

    p = ps.criar_pedido(loja, ps.PedidoIn(canal=CanalVenda.BALCAO, tipo_atendimento=TipoAtendimento.CONSUMO_LOCAL,
                                          itens=[ps.ItemIn(combo_id, 2)]), operador)
    assert p.total_centavos == 6600
    estoque.baixar_pedido(p)
    for k, antes, menos in (("lata", "10", 2), ("pao", "50", 2), ("carne", "50", 2)):
        cardapio[k].refresh_from_db()
        assert cardapio[k].estoque_atual == Decimal(antes) - menos

    r = api.put(f"/api/combos/{combo_id}/?loja={loja.id}", {"nome": "Combo X duplo", "preco_centavos": 3600, "itens": [
        {"produto_id": str(x.id), "quantidade": 2}, {"produto_id": str(lata.id), "quantidade": 1}]}, format="json")
    assert r.status_code == 200 and r.data["economia_centavos"] == 3100
    assert api.delete(f"/api/combos/{combo_id}/?loja={loja.id}").status_code == 204
    assert api.get(f"/api/combos/?loja={loja.id}").data == []


# ----------------------------------------------------------------------------- cardápio por horário
def test_cardapio_por_horario(loja, cardapio):
    from apps.cardapio.models import Categoria

    bebidas = Categoria.objects.get(loja=loja, nome="Bebidas")
    agora = timezone.localtime()
    depois = agora + timedelta(hours=2)
    bebidas.disponibilidade = [{"dia_semana": depois.weekday(), "inicio": depois.strftime("%H:00"),
                                "fim": (depois + timedelta(hours=1)).strftime("%H:00")}]
    bebidas.save()
    if depois.strftime("%H:00") < (depois + timedelta(hours=1)).strftime("%H:00"):  # não vale perto da meia-noite
        assert not bebidas.disponivel_em(timezone.now())
        cat = next(c for c in app().get(f"/api/publico/lojas/{loja.slug}/").data["categorias"] if c["nome"] == "Bebidas")
        assert cat["disponivel"] is False and cat["horario"].startswith("Disponível das ")
        r = app().post(f"/api/publico/lojas/{loja.slug}/pedidos/", {
            "tipo_atendimento": "RETIRADA", "nome_cliente": "Ana", "telefone_cliente": "11987654321",
            "forma_pagamento_prevista": "PIX", "itens": [{"produto_id": str(cardapio["lata"].id)}]}, format="json")
        assert r.status_code == 400 and "Lata" in str(r.data)

    # passa da meia-noite: domingo 22:00 às 02:00 vale na segunda à 01:00
    bebidas.disponibilidade = [{"dia_semana": 6, "inicio": "22:00", "fim": "02:00"}]
    seg_1h = timezone.make_aware(datetime(2026, 11, 16, 1, 0))
    seg_3h = timezone.make_aware(datetime(2026, 11, 16, 3, 0))
    dom_23h = timezone.make_aware(datetime(2026, 11, 15, 23, 0))
    assert bebidas.disponivel_em(seg_1h) and bebidas.disponivel_em(dom_23h) and not bebidas.disponivel_em(seg_3h)
    bebidas.disponibilidade = []
    assert bebidas.disponivel_em(seg_3h)


# ----------------------------------------------------------------------------- tela da cozinha
def test_cozinha_marca_o_pedido_inteiro_pronto(loja, cardapio, operador):
    p = pedido_entrega(loja, cardapio, operador, StatusPedido.RECEBIDO)
    api = painel(operador)
    fila = api.get(f"/api/cozinha/?loja={loja.id}").data
    assert fila and fila[0]["pedido"]["numero"] == p.numero and "observacao" in fila[0]["pedido"]
    assert api.post(f"/api/cozinha/pedido/{p.id}/pronto/?loja={loja.id}", {}, format="json").status_code == 200
    p.refresh_from_db()
    assert p.status == StatusPedido.PRONTO and not p.itens.exclude(status_producao="PRONTO").exists()
    assert api.get(f"/api/cozinha/?loja={loja.id}").data == []


# ----------------------------------------------------------------------------- várias entregas por viagem
def test_varias_entregas_na_mesma_viagem(loja, cardapio, operador, gerente):
    e = entregador(loja, "João", "11988887777", -23.5500, -46.6300)
    tok = entrar("11988887777", "2580")
    longe = pedido_entrega(loja, cardapio, operador)
    perto = pedido_entrega(loja, cardapio, operador)
    Pedido.objects.filter(pk=longe.pk).update(entrega_latitude=Decimal("-23.60"), entrega_longitude=Decimal("-46.70"))
    Pedido.objects.filter(pk=perto.pk).update(entrega_latitude=Decimal("-23.551"), entrega_longitude=Decimal("-46.631"))
    api = painel(gerente)
    sug = api.get(f"/api/pedidos/{longe.id}/chamada/?loja={loja.id}").data["juntar"]
    assert [s["numero"] for s in sug] == [perto.numero] and sug[0]["mesmo_bairro"] is True
    r = api.post(f"/api/pedidos/{longe.id}/chamada/?loja={loja.id}", {"juntar": [str(perto.id)]}, format="json")
    assert r.status_code == 200 and r.data["chamada"]["juntos"] == [perto.numero]

    o = app(tok).get("/api/entregador/estado/").data["oferta"]
    assert o["entregas"] == 2 and sorted(o["numeros"]) == sorted([longe.numero, perto.numero]) and o["ganho_centavos"] == 1400
    assert app(tok).post(f"/api/entregador/ofertas/{o['chamada']}/aceitar/").status_code == 200
    for p in (longe, perto):
        p.refresh_from_db()
        assert p.entregador == e
        assert app(tok).post(f"/api/entregador/entregas/{p.id}/retirar/", {"codigo": p.codigo_retirada}).status_code == 200
    ents = app(tok).get("/api/entregador/estado/").data["entregas"]
    assert [x["numero"] for x in ents] == [perto.numero, longe.numero]  # a mais perto primeiro
    assert [(x["parada"], x["paradas"]) for x in ents] == [(1, 2), (2, 2)]


# ----------------------------------------------------------------------------- foto na entrega
def test_conclui_com_foto_quando_o_cliente_nao_esta(loja, cardapio, operador, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    e = entregador(loja, "João", "11988887777", -23.55, -46.63)
    tok = entrar("11988887777", "2580")
    p = pedido_entrega(loja, cardapio, operador)
    ps.transicionar(p, StatusPedido.SAIU_PARA_ENTREGA, operador, entregador_id=e.id)
    url = f"/api/entregador/entregas/{p.id}/foto/"
    r = app(tok).post(url, {"foto": png()}, format="multipart")
    assert r.status_code == 400 and "pago" in str(r.data)  # dinheiro na entrega: sem cliente não cobra
    app(tok).post(f"/api/entregador/entregas/{p.id}/cobrar/", {"forma": "CARTAO_DEBITO"}, format="json")
    assert app(tok).post(url, {}, format="multipart").status_code == 400
    r = app(tok).post(url, {"foto": png(), "observacao": "na portaria"}, format="multipart")
    assert r.status_code == 200, r.data
    p.refresh_from_db()
    assert p.status == StatusPedido.CONCLUIDO and p.foto_entrega.name.endswith(".jpg")
    assert "portaria" in p.historico.order_by("-criado_em").first().observacao
    assert app().get(f"/api/publico/pedidos/{p.token_rastreio}/").data["foto_entrega"].endswith(".jpg")


# ----------------------------------------------------------------------------- carrinho abandonado
def test_carrinho_abandonado_lembra_uma_vez(loja, cardapio, django_capture_on_commit_callbacks):
    from apps.marketing import carrinho
    from apps.marketing.models import CarrinhoAberto

    corpo = {"telefone": "(11) 98765-4321", "nome": "Ana Lima", "itens": ["2x Lata"], "total_centavos": 1400}
    app().post(f"/api/publico/lojas/{loja.slug}/carrinho/", corpo, format="json")
    assert not CarrinhoAberto.objects.exists()  # desligado na loja
    loja.carrinho_ativo, loja.carrinho_cupom = True, "VOLTA5"
    loja.save()
    assert app().get(f"/api/publico/lojas/{loja.slug}/").data["loja"]["recuperar_carrinho"] is False  # sem WhatsApp
    Integracao.objects.create(loja=loja, tipo="WHATSAPP", provedor="whatsapp", ativo=True, configuracao={"instancia": "x"})
    assert app().get(f"/api/publico/lojas/{loja.slug}/").data["loja"]["recuperar_carrinho"] is True
    with django_capture_on_commit_callbacks(execute=True):
        assert app().post(f"/api/publico/lojas/{loja.slug}/carrinho/", corpo, format="json").status_code == 200
    c = CarrinhoAberto.objects.get()
    assert c.telefone == "11987654321"
    t = Tarefa.objects.get(tipo="carrinho.lembrar")
    assert t.executar_em > timezone.now() + timedelta(minutes=25)

    meio_dia = timezone.make_aware(datetime.combine(timezone.localdate(), datetime.min.time().replace(hour=12)))
    with django_capture_on_commit_callbacks(execute=True):
        carrinho.lembrar(**t.payload, _agora=meio_dia)
        carrinho.lembrar(**t.payload, _agora=meio_dia)  # só uma vez por dia
    msgs = Tarefa.objects.filter(tipo="whatsapp.enviar")
    assert msgs.count() == 1 and "Ana" in msgs[0].payload["mensagem"] and "VOLTA5" in msgs[0].payload["mensagem"]

    # quem finaliza não recebe lembrete
    CarrinhoAberto.objects.all().delete()
    with django_capture_on_commit_callbacks(execute=True):
        app().post(f"/api/publico/lojas/{loja.slug}/carrinho/", corpo, format="json")
    r = app().post(f"/api/publico/lojas/{loja.slug}/pedidos/", {
        "tipo_atendimento": "RETIRADA", "nome_cliente": "Ana", "telefone_cliente": "11987654321",
        "forma_pagamento_prevista": "PIX", "itens": [{"produto_id": str(cardapio["lata"].id)}]}, format="json")
    assert r.status_code == 201
    assert CarrinhoAberto.objects.get().convertido_em is not None


# ----------------------------------------------------------------------------- resumo do dia
def test_resumo_do_dia(loja, cardapio, operador, gerente, django_capture_on_commit_callbacks):
    from apps.lojas import resumo_diario

    p = pedido_entrega(loja, cardapio, operador)
    ps.transicionar(p, StatusPedido.CONCLUIDO, operador)
    r = resumo_diario.calcular(loja)
    assert r["pedidos"] == 1 and r["faturamento_centavos"] == p.total_centavos and r["entregas"] == 1
    assert r["mais_vendidos"] == [{"nome": "Lata", "quantidade": 2}]

    loja.resumo_diario_ativo, loja.resumo_diario_hora, loja.resumo_diario_whatsapp = True, 23, "(81) 99999-0000, 123"
    loja.save()
    Integracao.objects.create(loja=loja, tipo="WHATSAPP", provedor="whatsapp", ativo=True, configuracao={"instancia": "x"})
    as_23 = timezone.make_aware(datetime.combine(timezone.localdate(), datetime.min.time().replace(hour=23)))
    with django_capture_on_commit_callbacks(execute=True):
        assert not resumo_diario.rodar(loja, as_23 - timedelta(hours=1))
        assert resumo_diario.rodar(loja, as_23)
        assert resumo_diario.rodar(loja, as_23)  # de hora em hora: a tarefa do dia é uma só
    assert Tarefa.objects.filter(tipo="resumo.dia").count() == 1
    with django_capture_on_commit_callbacks(execute=True):
        r = painel(gerente).post(f"/api/resumo-diario/?loja={loja.id}")
    assert r.status_code == 200 and r.data["whatsapp"] == ["81999990000"] and "Resumo de hoje" in r.data["texto"]
    assert Tarefa.objects.filter(tipo="whatsapp.enviar", payload__telefone="81999990000").exists()


# ----------------------------------------------------------------------------- lista de compras
def test_lista_de_compras_pelo_estoque_minimo(loja, cardapio, gerente):
    from apps.compras.models import Compra

    api = painel(gerente)
    r = api.get(f"/api/estoque/lista-compras/?loja={loja.id}").data
    itens = {i["nome"]: i for g in r["grupos"] for i in g["itens"]}
    assert itens["Bacon"]["situacao"] == "abaixo" and itens["Bacon"]["sugerido"] == "8"  # 2 x 5 − 2
    assert itens["Lata"]["situacao"] == "quase" and "Pão" not in itens
    g = r["grupos"][0]
    r = api.post(f"/api/estoque/lista-compras/?loja={loja.id}", {"fornecedor_id": g["fornecedor_id"], "itens": [
        {"produto_id": i["produto_id"], "quantidade": i["sugerido"]} for i in g["itens"]]}, format="json")
    assert r.status_code == 201
    c = Compra.objects.get(pk=r.data["id"])
    assert c.status == "RASCUNHO" and c.itens.count() == len(g["itens"])


# ----------------------------------------------------------------------------- importar cardápio
def test_importar_cardapio_por_texto_e_por_ia(loja, gerente, settings, monkeypatch):
    from apps.cardapio.models import Produto

    api = painel(gerente)
    texto = "LANCHES\nX-Tudo ........ R$ 32,90\nPão, carne, ovo e bacon\nX-Salada 25,00\n\nBEBIDAS\nSuco natural 8,00"
    r = api.post(f"/api/cardapio/importar/?loja={loja.id}", {"texto": texto}, format="json")
    assert r.status_code == 200 and r.data["origem"] == "texto"
    cats = r.data["categorias"]
    assert [c["nome"] for c in cats] == ["Lanches", "Bebidas"]
    assert cats[0]["produtos"][0] == {"nome": "X-Tudo", "descricao": "Pão, carne, ovo e bacon", "preco_centavos": 3290}
    assert api.post(f"/api/cardapio/importar/confirmar/?loja={loja.id}", {"categorias": cats}, format="json").data == {
        "categorias": 2, "produtos": 3}
    assert api.post(f"/api/cardapio/importar/confirmar/?loja={loja.id}", {"categorias": cats}, format="json").data["produtos"] == 0
    assert Produto.objects.get(loja=loja, nome="Suco natural").preco_centavos == 800

    r = api.post(f"/api/cardapio/importar/?loja={loja.id}", {"arquivo": png("cardapio.png")}, format="multipart")
    assert r.status_code == 400 and "foto" in str(r.data)  # sem a chave da IA

    settings.APFOOD = {**settings.APFOOD, "IA_CHAVE": "teste"}

    class Resposta:
        status_code = 200

        @staticmethod
        def json():
            return {"content": [{"type": "text", "text": 'Aqui está: {"categorias":[{"nome":"Pizzas","produtos":['
                                 '{"nome":"Calabresa (G)","descricao":"","preco":"59,90"}]}]}'}]}

    chamadas = []
    monkeypatch.setattr("httpx.post", lambda url, **kw: chamadas.append(kw) or Resposta())
    r = api.post(f"/api/cardapio/importar/?loja={loja.id}", {"arquivo": png("cardapio.png")}, format="multipart")
    assert r.status_code == 200 and r.data["origem"] == "ia"
    assert r.data["categorias"] == [{"nome": "Pizzas", "produtos": [{"nome": "Calabresa (G)", "descricao": "", "preco_centavos": 5990}]}]
    assert chamadas[0]["json"]["messages"][0]["content"][0]["type"] == "image"


# ----------------------------------------------------------------------------- tempo por etapa
def test_tempo_por_etapa(loja, cardapio, operador, gerente):
    p = pedido_entrega(loja, cardapio, operador)
    ps.transicionar(p, StatusPedido.CONCLUIDO, operador)
    t0 = timezone.now() - timedelta(minutes=60)
    Pedido.objects.filter(pk=p.pk).update(criado_em=t0, aceito_em=t0 + timedelta(minutes=2), pronto_em=t0 + timedelta(minutes=32),
                                          saiu_entrega_em=t0 + timedelta(minutes=40), concluido_em=t0 + timedelta(minutes=55))
    hoje = timezone.localdate()
    r = painel(gerente).get(f"/api/relatorios/tempos/?loja={loja.id}&inicio={hoje - timedelta(days=1)}&fim={hoje}").data
    etapas = {e["etapa"]: e["media_min"] for e in r["etapas"]}
    assert etapas["aceite"] == 2 and etapas["preparo"] == 30 and etapas["espera_entregador"] == 8 and etapas["entrega"] == 15
    assert r["gargalo"] == "preparo" and r["total"]["media_min"] == 55 and r["mais_lentos"][0]["numero"] == p.numero
