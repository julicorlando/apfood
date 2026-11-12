from decimal import Decimal

from apfood_core.enums import StatusComanda
from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import DaLoja, ModeloBase, ModeloSincronizavel, choices, max_len

ABERTAS = [StatusComanda.ABERTA, StatusComanda.FECHANDO]


class Mesa(DaLoja, ModeloSincronizavel):
    nome = models.CharField(max_length=30, help_text='"Mesa 05", "Balcão 2"')
    area = models.CharField(max_length=40, blank=True, help_text='"Salão", "Varanda"')
    capacidade = models.PositiveSmallIntegerField(default=4)
    ordem = models.PositiveSmallIntegerField(default=0)
    ativa = models.BooleanField(default=True)

    class Meta:
        db_table = "mesas"
        ordering = ["area", "ordem", "nome"]
        constraints = [
            models.UniqueConstraint(
                fields=["loja", "nome"], condition=Q(excluido_em__isnull=True), name="mesa_nome_unico"
            )
        ]

    def __str__(self):
        return self.nome


class Comanda(DaLoja, ModeloBase):
    """Conta aberta no salão. Recebe vários pedidos (rodadas) ao longo do
    atendimento; o pagamento (inclusive dividido) é feito na comanda.

    Fluxo: ABERTA → FECHANDO (conta pedida, valores congelados) → FECHADA.
    Juntar mesas: os pedidos vão para a comanda destino e esta é CANCELADA
    com `unida_em` apontando para a destino. Transferir: troca `mesa`.
    """

    numero = models.CharField(max_length=20, blank=True, help_text="cartão/ficha física, se houver")
    mesa = models.ForeignKey(Mesa, on_delete=models.SET_NULL, null=True, blank=True, related_name="comandas")
    status = models.CharField(
        max_length=max_len(StatusComanda), choices=choices(StatusComanda), default=StatusComanda.ABERTA
    )
    nome_cliente = models.CharField(max_length=120, blank=True)
    cliente = models.ForeignKey(
        "clientes.Cliente", on_delete=models.SET_NULL, null=True, blank=True, related_name="comandas"
    )
    pessoas = models.PositiveSmallIntegerField(default=1)
    garcom = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    # Valores (centavos), recalculados a cada pedido; congelados em FECHANDO
    subtotal_centavos = models.PositiveIntegerField(default=0)
    cobrar_taxa_servico = models.BooleanField(default=True)
    taxa_servico_percentual = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("10"))
    taxa_servico_centavos = models.PositiveIntegerField(default=0)
    couvert_centavos = models.PositiveIntegerField(default=0)
    desconto_centavos = models.PositiveIntegerField(default=0)
    total_centavos = models.PositiveIntegerField(default=0)

    aberta_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    fechada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    turno = models.ForeignKey(
        "caixa.TurnoCaixa", on_delete=models.SET_NULL, null=True, blank=True, related_name="comandas"
    )
    conta_pedida_em = models.DateTimeField(null=True, blank=True)
    fechada_em = models.DateTimeField(null=True, blank=True)
    unida_em = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="comandas_unidas"
    )
    observacao = models.TextField(blank=True)

    class Meta:
        db_table = "comandas"
        ordering = ["-criado_em"]
        indexes = [models.Index(fields=["loja", "status"])]
        constraints = [
            models.UniqueConstraint(
                fields=["loja", "numero"],
                condition=Q(status__in=ABERTAS) & ~Q(numero=""),
                name="comanda_numero_aberto_unico",
            ),
            models.CheckConstraint(
                condition=~Q(status=StatusComanda.FECHADA) | Q(fechada_em__isnull=False),
                name="comanda_fechada_tem_data",
            ),
        ]

    def __str__(self):
        alvo = self.mesa or self.numero or self.nome_cliente or str(self.id)[:8]
        return f"Comanda {alvo}"
