"""Cálculos de relatórios independentes do banco."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LinhaABC:
    chave: str
    nome: str
    quantidade: float
    faturamento_centavos: int
    percentual: float  # do faturamento total
    acumulado: float  # percentual acumulado
    classe: str  # A, B ou C


def curva_abc(
    linhas: Iterable[tuple[str, str, float, int]], corte_a: float = 80.0, corte_b: float = 95.0
) -> list[LinhaABC]:
    """`linhas` = (chave, nome, quantidade, faturamento_centavos).
    A = itens que somam até 80% do faturamento, B = até 95%, C = o resto.
    O item que cruza o corte fica na classe de cima (padrão de mercado)."""
    ordenadas = sorted(linhas, key=lambda l: l[3], reverse=True)
    total = sum(l[3] for l in ordenadas) or 1
    resultado, acumulado = [], 0.0
    for chave, nome, qtd, fat in ordenadas:
        anterior = acumulado
        pct = fat * 100 / total
        acumulado += pct
        classe = "A" if anterior < corte_a else "B" if anterior < corte_b else "C"
        resultado.append(LinhaABC(chave, nome, qtd, fat, round(pct, 2), round(acumulado, 2), classe))
    return resultado


def ticket_medio(faturamento_centavos: int, pedidos: int) -> int:
    return round(faturamento_centavos / pedidos) if pedidos else 0
