"""Taxa de entrega: por bairro (nome normalizado) ou faixa de raio em km."""

from __future__ import annotations

import math
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from .enums import TipoZonaEntrega

RAIO_TERRA_KM = 6371.0088


def distancia_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distância em linha reta (haversine). Para rota real, use a integração MAPAS."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * RAIO_TERRA_KM * math.asin(math.sqrt(a))


def normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return " ".join(sem_acento.lower().split())


@dataclass(frozen=True, slots=True)
class Zona:
    id: str
    tipo: TipoZonaEntrega
    nome: str
    taxa_centavos: int
    raio_max_km: Decimal | None = None
    tempo_estimado_min: int | None = None


def encontrar_zona(
    zonas: Iterable[Zona], bairro: str | None = None, distancia: float | None = None
) -> Zona | None:
    """Bairro tem prioridade (taxa negociada por bairro); senão, a MENOR faixa de
    raio que contém a distância. `None` = fora da área de entrega."""
    zonas = list(zonas)
    if bairro:
        alvo = normalizar(bairro)
        for z in zonas:
            if z.tipo == TipoZonaEntrega.BAIRRO and normalizar(z.nome) == alvo:
                return z
    if distancia is not None:
        faixas = sorted(
            (z for z in zonas if z.tipo == TipoZonaEntrega.RAIO_KM and z.raio_max_km is not None),
            key=lambda z: z.raio_max_km,
        )
        for z in faixas:
            if Decimal(str(distancia)) <= z.raio_max_km:
                return z
    return None
