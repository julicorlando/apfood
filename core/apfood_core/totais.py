"""Cálculo de totais de itens e pedidos e validação de adicionais."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class AdicionalEscolhido:
    grupo_id: str
    adicional_id: str
    preco_unitario_centavos: int
    quantidade: int = 1


@dataclass(frozen=True, slots=True)
class RegraGrupo:
    grupo_id: str
    nome: str
    min_selecao: int
    max_selecao: int


@dataclass(frozen=True, slots=True)
class Item:
    preco_unitario_centavos: int
    quantidade: int
    adicionais: Sequence[AdicionalEscolhido] = field(default_factory=tuple)

    @property
    def adicionais_por_unidade_centavos(self) -> int:
        return sum(a.preco_unitario_centavos * a.quantidade for a in self.adicionais)

    @property
    def total_centavos(self) -> int:
        if self.quantidade <= 0:
            raise ValueError("quantidade deve ser positiva")
        return (self.preco_unitario_centavos + self.adicionais_por_unidade_centavos) * self.quantidade


@dataclass(frozen=True, slots=True)
class Totais:
    subtotal_centavos: int
    taxa_entrega_centavos: int
    desconto_centavos: int
    acrescimo_centavos: int

    @property
    def total_centavos(self) -> int:
        return max(
            0,
            self.subtotal_centavos
            + self.taxa_entrega_centavos
            + self.acrescimo_centavos
            - self.desconto_centavos,
        )


def calcular_totais(
    itens: Iterable[Item],
    taxa_entrega_centavos: int = 0,
    desconto_centavos: int = 0,
    acrescimo_centavos: int = 0,
) -> Totais:
    for v in (taxa_entrega_centavos, desconto_centavos, acrescimo_centavos):
        if v < 0:
            raise ValueError("taxa, desconto e acréscimo não podem ser negativos")
    return Totais(
        sum(i.total_centavos for i in itens),
        taxa_entrega_centavos,
        desconto_centavos,
        acrescimo_centavos,
    )


def validar_adicionais(
    regras: Iterable[RegraGrupo], escolhidos: Iterable[AdicionalEscolhido]
) -> list[str]:
    """Retorna a lista de erros (vazia = válido) de mín./máx. por grupo."""
    regras = list(regras)
    contagem: dict[str, int] = {}
    for a in escolhidos:
        contagem[a.grupo_id] = contagem.get(a.grupo_id, 0) + a.quantidade
    erros = []
    ids = {r.grupo_id for r in regras}
    for gid in contagem.keys() - ids:
        erros.append(f"grupo de adicionais {gid} não pertence ao produto")
    for r in regras:
        n = contagem.get(r.grupo_id, 0)
        if n < r.min_selecao:
            erros.append(f"'{r.nome}': escolha ao menos {r.min_selecao}")
        if n > r.max_selecao:
            erros.append(f"'{r.nome}': no máximo {r.max_selecao}")
    return erros
