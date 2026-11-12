from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from apfood_core.enums import RegraPrecoSabores as R
from apfood_core.enums import TipoCupom as T
from apfood_core.precos import (
    Cupom,
    CupomInvalido,
    calcular_desconto_cupom,
    custo_medio_ponderado,
    dividir_conta,
    preco_sabores,
    taxa_servico,
)

AGORA = datetime(2026, 11, 12, 20, 0)


def test_sabores():
    assert preco_sabores([5990, 6990], R.MAIOR) == 6990
    assert preco_sabores([5990, 6990], R.MEDIA) == 6490
    assert preco_sabores([5000, 5000, 5001], R.MEDIA) == 5000
    with pytest.raises(ValueError):
        preco_sabores([], R.MAIOR)


def test_taxa_servico_e_divisao():
    assert taxa_servico(12345, Decimal("10")) == 1235
    assert dividir_conta(10000, 3) == [3334, 3333, 3333]
    assert sum(dividir_conta(9999, 7)) == 9999


def test_cupons():
    pct = Cupom(T.PERCENTUAL, Decimal("10"), desconto_maximo_centavos=1500)
    assert calcular_desconto_cupom(pct, 10000, 500, AGORA) == 1000
    assert calcular_desconto_cupom(pct, 50000, 500, AGORA) == 1500
    frete = Cupom(T.FRETE_GRATIS, Decimal("0"))
    assert calcular_desconto_cupom(frete, 3000, 800, AGORA) == 800
    fixo = Cupom(T.VALOR_FIXO, Decimal("5000"))
    assert calcular_desconto_cupom(fixo, 3000, 0, AGORA) == 3000  # nunca negativo


@pytest.mark.parametrize(
    "cupom",
    [
        Cupom(T.VALOR_FIXO, Decimal("500"), ativo=False),
        Cupom(T.VALOR_FIXO, Decimal("500"), valido_ate=AGORA - timedelta(days=1)),
        Cupom(T.VALOR_FIXO, Decimal("500"), usos_maximos=10, usos=10),
        Cupom(T.VALOR_FIXO, Decimal("500"), pedido_minimo_centavos=5000),
    ],
)
def test_cupom_invalido(cupom):
    with pytest.raises(CupomInvalido):
        calcular_desconto_cupom(cupom, 3000, 0, AGORA)


def test_custo_medio():
    assert custo_medio_ponderado(Decimal("10"), 500, Decimal("10"), 700) == 600
    assert custo_medio_ponderado(Decimal("-2"), 500, Decimal("10"), 700) == 700
    assert custo_medio_ponderado(Decimal("0"), None, Decimal("1"), 900) == 900
