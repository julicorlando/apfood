"""Ponte de impressão: deixa o painel web imprimir direto na térmica.

Com o PDV aberto, o navegador do mesmo computador chama
http://127.0.0.1:17777 e o cupom sai na impressora configurada no PDV
(rede 9100, impressora do Windows ou pasta), sem a janela de impressão.

Segurança: só escuta no 127.0.0.1 e só aceita chamadas da origem do
servidor configurado (cabeçalho Origin), então outro site aberto no
navegador não consegue mandar nada para a impressora.
"""

from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable

from . import __version__
from .impressao import ErroImpressao, imprimir

log = logging.getLogger(__name__)
PORTA_PADRAO = 17777
MAX_CORPO = 512 * 1024


class Ponte:
    """`config()` devolve a Config atual; `impressoras_setores()` as impressoras
    cadastradas nos setores (únicos destinos extras aceitos)."""

    def __init__(self, config: Callable, impressoras_setores: Callable[[], set[str]] = set,
                 porta: int = PORTA_PADRAO, imprimir_fn: Callable = imprimir):
        self.config, self.impressoras_setores, self.porta = config, impressoras_setores, porta
        self.imprimir_fn = imprimir_fn
        self.servidor: ThreadingHTTPServer | None = None

    # ------------------------------------------------------------ regras
    def origem_permitida(self) -> str:
        from .config import normalizar_servidor

        return normalizar_servidor(self.config().api_url).lower()

    def destino(self, pedido: dict) -> str:
        cfg = self.config()
        if pedido.get("destino") == "cozinha":
            setor = (pedido.get("impressora") or "").strip()
            if setor and setor in self.impressoras_setores():
                return setor
            return cfg.impressora_cozinha_padrao or cfg.impressora_caixa
        return cfg.impressora_caixa

    def status(self) -> dict:
        cfg = self.config()
        return {"app": "ApFoodPDV", "versao": __version__, "terminal": cfg.nome_terminal,
                "caixa": bool(cfg.impressora_caixa),
                "cozinha": bool(cfg.impressora_cozinha_padrao or cfg.impressora_caixa)}

    def imprimir(self, pedido: dict) -> dict:
        linhas = pedido.get("linhas")
        if not isinstance(linhas, list) or not linhas:
            raise ValueError("envie as linhas do cupom")
        destino = self.destino(pedido)
        if not destino:
            raise ErroImpressao("nenhuma impressora configurada no PDV (Configurações)")
        cfg = self.config()
        feito = self.imprimir_fn(destino, linhas, largura=int(pedido.get("largura") or cfg.largura_bobina),
                                 abrir_gaveta=bool(pedido.get("abrir_gaveta")))
        return {"ok": True, "impressora": feito}

    # ------------------------------------------------------------ servidor
    def iniciar(self) -> bool:
        if not self.porta:
            return False
        try:
            self.servidor = ThreadingHTTPServer(("127.0.0.1", self.porta), _manipulador(self))
        except OSError as e:  # porta ocupada (outro PDV aberto)
            log.warning("ponte de impressão não iniciou na porta %s: %s", self.porta, e)
            return False
        self.servidor.daemon_threads = True
        threading.Thread(target=self.servidor.serve_forever, name="ponte-impressao", daemon=True).start()
        log.info("ponte de impressão em http://127.0.0.1:%s", self.porta)
        return True

    def parar(self) -> None:
        if self.servidor:
            self.servidor.shutdown()
            self.servidor.server_close()
            self.servidor = None


def _manipulador(ponte: Ponte):
    class Manipulador(BaseHTTPRequestHandler):
        server_version = "ApFoodPDV"

        def log_message(self, fmt, *args):  # silencioso (vai para o log do app)
            log.debug("ponte: " + fmt, *args)

        def _origem_ok(self) -> str | None:
            origem = (self.headers.get("Origin") or "").rstrip("/").lower()
            return origem if origem and origem == ponte.origem_permitida() else None

        def _responder(self, codigo: int, corpo: dict | None = None, origem: str | None = None):
            dados = json.dumps(corpo or {}, ensure_ascii=False).encode()
            self.send_response(codigo)
            if origem:
                self.send_header("Access-Control-Allow-Origin", origem)
                self.send_header("Vary", "Origin")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.send_header("Access-Control-Max-Age", "600")
                # Chrome: página https chamando a rede local/127.0.0.1
                self.send_header("Access-Control-Allow-Private-Network", "true")
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(dados)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(dados)

        def do_OPTIONS(self):  # noqa: N802
            origem = self._origem_ok()
            self._responder(204 if origem else 403, None, origem)

        def do_GET(self):  # noqa: N802
            origem = self._origem_ok()
            if self.path.split("?")[0] != "/status":
                return self._responder(404, {"erro": "não encontrado"}, origem)
            if not origem:
                return self._responder(403, {"erro": "origem não autorizada"})
            self._responder(200, ponte.status(), origem)

        def do_POST(self):  # noqa: N802
            origem = self._origem_ok()
            if self.path.split("?")[0] != "/imprimir":
                return self._responder(404, {"erro": "não encontrado"}, origem)
            if not origem:
                return self._responder(403, {"erro": "origem não autorizada"})
            try:
                tamanho = int(self.headers.get("Content-Length") or 0)
                if tamanho <= 0 or tamanho > MAX_CORPO:
                    raise ValueError("corpo inválido")
                pedido = json.loads(self.rfile.read(tamanho))
                if not isinstance(pedido, dict):
                    raise ValueError("corpo inválido")
                self._responder(200, ponte.imprimir(pedido), origem)
            except ErroImpressao as e:
                self._responder(502, {"erro": str(e)}, origem)
            except (ValueError, json.JSONDecodeError) as e:
                self._responder(400, {"erro": str(e)}, origem)
            except Exception as e:  # noqa: BLE001
                log.exception("ponte: falha ao imprimir")
                self._responder(500, {"erro": str(e)}, origem)

    return Manipulador
