from decimal import ROUND_HALF_UP, Decimal

from apfood_core.enums import StatusCompra
from apfood_core.enums import TipoMovimentacaoEstoque as T
from django.db import transaction
from django.utils import timezone

from apps.core.excecoes import ErroNegocio
from apps.estoque import services as estoque

from .models import Compra


def recalcular_total(compra) -> int:
    itens = sum(i.total_centavos for i in compra.itens.all())
    compra.total_centavos = max(0, itens + compra.frete_centavos - compra.desconto_centavos)
    compra.save(update_fields=["total_centavos", "atualizado_em"])
    return compra.total_centavos


@transaction.atomic
def lancar(compra, usuario) -> Compra:
    """Dá entrada no estoque (custo médio) e gera a conta a pagar."""
    from apps.financeiro.models import CategoriaDespesa, Despesa

    c = Compra.objects.select_for_update().get(pk=compra.pk)
    if c.status != StatusCompra.RASCUNHO:
        raise ErroNegocio("só compras em rascunho podem ser lançadas")
    itens = list(c.itens.select_related("produto"))
    if not itens:
        raise ErroNegocio("compra sem itens")
    for i in itens:
        if not i.produto.controla_estoque:
            raise ErroNegocio(f"'{i.produto}' não controla estoque — ative antes de lançar")
        qtd_estoque = i.quantidade * i.fator_conversao
        custo_unit = int((Decimal(i.custo_unitario_centavos) / i.fator_conversao).quantize(Decimal("1"), ROUND_HALF_UP))
        estoque.registrar_entrada(i.produto, qtd_estoque, custo_unit, usuario=usuario, motivo=f"compra {c}")
    total = recalcular_total(c)
    if total > 0:
        categoria = CategoriaDespesa.objects.filter(loja=c.loja, nome__iexact="Fornecedores").first()
        c.despesa = Despesa.objects.create(
            loja=c.loja, categoria=categoria, fornecedor=c.fornecedor,
            descricao=f"Compra NF {c.numero_nota}" if c.numero_nota else f"Compra {c.data_entrada:%d/%m/%Y}",
            valor_centavos=total, data_competencia=c.data_entrada, data_vencimento=c.vencimento, usuario=usuario,
        )
    c.status = StatusCompra.LANCADA
    c.lancada_por = usuario
    c.lancada_em = timezone.now()
    c.save()
    return c


@transaction.atomic
def cancelar(compra, usuario, motivo: str) -> Compra:
    c = Compra.objects.select_for_update().get(pk=compra.pk)
    if c.status == StatusCompra.CANCELADA:
        return c
    if c.status == StatusCompra.LANCADA:
        if c.despesa_id and c.despesa.data_pagamento:
            raise ErroNegocio("a conta desta compra já foi paga; estorne o pagamento antes")
        for i in c.itens.select_related("produto"):
            estoque.movimentar(i.produto, -(i.quantidade * i.fator_conversao), T.AJUSTE, usuario=usuario,
                               motivo=f"cancelamento da compra {c}: {motivo}")
        if c.despesa_id:
            c.despesa.excluir()
    c.status = StatusCompra.CANCELADA
    c.observacao = (c.observacao + f"\nCancelada: {motivo}").strip()
    c.save()
    return c
