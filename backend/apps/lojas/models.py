import secrets

from apfood_core.enums import MomentoBaixaEstoque
from django.db import models, transaction
from django.db.models import F

from apps.core.models import DaLoja, ModeloBase, choices, max_len


class Loja(ModeloBase):
    """Estabelecimento (tenant). Um ApFood pode atender várias lojas."""

    nome = models.CharField(max_length=120)
    slug = models.SlugField(unique=True, help_text="URL pública: apfood.app/<slug>/")
    cnpj = models.CharField(max_length=18, blank=True)
    telefone = models.CharField(max_length=20, blank=True)
    whatsapp = models.CharField(max_length=20, blank=True)
    logo = models.ImageField(upload_to="lojas/logos/", blank=True)
    cor_primaria = models.CharField(max_length=7, blank=True, help_text="#RRGGBB")

    # Endereço e geolocalização (base do cálculo de taxa por raio)
    logradouro = models.CharField(max_length=160, blank=True)
    numero = models.CharField(max_length=20, blank=True)
    bairro = models.CharField(max_length=80, blank=True)
    cidade = models.CharField(max_length=80, blank=True)
    uf = models.CharField(max_length=2, blank=True)
    cep = models.CharField(max_length=9, blank=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)

    # Operação
    aberta_para_pedidos = models.BooleanField(default=False)
    horarios = models.JSONField(
        default=list,
        blank=True,
        help_text='[{"dia_semana": 0-6, "abre": "18:00", "fecha": "23:30"}]',
    )
    pedido_minimo_centavos = models.PositiveIntegerField(default=0)
    tempo_preparo_min = models.PositiveSmallIntegerField(default=30)
    aceite_automatico = models.BooleanField(default=False)
    momento_baixa_estoque = models.CharField(
        max_length=max_len(MomentoBaixaEstoque),
        choices=choices(MomentoBaixaEstoque),
        default=MomentoBaixaEstoque.CONCLUSAO,
    )

    class Meta:
        db_table = "lojas"
        ordering = ["nome"]

    def __str__(self):
        return self.nome


class SequenciaPedido(ModeloBase):
    """Contador atômico de pedidos por loja e por dia (#1, #2...).

    O número é atribuído pelo SERVIDOR; pedidos criados offline no PDV recebem
    um código local provisório até sincronizar.
    """

    loja = models.ForeignKey(Loja, on_delete=models.CASCADE, related_name="sequencias")
    data = models.DateField()
    ultimo = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "sequencias_pedido"
        constraints = [
            models.UniqueConstraint(fields=["loja", "data"], name="sequencia_unica_loja_dia")
        ]

    @classmethod
    def proximo(cls, loja, data) -> int:
        with transaction.atomic():
            seq, _ = cls.objects.select_for_update().get_or_create(loja=loja, data=data)
            cls.objects.filter(pk=seq.pk).update(ultimo=F("ultimo") + 1)
            seq.refresh_from_db(fields=["ultimo"])
            return seq.ultimo


def _gerar_token():
    return secrets.token_urlsafe(32)


class Dispositivo(DaLoja, ModeloBase):
    """PC onde o PDV está instalado. Rastreia a origem dos dados sincronizados
    e o último cursor de sync."""

    nome = models.CharField(max_length=60, help_text='"Caixa 1", "Cozinha"')
    token_hash = models.CharField(max_length=128, editable=False)
    ultimo_sync_em = models.DateTimeField(null=True, blank=True)
    versao_app = models.CharField(max_length=20, blank=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        db_table = "dispositivos"
        ordering = ["nome"]

    def __str__(self):
        return self.nome

    def gerar_token(self) -> str:
        """Gera um token novo, guarda só o hash e devolve o token em texto puro
        (mostrado uma única vez no pareamento do PDV)."""
        from django.contrib.auth.hashers import make_password

        token = _gerar_token()
        self.token_hash = make_password(token)
        return token
