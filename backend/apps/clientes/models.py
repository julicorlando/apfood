import re

from apfood_core.enums import TipoZonaEntrega
from django.db import models
from django.db.models import Q

from apps.core.models import DaLoja, ModeloSincronizavel, choices, max_len


def so_digitos(valor: str) -> str:
    return re.sub(r"\D", "", valor or "")


class Cliente(DaLoja, ModeloSincronizavel):
    nome = models.CharField(max_length=120)
    telefone = models.CharField(max_length=13, help_text="só dígitos com DDD: 11987654321")
    email = models.EmailField(blank=True)
    observacoes = models.TextField(blank=True)

    class Meta:
        db_table = "clientes"
        ordering = ["nome"]
        indexes = [models.Index(fields=["loja", "atualizado_em"])]
        constraints = [
            # busca por telefone no delivery (auto-preenchimento do endereço)
            models.UniqueConstraint(fields=["loja", "telefone"], name="cliente_telefone_unico"),
        ]

    def __str__(self):
        return f"{self.nome} ({self.telefone})"

    def save(self, *args, **kwargs):
        self.telefone = so_digitos(self.telefone)
        super().save(*args, **kwargs)


class EnderecoCliente(ModeloSincronizavel):
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name="enderecos")
    apelido = models.CharField(max_length=30, blank=True, help_text='"Casa", "Trabalho"')
    logradouro = models.CharField(max_length=160)
    numero = models.CharField(max_length=20)
    complemento = models.CharField(max_length=80, blank=True)
    bairro = models.CharField(max_length=80)
    cidade = models.CharField(max_length=80)
    uf = models.CharField(max_length=2, blank=True)
    cep = models.CharField(max_length=9, blank=True)
    referencia = models.CharField(max_length=160, blank=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    principal = models.BooleanField(default=False)

    class Meta:
        db_table = "enderecos_cliente"
        verbose_name = "endereço"
        ordering = ["-principal", "-atualizado_em"]
        constraints = [
            models.UniqueConstraint(
                fields=["cliente"],
                condition=Q(principal=True, excluido_em__isnull=True),
                name="um_endereco_principal",
            ),
        ]

    def __str__(self):
        return f"{self.logradouro}, {self.numero} — {self.bairro}"


class ZonaEntrega(DaLoja, ModeloSincronizavel):
    """Taxa por BAIRRO (match pelo nome normalizado) ou por faixa de RAIO_KM a
    partir das coordenadas da loja (a menor faixa que contém a distância)."""

    tipo = models.CharField(max_length=max_len(TipoZonaEntrega), choices=choices(TipoZonaEntrega))
    nome = models.CharField(max_length=80, help_text="nome do bairro ou rótulo da faixa")
    raio_max_km = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    taxa_centavos = models.PositiveIntegerField()
    tempo_estimado_min = models.PositiveSmallIntegerField(null=True, blank=True)
    ativa = models.BooleanField(default=True)

    class Meta:
        db_table = "zonas_entrega"
        verbose_name = "zona de entrega"
        verbose_name_plural = "zonas de entrega"
        ordering = ["tipo", "raio_max_km", "nome"]
        indexes = [models.Index(fields=["loja", "tipo", "ativa"])]
        constraints = [
            models.CheckConstraint(
                condition=Q(tipo=TipoZonaEntrega.BAIRRO) | Q(raio_max_km__gt=0),
                name="zona_raio_exige_km",
            ),
        ]

    def __str__(self):
        return self.nome


class Entregador(DaLoja, ModeloSincronizavel):
    nome = models.CharField(max_length=80)
    telefone = models.CharField(max_length=13, blank=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        db_table = "entregadores"
        verbose_name_plural = "entregadores"
        ordering = ["nome"]
        indexes = [models.Index(fields=["loja", "atualizado_em"])]

    def __str__(self):
        return self.nome
