"""Classes-base de todos os models do ApFood.

Convenções:
  • PK UUID, que pode ser gerado no CLIENTE (PDV offline): reenviar o mesmo
    registro na sincronização vira upsert idempotente.
  • Dinheiro em CENTAVOS (`PositiveIntegerField`/`IntegerField`), nunca float.
  • Quantidades de estoque em Decimal(12,3) — suporta kg, g, L, ml, un.
  • `atualizado_em` indexado = cursor de "pull" incremental do PDV.
  • `excluido_em` = soft delete para cadastros sincronizáveis (o PDV precisa
    saber que algo foi removido).
"""

import uuid

from django.db import models
from django.utils import timezone


def choices(enum_cls):
    """Converte um StrEnum do apfood_core em `choices` do Django."""
    return enum_cls.choices()


def max_len(enum_cls) -> int:
    return max(len(m.value) for m in enum_cls)


class ModeloBase(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True, db_index=True)

    class Meta:
        abstract = True
        ordering = ["-criado_em"]


class AtivosQuerySet(models.QuerySet):
    def ativos(self):
        return self.filter(excluido_em__isnull=True)

    def excluidos(self):
        return self.filter(excluido_em__isnull=False)


class ModeloSincronizavel(ModeloBase):
    """Cadastro que o PDV desktop replica localmente."""

    excluido_em = models.DateTimeField("excluído em", null=True, blank=True)

    objects = AtivosQuerySet.as_manager()

    class Meta(ModeloBase.Meta):
        abstract = True

    def excluir(self, save: bool = True):
        self.excluido_em = timezone.now()
        if save:
            self.save(update_fields=["excluido_em", "atualizado_em"])


class DaLoja(models.Model):
    """Mixin multi-loja (tenant). Toda consulta da API deve filtrar por loja."""

    loja = models.ForeignKey("lojas.Loja", on_delete=models.CASCADE, related_name="+")

    class Meta:
        abstract = True
