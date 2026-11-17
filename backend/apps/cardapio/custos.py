"""Custo teórico (CMV) pela ficha técnica.

Custo de uma unidade vendida:
  • produto com ficha técnica → Σ (custo médio do insumo × quantidade) × fator do tamanho;
  • produto sem ficha (revenda: lata, água) → o próprio custo médio das compras;
  • pizza meio a meio → média do custo dos sabores;
  • adicionais com insumo (bacon extra) → custo do insumo × quantidade.
Sem custo cadastrado o item entra como "sem custo" (não distorce a margem).
O custo médio dos insumos vem das compras lançadas (Estoque → Compras).
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from .models import FichaTecnicaItem, Produto


def _centavos(v: Decimal) -> int:
    return int(v.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


class Custos:
    """Calcula com cache (uma consulta por produto)."""

    def __init__(self, loja):
        self.loja = loja
        self._ficha: dict[str, list[tuple[Decimal, int | None]]] = {}
        fichas = (FichaTecnicaItem.objects.filter(produto__loja=loja)
                  .select_related("insumo").values_list("produto_id", "quantidade", "insumo__custo_centavos"))
        for pid, qtd, custo in fichas:
            self._ficha.setdefault(str(pid), []).append((Decimal(qtd), custo))
        self._custo_proprio = {str(i): c for i, c in Produto.objects.filter(loja=loja).values_list("id", "custo_centavos")}

    def produto(self, produto_id, fator=Decimal("1")) -> int | None:
        """Custo unitário (centavos) ou None se faltar custo de algum insumo."""
        pid = str(produto_id)
        ficha = self._ficha.get(pid)
        if ficha:
            if any(c is None for _, c in ficha):
                return None
            return _centavos(sum((q * c for q, c in ficha), Decimal(0)) * Decimal(fator or 1))
        return self._custo_proprio.get(pid)

    def item(self, item) -> int | None:
        """Custo unitário de um ItemPedido (tamanho, sabores e adicionais)."""
        fator = item.variacao.fator_insumos if item.variacao_id and item.variacao else Decimal("1")
        sabores = list(item.sabores.all())
        if len(sabores) > 1:
            custos = [self.produto(s.produto_id, fator) for s in sabores if s.produto_id]
            if not custos or any(c is None for c in custos):
                return None
            base = _centavos(Decimal(sum(custos)) / len(custos))
        else:
            base = self.produto(item.produto_id, fator) if item.produto_id else None
            if base is None:
                return None
        extra = Decimal(0)
        for a in item.adicionais.all():
            ad = a.adicional
            if ad is not None and ad.insumo_id and ad.quantidade_insumo:
                c = self._custo_proprio.get(str(ad.insumo_id))
                if c is None:
                    continue
                extra += Decimal(c) * Decimal(ad.quantidade_insumo) * a.quantidade
        return base + _centavos(extra)


def margem(preco: int, custo: int | None) -> float | None:
    if custo is None or not preco:
        return None
    return round((preco - custo) * 100 / preco, 1)
