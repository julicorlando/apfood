"""Conexões com serviços externos, por loja.

    MARKETPLACE: ifood, 99food, rappi       PAGAMENTO: mercadopago, asaas, efi
    FISCAL: focusnfe, plugnotas, nfeio      WHATSAPP: zapi, evolution, meta
    MAPAS: google, osrm

`credenciais` guarda tokens/segredos e NUNCA vai para a API do PDV nem para o
admin em texto puro (Passo 2: criptografia com chave em variável de ambiente).
"""

from apfood_core.enums import TipoIntegracao
from django.db import models

from apps.core.models import DaLoja, ModeloBase, choices, max_len


class Integracao(DaLoja, ModeloBase):
    tipo = models.CharField(max_length=max_len(TipoIntegracao), choices=choices(TipoIntegracao))
    provedor = models.CharField(max_length=30, help_text='"ifood", "focusnfe", "mercadopago"...')
    ativo = models.BooleanField(default=False)
    configuracao = models.JSONField(default=dict, blank=True, help_text="dados não secretos (ex.: merchant_id)")
    credenciais = models.JSONField(default=dict, blank=True, editable=False)
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
