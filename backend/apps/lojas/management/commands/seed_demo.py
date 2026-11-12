"""Cria um cenário multiempresa de demonstração:

  • usuário MASTER da plataforma ("master")
  • empresa "Burger Demo" com a loja "burger-demo" (cardápio, insumos, zonas)
    e os usuários admin / gerente / caixa1
  • empresa "Pizza Teste" com a loja "pizza-teste" e o usuário admin.pizza,
    para conferir que uma empresa não enxerga a outra

    python manage.py seed_demo            # senha padrão: apfood123
"""

from decimal import Decimal

from apfood_core.enums import (
    FormaPagamento,
    PapelUsuario,
    RegraPrecoSabores,
    StatusAssinatura,
    TipoCupom,
    TipoProduto,
    TipoZonaEntrega,
    UnidadeMedida,
)
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.cardapio.models import (
    Adicional,
    Categoria,
    FichaTecnicaItem,
    GrupoAdicional,
    Produto,
    ProdutoGrupoAdicional,
    ProdutoVariacao,
    SetorProducao,
)
from apps.clientes.models import Entregador, ZonaEntrega
from apps.contas.models import Usuario
from apps.compras.models import Fornecedor
from apps.financeiro.models import CategoriaDespesa, TaxaFormaPagamento
from apps.fiscal.models import ConfiguracaoFiscal
from apps.marketing.models import Cupom
from apps.plataforma.models import Plano
from apps.salao.models import Mesa
from apps.lojas.models import Empresa, Loja


class Command(BaseCommand):
    help = "Popula o banco com a loja demo burger-demo"

    def add_arguments(self, parser):
        parser.add_argument("--senha", default="apfood123")

    @transaction.atomic
    def handle(self, *args, senha, **opts):
        if Loja.objects.filter(slug="burger-demo").exists():
            self.stdout.write(self.style.WARNING("Dados demo já existem — nada a fazer."))
            return

        def usuario(login, nome, papel, empresa=None, lojas=()):
            u = Usuario(username=login, first_name=nome, papel=papel, empresa=empresa)
            u.set_password(senha)
            u.definir_pin("1234")
            u.save()
            u.lojas.set(lojas)
            return u

        if not Usuario.objects.filter(username="master").exists():  # no deploy, o master já é criado
            usuario("master", "Master da plataforma", PapelUsuario.MASTER)

        basico = Plano.objects.create(
            nome="Básico", preco_mensal_centavos=9900, limite_lojas=1, limite_usuarios=5,
            recursos=["pix"], ordem=1,
        )
        Plano.objects.create(
            nome="Completo", preco_mensal_centavos=24900, limite_lojas=3, limite_usuarios=30,
            recursos=["fiscal", "mesas", "marketplace", "pix", "whatsapp", "multiloja", "kds"], ordem=2,
        )
        completo = Plano.objects.get(nome="Completo")

        empresa = Empresa.objects.create(
            nome="Burger Demo", razao_social="Burger Demo Ltda", responsavel="Fulano",
            plano=completo, status_assinatura=StatusAssinatura.ATIVA,
        )
        loja, criada = Loja.objects.get_or_create(
            slug="burger-demo",
            defaults=dict(
                empresa=empresa,
                nome="Burger Demo",
                cidade="São Paulo",
                uf="SP",
                aberta_para_pedidos=True,
                pedido_minimo_centavos=2000,
                latitude=Decimal("-23.5505200"),
                longitude=Decimal("-46.6333080"),
                horarios=[{"dia_semana": d, "abre": "18:00", "fecha": "23:30"} for d in range(7)],
            ),
        )
        usuario("admin", "Administrador Burger", PapelUsuario.ADMIN, empresa)
        usuario("gerente", "Gerente", PapelUsuario.GERENTE, empresa, [loja])
        usuario("caixa1", "Operador 1", PapelUsuario.OPERADOR, empresa, [loja])

        pizza = Empresa.objects.create(nome="Pizza Teste", plano=basico)
        Loja.objects.create(empresa=pizza, slug="pizza-teste", nome="Pizza Teste")
        usuario("admin.pizza", "Administrador Pizza", PapelUsuario.ADMIN, pizza)

        def insumo(nome, unidade, estoque, minimo):
            return Produto.objects.create(
                loja=loja, tipo=TipoProduto.INSUMO, nome=nome, unidade=unidade,
                controla_estoque=True, estoque_atual=Decimal(estoque), estoque_minimo=Decimal(minimo),
            )

        pao = insumo("Pão brioche", UnidadeMedida.UN, "100", "20")
        carne = insumo("Blend bovino 150 g", UnidadeMedida.UN, "80", "20")
        queijo = insumo("Queijo cheddar (fatia)", UnidadeMedida.UN, "200", "40")
        bacon = insumo("Bacon", UnidadeMedida.KG, "5", "1")
        insumo("Embalagem delivery", UnidadeMedida.UN, "300", "50")

        chapa = SetorProducao.objects.create(loja=loja, nome="Chapa", impressora="COZINHA", ordem=1)
        bar = SetorProducao.objects.create(loja=loja, nome="Bar", impressora="192.168.0.50:9100", ordem=2)
        forno = SetorProducao.objects.create(loja=loja, nome="Forno", impressora="COZINHA", ordem=3)

        lanches = Categoria.objects.create(loja=loja, nome="Lanches", ordem=1, setor=chapa)
        bebidas = Categoria.objects.create(loja=loja, nome="Bebidas", ordem=2, setor=bar)
        pizzas = Categoria.objects.create(
            loja=loja, nome="Pizzas", ordem=3, setor=forno, max_sabores=2,
            regra_preco_sabores=RegraPrecoSabores.MAIOR,
        )

        def lanche(nome, preco, ficha):
            p = Produto.objects.create(
                loja=loja, categoria=lanches, nome=nome, preco_centavos=preco, baixar_insumos=True
            )
            for ins, qtd in ficha:
                FichaTecnicaItem.objects.create(produto=p, insumo=ins, quantidade=Decimal(qtd))
            return p

        x_burger = lanche("X-Burger", 2990, [(pao, "1"), (carne, "1"), (queijo, "1")])
        x_bacon = lanche("X-Bacon", 3490, [(pao, "1"), (carne, "1"), (queijo, "1"), (bacon, "0.040")])
        lata = Produto.objects.create(
            loja=loja, categoria=bebidas, nome="Refrigerante lata 350 ml", preco_centavos=700,
            controla_estoque=True, estoque_atual=Decimal("48"), estoque_minimo=Decimal("12"),
            ncm="22021000", cest="0300700", cst_csosn="500",
        )
        for nome, precos in [("Calabresa", (4490, 5990)), ("Marguerita", (4690, 6290)), ("Portuguesa", (4990, 6690))]:
            p = Produto.objects.create(loja=loja, categoria=pizzas, nome=f"Pizza {nome}", preco_centavos=precos[0])
            ProdutoVariacao.objects.create(produto=p, nome="Média", preco_centavos=precos[0], ordem=0)
            ProdutoVariacao.objects.create(
                produto=p, nome="Grande", preco_centavos=precos[1], fator_insumos=Decimal("1.5"), ordem=1
            )

        combo = Produto.objects.create(loja=loja, categoria=lanches, nome="Combo X-Burger + bebida", preco_centavos=3490)
        g_bebida = GrupoAdicional.objects.create(loja=loja, nome="Escolha a bebida", min_selecao=1, max_selecao=1)
        Adicional.objects.create(grupo=g_bebida, nome="Refrigerante lata", insumo=lata, quantidade_insumo=Decimal("1"))
        ProdutoGrupoAdicional.objects.create(produto=combo, grupo=g_bebida)

        ponto = GrupoAdicional.objects.create(loja=loja, nome="Ponto da carne", min_selecao=1, max_selecao=1)
        for i, n in enumerate(["Mal passado", "Ao ponto", "Bem passado"]):
            Adicional.objects.create(grupo=ponto, nome=n, ordem=i)
        extras = GrupoAdicional.objects.create(loja=loja, nome="Adicionais", min_selecao=0, max_selecao=5, ordem=1)
        Adicional.objects.create(grupo=extras, nome="Bacon extra", preco_centavos=500, max_por_item=3,
                                 insumo=bacon, quantidade_insumo=Decimal("0.030"))
        Adicional.objects.create(grupo=extras, nome="Cheddar extra", preco_centavos=400, max_por_item=2,
                                 insumo=queijo, quantidade_insumo=Decimal("1"))
        for p in (x_burger, x_bacon):
            ProdutoGrupoAdicional.objects.create(produto=p, grupo=ponto, ordem=0)
            ProdutoGrupoAdicional.objects.create(produto=p, grupo=extras, ordem=1)

        for nome, km, taxa, tempo in [("Até 3 km", "3", 500, 30), ("Até 6 km", "6", 800, 40), ("Até 10 km", "10", 1200, 55)]:
            ZonaEntrega.objects.create(loja=loja, tipo=TipoZonaEntrega.RAIO_KM, nome=nome,
                                       raio_max_km=Decimal(km), taxa_centavos=taxa, tempo_estimado_min=tempo)
        Entregador.objects.create(loja=loja, nome="Motoboy João", telefone="11999990000")
        for n in ["Fornecedores", "Motoboys", "Aluguel", "Energia", "Outros"]:
            CategoriaDespesa.objects.create(loja=loja, nome=n)

        for i in range(1, 11):
            Mesa.objects.create(loja=loja, nome=f"Mesa {i:02d}", area="Salão" if i <= 8 else "Varanda", ordem=i)
        for forma, pct, prazo in [
            (FormaPagamento.CARTAO_DEBITO, "1.39", 1),
            (FormaPagamento.CARTAO_CREDITO, "3.19", 30),
            (FormaPagamento.PIX, "0.99", 0),
            (FormaPagamento.VOUCHER, "6.50", 30),
        ]:
            TaxaFormaPagamento.objects.create(
                loja=loja, forma_pagamento=forma, taxa_percentual=Decimal(pct), prazo_recebimento_dias=prazo
            )
        Cupom.objects.create(
            loja=loja, codigo="BEMVINDO10", tipo=TipoCupom.PERCENTUAL, valor=Decimal("10"),
            desconto_maximo_centavos=1500, somente_primeira_compra=True,
        )
        Fornecedor.objects.create(loja=loja, nome="Distribuidora de Bebidas Exemplo")
        ConfiguracaoFiscal.objects.create(loja=loja)

        self.stdout.write(self.style.SUCCESS(
            f"Demo criada (senha {senha}, PIN 1234): master | Burger Demo: admin, gerente, caixa1 "
            f"| Pizza Teste: admin.pizza"
        ))
