from datetime import datetime

from apfood_core.promocoes import PERCENTUAL, PRECO_FIXO, VALOR, Promocao, melhor

TERCA_19H = datetime(2026, 11, 17, 19, 0)  # 17/11/2026 é terça (weekday 1)


def promo(**kw):
    base = {"id": "p", "nome": "Terça do burger", "tipo": PERCENTUAL, "valor": 20}
    return Promocao.de_dict({**base, **kw})


def test_percentual_valor_e_preco_fixo():
    assert promo().desconto(3000) == 600
    assert promo(tipo=VALOR, valor=500).desconto(3000) == 500
    assert promo(tipo=VALOR, valor=5000).desconto(3000) == 3000  # nunca negativo
    assert promo(tipo=PRECO_FIXO, valor=1990).desconto(2990) == 1000
    assert promo(tipo=PRECO_FIXO, valor=3500).desconto(2990) == 0


def test_dia_da_semana_e_horario():
    p = promo(dias=[1], hora_inicio="18:00", hora_fim="23:00")
    assert p.vale_em(TERCA_19H)
    assert not p.vale_em(datetime(2026, 11, 17, 17, 59))
    assert not p.vale_em(datetime(2026, 11, 18, 19, 0))  # quarta


def test_atravessa_meia_noite_vale_pelo_dia_que_comecou():
    p = promo(dias=[1], hora_inicio="18:00", hora_fim="02:00")
    assert p.vale_em(datetime(2026, 11, 18, 1, 30))  # madrugada de quarta = noite de terça
    assert not p.vale_em(datetime(2026, 11, 17, 1, 30))  # madrugada de terça = noite de segunda


def test_periodo_canal_e_marketplace():
    p = promo(data_inicio="2026-11-18", canais=["ONLINE"])
    assert not p.vale_em(TERCA_19H, "ONLINE")
    p = promo(canais=["ONLINE"])
    assert p.vale_em(TERCA_19H, "ONLINE") and not p.vale_em(TERCA_19H, "BALCAO")
    assert not promo().vale_em(TERCA_19H, "MARKETPLACE")
    assert not promo(ativa=False).vale_em(TERCA_19H)


def test_escopo_e_melhor_promocao():
    a = promo(id="a", produtos=["x"], valor=10)
    b = promo(id="b", categorias=["burgers"], valor=25)
    c = promo(id="c", produtos=["y"], valor=50)
    d, p = melhor([a, b, c], "x", "burgers", 2000, TERCA_19H)
    assert (d, p.id) == (500, "b")
    assert melhor([a, c], "z", "bebidas", 2000, TERCA_19H) == (0, None)
    assert melhor([promo()], "qualquer", None, 1000, TERCA_19H)[0] == 200  # sem escopo = cardápio todo
