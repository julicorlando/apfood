"""Cria a loja demo "burger-demo" com cardápio, insumos, zonas e usuários.

    python manage.py seed_demo            # senha padrão: apfood123
"""

from decimal import Decimal

from apfood_core.enums import PapelUsuario, TipoProduto, TipoZonaEntrega, UnidadeMedida
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.cardapio.models import (
    Adicional,
    Categoria,
    FichaTecnicaItem,
    GrupoAdicional,
    Produto,
    ProdutoGrupoAdicional,
)
from apps.clientes.models import Entregador, ZonaEntrega
from apps.contas.models import Usuario
from apps.financeiro.models import CategoriaDespesa
from apps.lojas.models import Loja


class Command(BaseCommand):
    help = "Popula o banco com a loja demo burger-demo"

    def add_arguments(self, parser):
        parser.add_argument("--senha", default="apfood123")

    @transaction.atomic
    def handle(self, *args, senha, **opts):
        loja, criada = Loja.objects.get_or_create(
            slug="burger-demo",
            defaults=dict(
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
        if not criada:
            self.stdout.write(self.style.WARNING("Loja demo já existe — nada a fazer."))
            return

        for login, nome, papel in [
            ("admin", "Administrador", PapelUsuario.ADMIN),
            ("gerente", "Gerente", PapelUsuario.GERENTE),
            ("caixa1", "Operador 1", PapelUsuario.OPERADOR),
        ]:
            u = Usuario(username=login, first_name=nome, loja=loja, papel=papel)
            u.is_staff = papel != PapelUsuario.OPERADOR
            u.is_superuser = papel == PapelUsuario.ADMIN
            u.set_password(senha)
            u.definir_pin("1234")
            u.save()

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

        lanches = Categoria.objects.create(loja=loja, nome="Lanches", ordem=1)
        bebidas = Categoria.objects.create(loja=loja, nome="Bebidas", ordem=2)

        def lanche(nome, preco, ficha):
            p = Produto.objects.create(
                loja=loja, categoria=lanches, nome=nome, preco_centavos=preco, baixar_insumos=True
            )
            for ins, qtd in ficha:
                FichaTecnicaItem.objects.create(produto=p, insumo=ins, quantidade=Decimal(qtd))
            return p

        x_burger = lanche("X-Burger", 2990, [(pao, "1"), (carne, "1"), (queijo, "1")])
        x_bacon = lanche("X-Bacon", 3490, [(pao, "1"), (carne, "1"), (queijo, "1"), (bacon, "0.040")])
        Produto.objects.create(
            loja=loja, categoria=bebidas, nome="Refrigerante lata 350 ml", preco_centavos=700,
            controla_estoque=True, estoque_atual=Decimal("48"), estoque_minimo=Decimal("12"),
        )

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

        self.stdout.write(self.style.SUCCESS(
            f"Loja demo criada: /burger-demo/ — usuários admin, gerente, caixa1 (senha {senha}, PIN 1234)"
        ))
