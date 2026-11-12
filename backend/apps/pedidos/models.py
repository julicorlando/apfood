import secrets

from apfood_core.enums import (
    CanalVenda,
    FormaPagamento,
    OrigemContato,
    StatusPagamento,
    StatusPedido,
    TipoAtendimento,
)
from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.core.models import DaLoja, ModeloBase, choices, max_len


def gerar_token_rastreio() -> str:
    return secrets.token_urlsafe(12)


def hoje():
    return timezone.localdate()


class Pedido(DaLoja, ModeloBase):
    numero = models.PositiveIntegerField(
        null=True, blank=True, help_text="sequência diária atribuída pelo servidor"
    )
    data_referencia = models.DateField(default=hoje)
    codigo_local = models.CharField(
        max_length=20, blank=True, help_text="provisório quando criado offline no PDV"
    )
    canal = models.CharField(max_length=max_len(CanalVenda), choices=choices(CanalVenda))
    origem_contato = models.CharField(
        max_length=max_len(OrigemContato), choices=choices(OrigemContato), blank=True
    )
    tipo_atendimento = models.CharField(
        max_length=max_len(TipoAtendimento), choices=choices(TipoAtendimento)
    )
    status = models.CharField(
        max_length=max_len(StatusPedido), choices=choices(StatusPedido), default=StatusPedido.PENDENTE
    )
    token_rastreio = models.CharField(
        max_length=24, unique=True, default=gerar_token_rastreio, editable=False,
        help_text="link público de acompanhamento do cliente",
    )

    # Identificação (balcão: nome/senha/mesa)
    cliente = models.ForeignKey(
        "clientes.Cliente", on_delete=models.SET_NULL, null=True, blank=True, related_name="pedidos"
    )
    nome_cliente = models.CharField(max_length=120, blank=True)
    telefone_cliente = models.CharField(max_length=13, blank=True)
    mesa = models.CharField(max_length=10, blank=True)
    senha = models.CharField(max_length=10, blank=True)

    # Endereço de entrega (SNAPSHOT — não muda se o cadastro do cliente mudar)
    entrega_logradouro = models.CharField(max_length=160, blank=True)
    entrega_numero = models.CharField(max_length=20, blank=True)
    entrega_complemento = models.CharField(max_length=80, blank=True)
    entrega_bairro = models.CharField(max_length=80, blank=True)
    entrega_cidade = models.CharField(max_length=80, blank=True)
    entrega_cep = models.CharField(max_length=9, blank=True)
    entrega_referencia = models.CharField(max_length=160, blank=True)
    entrega_latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    entrega_longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    zona_entrega = models.ForeignKey(
        "clientes.ZonaEntrega", on_delete=models.SET_NULL, null=True, blank=True, related_name="pedidos"
    )
    entregador = models.ForeignKey(
        "clientes.Entregador", on_delete=models.SET_NULL, null=True, blank=True, related_name="pedidos"
    )

    # Valores (centavos) — calculados por apfood_core.totais
    subtotal_centavos = models.PositiveIntegerField(default=0)
    taxa_entrega_centavos = models.PositiveIntegerField(default=0)
    desconto_centavos = models.PositiveIntegerField(default=0)
    acrescimo_centavos = models.PositiveIntegerField(default=0)
    total_centavos = models.PositiveIntegerField(default=0)
    troco_para_centavos = models.PositiveIntegerField(null=True, blank=True)

    observacao = models.TextField(blank=True)
    motivo_cancelamento = models.CharField(max_length=255, blank=True)
    estoque_baixado = models.BooleanField(default=False, help_text="idempotência da baixa")

    # Vínculos operacionais
    turno = models.ForeignKey(
        "caixa.TurnoCaixa", on_delete=models.SET_NULL, null=True, blank=True, related_name="pedidos"
    )
    atendente = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="pedidos_lancados"
    )
    dispositivo = models.ForeignKey(
        "lojas.Dispositivo", on_delete=models.SET_NULL, null=True, blank=True, related_name="pedidos"
    )

    # Linha do tempo (preenchida conforme apfood_core.pedido_status.CAMPO_TIMESTAMP)
    aceito_em = models.DateTimeField(null=True, blank=True)
    em_preparo_em = models.DateTimeField(null=True, blank=True)
    pronto_em = models.DateTimeField(null=True, blank=True)
    saiu_entrega_em = models.DateTimeField(null=True, blank=True)
    concluido_em = models.DateTimeField(null=True, blank=True)
    cancelado_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "pedidos"
        ordering = ["-criado_em"]
        indexes = [
            models.Index(fields=["loja", "status"]),
            models.Index(fields=["loja", "criado_em"]),
            models.Index(fields=["loja", "canal", "criado_em"]),
            models.Index(fields=["loja", "atualizado_em"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["loja", "data_referencia", "numero"],
                condition=Q(numero__isnull=False),
                name="pedido_numero_unico_dia",
            ),
            models.CheckConstraint(
                condition=~Q(tipo_atendimento=TipoAtendimento.ENTREGA) | ~Q(entrega_logradouro=""),
                name="pedido_entrega_tem_endereco",
            ),
        ]

    def __str__(self):
        return f"#{self.numero or self.codigo_local or str(self.id)[:8]}"


class ItemPedido(ModeloBase):
    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name="itens")
    produto = models.ForeignKey(
        "cardapio.Produto", on_delete=models.SET_NULL, null=True, blank=True, related_name="itens_pedido"
    )
    nome_produto = models.CharField(max_length=120, help_text="snapshot")
    quantidade = models.PositiveIntegerField()
    preco_unitario_centavos = models.PositiveIntegerField(help_text="snapshot")
    total_adicionais_centavos = models.PositiveIntegerField(default=0, help_text="por unidade")
    total_centavos = models.PositiveIntegerField(help_text="(unitário + adicionais) × quantidade")
    observacao = models.CharField(max_length=255, blank=True, help_text='"sem cebola"')

    class Meta:
        db_table = "itens_pedido"
        verbose_name = "item do pedido"
        verbose_name_plural = "itens do pedido"
        ordering = ["criado_em"]
        constraints = [
            models.CheckConstraint(condition=Q(quantidade__gt=0), name="item_quantidade_positiva")
        ]

    def __str__(self):
        return f"{self.quantidade}× {self.nome_produto}"


class ItemPedidoAdicional(models.Model):
    item = models.ForeignKey(ItemPedido, on_delete=models.CASCADE, related_name="adicionais")
    adicional = models.ForeignKey(
        "cardapio.Adicional", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    nome = models.CharField(max_length=80, help_text="snapshot")
    quantidade = models.PositiveSmallIntegerField(default=1)
    preco_unitario_centavos = models.PositiveIntegerField(help_text="snapshot")

    class Meta:
        db_table = "itens_pedido_adicionais"
        verbose_name = "adicional do item"
        verbose_name_plural = "adicionais do item"


class Pagamento(ModeloBase):
    """Um pedido pode ter vários pagamentos (parte Pix, parte dinheiro)."""

    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name="pagamentos")
    forma = models.CharField(max_length=max_len(FormaPagamento), choices=choices(FormaPagamento))
    status = models.CharField(
        max_length=max_len(StatusPagamento), choices=choices(StatusPagamento), default=StatusPagamento.PENDENTE
    )
    valor_centavos = models.PositiveIntegerField(help_text="valor abatido do pedido")
    valor_recebido_centavos = models.PositiveIntegerField(
        null=True, blank=True, help_text="dinheiro entregue pelo cliente"
    )
    troco_centavos = models.PositiveIntegerField(default=0)
    pago_online = models.BooleanField(default=False)
    referencia_externa = models.CharField(max_length=80, blank=True, help_text="txid Pix, NSU")
    # Turno em que o dinheiro efetivamente entrou (definido ao CONFIRMAR)
    turno = models.ForeignKey(
        "caixa.TurnoCaixa", on_delete=models.SET_NULL, null=True, blank=True, related_name="pagamentos"
    )
    recebido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    confirmado_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "pagamentos"
        ordering = ["criado_em"]
        indexes = [models.Index(fields=["turno", "forma"])]
        constraints = [
            models.CheckConstraint(condition=Q(valor_centavos__gt=0), name="pagamento_valor_positivo"),
            models.CheckConstraint(
                condition=~Q(status=StatusPagamento.CONFIRMADO) | Q(confirmado_em__isnull=False),
                name="pagamento_confirmado_tem_data",
            ),
        ]

    def __str__(self):
        return f"{self.get_forma_display()} {self.valor_centavos}"


class HistoricoStatusPedido(ModeloBase):
    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name="historico")
    status_de = models.CharField(max_length=max_len(StatusPedido), choices=choices(StatusPedido), blank=True)
    status_para = models.CharField(max_length=max_len(StatusPedido), choices=choices(StatusPedido))
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    observacao = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "historico_status_pedido"
        ordering = ["criado_em"]
        indexes = [models.Index(fields=["pedido", "criado_em"])]
