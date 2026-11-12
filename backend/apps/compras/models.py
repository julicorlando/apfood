"""Fornecedores e compras (entrada de mercadoria).

Lançar uma compra (Passo 2: compras/services.py, transação única):
  1. para cada item: MovimentacaoEstoque ENTRADA de `quantidade × fator_conversao`
     e novo custo médio (apfood_core.precos.custo_medio_ponderado);
  2. gera a Despesa (conta a pagar) com o vencimento informado;
  3. status → LANCADA. Cancelar estorna o estoque e a despesa.
"""

from decimal import Decimal

from apfood_core.enums import StatusCompra
from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import DaLoja, ModeloBase, ModeloSincronizavel, choices, max_len

QTD = {"max_digits": 12, "decimal_places": 3}


class Fornecedor(DaLoja, ModeloSincronizavel):
    nome = models.CharField(max_length=120)
    cnpj = models.CharField("CNPJ/CPF", max_length=14, blank=True)
    telefone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    contato = models.CharField(max_length=80, blank=True)
    observacoes = models.TextField(blank=True)

    class Meta:
        db_table = "fornecedores"
        verbose_name_plural = "fornecedores"
        ordering = ["nome"]

    def __str__(self):
        return self.nome


class Compra(DaLoja, ModeloBase):
    fornecedor = models.ForeignKey(
        Fornecedor, on_delete=models.PROTECT, null=True, blank=True, related_name="compras"
    )
    status = models.CharField(max_length=max_len(StatusCompra), choices=choices(StatusCompra), default=StatusCompra.RASCUNHO)
    numero_nota = models.CharField(max_length=20, blank=True)
    serie_nota = models.CharField(max_length=5, blank=True)
    chave_nfe = models.CharField(max_length=44, blank=True, help_text="importação do XML da NF-e")
    data_emissao = models.DateField(null=True, blank=True)
    data_entrada = models.DateField()
    vencimento = models.DateField(null=True, blank=True, help_text="gera a conta a pagar")
    frete_centavos = models.PositiveIntegerField(default=0)
    desconto_centavos = models.PositiveIntegerField(default=0)
    total_centavos = models.PositiveIntegerField(default=0)
    observacao = models.TextField(blank=True)
    despesa = models.OneToOneField(
        "financeiro.Despesa", on_delete=models.SET_NULL, null=True, blank=True, related_name="compra"
    )
    lancada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    lancada_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "compras"
        ordering = ["-data_entrada"]
        indexes = [models.Index(fields=["loja", "data_entrada"])]
        constraints = [
            models.UniqueConstraint(
                fields=["loja", "chave_nfe"], condition=~Q(chave_nfe="") & ~Q(status=StatusCompra.CANCELADA),
                name="compra_nfe_unica",
            ),
        ]

    def __str__(self):
        return f"Compra {self.numero_nota or str(self.id)[:8]} — {self.fornecedor or 'sem fornecedor'}"


class ItemCompra(models.Model):
    compra = models.ForeignKey(Compra, on_delete=models.CASCADE, related_name="itens")
    produto = models.ForeignKey("cardapio.Produto", on_delete=models.PROTECT, related_name="itens_compra")
    descricao_nota = models.CharField(max_length=160, blank=True, help_text="como veio no XML do fornecedor")
    quantidade = models.DecimalField(**QTD, help_text="na unidade de compra (ex.: 2 caixas)")
    fator_conversao = models.DecimalField(
        **QTD, default=Decimal("1"), help_text="unidades de estoque por unidade de compra (caixa com 12 = 12)"
    )
    custo_unitario_centavos = models.PositiveIntegerField(help_text="por unidade de compra")
    total_centavos = models.PositiveIntegerField()

    class Meta:
        db_table = "itens_compra"
        verbose_name = "item da compra"
        verbose_name_plural = "itens da compra"
        constraints = [
            models.CheckConstraint(condition=Q(quantidade__gt=0), name="item_compra_qtd_positiva"),
            models.CheckConstraint(condition=Q(fator_conversao__gt=0), name="item_compra_fator_positivo"),
        ]

    def __str__(self):
        return f"{self.quantidade} × {self.produto}"
