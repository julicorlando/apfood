import secrets

from apfood_core.enums import MomentoBaixaEstoque, StatusAssinatura
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models, transaction
from django.db.models import F

from apps.core.models import DaLoja, ModeloBase, choices, max_len


class Empresa(ModeloBase):
    """Cliente da plataforma (tenant de topo). Cadastrada só pelo MASTER.

    Uma empresa tem uma ou mais lojas (filiais). Usuários de uma empresa nunca
    enxergam dados de outra. `ativa=False` bloqueia o acesso de todos os
    usuários da empresa (ex.: inadimplência), sem apagar nada.
    """

    nome = models.CharField("nome fantasia", max_length=120)
    razao_social = models.CharField(max_length=160, blank=True)
    cnpj = models.CharField("CNPJ/CPF", max_length=18, unique=True, null=True, blank=True)
    email = models.EmailField(blank=True)
    telefone = models.CharField(max_length=20, blank=True)
    responsavel = models.CharField(max_length=120, blank=True)
    ativa = models.BooleanField(default=True, help_text="desmarcar bloqueia todos os usuários")
    motivo_bloqueio = models.CharField(max_length=255, blank=True)

    # Assinatura
    plano = models.ForeignKey(
        "plataforma.Plano", on_delete=models.PROTECT, null=True, blank=True, related_name="empresas"
    )
    status_assinatura = models.CharField(
        max_length=max_len(StatusAssinatura), choices=choices(StatusAssinatura),
        default=StatusAssinatura.TRIAL,
    )
    trial_ate = models.DateField(null=True, blank=True)
    dia_vencimento = models.PositiveSmallIntegerField(default=10)
    # Limites: vazio = usa o do plano (e plano sem limite = ilimitado)
    limite_lojas = models.PositiveSmallIntegerField(null=True, blank=True)
    limite_usuarios = models.PositiveSmallIntegerField(null=True, blank=True)
    observacoes = models.TextField(blank=True)

    class Meta:
        db_table = "empresas"
        ordering = ["nome"]

    def __str__(self):
        return self.nome

    @property
    def liberada(self) -> bool:
        """Usuários da empresa podem entrar?"""
        return self.ativa and self.status_assinatura != StatusAssinatura.CANCELADA

    @property
    def limite_lojas_efetivo(self) -> int | None:
        if self.limite_lojas is not None:
            return self.limite_lojas
        return self.plano.limite_lojas if self.plano_id else None

    @property
    def limite_usuarios_efetivo(self) -> int | None:
        if self.limite_usuarios is not None:
            return self.limite_usuarios
        return self.plano.limite_usuarios if self.plano_id else None

    def tem_recurso(self, recurso: str) -> bool:
        """Recursos do plano: "fiscal", "mesas", "marketplace", "pix", "whatsapp"..."""
        return bool(self.plano_id) and recurso in (self.plano.recursos or [])


class Loja(ModeloBase):
    """Estabelecimento (filial) de uma empresa. É a unidade de operação:
    cardápio, caixa, estoque e pedidos são sempre por loja."""

    empresa = models.ForeignKey(Empresa, on_delete=models.PROTECT, related_name="lojas")
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
    taxa_servico_percentual = models.DecimalField(
        max_digits=5, decimal_places=2, default=10, help_text="taxa de serviço padrão das comandas"
    )
    tempo_preparo_min = models.PositiveSmallIntegerField(default=30)
    aceite_automatico = models.BooleanField(default=False)
    momento_baixa_estoque = models.CharField(
        max_length=max_len(MomentoBaixaEstoque),
        choices=choices(MomentoBaixaEstoque),
        default=MomentoBaixaEstoque.CONCLUSAO,
    )

    ativa = models.BooleanField(default=True)

    class Meta:
        db_table = "lojas"
        ordering = ["nome"]
        indexes = [models.Index(fields=["empresa", "ativa"])]

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


class OperacaoSincronizada(models.Model):
    """Registro de cada operação recebida do PDV via /api/sync/push/. Reenviar
    a mesma operação (mesmo `id`) devolve o resultado gravado, sem reexecutar."""

    id = models.UUIDField(primary_key=True)
    loja = models.ForeignKey(Loja, on_delete=models.CASCADE, related_name="+")
    dispositivo = models.ForeignKey(Dispositivo, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    usuario = models.ForeignKey("contas.Usuario", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    operacao = models.CharField(max_length=40)
    ok = models.BooleanField()
    resultado = models.JSONField(default=dict, encoder=DjangoJSONEncoder)
    recebida_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "operacoes_sincronizadas"
        indexes = [models.Index(fields=["loja", "recebida_em"])]
