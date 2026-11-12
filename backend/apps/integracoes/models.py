"""Conexões com serviços externos, por loja.

    MARKETPLACE: ifood, 99food, rappi       PAGAMENTO: mercadopago, asaas, efi
    FISCAL: focusnfe, plugnotas, nfeio      WHATSAPP: zapi, evolution, meta
    MAPAS: google, osrm

`credenciais` guarda tokens/segredos CIFRADOS (Fernet, ver cripto.py) e nunca
sai pela API nem aparece no admin. Use `definir_credenciais()` / `obter_credenciais()`.
"""

from apfood_core.enums import TipoIntegracao
from django.db import models
from django.utils import timezone

from apps.core.models import DaLoja, ModeloBase, choices, max_len  # noqa: I001


class Integracao(DaLoja, ModeloBase):
    tipo = models.CharField(max_length=max_len(TipoIntegracao), choices=choices(TipoIntegracao))
    provedor = models.CharField(max_length=30, help_text='"ifood", "focusnfe", "mercadopago"...')
    ativo = models.BooleanField(default=False)
    configuracao = models.JSONField(default=dict, blank=True, help_text="dados não secretos (ex.: merchant_id)")
    credenciais_cifradas = models.TextField(blank=True, editable=False)
    ultimo_sucesso_em = models.DateTimeField(null=True, blank=True)
    ultimo_erro = models.TextField(blank=True)

    class Meta:
        db_table = "integracoes"
        verbose_name = "integração"
        verbose_name_plural = "integrações"
        constraints = [
            models.UniqueConstraint(fields=["loja", "tipo", "provedor"], name="integracao_unica")
        ]

    def __str__(self):
        return f"{self.get_tipo_display()} — {self.provedor}"

    def definir_credenciais(self, dados: dict) -> None:
        from .cripto import cifrar

        self.credenciais_cifradas = cifrar(dados) if dados else ""

    def obter_credenciais(self) -> dict:
        from .cripto import decifrar

        return decifrar(self.credenciais_cifradas) if self.credenciais_cifradas else {}

    def registrar_sucesso(self):
        Integracao.objects.filter(pk=self.pk).update(ultimo_sucesso_em=timezone.now(), ultimo_erro="")

    def registrar_erro(self, erro: str):
        Integracao.objects.filter(pk=self.pk).update(ultimo_erro=str(erro)[:2000])

    @classmethod
    def ativa(cls, loja, tipo, provedor: str | None = None):
        qs = cls.objects.filter(loja=loja, tipo=tipo, ativo=True)
        if provedor:
            qs = qs.filter(provedor=provedor)
        return qs.first()


class Tarefa(ModeloBase):
    """Fila de trabalho em segundo plano, guardada no banco (sem Redis/Celery).
    Executada por `python manage.py processar_tarefas` (loop). Falhas são
    reprocessadas com espera crescente até `max_tentativas`."""

    PENDENTE, EXECUTANDO, CONCLUIDA, FALHOU = "PENDENTE", "EXECUTANDO", "CONCLUIDA", "FALHOU"

    tipo = models.CharField(max_length=60, help_text='"fiscal.emitir", "whatsapp.status", "ifood.sincronizar"...')
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=12, default=PENDENTE, choices=[(s, s) for s in
                              (PENDENTE, EXECUTANDO, CONCLUIDA, FALHOU)])
    executar_em = models.DateTimeField(default=timezone.now)
    tentativas = models.PositiveSmallIntegerField(default=0)
    max_tentativas = models.PositiveSmallIntegerField(default=5)
    chave = models.CharField(max_length=120, blank=True, help_text="evita duplicar a mesma tarefa")
    erro = models.TextField(blank=True)
    concluida_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "tarefas"
        ordering = ["executar_em"]
        indexes = [models.Index(fields=["status", "executar_em"])]
        constraints = [
            models.UniqueConstraint(fields=["chave"], condition=~models.Q(chave="") &
                                    models.Q(status__in=["PENDENTE", "EXECUTANDO"]), name="tarefa_chave_unica"),
        ]

    def __str__(self):
        return f"{self.tipo} ({self.status})"


class WebhookRecebido(ModeloBase):
    """Todo webhook é gravado antes de processar: auditoria, reprocessamento e
    idempotência (o mesmo evento nunca é aplicado duas vezes)."""

    provedor = models.CharField(max_length=30)
    loja = models.ForeignKey("lojas.Loja", on_delete=models.CASCADE, null=True, blank=True, related_name="+")
    evento = models.CharField(max_length=80)
    id_evento = models.CharField(max_length=120)
    payload = models.JSONField()
    processado_em = models.DateTimeField(null=True, blank=True)
    erro = models.TextField(blank=True)

    class Meta:
        db_table = "webhooks_recebidos"
        ordering = ["-criado_em"]
        indexes = [models.Index(fields=["processado_em", "criado_em"])]
        constraints = [
            models.UniqueConstraint(fields=["provedor", "id_evento"], name="webhook_evento_unico")
        ]
