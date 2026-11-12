"""Documentos fiscais (NFC-e, CF-e SAT, NF-e).

A emissão é feita por um provedor externo (Focus NFe, PlugNotas, NFE.io...)
configurado em `integracoes.Integracao` (tipo FISCAL). O certificado A1 e o
CSC ficam cadastrados NO PROVEDOR — o ApFood não guarda certificado.
"""

from apfood_core.enums import AmbienteFiscal, ModeloDocumentoFiscal, RegimeTributario, StatusNotaFiscal
from django.db import models
from django.db.models import Q

from apps.core.models import DaLoja, ModeloBase, choices, max_len


class ConfiguracaoFiscal(ModeloBase):
    loja = models.OneToOneField("lojas.Loja", on_delete=models.CASCADE, related_name="config_fiscal")
    ativa = models.BooleanField(default=False)
    regime_tributario = models.CharField(
        max_length=max_len(RegimeTributario), choices=choices(RegimeTributario),
        default=RegimeTributario.SIMPLES_NACIONAL,
    )
    inscricao_estadual = models.CharField(max_length=20, blank=True)
    inscricao_municipal = models.CharField(max_length=20, blank=True)
    cnae = models.CharField(max_length=10, blank=True)
    ambiente = models.CharField(
        max_length=max_len(AmbienteFiscal), choices=choices(AmbienteFiscal), default=AmbienteFiscal.HOMOLOGACAO
    )
    modelo_padrao = models.CharField(
        max_length=max_len(ModeloDocumentoFiscal), choices=choices(ModeloDocumentoFiscal),
        default=ModeloDocumentoFiscal.NFCE,
    )
    serie = models.PositiveSmallIntegerField(default=1)
    emitir_automaticamente = models.BooleanField(
        default=False, help_text="emite ao concluir o pedido; senão, só quando o operador pedir"
    )
    informacoes_complementares = models.TextField(blank=True)

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.modelo_padrao == ModeloDocumentoFiscal.SAT:
            raise ValidationError({"modelo_padrao": "CF-e SAT está vedado em SP desde 01/01/2026 — use NFC-e."})

    class Meta:
        db_table = "configuracoes_fiscais"
        verbose_name = "configuração fiscal"
        verbose_name_plural = "configurações fiscais"

    def __str__(self):
        return f"Fiscal {self.loja}"


class NotaFiscal(DaLoja, ModeloBase):
    pedido = models.ForeignKey(
        "pedidos.Pedido", on_delete=models.PROTECT, null=True, blank=True, related_name="notas_fiscais"
    )
    comanda = models.ForeignKey(
        "salao.Comanda", on_delete=models.PROTECT, null=True, blank=True, related_name="notas_fiscais"
    )
    modelo = models.CharField(max_length=max_len(ModeloDocumentoFiscal), choices=choices(ModeloDocumentoFiscal))
    ambiente = models.CharField(max_length=max_len(AmbienteFiscal), choices=choices(AmbienteFiscal))
    status = models.CharField(
        max_length=max_len(StatusNotaFiscal), choices=choices(StatusNotaFiscal), default=StatusNotaFiscal.PENDENTE
    )
    numero = models.PositiveIntegerField(null=True, blank=True)
    serie = models.PositiveSmallIntegerField(null=True, blank=True)
    chave = models.CharField(max_length=44, unique=True, null=True, blank=True)
    protocolo = models.CharField(max_length=30, blank=True)
    valor_total_centavos = models.PositiveIntegerField()
    cpf_cnpj_consumidor = models.CharField(max_length=14, blank=True)
    destinatario = models.JSONField(default=dict, blank=True, help_text="NF-e 55: dados do destinatário")
    provedor = models.CharField(max_length=30, blank=True)
    referencia_provedor = models.CharField(max_length=80, help_text="id enviado ao provedor (idempotência)")
    url_xml = models.URLField(max_length=500, blank=True)
    url_danfe = models.URLField(max_length=500, blank=True)
    url_consulta = models.URLField(max_length=500, blank=True, help_text="consulta pública da SEFAZ")
    qrcode = models.TextField(blank=True, help_text="conteúdo do QR Code da NFC-e (impresso no DANFE)")
    mensagem_retorno = models.TextField(blank=True)
    tentativas = models.PositiveSmallIntegerField(default=0)
    autorizada_em = models.DateTimeField(null=True, blank=True)
    cancelada_em = models.DateTimeField(null=True, blank=True)
    motivo_cancelamento = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "notas_fiscais"
        verbose_name = "nota fiscal"
        verbose_name_plural = "notas fiscais"
        ordering = ["-criado_em"]
        indexes = [models.Index(fields=["loja", "status"]), models.Index(fields=["loja", "criado_em"])]
        constraints = [
            models.UniqueConstraint(fields=["loja", "referencia_provedor"], name="nota_referencia_unica"),
            models.CheckConstraint(
                condition=Q(pedido__isnull=False) | Q(comanda__isnull=False), name="nota_tem_origem"
            ),
        ]

    def __str__(self):
        return f"{self.get_modelo_display()} {self.numero or '—'} ({self.get_status_display()})"
