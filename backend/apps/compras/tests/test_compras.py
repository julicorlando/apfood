from datetime import date
from decimal import Decimal

from apps.cardapio.models import Produto
from apps.compras import services as compras
from apps.compras.models import Compra, Fornecedor, ItemCompra
from apps.estoque import services as estoque


def test_lancar_compra_custo_medio_e_conta_a_pagar(loja, cardapio, gerente):
    lata = cardapio["lata"]
    lata.custo_centavos = 300
    lata.save()
    f = Fornecedor.objects.create(loja=loja, nome="Distribuidora")
    c = Compra.objects.create(loja=loja, fornecedor=f, data_entrada=date(2026, 11, 12),
                              vencimento=date(2026, 12, 12), numero_nota="123")
    # 1 caixa com 10 latas a R$ 50,00 a caixa → R$ 5,00 por lata
    ItemCompra.objects.create(compra=c, produto=lata, quantidade=1, fator_conversao=10,
                              custo_unitario_centavos=5000, total_centavos=5000)
    compras.lancar(c, gerente)
    lata = Produto.objects.get(pk=lata.pk)
    assert lata.estoque_atual == 20 and lata.custo_centavos == 400  # (10×300 + 10×500) / 20
    c.refresh_from_db()
    assert c.status == "LANCADA" and c.despesa.valor_centavos == 5000 and c.despesa.data_pagamento is None
    compras.cancelar(c, gerente, "nota errada")
    assert Produto.objects.get(pk=lata.pk).estoque_atual == 10


def test_inventario_e_perda(loja, cardapio, gerente):
    lata = cardapio["lata"]
    estoque.ajustar_inventario(lata, Decimal("7"), usuario=gerente)
    estoque.registrar_perda(lata, 1, usuario=gerente, motivo="amassada")
    assert Produto.objects.get(pk=lata.pk).estoque_atual == 6
