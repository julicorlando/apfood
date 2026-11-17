"""Promoções programadas: desconto no preço do produto em dias e horários definidos.

Mesma regra no servidor (que sempre recalcula o pedido), no PDV do PC (offline)
e no navegador (`vitrine/carrinho.js`, função `descontoPromocao`).

- Vale para os produtos e/ou categorias escolhidos (os dois vazios = cardápio todo).
- `dias`: 0=segunda … 6=domingo (vazio = todos os dias).
- `hora_inicio`/`hora_fim` (vazios = o dia todo). Se o fim for menor que o início,
  atravessa a meia-noite (ex.: 18:00–02:00) e vale pelo dia em que começou.
- `canais`: ONLINE, BALCAO, DELIVERY, MESA (vazio = todos). Marketplace (iFood) nunca.
- O desconto é no preço do produto (tamanho/sabores), não nos adicionais.
- Mais de uma promoção valendo para o mesmo item: fica a de MAIOR desconto.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

PERCENTUAL = "PERCENTUAL"  # valor = % (ex.: 20 → 20% off)
VALOR = "VALOR"  # valor = centavos de desconto por unidade
PRECO_FIXO = "PRECO_FIXO"  # valor = preço final em centavos

DIAS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]


def _hora(v) -> time | None:
    if v in (None, ""):
        return None
    if isinstance(v, time):
        return v
    partes = [int(x) for x in str(v).split(":")[:2]]
    return time(partes[0], partes[1] if len(partes) > 1 else 0)


def _data(v) -> date | None:
    if v in (None, ""):
        return None
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v)[:10])


@dataclass
class Promocao:
    id: str
    nome: str
    tipo: str
    valor: int
    produtos: frozenset = field(default_factory=frozenset)
    categorias: frozenset = field(default_factory=frozenset)
    dias: frozenset = field(default_factory=frozenset)
    hora_inicio: time | None = None
    hora_fim: time | None = None
    data_inicio: date | None = None
    data_fim: date | None = None
    canais: frozenset = field(default_factory=frozenset)
    ativa: bool = True

    @classmethod
    def de_dict(cls, d: dict) -> "Promocao":
        return cls(
            id=str(d.get("id", "")), nome=d.get("nome", ""), tipo=d.get("tipo", PERCENTUAL),
            valor=int(d.get("valor") or 0),
            produtos=frozenset(str(x) for x in d.get("produtos") or []),
            categorias=frozenset(str(x) for x in d.get("categorias") or []),
            dias=frozenset(int(x) for x in d.get("dias") or []),
            hora_inicio=_hora(d.get("hora_inicio")), hora_fim=_hora(d.get("hora_fim")),
            data_inicio=_data(d.get("data_inicio")), data_fim=_data(d.get("data_fim")),
            canais=frozenset(d.get("canais") or []), ativa=bool(d.get("ativa", True)),
        )

    # ------------------------------------------------------------ quando vale
    def _dia_que_vale(self, agora: datetime) -> date | None:
        """Dia "dono" do horário (madrugada de uma promoção que atravessa a meia-noite
        pertence ao dia anterior). None se fora do horário."""
        h = agora.time()
        ini, fim = self.hora_inicio, self.hora_fim
        if ini is None and fim is None:
            return agora.date()
        ini = ini or time(0, 0)
        if fim is None or fim == time(0, 0):
            return agora.date() if h >= ini else None
        if ini < fim:
            return agora.date() if ini <= h < fim else None
        # atravessa a meia-noite
        if h >= ini:
            return agora.date()
        if h < fim:
            return agora.date() - timedelta(days=1)
        return None

    def vale_em(self, agora: datetime, canal: str = "") -> bool:
        if not self.ativa or self.valor <= 0:
            return False
        if canal == "MARKETPLACE" or (self.canais and canal and canal not in self.canais):
            return False
        dia = self._dia_que_vale(agora)
        if dia is None:
            return False
        if self.dias and dia.weekday() not in self.dias:
            return False
        if self.data_inicio and dia < self.data_inicio:
            return False
        if self.data_fim and dia > self.data_fim:
            return False
        return True

    def vale_para(self, produto_id: str, categoria_id: str | None) -> bool:
        if not self.produtos and not self.categorias:
            return True
        return str(produto_id) in self.produtos or (categoria_id is not None and str(categoria_id) in self.categorias)

    def desconto(self, preco_centavos: int) -> int:
        if preco_centavos <= 0:
            return 0
        if self.tipo == PERCENTUAL:
            pct = min(max(self.valor, 0), 100)
            d = int((Decimal(preco_centavos) * pct / 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        elif self.tipo == VALOR:
            d = self.valor
        elif self.tipo == PRECO_FIXO:
            d = preco_centavos - self.valor
        else:
            d = 0
        return max(0, min(d, preco_centavos))

    def descricao(self) -> str:
        if self.tipo == PERCENTUAL:
            oferta = f"{self.valor}% off"
        elif self.tipo == VALOR:
            oferta = f"R$ {self.valor / 100:.2f} off".replace(".", ",")
        else:
            oferta = f"por R$ {self.valor / 100:.2f}".replace(".", ",")
        quando = ", ".join(DIAS[d][:3] for d in sorted(self.dias)) if self.dias else "todos os dias"
        if self.hora_inicio or self.hora_fim:
            quando += f" {(self.hora_inicio or time(0)).strftime('%H:%M')}–{(self.hora_fim or time(0)).strftime('%H:%M')}"
        return f"{oferta} · {quando}"


def melhor(promocoes, produto_id: str, categoria_id: str | None, preco_centavos: int,
           agora: datetime, canal: str = "") -> tuple[int, Promocao | None]:
    """(desconto por unidade, promoção) — a de maior desconto que vale agora."""
    escolhida, maior = None, 0
    for p in promocoes:
        if not isinstance(p, Promocao):
            p = Promocao.de_dict(p)
        if not (p.vale_em(agora, canal) and p.vale_para(produto_id, categoria_id)):
            continue
        d = p.desconto(preco_centavos)
        if d > maior:
            escolhida, maior = p, d
    return maior, escolhida
