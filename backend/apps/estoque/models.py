from apfood_core.enums import TipoMovimentacaoEstoque
from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import DaLoja, ModeloBase, choices, max_len

QTD = {"max_digits": 12, "decimal_places": 3}


class MovimentacaoEstoque(DaLoja, ModeloBase):
    """Kardex: toda alteração de saldo gera uma linha. `quantidade` é ASSINADA
    (positiva = entrada, negativa = saída). O saldo corrente fica em
    `Produto.estoque_atual`, atualizado na mesma transação com
    `select_for_update` (Passo 2: apps/estoque/services.py)."""

    produto = models.ForeignKey(
        "cardapio.Produto", on_delete=models.CASCADE, related_name="movimentacoes_estoque"
    )
    tipo = models.CharField(
        max_length=max_len(TipoMovimentacaoEstoque), choices=choices(TipoMovimentacaoEstoque)
    )
    quantidade = models.DecimalField(**QTD)
    saldo_anterior = models.DecimalField(**QTD)
    saldo_posterior = models.DecimalField(**QTD)
    custo_unitario_centavos = models.PositiveIntegerField(null=True, blank=True)
    motivo = models.CharField(max_length=255, blank=True)
    pedido = models.ForeignKey(
        "pedidos.Pedido", on_delete=models.SET_NULL, null=True, blank=True, related_name="movimentacoes_estoque"
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        db_table = "movimentacoes_estoque"
        verbose_name = "movimentação de estoque"
        verbose_name_plural = "movimentações de estoque"
        ordering = ["-criado_em"]
        indexes = [
            models.Index(fields=["produto", "criado_em"]),
            models.Index(fields=["loja", "criado_em"]),
        ]
        constraints = [
            models.CheckConstraint(condition=~Q(quantidade=0), name="mov_estoque_quantidade_nao_zero"),
            models.CheckConstraint(
                condition=~Q(tipo__in=["SAIDA_VENDA", "PERDA"]) | Q(quantidade__lt=0),
                name="mov_estoque_saida_negativa",
            ),
            models.CheckConstraint(
                condition=~Q(tipo__in=["ENTRADA", "ESTORNO_VENDA"]) | Q(quantidade__gt=0),
                name="mov_estoque_entrada_positiva",
            ),
        ]

    def __str__(self):
        return f"{self.get_tipo_display()} {self.quantidade} {self.produto}"
