"""Geocodificação de endereço (texto → latitude/longitude) para a taxa por raio.

Provedores (Integração tipo MAPAS da loja):
  • "google"    — Geocoding API. Credenciais {"api_key": "..."}. Recomendado em produção.
  • "nominatim" — OpenStreetMap, grátis, máx. ~1 req/s e exige identificação.
                  Configuração {"email": "contato@sualoja.com"} (política de uso do OSM).
Resultados ficam em cache por 30 dias (mesmo endereço não consulta de novo).
"""

from __future__ import annotations

import hashlib

from apfood_core.entrega import normalizar
from django.core.cache import cache

from .base import ErroProvedor, checar, cliente

CACHE_S = 60 * 60 * 24 * 30


def texto_endereco(endereco: dict, cidade_padrao: str = "", uf: str = "") -> str:
    partes = [f"{endereco.get('logradouro', '')}, {endereco.get('numero', '')}".strip(", "),
              endereco.get("bairro", ""), endereco.get("cidade") or cidade_padrao, uf, endereco.get("cep", ""), "Brasil"]
    return ", ".join(p for p in partes if p)


class Google:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.http = cliente("https://maps.googleapis.com", timeout=10)

    def geocodificar(self, endereco: str) -> tuple[float, float] | None:
        r = checar(self.http.get("/maps/api/geocode/json",
                                 params={"address": endereco, "key": self.api_key, "region": "br", "language": "pt-BR"}),
                   "Google Geocoding")
        if r.get("status") == "ZERO_RESULTS":
            return None
        if r.get("status") != "OK":
            raise ErroProvedor(f"Google Geocoding: {r.get('status')} {r.get('error_message', '')}".strip())
        loc = r["results"][0]["geometry"]["location"]
        return float(loc["lat"]), float(loc["lng"])


class Nominatim:
    def __init__(self, email: str = ""):
        self.email = email
        self.http = cliente("https://nominatim.openstreetmap.org", timeout=10,
                            headers={"User-Agent": f"ApFood/1.0 ({email or 'sem-contato'})"})

    def geocodificar(self, endereco: str) -> tuple[float, float] | None:
        params = {"q": endereco, "format": "jsonv2", "limit": 1, "countrycodes": "br"}
        if self.email:
            params["email"] = self.email
        r = checar(self.http.get("/search", params=params), "Nominatim")
        if not r:
            return None
        return float(r[0]["lat"]), float(r[0]["lon"])


def geocodificar(loja, endereco: dict) -> tuple[float, float] | None:
    """None quando a loja não tem integração MAPAS ou o endereço não foi encontrado.
    Falha do provedor também devolve None (a taxa cai para bairro/atendente)."""
    from apfood_core.enums import TipoIntegracao

    from apps.integracoes.models import Integracao

    integ = Integracao.ativa(loja, TipoIntegracao.MAPAS)
    if integ is None:
        return None
    texto = texto_endereco(endereco, loja.cidade, loja.uf)
    chave = "geo:" + hashlib.sha1(normalizar(texto).encode()).hexdigest()
    if (em_cache := cache.get(chave)) is not None:
        return tuple(em_cache) if em_cache else None
    try:
        if integ.provedor == "google":
            prov = Google(integ.obter_credenciais()["api_key"])
        else:
            prov = Nominatim((integ.configuracao or {}).get("email", ""))
        coords = prov.geocodificar(texto)
        integ.registrar_sucesso()
    except (ErroProvedor, KeyError, OSError) as exc:
        integ.registrar_erro(str(exc))
        return None
    cache.set(chave, list(coords) if coords else [], CACHE_S)
    return coords
