from apfood_core.relatorios import curva_abc, ticket_medio


def test_curva_abc():
    linhas = [("x", "X", 1, 7000), ("y", "Y", 1, 1500), ("z", "Z", 1, 1000), ("w", "W", 1, 500)]
    r = {l.chave: l.classe for l in curva_abc(linhas)}
    assert r == {"x": "A", "y": "A", "z": "B", "w": "C"}


def test_curva_vazia_e_ticket():
    assert curva_abc([]) == []
    assert ticket_medio(10000, 3) == 3333
    assert ticket_medio(0, 0) == 0
