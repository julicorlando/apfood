"""Sincronização PDV <-> servidor. Esqueleto — implementação no Passo 2/3.

Ciclo (a cada N segundos, em thread própria):
  1. PUSH: envia `outbox` em ordem para POST /api/sync/push/ (lote). O servidor
     responde, por operação, ok/erro; ok -> marcar_enviado; erro de rede ->
     para o ciclo e tenta depois; erro de negócio -> marcar_falha e alerta.
  2. PULL: GET /api/sync/pull/?desde=<cursor> por entidade -> aplicar_pull.
Em paralelo, o WebSocket ws/pdv/<loja>/ entrega pedidos online em tempo real
(alerta sonoro). Se o WS cair, o PULL periódico garante que nada se perde.
"""

from __future__ import annotations

import logging
import threading

from .local_db import BancoLocal

log = logging.getLogger(__name__)

ENTIDADES_PULL = [
    "categorias", "produtos", "grupos_adicionais", "adicionais",
    "clientes", "enderecos", "zonas_entrega", "entregadores", "usuarios",
]


class SyncWorker(threading.Thread):
    def __init__(self, banco: BancoLocal, cliente_api, intervalo_s: int = 5):
        super().__init__(daemon=True, name="apfood-sync")
        self.banco = banco
        self.api = cliente_api  # httpx.Client autenticado (Passo 3)
        self.intervalo_s = intervalo_s
        self._parar = threading.Event()
        self.online = False

    def run(self):
        while not self._parar.wait(self.intervalo_s):
            try:
                self.ciclo()
                self.online = True
            except Exception as exc:  # rede caiu: continua offline
                self.online = False
                log.warning("sync falhou: %s", exc)

    def parar(self):
        self._parar.set()

    def ciclo(self):
        raise NotImplementedError("Passo 2/3")
