"""Regras de preço: sabores, taxa de serviço, divisão de conta, cupons e custo médio."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from .enums import RegraPrecoSabores, TipoCupom


def _arredondar(valor: Decimal) -> int:
    return int(valor.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


# --- pizza meio a meio --------------------------------------------------------
def preco_sabores(precos_centavos: Sequence[int], regra: RegraPrecoSabores) -> int:
    """Preço unitário de um item montado com vários sabores (ex.: 1/2 calabresa
    + 1/2 portuguesa). `precos_centavos` = preço de cada sabor no tamanho escolhido."""
    if not precos_centavos:
        raise ValueError("informe ao menos um sabor")
    if regra == RegraPrecoSabores.MAIOR:
        return max(precos_centavos)
    if regra == RegraPrecoSabores.MEDIA:
        return _arredondar(Decimal(sum(precos_centavos)) / len(precos_centavos))
    raise ValueError(f"regra desconhecida: {regra}")


# --- salão ------------------------------------------------------------------
def taxa_servico(subtotal_centavos: int, percentual: Decimal) -> int:
    """Taxa de serviço (garçom), ex.: 10% sobre o consumo."""
    if percentual < 0 or percentual > 100:
        raise ValueError("percentual inválido")
    return _arredondar(Decimal(subtotal_centavos) * percentual / 100)


def dividir_conta(total_centavos: int, pessoas: int) -> list[int]:
    """Divide sem perder centavo: 10000 / 3 -> [3334, 3333, 3333]."""
    if pessoas <= 0:
        raise ValueError("número de pessoas deve ser positivo")
    base, resto = divmod(total_centavos, pessoas)
    return [base + (1 if i < resto else 0) for i in range(pessoas)]


# --- cupons -----------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Cupom:
    tipo: TipoCupom
    valor: Decimal  # % (PERCENTUAL) ou centavos (VALOR_FIXO); ignorado em FRETE_GRATIS
    pedido_minimo_centavos: int = 0
    desconto_maximo_centavos: int | None = None
    valido_de: datetime | None = None
    valido_ate: datetime | None = None
    usos_maximos: int | None = None
    usos: int = 0
    ativo: bool = True


class CupomInvalido(ValueError):
    pass


def calcular_desconto_cupom(
    cupom: Cupom, subtotal_centavos: int, taxa_entrega_centavos: int, agora: datetime
) -> int:
    """Desconto em centavos ou `CupomInvalido` com o motivo para o cliente."""
    if not cupom.ativo:
        raise CupomInvalido("cupom inativo")
    if cupom.valido_de and agora < cupom.valido_de:
        raise CupomInvalido("cupom ainda não está valendo")
    if cupom.valido_ate and agora > cupom.valido_ate:
        raise CupomInvalido("cupom expirado")
    if cupom.usos_maximos is not None and cupom.usos >= cupom.usos_maximos:
        raise CupomInvalido("cupom esgotado")
    if subtotal_centavos < cupom.pedido_minimo_centavos:
        raise CupomInvalido("pedido abaixo do mínimo do cupom")

    if cupom.tipo == TipoCupom.FRETE_GRATIS:
        desconto = taxa_entrega_centavos
    elif cupom.tipo == TipoCupom.PERCENTUAL:
        desconto = _arredondar(Decimal(subtotal_centavos) * cupom.valor / 100)
    else:
        desconto = int(cupom.valor)
    if cupom.desconto_maximo_centavos is not None:
        desconto = min(desconto, cupom.desconto_maximo_centavos)
    return max(0, min(desconto, subtotal_centavos + taxa_entrega_centavos))


# --- estoque ----------------------------------------------------------------
def custo_medio_ponderado(
    saldo_atual: Decimal, custo_atual_centavos: int | None, qtd_entrada: Decimal, custo_entrada_centavos: int
) -> int:
    """Novo custo médio unitário após uma compra. Saldo negativo ou zerado
    (comum quando a venda baixa antes da nota entrar) assume o custo da compra."""
    if qtd_entrada <= 0:
        raise ValueError("quantidade de entrada deve ser positiva")
    if saldo_atual <= 0 or custo_atual_centavos is None:
        return custo_entrada_centavos
    total = saldo_atual * custo_atual_centavos + qtd_entrada * custo_entrada_centavos
    return _arredondar(total / (saldo_atual + qtd_entrada))
