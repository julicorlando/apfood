from apfood_core.enums import (
    FormaPagamento,
    StatusTurno,
    TipoConferencia,
    TipoMovimentacaoCaixa,
)
from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import DaLoja, ModeloBase, choices, max_len


class TurnoCaixa(DaLoja, ModeloBase):
    """Turno de caixa de UM operador. Regra garantida no banco: no máximo um
    turno ABERTO por usuário."""

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="turnos"
    )
    dispositivo = models.ForeignKey(
        "lojas.Dispositivo", on_delete=models.SET_NULL, null=True, blank=True, related_name="turnos"
    )
    status = models.CharField(
        max_length=max_len(StatusTurno), choices=choices(StatusTurno), default=StatusTurno.ABERTO
    )
    valor_abertura_centavos = models.PositiveIntegerField(help_text="fundo de troco")
    aberto_em = models.DateTimeField(auto_now_add=True)

    # Fechamento
    fechado_em = models.DateTimeField(null=True, blank=True)
    fechado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="turnos_fechados",
    )
    tipo_conferencia = models.CharField(
        max_length=max_len(TipoConferencia), choices=choices(TipoConferencia), blank=True
    )
    total_esperado_centavos = models.IntegerField(null=True, blank=True)
    total_informado_centavos = models.IntegerField(null=True, blank=True)
    diferenca_centavos = models.IntegerField(
        null=True, blank=True, help_text="> 0 sobra, < 0 quebra"
    )
    observacao_fechamento = models.TextField(blank=True)

    class Meta:
        db_table = "turnos_caixa"
        verbose_name = "turno de caixa"
        verbose_name_plural = "turnos de caixa"
        ordering = ["-aberto_em"]
        indexes = [
            models.Index(fields=["loja", "usuario", "status"]),
            models.Index(fields=["loja", "aberto_em"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["usuario"],
                condition=Q(status=StatusTurno.ABERTO),
                name="turno_aberto_por_usuario",
            ),
            models.CheckConstraint(
                condition=Q(status=StatusTurno.ABERTO) | Q(fechado_em__isnull=False),
                name="turno_fechado_tem_data",
            ),
        ]

    def __str__(self):
        return f"Turno {self.usuario} {self.aberto_em:%d/%m %H:%M}"


class MovimentacaoCaixa(DaLoja, ModeloBase):
    """Livro-razão do turno. Valor sempre POSITIVO; o sinal vem do tipo
    (VENDA/SUPRIMENTO entram; SANGRIA/DESPESA/ESTORNO_VENDA saem).
    Cálculo do esperado: `apfood_core.caixa.calcular_esperado`."""

    turno = models.ForeignKey(TurnoCaixa, on_delete=models.CASCADE, related_name="movimentacoes")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    tipo = models.CharField(max_length=max_len(TipoMovimentacaoCaixa), choices=choices(TipoMovimentacaoCaixa))
    forma_pagamento = models.CharField(
        max_length=max_len(FormaPagamento),
        choices=choices(FormaPagamento),
        default=FormaPagamento.DINHEIRO,
    )
    valor_centavos = models.PositiveIntegerField()
    motivo = models.CharField(max_length=255, blank=True)
    pagamento = models.OneToOneField(
        "pedidos.Pagamento", on_delete=models.SET_NULL, null=True, blank=True, related_name="movimentacao"
    )
    despesa = models.OneToOneField(
        "financeiro.Despesa", on_delete=models.SET_NULL, null=True, blank=True, related_name="movimentacao"
    )

    class Meta:
        db_table = "movimentacoes_caixa"
        verbose_name = "movimentação de caixa"
        verbose_name_plural = "movimentações de caixa"
        ordering = ["criado_em"]
        indexes = [
            models.Index(fields=["turno", "tipo"]),
            models.Index(fields=["loja", "criado_em"]),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(valor_centavos__gt=0), name="mov_caixa_valor_positivo"),
            models.CheckConstraint(
                condition=~Q(tipo__in=["SUPRIMENTO", "SANGRIA", "DESPESA"])
                | Q(forma_pagamento=FormaPagamento.DINHEIRO),
                name="mov_caixa_gaveta_so_dinheiro",
            ),
        ]

    def __str__(self):
        return f"{self.get_tipo_display()} {self.valor_centavos}"


class ConferenciaCaixa(ModeloBase):
    """Uma linha por forma de pagamento no fechamento: esperado x informado."""

    turno = models.ForeignKey(TurnoCaixa, on_delete=models.CASCADE, related_name="conferencias")
    forma_pagamento = models.CharField(max_length=max_len(FormaPagamento), choices=choices(FormaPagamento))
    valor_esperado_centavos = models.IntegerField()
    valor_informado_centavos = models.PositiveIntegerField()
    diferenca_centavos = models.IntegerField()

    class Meta:
        db_table = "conferencias_caixa"
        verbose_name = "conferência de caixa"
        ordering = ["forma_pagamento"]
        constraints = [
            models.UniqueConstraint(fields=["turno", "forma_pagamento"], name="conferencia_forma_unica")
        ]
