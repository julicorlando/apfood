"""Sincronização PDV ⇄ servidor, em thread própria.

Ciclo (a cada N s ou quando `acordar()` é chamado):
  1. PUSH da outbox em ordem (lotes de 50). Operação aceita → enviada;
     recusada pelo servidor (regra de negócio) → rejeitada (avisa o operador e
     NÃO trava a fila); falha de rede → para e tenta no próximo ciclo.
  2. PULL dos cadastros alterados desde o último cursor de cada entidade.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from .api import ApiClient, ErroApi, SemConexao
from .local_db import BancoLocal

log = logging.getLogger(__name__)

ENTIDADES_PULL = ["setores", "categorias", "produtos", "variacoes", "grupos_adicionais", "adicionais",
                  "clientes", "enderecos", "zonas_entrega", "entregadores", "mesas"]


class Sincronizador:
    """Lógica de um ciclo (testável sem thread)."""

    def __init__(self, banco: BancoLocal, api: ApiClient):
        self.banco, self.api = banco, api
        self.ao_rejeitar: Callable[[str, str, str], None] | None = None  # (op_id, operacao, erro)

    def push(self) -> int:
        enviados = 0
        while ops := self.banco.pendentes(50):
            lote = [{"id": o.id, "operacao": o.operacao, "payload": o.payload} for o in ops]
            resp = self.api.post("/api/sync/push/", {"operacoes": lote})
            for r in resp["resultados"]:
                if r.get("ok"):
                    self.banco.marcar_enviado(r["id"], r.get("resultado"))
                    enviados += 1
                else:
                    erro = r.get("erro") or "recusada"
                    self.banco.marcar_rejeitada(r["id"], erro)
                    op = next((o for o in ops if o.id == r["id"]), None)
                    if self.ao_rejeitar and op:
                        self.ao_rejeitar(r["id"], op.operacao, erro)
            if len(ops) < 50:
                break
        return enviados

    def pull(self) -> int:
        recebidos = 0
        params = {"entidades": ",".join(ENTIDADES_PULL)}
        for e in ENTIDADES_PULL:
            if c := self.banco.cursor(e):
                params[f"desde_{e}"] = c
        resp = self.api.get("/api/sync/pull/", **params)
        for nome, bloco in resp["entidades"].items():
            self.banco.aplicar_pull(nome, bloco["registros"])
            recebidos += len(bloco["registros"])
        return recebidos

    def ciclo(self) -> dict:
        return {"enviados": self.push(), "recebidos": self.pull()}


class SyncWorker(threading.Thread):
    def __init__(self, sincronizador: Sincronizador, intervalo_s: int = 5,
                 ao_mudar_estado: Callable[[bool, int], None] | None = None):
        super().__init__(daemon=True, name="apfood-sync")
        self.s = sincronizador
        self.intervalo_s = intervalo_s
        self.ao_mudar_estado = ao_mudar_estado
        self._parar, self._acordar = threading.Event(), threading.Event()
        self.online = False

    def acordar(self):
        self._acordar.set()

    def parar(self):
        self._parar.set()
        self._acordar.set()

    def run(self):
        while not self._parar.is_set():
            try:
                self.s.ciclo()
                self._estado(True)
            except SemConexao as exc:
                log.info("offline: %s", exc)
                self._estado(False)
            except ErroApi as exc:  # sessão expirada etc.
                log.warning("sync: %s", exc)
                self._estado(exc.status not in (401, 403))
            except Exception:  # noqa: BLE001
                log.exception("sync: erro inesperado")
            self._acordar.wait(self.intervalo_s)
            self._acordar.clear()

    def _estado(self, online: bool):
        self.online = online
        if self.ao_mudar_estado:
            self.ao_mudar_estado(online, self.s.banco.total_pendentes())
