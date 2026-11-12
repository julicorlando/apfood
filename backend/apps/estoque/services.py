"""Regras de estoque. Todo saldo muda aqui, com o produto travado
(`select_for_update`) e uma linha de kardex na mesma transação."""

from collections import defaultdict
from decimal import Decimal

from apfood_core.enums import TipoMovimentacaoEstoque as T
from apfood_core.precos import custo_medio_ponderado
from django.db import transaction
from django.db.models import Sum

from apps.cardapio.models import Produto
from apps.core.excecoes import ErroNegocio
from apps.realtime import eventos

from .models import MovimentacaoEstoque

ZERO = Decimal("0")


@transaction.atomic
def movimentar(
    produto: Produto,
    quantidade: Decimal,
    tipo: T,
    *,
    usuario=None,
    pedido=None,
    motivo: str = "",
    custo_unitario_centavos: int | None = None,
) -> MovimentacaoEstoque:
    """`quantidade` assinada (+ entrada, − saída). Saldo pode ficar negativo:
    restaurante não para de vender porque a nota de compra ainda não entrou."""
    quantidade = Decimal(quantidade)
    if quantidade == 0:
        raise ErroNegocio("quantidade não pode ser zero")
    p = Produto.objects.select_for_update().get(pk=produto.pk)
    if not p.controla_estoque:
        raise ErroNegocio(f"'{p.nome}' não controla estoque")
    antes = p.estoque_atual
    estava_ok = not p.abaixo_do_minimo
    p.estoque_atual = antes + quantidade
    campos = ["estoque_atual", "atualizado_em"]
    if tipo == T.ENTRADA and custo_unitario_centavos is not None:
        p.custo_centavos = custo_medio_ponderado(antes, p.custo_centavos, quantidade, custo_unitario_centavos)
        campos.append("custo_centavos")
    p.save(update_fields=campos)
    mov = MovimentacaoEstoque.objects.create(
        loja_id=p.loja_id, produto=p, tipo=tipo, quantidade=quantidade, saldo_anterior=antes,
        saldo_posterior=p.estoque_atual, custo_unitario_centavos=custo_unitario_centavos,
        motivo=motivo, pedido=pedido, usuario=usuario,
    )
    if estava_ok and p.abaixo_do_minimo:
        eventos.estoque_alerta(p)
    produto.estoque_atual, produto.custo_centavos = p.estoque_atual, p.custo_centavos
    return mov


def registrar_entrada(produto, quantidade, custo_unitario_centavos=None, *, usuario=None, motivo=""):
    if Decimal(quantidade) <= 0:
        raise ErroNegocio("entrada deve ser positiva")
    return movimentar(produto, quantidade, T.ENTRADA, usuario=usuario, motivo=motivo,
                      custo_unitario_centavos=custo_unitario_centavos)


def registrar_perda(produto, quantidade, *, usuario=None, motivo=""):
    if Decimal(quantidade) <= 0:
        raise ErroNegocio("informe a quantidade perdida (positiva)")
    if not motivo:
        raise ErroNegocio("informe o motivo da perda", "motivo")
    return movimentar(produto, -Decimal(quantidade), T.PERDA, usuario=usuario, motivo=motivo)


def ajustar_inventario(produto, saldo_contado, *, usuario=None, motivo="inventário"):
    """Acerta o saldo para o valor contado fisicamente."""
    p = Produto.objects.get(pk=produto.pk)
    diferenca = Decimal(saldo_contado) - p.estoque_atual
    if diferenca == 0:
        return None
    return movimentar(p, diferenca, T.AJUSTE, usuario=usuario, motivo=motivo)


# --- pedidos ----------------------------------------------------------------
def consumo_do_pedido(pedido) -> dict[str, Decimal]:
    """Quanto o pedido consome de cada produto com estoque controlado.

    • produto com controla_estoque → baixa ele mesmo;
    • produto com baixar_insumos  → baixa a ficha técnica × fator da variação;
    • item com N sabores          → cada sabor baixa 1/N da sua ficha;
    • adicional com insumo         → baixa quantidade_insumo × qtd do adicional.
    """
    consumo: dict[str, Decimal] = defaultdict(lambda: ZERO)

    def ficha(produto, fator):
        for f in produto.ficha_tecnica.select_related("insumo"):
            if f.insumo.controla_estoque:
                consumo[str(f.insumo_id)] += f.quantidade * fator

    itens = pedido.itens.select_related("produto", "variacao").prefetch_related(
        "sabores__produto", "adicionais__adicional__insumo"
    )
    for item in itens:
        qtd = Decimal(item.quantidade)
        fator_var = item.variacao.fator_insumos if item.variacao_id else Decimal("1")
        sabores = [s for s in item.sabores.all() if s.produto_id]
        if sabores:
            parte = Decimal(1) / len(sabores)
            for s in sabores:
                if s.produto.controla_estoque:
                    consumo[str(s.produto_id)] += qtd * parte
                if s.produto.baixar_insumos:
                    ficha(s.produto, qtd * fator_var * parte)
        elif item.produto_id:
            if item.produto.controla_estoque:
                consumo[str(item.produto_id)] += qtd
            if item.produto.baixar_insumos:
                ficha(item.produto, qtd * fator_var)
        for ad in item.adicionais.all():
            a = ad.adicional
            if a and a.insumo_id and a.quantidade_insumo and a.insumo.controla_estoque:
                consumo[str(a.insumo_id)] += a.quantidade_insumo * ad.quantidade * qtd
    return {k: v.quantize(Decimal("0.001")) for k, v in consumo.items() if v}


@transaction.atomic
def baixar_pedido(pedido, usuario=None) -> None:
    """Idempotente: só baixa uma vez (`Pedido.estoque_baixado`)."""
    from apps.pedidos.models import Pedido

    p = Pedido.objects.select_for_update().get(pk=pedido.pk)
    if p.estoque_baixado:
        return
    consumo = consumo_do_pedido(p)
    produtos = {str(k): v for k, v in Produto.objects.in_bulk(list(consumo)).items()}
    for produto_id, qtd in sorted(consumo.items()):  # ordem fixa evita deadlock
        movimentar(produtos[produto_id], -qtd, T.SAIDA_VENDA, usuario=usuario, pedido=p,
                   motivo=f"pedido {p}")
    p.estoque_baixado = True
    p.save(update_fields=["estoque_baixado", "atualizado_em"])
    pedido.estoque_baixado = True


@transaction.atomic
def estornar_pedido(pedido, usuario=None) -> None:
    """Devolve exatamente o que foi baixado (lido do kardex, não recalculado)."""
    from apps.pedidos.models import Pedido

    p = Pedido.objects.select_for_update().get(pk=pedido.pk)
    if not p.estoque_baixado:
        return
    baixado = (
        MovimentacaoEstoque.objects.filter(pedido=p, tipo__in=[T.SAIDA_VENDA, T.ESTORNO_VENDA])
        .values("produto_id").annotate(total=Sum("quantidade"))
    )
    produtos = Produto.objects.in_bulk([b["produto_id"] for b in baixado])
    for b in sorted(baixado, key=lambda b: str(b["produto_id"])):
        if b["total"] < 0:
            movimentar(produtos[b["produto_id"]], -b["total"], T.ESTORNO_VENDA, usuario=usuario, pedido=p,
                       motivo=f"cancelamento do pedido {p}")
    p.estoque_baixado = False
    p.save(update_fields=["estoque_baixado", "atualizado_em"])
    pedido.estoque_baixado = False
