"""Infra comum dos provedores externos: cliente HTTP com timeout e erros claros.

Em testes, troque `transporte` por `httpx.MockTransport` (sem rede)."""

import httpx

transporte: httpx.BaseTransport | None = None  # substituído nos testes


class ErroProvedor(Exception):
    def __init__(self, mensagem: str, status: int | None = None, corpo=None):
        super().__init__(mensagem)
        self.status, self.corpo = status, corpo


def cliente(base_url: str, **kw) -> httpx.Client:
    return httpx.Client(base_url=base_url, timeout=kw.pop("timeout", 30), transport=transporte, **kw)


def checar(resp: httpx.Response, contexto: str):
    if resp.status_code >= 400:
        try:
            corpo = resp.json()
        except ValueError:
            corpo = resp.text[:500]
        msg = corpo.get("mensagem") or corpo.get("message") or corpo.get("error") if isinstance(corpo, dict) else corpo
        raise ErroProvedor(f"{contexto}: HTTP {resp.status_code} — {msg}", resp.status_code, corpo)
    return resp.json() if resp.content else {}
