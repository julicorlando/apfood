"""Lado SaaS do ApFood: planos e cobrança das empresas (gerido pelo MASTER)."""

from apfood_core.enums import FormaPagamento, StatusFatura
from django.db import models

from apps.core.models import ModeloBase, choices, max_len

RECURSOS = ["fiscal", "mesas", "marketplace", "pix", "whatsapp", "multiloja", "kds"]


class Plano(ModeloBase):
    nome = models.CharField(max_length=60, unique=True)
    descricao = models.TextField(blank=True)
    preco_mensal_centavos = models.PositiveIntegerField()
    limite_lojas = models.PositiveSmallIntegerField(null=True, blank=True, help_text="vazio = ilimitado")
    limite_usuarios = models.PositiveSmallIntegerField(null=True, blank=True, help_text="vazio = ilimitado")
    recursos = models.JSONField(default=list, blank=True, help_text=f"subconjunto de {RECURSOS}")
    dias_trial = models.PositiveSmallIntegerField(default=14)
    publico = models.BooleanField(default=True, help_text="aparece na página de planos")
    ativo = models.BooleanField(default=True)
    ordem = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "planos"
        ordering = ["ordem", "preco_mensal_centavos"]

    def __str__(self):
        return self.nome


class Fatura(ModeloBase):
    empresa = models.ForeignKey("lojas.Empresa", on_delete=models.CASCADE, related_name="faturas")
    plano = models.ForeignKey(Plano, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    competencia = models.DateField(help_text="1º dia do mês de referência")
    valor_centavos = models.PositiveIntegerField()
    vencimento = models.DateField()
    status = models.CharField(max_length=max_len(StatusFatura), choices=choices(StatusFatura), default=StatusFatura.ABERTA)
    pago_em = models.DateTimeField(null=True, blank=True)
    forma_pagamento = models.CharField(
        max_length=max_len(FormaPagamento), choices=choices(FormaPagamento), blank=True
    )
    link_pagamento = models.URLField(max_length=500, blank=True)
    referencia_externa = models.CharField(max_length=80, blank=True, help_text="id no gateway (Asaas, Iugu...)")

    class Meta:
        db_table = "faturas"
        ordering = ["-competencia"]
        constraints = [
            models.UniqueConstraint(fields=["empresa", "competencia"], name="fatura_unica_por_mes")
        ]

    def __str__(self):
        return f"{self.empresa} {self.competencia:%m/%Y}"
