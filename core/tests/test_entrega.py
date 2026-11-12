from decimal import Decimal

from apfood_core.entrega import Zona, distancia_km, encontrar_zona, normalizar
from apfood_core.enums import TipoZonaEntrega as T

ZONAS = [
    Zona("b", T.BAIRRO, "Vila Mariana", 400),
    Zona("r6", T.RAIO_KM, "Até 6 km", 800, Decimal("6")),
    Zona("r3", T.RAIO_KM, "Até 3 km", 500, Decimal("3")),
]


def test_distancia_sp_campinas():
    assert 80 < distancia_km(-23.5505, -46.6333, -22.9056, -47.0608) < 90


def test_normalizar():
    assert normalizar("  São  JOÃO ") == "sao joao"


def test_zona_por_bairro_tem_prioridade():
    assert encontrar_zona(ZONAS, bairro="vila mariana", distancia=5).id == "b"


def test_menor_faixa_que_cabe():
    assert encontrar_zona(ZONAS, distancia=2.5).id == "r3"
    assert encontrar_zona(ZONAS, distancia=4).id == "r6"
    assert encontrar_zona(ZONAS, distancia=12) is None
