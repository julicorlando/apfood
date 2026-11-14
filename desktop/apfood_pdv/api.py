"""Cliente da API do ApFood (biblioteca padrão — urllib).

Erros: `SemConexao` (rede/servidor fora) → o PDV entra em modo offline;
`ErroApi` (400/403/404...) → mensagem de negócio para mostrar ao operador.
O token de acesso é renovado sozinho com o refresh token.
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable


class ErroApi(Exception):
    def __init__(self, mensagem: str, status: int = 0, corpo=None):
        super().__init__(mensagem)
        self.mensagem, self.status, self.corpo = mensagem, status, corpo


class SemConexao(ErroApi):
    pass


Transporte = Callable[[str, str, dict, bytes | None, float], tuple[int, bytes]]


def user_agent() -> str:
    """O Cloudflare bloqueia o "Python-urllib" padrão (erro 1010, "browser's
    signature"). O PDV se identifica como um navegador + ApFoodPDV/versão."""
    from . import __version__

    return f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) ApFoodPDV/{__version__}"


def transporte_urllib(metodo: str, url: str, headers: dict, corpo: bytes | None, timeout: float) -> tuple[int, bytes]:
    headers = {"User-Agent": user_agent(), "Accept": "application/json", **headers}
    req = urllib.request.Request(url, data=corpo, method=metodo, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (URL configurada pelo usuário)
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except (urllib.error.URLError, socket.timeout, ConnectionError, OSError) as e:
        raise SemConexao(f"sem conexão com o servidor ({e})") from e


def _bloqueio_cloudflare(bruto: bytes) -> bool:
    texto = (bruto or b"")[:20000].decode("utf-8", "ignore").lower()
    return "cloudflare" in texto or "browser's signature" in texto or "error 1010" in texto


def mensagem_de_erro(corpo) -> str:
    if isinstance(corpo, dict):
        if "detail" in corpo:
            d = corpo["detail"]
            return d if isinstance(d, str) else "; ".join(map(str, d))
        partes = []
        for campo, erros in corpo.items():
            erros = erros if isinstance(erros, list) else [erros]
            partes.append(f"{campo}: " + "; ".join(mensagem_de_erro(e) if isinstance(e, dict) else str(e) for e in erros))
        return " | ".join(partes) or "erro"
    if isinstance(corpo, list):
        return "; ".join(map(str, corpo))
    return str(corpo or "erro")


class ApiClient:
    def __init__(self, base_url: str, transporte: Transporte | None = None, timeout: float = 15):
        self.base_url = base_url.rstrip("/")
        self.transporte = transporte or transporte_urllib
        self.timeout = timeout
        self.access = self.refresh = ""
        self.loja_id = ""
        self.ao_renovar: Callable[[str, str], None] | None = None  # persistir tokens

    # --- baixo nível -------------------------------------------------------
    def _url(self, caminho: str, params: dict | None) -> str:
        url = self.base_url + (caminho if caminho.startswith("/") else "/" + caminho)
        if params:
            url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v not in (None, "")}, doseq=True)
        return url

    def requisicao(self, metodo: str, caminho: str, corpo=None, params=None, *, autenticar=True, _repetir=True):
        headers = {"Accept": "application/json"}
        dados = None
        if corpo is not None:
            dados = json.dumps(corpo, default=str).encode()
            headers["Content-Type"] = "application/json"
        if autenticar and self.access:
            headers["Authorization"] = f"Bearer {self.access}"
        if self.loja_id:
            headers["X-Loja"] = self.loja_id
        status, bruto = self.transporte(metodo, self._url(caminho, params), headers, dados, self.timeout)
        try:
            resposta = json.loads(bruto) if bruto else None
        except ValueError:
            resposta = bruto.decode(errors="replace")
        if status == 401 and autenticar and _repetir and self.refresh:
            self.renovar()
            return self.requisicao(metodo, caminho, corpo, params, autenticar=autenticar, _repetir=False)
        if status >= 500:
            raise SemConexao(f"servidor indisponível (HTTP {status})", status, resposta)
        if status >= 400:
            if not isinstance(resposta, (dict, list)) and status in (403, 503) and _bloqueio_cloudflare(bruto):
                raise ErroApi("O Cloudflare bloqueou este computador (proteção contra robôs). "
                              "Peça ao administrador para liberar o PDV no Cloudflare.", status, None)
            raise ErroApi(mensagem_de_erro(resposta), status, resposta)
        return resposta

    def get(self, caminho, **params):
        return self.requisicao("GET", caminho, params=params)

    def post(self, caminho, corpo=None, **params):
        return self.requisicao("POST", caminho, corpo=corpo if corpo is not None else {}, params=params)

    def put(self, caminho, corpo=None):
        return self.requisicao("PUT", caminho, corpo=corpo)

    # --- sessão ------------------------------------------------------------
    def login(self, usuario: str, senha: str) -> dict:
        r = self.requisicao("POST", "/api/auth/token/", {"username": usuario, "password": senha}, autenticar=False)
        self._tokens(r["access"], r["refresh"])
        return self.eu()

    def renovar(self) -> None:
        try:
            r = self.requisicao("POST", "/api/auth/token/refresh/", {"refresh": self.refresh}, autenticar=False,
                                _repetir=False)
        except ErroApi as e:
            if isinstance(e, SemConexao):
                raise
            self.access = self.refresh = ""
            raise ErroApi("sessão expirada — entre novamente", 401) from e
        self._tokens(r["access"], r.get("refresh", self.refresh))

    def _tokens(self, access: str, refresh: str) -> None:
        self.access, self.refresh = access, refresh
        if self.ao_renovar:
            self.ao_renovar(access, refresh)

    def eu(self) -> dict:
        return self.get("/api/eu/")

    def trocar_operador(self, usuario: str, pin: str) -> dict:
        r = self.post("/api/auth/pin/", {"username": usuario, "pin": pin})
        self._tokens(r["access"], r["refresh"])
        return r["usuario"]

    def lista(self, caminho, **params) -> list:
        """Lê todas as páginas de um endpoint paginado (LimitOffset)."""
        params.setdefault("limit", 500)
        r = self.get(caminho, **params)
        if isinstance(r, dict) and "results" in r:
            itens = list(r["results"])
            offset = params["limit"]
            while r.get("next"):
                r = self.get(caminho, **{**params, "offset": offset})
                itens += r["results"]
                offset += params["limit"]
            return itens
        return r or []
