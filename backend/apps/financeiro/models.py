from apfood_core.enums import FormaPagamento
from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import DaLoja, ModeloBase, ModeloSincronizavel, choices, max_len


class CategoriaDespesa(DaLoja, ModeloBase):
    nome = models.CharField(max_length=60, help_text='"Fornecedores", "Aluguel", "Motoboys"...')
    ativa = models.BooleanField(default=True)

    class Meta:
        db_table = "categorias_despesa"
        verbose_name = "categoria de despesa"
        verbose_name_plural = "categorias de despesa"
        ordering = ["nome"]
        constraints = [
            models.UniqueConstraint(fields=["loja", "nome"], name="categoria_despesa_unica")
        ]

    def __str__(self):
        return self.nome


class Despesa(DaLoja, ModeloSincronizavel):
    """Saída para o fluxo de caixa. Se paga com dinheiro da gaveta, vincula ao
    turno e gera uma MovimentacaoCaixa do tipo DESPESA."""

    categoria = models.ForeignKey(
        CategoriaDespesa, on_delete=models.SET_NULL, null=True, blank=True, related_name="despesas"
    )
    descricao = models.CharField(max_length=160)
    valor_centavos = models.PositiveIntegerField()
    data_competencia = models.DateField()
    data_pagamento = models.DateField(null=True, blank=True)
    forma_pagamento = models.CharField(
        max_length=max_len(FormaPagamento), choices=choices(FormaPagamento), blank=True
    )
    turno = models.ForeignKey(
        "caixa.TurnoCaixa", on_delete=models.SET_NULL, null=True, blank=True, related_name="despesas"
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        db_table = "despesas"
        ordering = ["-data_competencia"]
        indexes = [models.Index(fields=["loja", "data_competencia"])]
        constraints = [
            models.CheckConstraint(condition=Q(valor_centavos__gt=0), name="despesa_valor_positivo")
        ]

    def __str__(self):
        return self.descricao
