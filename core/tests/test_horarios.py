from datetime import datetime

from apfood_core.horarios import aberta_em, proxima_abertura

# quinta (3) 18:00–02:00 e sexta (4) 18:00–23:00
H = [{"dia_semana": 3, "abre": "18:00", "fecha": "02:00"}, {"dia_semana": 4, "abre": "18:00", "fecha": "23:00"}]


def test_sem_horarios_sempre_aberta():
    assert aberta_em([], datetime(2026, 11, 12, 3, 0))


def test_turno_que_passa_da_meia_noite():
    assert aberta_em(H, datetime(2026, 11, 12, 19, 0))  # quinta 19h
    assert aberta_em(H, datetime(2026, 11, 13, 1, 30))  # madrugada de sexta, turno de quinta
    assert not aberta_em(H, datetime(2026, 11, 13, 2, 0))
    assert not aberta_em(H, datetime(2026, 11, 13, 17, 59))
    assert aberta_em(H, datetime(2026, 11, 13, 22, 59))
    assert not aberta_em(H, datetime(2026, 11, 14, 0, 30))  # sábado: sexta fecha 23h


def test_proxima_abertura():
    assert proxima_abertura(H, datetime(2026, 11, 13, 10, 0)) == datetime(2026, 11, 13, 18, 0)
    assert proxima_abertura(H, datetime(2026, 11, 14, 10, 0)) == datetime(2026, 11, 19, 18, 0)
