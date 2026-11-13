from apfood_core.enums import TipoCupom
from django.db import models
from django.db.models import Q

from apps.core.models import DaLoja, ModeloBase, ModeloSincronizavel, choices, max_len


class Cupom(DaLoja, ModeloSincronizavel):
    """Regras de cálculo em apfood_core.precos.calcular_desconto_cupom."""

    codigo = models.CharField(max_length=30, help_text="maiúsculas, sem espaço: BEMVINDO10")
    descricao = models.CharField(max_length=160, blank=True)
    tipo = models.CharField(max_length=max_len(TipoCupom), choices=choices(TipoCupom))
    valor = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, help_text="% para PERCENTUAL; centavos para VALOR_FIXO"
    )
    pedido_minimo_centavos = models.PositiveIntegerField(default=0)
    desconto_maximo_centavos = models.PositiveIntegerField(null=True, blank=True)
    valido_de = models.DateTimeField(null=True, blank=True)
    valido_ate = models.DateTimeField(null=True, blank=True)
    usos_maximos = models.PositiveIntegerField(null=True, blank=True, help_text="vazio = ilimitado")
    usos_por_cliente = models.PositiveSmallIntegerField(null=True, blank=True)
    usos = models.PositiveIntegerField(default=0)
    somente_primeira_compra = models.BooleanField(default=False)
    canais = models.JSONField(default=list, blank=True, help_text='vazio = todos; ou ["ONLINE", "DELIVERY"]')
    ativo = models.BooleanField(default=True)

    class Meta:
        db_table = "cupons"
        verbose_name_plural = "cupons"
        ordering = ["-criado_em"]
        constraints = [
            models.UniqueConstraint(
                fields=["loja", "codigo"], condition=Q(excluido_em__isnull=True), name="cupom_codigo_unico"
            ),
        ]

    def __str__(self):
        return self.codigo

    def save(self, *args, **kwargs):
        self.codigo = self.codigo.strip().upper().replace(" ", "")
        super().save(*args, **kwargs)


class UsoCupom(ModeloBase):
    cupom = models.ForeignKey(Cupom, on_delete=models.CASCADE, related_name="usos_registrados")
    pedido = models.OneToOneField("pedidos.Pedido", on_delete=models.CASCADE, related_name="uso_cupom")
    cliente = models.ForeignKey(
        "clientes.Cliente", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    telefone = models.CharField(max_length=13, blank=True)
    desconto_centavos = models.PositiveIntegerField()

    class Meta:
        db_table = "usos_cupom"
        indexes = [models.Index(fields=["cupom", "telefone"])]


class Campanha(DaLoja, ModeloBase):
    """Mensagem de WhatsApp para os clientes que aceitaram receber promoções."""

    RASCUNHO, ENVIANDO, CONCLUIDA = "RASCUNHO", "ENVIANDO", "CONCLUIDA"
    MARKETING, CASHBACK, INATIVOS = "MARKETING", "CASHBACK", "INATIVOS"

    nome = models.CharField(max_length=80)
    mensagem = models.TextField(help_text="use {nome}, {loja}, {cashback} e {link}")
    publico = models.CharField(max_length=12, default=MARKETING, choices=[
        (MARKETING, "Todos que aceitam promoções"), (CASHBACK, "Quem tem saldo de cashback"),
        (INATIVOS, "Quem não compra há X dias"),
    ])
    dias_inativo = models.PositiveSmallIntegerField(default=30)
    status = models.CharField(max_length=10, default=RASCUNHO, choices=[
        (RASCUNHO, "Rascunho"), (ENVIANDO, "Enviando"), (CONCLUIDA, "Concluída"),
    ])
    total = models.PositiveIntegerField(default=0)
    enviados = models.PositiveIntegerField(default=0)
    falhas = models.PositiveIntegerField(default=0)
    iniciada_em = models.DateTimeField(null=True, blank=True)
    concluida_em = models.DateTimeField(null=True, blank=True)
    criado_por = models.ForeignKey("contas.Usuario", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        db_table = "campanhas"
        ordering = ["-criado_em"]

    def __str__(self):
        return self.nome


class EnvioCampanha(ModeloBase):
    PENDENTE, ENVIADO, FALHOU = "PENDENTE", "ENVIADO", "FALHOU"

    campanha = models.ForeignKey(Campanha, on_delete=models.CASCADE, related_name="envios")
    cliente = models.ForeignKey("clientes.Cliente", on_delete=models.SET_NULL, null=True, related_name="+")
    telefone = models.CharField(max_length=13)
    texto = models.TextField()
    status = models.CharField(max_length=8, default=PENDENTE)
    erro = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "campanhas_envios"
        constraints = [models.UniqueConstraint(fields=["campanha", "telefone"], name="envio_unico_por_telefone")]
