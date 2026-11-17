"""Loja de demonstração: cardápio completo, estoque com custos, salão, entrega,
marketing e um mês de pedidos (para relatórios, CMV e painel terem números).

Roda pela fila de tarefas ("plataforma.demonstracao"), disparada pelo MASTER em
Plataforma → Empresas → Demonstração. Não apaga nada: só cria o que falta
(pelo nome), então pode rodar de novo sem duplicar.
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, time, timedelta
from decimal import Decimal

from apfood_core.enums import (
    CanalVenda, FormaPagamento, StatusPedido, TipoAtendimento, TipoProduto, TipoZonaEntrega, UnidadeMedida,
)
from django.db import transaction
from django.utils import timezone

from apps.integracoes.tarefas import executor

log = logging.getLogger(__name__)
D = Decimal

INSUMOS = [  # nome, unidade, custo (centavos por unidade), estoque, mínimo
    ("Pão brioche", UnidadeMedida.UN, 120, 400, 60),
    ("Blend bovino 150 g", UnidadeMedida.UN, 520, 300, 50),
    ("Queijo cheddar (fatia)", UnidadeMedida.UN, 90, 500, 80),
    ("Bacon", UnidadeMedida.KG, 4200, 8, 2),
    ("Alface/tomate (porção)", UnidadeMedida.UN, 40, 300, 50),
    ("Molho da casa", UnidadeMedida.KG, 1800, 6, 1),
    ("Cebola caramelizada", UnidadeMedida.KG, 1500, 4, 1),
    ("Ovo", UnidadeMedida.UN, 70, 120, 24),
    ("Peito de frango empanado", UnidadeMedida.UN, 380, 120, 20),
    ("Batata congelada", UnidadeMedida.KG, 1400, 40, 8),
    ("Embalagem delivery", UnidadeMedida.UN, 110, 600, 100),
]

# categoria, nome, descrição, preço, ficha [(insumo, qtd)], variações [(nome, preço, fator)], grupos
CARDAPIO = [
    ("Hambúrgueres", "Smash Clássico", "Pão brioche, blend 150 g, cheddar e molho da casa.", 2490,
     [("Pão brioche", 1), ("Blend bovino 150 g", 1), ("Queijo cheddar (fatia)", 1), ("Molho da casa", "0.02")],
     [], ["Ponto da carne", "Turbine seu lanche"]),
    ("Hambúrgueres", "Bacon Lovers", "Blend 150 g, cheddar duplo, bacon crocante e cebola caramelizada.", 3290,
     [("Pão brioche", 1), ("Blend bovino 150 g", 1), ("Queijo cheddar (fatia)", 2), ("Bacon", "0.04"),
      ("Cebola caramelizada", "0.03")], [], ["Ponto da carne", "Turbine seu lanche"]),
    ("Hambúrgueres", "Duplo Cheddar", "Dois blends de 150 g, cheddar duplo e molho da casa.", 3690,
     [("Pão brioche", 1), ("Blend bovino 150 g", 2), ("Queijo cheddar (fatia)", 2), ("Molho da casa", "0.03")],
     [], ["Ponto da carne", "Turbine seu lanche"]),
    ("Hambúrgueres", "Salada Fit", "Blend 150 g, alface, tomate, queijo e molho leve.", 2790,
     [("Pão brioche", 1), ("Blend bovino 150 g", 1), ("Queijo cheddar (fatia)", 1), ("Alface/tomate (porção)", 1)],
     [], ["Ponto da carne"]),
    ("Hambúrgueres", "Chicken Crispy", "Frango empanado crocante, alface, tomate e maionese temperada.", 2690,
     [("Pão brioche", 1), ("Peito de frango empanado", 1), ("Alface/tomate (porção)", 1)], [],
     ["Turbine seu lanche"]),
    ("Combos", "Combo Smash", "Smash Clássico + batata média + refrigerante lata.", 3990,
     [("Pão brioche", 1), ("Blend bovino 150 g", 1), ("Queijo cheddar (fatia)", 1), ("Batata congelada", "0.25"),
      ("Embalagem delivery", 1)], [], ["Ponto da carne"]),
    ("Combos", "Combo Bacon", "Bacon Lovers + batata média + refrigerante lata.", 4690,
     [("Pão brioche", 1), ("Blend bovino 150 g", 1), ("Queijo cheddar (fatia)", 2), ("Bacon", "0.04"),
      ("Batata congelada", "0.25"), ("Embalagem delivery", 1)], [], ["Ponto da carne"]),
    ("Porções", "Batata frita", "Crocante, com sal e orégano.", 1490, [("Batata congelada", "0.25")],
     [("Pequena", 1490, "0.6"), ("Média", 1990, "1"), ("Grande", 2690, "1.6")], []),
    ("Porções", "Batata cheddar e bacon", "Batata média coberta com cheddar cremoso e bacon.", 2690,
     [("Batata congelada", "0.25"), ("Bacon", "0.03"), ("Queijo cheddar (fatia)", 2)], [], []),
    ("Porções", "Onion rings", "Anéis de cebola empanados, 12 unidades.", 1890, [], [], []),
    ("Bebidas", "Refrigerante lata", "Coca-Cola, Guaraná ou Fanta, 350 ml.", 690, [], [], []),
    ("Bebidas", "Suco natural", "Laranja, maracujá ou acerola, 400 ml.", 990, [], [], []),
    ("Bebidas", "Água mineral", "500 ml, com ou sem gás.", 450, [], [], []),
    ("Sobremesas", "Brownie com sorvete", "Brownie quente com bola de sorvete de creme.", 1690, [], [], []),
    ("Sobremesas", "Milkshake", "Chocolate, morango ou Ovomaltine, 400 ml.", 1890, [], [], []),
]
CUSTO_REVENDA = {"Refrigerante lata": 310, "Suco natural": 280, "Água mineral": 140, "Onion rings": 620,
                 "Brownie com sorvete": 560, "Milkshake": 640}

CLIENTES = [
    ("Ana Beatriz Lima", "81991110001", "Boa Viagem", "Rua dos Navegantes", "1200"),
    ("Bruno Carvalho", "81991110002", "Pina", "Rua Herculano Bandeira", "350"),
    ("Camila Rocha", "81991110003", "Boa Viagem", "Av. Conselheiro Aguiar", "2450"),
    ("Diego Santos", "81991110004", "Imbiribeira", "Av. Mascarenhas de Morais", "4100"),
    ("Eduarda Melo", "81991110005", "Setúbal", "Rua João Cardoso Aires", "780"),
    ("Felipe Araújo", "81991110006", "Boa Viagem", "Rua Ernesto de Paula Santos", "960"),
    ("Gabriela Nunes", "81991110007", "Pina", "Rua Bruno Veloso", "120"),
    ("Henrique Alves", "81991110008", "Imbiribeira", "Rua Jean Emile Favre", "55"),
    ("Isabela Costa", "81991110009", "Setúbal", "Rua Padre Carapuceiro", "610"),
    ("João Pedro Silva", "81991110010", "Boa Viagem", "Rua Barão de Souza Leão", "1500"),
]
ZONAS = [("Boa Viagem", 500, 35), ("Pina", 600, 40), ("Setúbal", 600, 40), ("Imbiribeira", 700, 45)]
FORMAS = [FormaPagamento.PIX] * 5 + [FormaPagamento.CARTAO_CREDITO] * 3 + [FormaPagamento.CARTAO_DEBITO] * 2 \
    + [FormaPagamento.DINHEIRO]


def _cardapio(loja) -> dict:
    from apps.cardapio.models import (
        Adicional, Categoria, FichaTecnicaItem, GrupoAdicional, Produto, ProdutoGrupoAdicional, ProdutoVariacao,
        SetorProducao,
    )

    chapa, _ = SetorProducao.objects.get_or_create(loja=loja, nome="Chapa", defaults={"ordem": 1})
    bar, _ = SetorProducao.objects.get_or_create(loja=loja, nome="Bar", defaults={"ordem": 2})
    insumos = {}
    for nome, un, custo, est, minimo in INSUMOS:
        p, criado = Produto.objects.get_or_create(
            loja=loja, tipo=TipoProduto.INSUMO, nome=nome,
            defaults={"unidade": un, "custo_centavos": custo, "controla_estoque": True,
                      "estoque_atual": D(est), "estoque_minimo": D(minimo)})
        if not criado and p.custo_centavos is None:
            p.custo_centavos = custo
            p.save(update_fields=["custo_centavos", "atualizado_em"])
        insumos[nome] = p

    ponto, _ = GrupoAdicional.objects.get_or_create(loja=loja, nome="Ponto da carne",
                                                    defaults={"min_selecao": 1, "max_selecao": 1, "ordem": 1})
    for i, n in enumerate(["Mal passado", "Ao ponto", "Bem passado"]):
        Adicional.objects.get_or_create(grupo=ponto, nome=n, defaults={"ordem": i})
    extras, _ = GrupoAdicional.objects.get_or_create(loja=loja, nome="Turbine seu lanche",
                                                     defaults={"min_selecao": 0, "max_selecao": 4, "ordem": 2})
    for i, (n, preco, ins, qtd, mx) in enumerate([
        ("Bacon extra", 500, "Bacon", "0.03", 2), ("Cheddar extra", 350, "Queijo cheddar (fatia)", "1", 2),
        ("Ovo", 300, "Ovo", "1", 1), ("Blend extra 150 g", 900, "Blend bovino 150 g", "1", 1),
        ("Cebola caramelizada", 400, "Cebola caramelizada", "0.03", 1)]):
        Adicional.objects.get_or_create(grupo=extras, nome=n, defaults={
            "preco_centavos": preco, "max_por_item": mx, "ordem": i, "insumo": insumos[ins],
            "quantidade_insumo": D(qtd)})
    grupos = {"Ponto da carne": ponto, "Turbine seu lanche": extras}

    categorias = {}
    for i, nome in enumerate(["Hambúrgueres", "Combos", "Porções", "Bebidas", "Sobremesas"]):
        c, _ = Categoria.objects.get_or_create(
            loja=loja, nome=nome, defaults={"ordem": i, "setor": bar if nome == "Bebidas" else chapa})
        categorias[nome] = c

    produtos = {}
    for ordem, (cat, nome, desc, preco, ficha, variacoes, gs) in enumerate(CARDAPIO):
        p, criado = Produto.objects.get_or_create(
            loja=loja, tipo=TipoProduto.VENDA, nome=nome,
            defaults={"categoria": categorias[cat], "descricao": desc, "preco_centavos": preco, "ordem": ordem,
                      "baixar_insumos": bool(ficha), "custo_centavos": CUSTO_REVENDA.get(nome),
                      "ncm": "21069090" if cat != "Bebidas" else "22021000", "cst_csosn": "102"})
        if criado:
            for ins, qtd in ficha:
                FichaTecnicaItem.objects.create(produto=p, insumo=insumos[ins], quantidade=D(str(qtd)))
            for j, (vn, vp, fator) in enumerate(variacoes):
                ProdutoVariacao.objects.create(produto=p, nome=vn, preco_centavos=vp, fator_insumos=D(fator), ordem=j)
            for j, g in enumerate(gs):
                ProdutoGrupoAdicional.objects.create(produto=p, grupo=grupos[g], ordem=j)
        produtos[nome] = p
    return {"produtos": produtos, "ponto": ponto, "extras": extras}


def _loja(loja):
    from apps.clientes.models import Entregador, ZonaEntrega
    from apps.marketing.models import Cupom
    from apps.salao.models import Mesa

    loja.cidade, loja.uf = loja.cidade or "Recife", loja.uf or "PE"
    if not loja.logradouro:
        loja.logradouro, loja.numero, loja.bairro, loja.cep = "Av. Boa Viagem", "3500", "Boa Viagem", "51020-001"
        loja.latitude, loja.longitude = D("-8.1185"), D("-34.8970")
    loja.telefone = loja.telefone or "(81) 3333-0000"
    loja.whatsapp = loja.whatsapp or "81989328045"
    if not loja.horarios:
        loja.horarios = [{"dia_semana": d, "abre": "11:00", "fecha": "23:59"} for d in range(7)]
    loja.pedido_minimo_centavos = loja.pedido_minimo_centavos or 2000
    loja.tempo_preparo_min = 25
    loja.cashback_percentual = loja.cashback_percentual or D("5")
    loja.fidelidade_selos = loja.fidelidade_selos or 8
    loja.fidelidade_premio_centavos = loja.fidelidade_premio_centavos or 2490
    loja.fidelidade_premio_descricao = loja.fidelidade_premio_descricao or "Um Smash Clássico por nossa conta"
    loja.pedido_na_mesa = True
    loja.aberta_para_pedidos = True
    loja.save()

    for nome, taxa, minutos in ZONAS:
        ZonaEntrega.objects.get_or_create(loja=loja, tipo=TipoZonaEntrega.BAIRRO, nome=nome,
                                          defaults={"taxa_centavos": taxa, "tempo_estimado_min": minutos})
    for i in range(1, 11):
        Mesa.objects.get_or_create(loja=loja, nome=f"Mesa {i}",
                                   defaults={"capacidade": 4 if i <= 8 else 6, "ordem": i, "area": "Salão"})
    entregadores = [Entregador.objects.get_or_create(loja=loja, nome=n, defaults={"telefone": t})[0]
                    for n, t in [("Carlos Motoboy", "81992220001"), ("Rafael Entregas", "81992220002")]]
    Cupom.objects.get_or_create(loja=loja, codigo="BEMVINDO10", defaults={
        "descricao": "10% no primeiro pedido", "tipo": "PERCENTUAL", "valor": D("10"),
        "pedido_minimo_centavos": 3000, "usos_por_cliente": 1})
    Cupom.objects.get_or_create(loja=loja, codigo="FRETEGRATIS", defaults={
        "descricao": "Entrega grátis acima de R$ 60", "tipo": "FRETE_GRATIS", "valor": D("0"),
        "pedido_minimo_centavos": 6000})
    return entregadores


def _promocoes(loja, produtos):
    from apps.marketing.models import Promocao

    burgers = str(produtos["Smash Clássico"].categoria_id)
    Promocao.objects.get_or_create(loja=loja, nome="Terça do Burger", defaults={
        "descricao": "Todos os hambúrgueres com 20% off", "tipo": "PERCENTUAL", "valor": 20,
        "categorias": [burgers], "dias": [1], "hora_inicio": time(18, 0), "hora_fim": time(23, 59)})
    Promocao.objects.get_or_create(loja=loja, nome="Happy hour da batata", defaults={
        "descricao": "Batata frita por R$ 9,90 das 17h às 19h", "tipo": "PRECO_FIXO", "valor": 990,
        "produtos": [str(produtos["Batata frita"].id)], "hora_inicio": time(17, 0), "hora_fim": time(19, 0)})


def _itens(rnd, card):
    from apps.pedidos import services as ps

    p = card["produtos"]
    ponto = list(card["ponto"].adicionais.all())
    extras = list(card["extras"].adicionais.all())
    batata = p["Batata frita"]
    var_batata = list(batata.variacoes.all())
    itens = []
    for _ in range(rnd.choice([1, 1, 2, 2, 3])):
        nome = rnd.choice(["Smash Clássico", "Smash Clássico", "Bacon Lovers", "Bacon Lovers", "Duplo Cheddar",
                           "Salada Fit", "Chicken Crispy", "Combo Smash", "Combo Bacon"])
        prod = p[nome]
        ads = []
        if nome != "Chicken Crispy":
            ads.append(ps.AdicionalIn(str(rnd.choice(ponto).id), 1))
        if nome in ("Smash Clássico", "Bacon Lovers", "Duplo Cheddar", "Chicken Crispy") and rnd.random() < 0.35:
            ads.append(ps.AdicionalIn(str(rnd.choice(extras).id), 1))
        itens.append(ps.ItemIn(str(prod.id), 1, adicionais=ads))
    if rnd.random() < 0.6:
        itens.append(ps.ItemIn(str(batata.id), 1, variacao_id=str(rnd.choice(var_batata).id)))
    if rnd.random() < 0.15:
        itens.append(ps.ItemIn(str(p[rnd.choice(["Batata cheddar e bacon", "Onion rings"])].id), 1))
    for _ in range(rnd.choice([0, 1, 1, 2])):
        itens.append(ps.ItemIn(str(p[rnd.choice(["Refrigerante lata", "Suco natural", "Água mineral"])].id), 1))
    if rnd.random() < 0.2:
        itens.append(ps.ItemIn(str(p[rnd.choice(["Brownie com sorvete", "Milkshake"])].id), 1))
    return itens


def _datar(pedido, hora, entrega=False, canal=None):
    from apps.pedidos.models import Pagamento, Pedido

    campos = {"criado_em": hora, "data_referencia": timezone.localtime(hora).date(), "aceito_em": hora,
              "pronto_em": hora + timedelta(minutes=20), "concluido_em": hora + timedelta(minutes=45)}
    if entrega:
        campos["saiu_entrega_em"] = hora + timedelta(minutes=25)
    if canal:
        campos["canal"] = canal
    Pedido.objects.filter(pk=pedido.pk).update(**campos)
    Pagamento.objects.filter(pedido=pedido).update(criado_em=hora, confirmado_em=hora)


def _historico(loja, card, entregadores, admin, inicio, fim) -> int:
    """Pedidos de `inicio` a `fim` (datas): balcão, delivery por telefone e pelo
    cardápio online (Pix), mesas abertas e fechadas, e alguns cancelamentos."""
    from apps.pedidos import services as ps
    from apps.pedidos.models import Pagamento
    from apps.salao import services as salao
    from apps.salao.models import Comanda, Mesa

    rnd = random.Random(f"demo-{loja.id}-{inicio}")
    mesas = list(Mesa.objects.filter(loja=loja, ativa=True))
    criados = 0
    dia = inicio
    while dia <= fim:
        n = rnd.randint(10, 15) + (7 if dia.weekday() >= 4 else 0)
        for _ in range(n):
            hora = timezone.make_aware(datetime.combine(dia, time(rnd.choice([12, 12, 13, 18, 19, 19, 20, 20, 21, 22]),
                                                                  rnd.randint(0, 59))))
            tipo = rnd.choices(["balcao", "telefone", "online", "mesa", "cancelado"], [25, 20, 35, 17, 3])[0]
            nome_c, tel, bairro, rua, num = rnd.choice(CLIENTES)
            with transaction.atomic():
                if tipo == "mesa" and mesas:
                    mesa = rnd.choice(mesas)
                    if Comanda.objects.filter(mesa=mesa, status__in=["ABERTA", "FECHANDO"]).exists():
                        continue
                    c = salao.abrir(loja, None, mesa=mesa, pessoas=rnd.randint(2, 5))
                    rodadas = [ps.criar_pedido(loja, ps.PedidoIn(CanalVenda.MESA, TipoAtendimento.CONSUMO_LOCAL,
                                                                 _itens(rnd, card), comanda=c, mesa=mesa.nome), None)
                               for _ in range(rnd.choice([1, 1, 2]))]
                    c = salao.pedir_conta(c, admin)
                    pessoas = rnd.choice([1, 1, 2])
                    resto = c.total_centavos
                    parte = c.total_centavos // pessoas
                    for k in range(pessoas):
                        valor = resto if k == pessoas - 1 else parte
                        resto -= valor
                        ps.registrar_pagamento(usuario=admin, comanda=c, forma=rnd.choice(FORMAS), valor_centavos=valor,
                                               pago_online=True, pagador=f"Cliente {k + 1}" if pessoas > 1 else "")
                    salao.fechar(c, admin)
                    for r in rodadas:
                        _datar(r, hora)
                    Comanda.objects.filter(pk=c.pk).update(criado_em=hora, conta_pedida_em=hora + timedelta(minutes=70),
                                                          fechada_em=hora + timedelta(minutes=80))
                    Pagamento.objects.filter(comanda=c).update(criado_em=hora + timedelta(minutes=75),
                                                               confirmado_em=hora + timedelta(minutes=75))
                    criados += 1
                    continue
                entrega = tipo in ("telefone", "online")
                taxa = next(t for b, t, _ in ZONAS if b == bairro) if entrega else None
                ped = ps.criar_pedido(loja, ps.PedidoIn(
                    CanalVenda.DELIVERY if entrega else CanalVenda.BALCAO,
                    TipoAtendimento.ENTREGA if entrega else TipoAtendimento.RETIRADA, _itens(rnd, card),
                    nome_cliente=nome_c, telefone_cliente=tel, taxa_entrega_centavos=taxa,
                    endereco={"logradouro": rua, "numero": num, "bairro": bairro, "cidade": "Recife"} if entrega else None),
                    None)
                if tipo == "cancelado":
                    ps.transicionar(ped, StatusPedido.CANCELADO, admin,
                                    motivo=rnd.choice(["cliente desistiu", "endereço fora da área", "item em falta"]))
                    _datar(ped, hora)
                    criados += 1
                    continue
                forma = FormaPagamento.PIX if tipo == "online" else rnd.choice(FORMAS)
                ps.registrar_pagamento(usuario=admin, pedido=ped, forma=forma, valor_centavos=ped.total_centavos,
                                       pago_online=True)
                ps.transicionar(ped, StatusPedido.PRONTO, admin)
                if entrega:
                    ps.transicionar(ped, StatusPedido.SAIU_PARA_ENTREGA, admin, entregador_id=rnd.choice(entregadores).id)
                ps.transicionar(ped, StatusPedido.CONCLUIDO, admin)
                _datar(ped, hora, entrega, canal=CanalVenda.ONLINE if tipo == "online" else None)
            criados += 1
        dia += timedelta(days=1)
    return criados


def _compras(loja, inicio, fim):
    """Entradas de estoque (compras semanais dos insumos), para a tela de estoque ter movimento."""
    from apps.cardapio.models import Produto
    from apps.estoque import services as estoque
    from apps.estoque.models import MovimentacaoEstoque

    insumos = list(Produto.objects.filter(loja=loja, tipo=TipoProduto.INSUMO, nome__in=[i[0] for i in INSUMOS]))
    dia, n = inicio, 0
    while dia <= fim:
        if dia.weekday() == 0:  # toda segunda
            for p in insumos:
                info = next(i for i in INSUMOS if i[0] == p.nome)
                qtd = D(info[3]) / 2
                m = estoque.registrar_entrada(p, qtd, info[2], motivo="Compra semanal (demonstração)")
                quando = timezone.make_aware(datetime.combine(dia, time(9, 0)))
                if m is not None:
                    MovimentacaoEstoque.objects.filter(pk=m.pk).update(criado_em=quando)
                n += 1
        dia += timedelta(days=1)
    return n


def _hoje(loja, card, admin):
    """Movimento ao vivo: pedidos em andamento e uma mesa aberta."""
    from apps.pedidos import services as ps
    from apps.salao import services as salao
    from apps.salao.models import ABERTAS, Comanda, Mesa

    p = card["produtos"]
    ponto = card["ponto"].adicionais.filter(nome="Ao ponto").first()
    for nome, tel, status in [("Ana Beatriz Lima", "81991110001", StatusPedido.EM_PREPARO),
                              ("Felipe Araújo", "81991110006", StatusPedido.PRONTO),
                              ("Gabriela Nunes", "81991110007", StatusPedido.SAIU_PARA_ENTREGA),
                              ("Diego Santos", "81991110004", StatusPedido.EM_PREPARO),
                              ("Camila Rocha", "81991110003", None)]:
        ped = ps.criar_pedido(loja, ps.PedidoIn(
            CanalVenda.DELIVERY, TipoAtendimento.ENTREGA,
            [ps.ItemIn(str(p["Bacon Lovers"].id), 1, adicionais=[ps.AdicionalIn(str(ponto.id), 1)]),
             ps.ItemIn(str(p["Refrigerante lata"].id), 1)], nome_cliente=nome, telefone_cliente=tel,
            taxa_entrega_centavos=500, endereco={"logradouro": "Av. Conselheiro Aguiar", "numero": "100",
                                                 "bairro": "Boa Viagem", "cidade": "Recife"}), None)
        if status:
            ps.registrar_pagamento(usuario=admin, pedido=ped, forma=FormaPagamento.PIX,
                                   valor_centavos=ped.total_centavos, pago_online=True)
            ps.transicionar(ped, StatusPedido.EM_PREPARO, admin)
            if status in (StatusPedido.PRONTO, StatusPedido.SAIU_PARA_ENTREGA):
                ps.transicionar(ped, StatusPedido.PRONTO, admin)
            if status == StatusPedido.SAIU_PARA_ENTREGA:
                from apps.clientes.models import Entregador

                e = Entregador.objects.filter(loja=loja, ativo=True).first()
                if e:
                    ps.transicionar(ped, StatusPedido.SAIU_PARA_ENTREGA, admin, entregador_id=e.id)
    mesa = Mesa.objects.filter(loja=loja, nome="Mesa 3").first()
    if mesa and not Comanda.objects.filter(mesa=mesa, status__in=ABERTAS).exists():
        c = salao.abrir(loja, None, mesa=mesa, pessoas=3)
        ps.criar_pedido(loja, ps.PedidoIn(CanalVenda.MESA, TipoAtendimento.CONSUMO_LOCAL, [
            ps.ItemIn(str(p["Duplo Cheddar"].id), 2, adicionais=[ps.AdicionalIn(str(ponto.id), 1)]),
            ps.ItemIn(str(p["Batata cheddar e bacon"].id), 1), ps.ItemIn(str(p["Suco natural"].id), 3)],
            comanda=c, mesa=mesa.nome), None)


def preencher(loja, dias: int = 30, mais: bool = False) -> dict:
    """Primeira vez: `dias` de histórico até ontem. `mais=True`: mais `dias` de
    histórico ANTES do mais antigo e mais pedidos em andamento hoje."""
    from apfood_core.enums import PapelUsuario
    from django.db.models import Min

    from apps.contas.models import Usuario
    from apps.pedidos.models import Pedido

    admin = (Usuario.objects.filter(empresa=loja.empresa, papel=PapelUsuario.ADMIN, is_active=True).first()
             or Usuario.objects.filter(is_superuser=True).first())
    with transaction.atomic():
        card = _cardapio(loja)
        entregadores = _loja(loja)
        _promocoes(loja, card["produtos"])
    hoje = timezone.localdate()
    passados = Pedido.objects.filter(loja=loja, data_referencia__lt=hoje)
    if mais and passados.exists():
        fim = passados.aggregate(m=Min("data_referencia"))["m"] - timedelta(days=1)
    elif passados.count() < 50:
        fim = hoje - timedelta(days=1)
    else:
        return {"produtos": len(card["produtos"]), "pedidos_historico": 0}
    inicio = fim - timedelta(days=dias - 1)
    historico = _historico(loja, card, entregadores, admin, inicio, fim)
    try:
        _compras(loja, inicio, fim)
    except Exception:  # noqa: BLE001 — estoque é enfeite da demonstração
        log.exception("demonstração: compras")
    _hoje(loja, card, admin)
    # estoque "de hoje" depois do período simulado (o Ovo fica abaixo do mínimo, para o alerta)
    from apps.cardapio.models import Produto

    for nome, _un, _c, est, minimo in INSUMOS:
        Produto.objects.filter(loja=loja, tipo=TipoProduto.INSUMO, nome=nome).update(
            estoque_atual=D(minimo - 6) if nome == "Ovo" else D(est))
    return {"produtos": len(card["produtos"]), "pedidos_historico": historico, "de": str(inicio), "ate": str(fim)}


@executor("plataforma.demonstracao")
def tarefa(loja_id: str, dias: int = 30, mais: bool = False):
    from apps.lojas.models import Loja

    r = preencher(Loja.objects.get(pk=loja_id), dias, mais)
    log.info("demonstração da loja %s: %s", loja_id, r)
