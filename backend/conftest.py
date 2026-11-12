from decimal import Decimal

import pytest
from apfood_core.enums import PapelUsuario, TipoProduto, TipoZonaEntrega, UnidadeMedida


@pytest.fixture(autouse=True)
def _db_liberado(db):
    """Todos os testes do backend podem usar o banco."""


@pytest.fixture
def loja(db):
    from apps.lojas.models import Empresa, Loja

    e = Empresa.objects.create(nome="Burger")
    return Loja.objects.create(
        empresa=e, nome="Burger Centro", slug="burger-centro", aberta_para_pedidos=True,
        latitude=Decimal("-23.55"), longitude=Decimal("-46.63"),
    )


@pytest.fixture
def operador(loja):
    from apps.contas.models import Usuario

    u = Usuario.objects.create_user("caixa", password="x", papel=PapelUsuario.OPERADOR, empresa=loja.empresa)
    u.lojas.set([loja])
    return u


@pytest.fixture
def gerente(loja):
    from apps.contas.models import Usuario

    u = Usuario.objects.create_user("gerente", password="x", papel=PapelUsuario.GERENTE, empresa=loja.empresa)
    u.lojas.set([loja])
    return u


@pytest.fixture
def cardapio(loja):
    """X-Burger (baixa insumos), lata (controla estoque), pizza com tamanhos e
    2 sabores, grupo obrigatório 'Ponto' e extras com bacon que baixa insumo."""
    from apps.cardapio.models import (
        Adicional, Categoria, FichaTecnicaItem, GrupoAdicional, Produto, ProdutoGrupoAdicional, ProdutoVariacao,
        SetorProducao,
    )
    from apps.clientes.models import ZonaEntrega

    chapa = SetorProducao.objects.create(loja=loja, nome="Chapa")
    lanches = Categoria.objects.create(loja=loja, nome="Lanches", setor=chapa)
    bebidas = Categoria.objects.create(loja=loja, nome="Bebidas")
    pizzas = Categoria.objects.create(loja=loja, nome="Pizzas", max_sabores=2)

    def insumo(nome, saldo, un=UnidadeMedida.UN):
        return Produto.objects.create(loja=loja, tipo=TipoProduto.INSUMO, nome=nome, unidade=un,
                                      controla_estoque=True, estoque_atual=Decimal(saldo), estoque_minimo=Decimal("5"))

    pao, carne, bacon = insumo("Pão", "50"), insumo("Carne", "50"), insumo("Bacon", "2", UnidadeMedida.KG)
    massa = insumo("Massa", "20")
    x = Produto.objects.create(loja=loja, categoria=lanches, nome="X-Burger", preco_centavos=3000, baixar_insumos=True)
    FichaTecnicaItem.objects.create(produto=x, insumo=pao, quantidade=1)
    FichaTecnicaItem.objects.create(produto=x, insumo=carne, quantidade=1)
    lata = Produto.objects.create(loja=loja, categoria=bebidas, nome="Lata", preco_centavos=700,
                                  controla_estoque=True, estoque_atual=Decimal("10"), estoque_minimo=Decimal("9"))
    ponto = GrupoAdicional.objects.create(loja=loja, nome="Ponto", min_selecao=1, max_selecao=1)
    ao_ponto = Adicional.objects.create(grupo=ponto, nome="Ao ponto")
    extras = GrupoAdicional.objects.create(loja=loja, nome="Extras", min_selecao=0, max_selecao=3)
    bacon_extra = Adicional.objects.create(grupo=extras, nome="Bacon", preco_centavos=500, max_por_item=2,
                                           insumo=bacon, quantidade_insumo=Decimal("0.030"))
    ProdutoGrupoAdicional.objects.create(produto=x, grupo=ponto)
    ProdutoGrupoAdicional.objects.create(produto=x, grupo=extras)

    sabores = {}
    for nome, (m, g) in {"Calabresa": (4000, 5000), "Portuguesa": (4500, 6000)}.items():
        p = Produto.objects.create(loja=loja, categoria=pizzas, nome=nome, preco_centavos=m, baixar_insumos=True)
        FichaTecnicaItem.objects.create(produto=p, insumo=massa, quantidade=1)
        sabores[nome] = (p, ProdutoVariacao.objects.create(produto=p, nome="Média", preco_centavos=m),
                         ProdutoVariacao.objects.create(produto=p, nome="Grande", preco_centavos=g,
                                                        fator_insumos=Decimal("1.5")))
    ZonaEntrega.objects.create(loja=loja, tipo=TipoZonaEntrega.BAIRRO, nome="Centro", taxa_centavos=500)
    ZonaEntrega.objects.create(loja=loja, tipo=TipoZonaEntrega.RAIO_KM, nome="Até 5 km",
                               raio_max_km=Decimal("5"), taxa_centavos=800)
    return {"x": x, "lata": lata, "ao_ponto": ao_ponto, "bacon_extra": bacon_extra, "pao": pao, "carne": carne,
            "bacon": bacon, "massa": massa, "sabores": sabores, "chapa": chapa}
