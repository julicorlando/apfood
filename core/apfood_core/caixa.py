"""Regras de caixa: valor esperado por forma de pagamento e conferência.

Convenção do livro-razão (`MovimentacaoCaixa`): o valor é sempre POSITIVO e o
sinal vem do tipo:
    entrada -> VENDA, SUPRIMENTO
    saída   -> SANGRIA, DESPESA, ESTORNO_VENDA

Fundo de troco (abertura), suprimentos, sangrias e despesas mexem apenas na
gaveta de DINHEIRO. Vendas e estornos mexem na forma de pagamento da venda.
O troco não entra aqui: a movimentação de VENDA registra o valor abatido do
pedido, não o valor entregue pelo cliente.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from .enums import FormaPagamento, TipoMovimentacaoCaixa

ENTRADAS = frozenset({TipoMovimentacaoCaixa.VENDA, TipoMovimentacaoCaixa.SUPRIMENTO})
SAIDAS = frozenset(
    {
        TipoMovimentacaoCaixa.SANGRIA,
        TipoMovimentacaoCaixa.DESPESA,
        TipoMovimentacaoCaixa.ESTORNO_VENDA,
    }
)
SOMENTE_DINHEIRO = frozenset(
    {
        TipoMovimentacaoCaixa.SUPRIMENTO,
        TipoMovimentacaoCaixa.SANGRIA,
        TipoMovimentacaoCaixa.DESPESA,
    }
)

#: Formas sempre exibidas no fechamento, mesmo zeradas.
FORMAS_FECHAMENTO = (
    FormaPagamento.DINHEIRO,
    FormaPagamento.PIX,
    FormaPagamento.CARTAO_CREDITO,
    FormaPagamento.CARTAO_DEBITO,
)


@dataclass(frozen=True, slots=True)
class Movimento:
    tipo: TipoMovimentacaoCaixa
    forma: FormaPagamento
    valor_centavos: int


@dataclass(frozen=True, slots=True)
class LinhaConferencia:
    forma: FormaPagamento
    esperado_centavos: int
    informado_centavos: int

    @property
    def diferenca_centavos(self) -> int:
        """> 0 sobra, < 0 quebra."""
        return self.informado_centavos - self.esperado_centavos


@dataclass(frozen=True, slots=True)
class ResultadoConferencia:
    linhas: tuple[LinhaConferencia, ...]

    @property
    def total_esperado_centavos(self) -> int:
        return sum(l.esperado_centavos for l in self.linhas)

    @property
    def total_informado_centavos(self) -> int:
        return sum(l.informado_centavos for l in self.linhas)

    @property
    def diferenca_centavos(self) -> int:
        return self.total_informado_centavos - self.total_esperado_centavos

    @property
    def situacao(self) -> str:
        d = self.diferenca_centavos
        return "SOBRA" if d > 0 else "QUEBRA" if d < 0 else "OK"


def validar_movimento(m: Movimento) -> None:
    if m.valor_centavos <= 0:
        raise ValueError("valor da movimentação deve ser positivo")
    if m.tipo in SOMENTE_DINHEIRO and m.forma != FormaPagamento.DINHEIRO:
        raise ValueError(f"{m.tipo} só pode ser em dinheiro")


def calcular_esperado(
    valor_abertura_centavos: int, movimentos: Iterable[Movimento]
) -> dict[FormaPagamento, int]:
    """Saldo esperado em cada forma de pagamento ao final do turno."""
    if valor_abertura_centavos < 0:
        raise ValueError("valor de abertura não pode ser negativo")
    saldo: dict[FormaPagamento, int] = {f: 0 for f in FORMAS_FECHAMENTO}
    saldo[FormaPagamento.DINHEIRO] = valor_abertura_centavos
    for m in movimentos:
        validar_movimento(m)
        sinal = 1 if m.tipo in ENTRADAS else -1
        saldo[m.forma] = saldo.get(m.forma, 0) + sinal * m.valor_centavos
    return saldo


def conferir(
    esperado: Mapping[FormaPagamento, int], informado: Mapping[FormaPagamento, int]
) -> ResultadoConferencia:
    """Compara esperado x informado. Formas ausentes no informado contam como 0."""
    for forma, valor in informado.items():
        if valor < 0:
            raise ValueError(f"valor informado negativo em {forma}")
    formas = list(FORMAS_FECHAMENTO) + [
        f for f in {*esperado, *informado} if f not in FORMAS_FECHAMENTO
    ]
    return ResultadoConferencia(
        tuple(
            LinhaConferencia(f, esperado.get(f, 0), informado.get(f, 0))
            for f in formas
        )
    )
