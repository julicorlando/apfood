"""Banco local do PDV (SQLite, só biblioteca padrão).

Duas responsabilidades:
  1. CACHE de cadastros (produtos, adicionais, clientes, zonas...) para o PDV
     continuar vendendo sem internet. Atualizado por "pull" incremental usando
     o cursor `atualizado_em` do servidor.
  2. OUTBOX: toda operação feita no PDV (pedido, pagamento, sangria, abertura e
     fechamento de caixa) vira uma linha na fila ANTES de ir para a API. O
     worker de sync envia em ordem; cada operação carrega um UUID gerado aqui,
     então reenviar é idempotente (o servidor faz upsert).
"""

from __future__ import annotations

import functools
import json
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS cache (
    entidade      TEXT NOT NULL,          -- 'produto', 'cliente', 'zona_entrega'...
    id            TEXT NOT NULL,
    dados         TEXT NOT NULL,          -- JSON como veio da API
    atualizado_em TEXT NOT NULL,
    excluido      INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (entidade, id)
);

CREATE TABLE IF NOT EXISTS cursor_sync (
    entidade      TEXT PRIMARY KEY,
    atualizado_em TEXT NOT NULL           -- maior atualizado_em já recebido
);

CREATE TABLE IF NOT EXISTS outbox (
    seq          INTEGER PRIMARY KEY AUTOINCREMENT,
    id           TEXT NOT NULL UNIQUE,    -- UUID da operação (idempotência)
    operacao     TEXT NOT NULL,           -- 'pedido.criar', 'caixa.sangria'...
    payload      TEXT NOT NULL,
    criado_em    TEXT NOT NULL,
    tentativas   INTEGER NOT NULL DEFAULT 0,
    ultimo_erro  TEXT,
    enviado_em   TEXT,
    rejeitada_em TEXT,                    -- servidor recusou (regra de negócio): não bloqueia a fila
    resultado    TEXT
);

CREATE TABLE IF NOT EXISTS kv (
    chave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS outbox_pendentes ON outbox (enviado_em, seq);
"""


def _agora() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True, slots=True)
class Operacao:
    seq: int
    id: str
    operacao: str
    payload: dict
    tentativas: int


def _travado(fn):
    """Uma conexão, duas threads (UI + sync): serializa o acesso."""

    @functools.wraps(fn)
    def envolto(self, *a, **kw):
        with self._trava:
            return fn(self, *a, **kw)

    return envolto


class BancoLocal:
    def __init__(self, caminho: str | Path = ":memory:"):
        self._trava = threading.RLock()
        self.conn = sqlite3.connect(str(caminho), isolation_level=None, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self._migrar()

    def _migrar(self):
        """Bancos criados por versões antigas do PDV."""
        colunas = {r[1] for r in self.conn.execute("PRAGMA table_info(outbox)")}
        for nome in ("rejeitada_em", "resultado"):
            if nome not in colunas:
                self.conn.execute(f"ALTER TABLE outbox ADD COLUMN {nome} TEXT")

    # --- outbox -------------------------------------------------------------
    @_travado
    def enfileirar(self, operacao: str, payload: dict, op_id: str | None = None) -> str:
        op_id = op_id or str(uuid.uuid4())
        self.conn.execute(
            "INSERT OR IGNORE INTO outbox (id, operacao, payload, criado_em) VALUES (?, ?, ?, ?)",
            (op_id, operacao, json.dumps(payload, default=str), _agora()),
        )
        return op_id

    @_travado
    def pendentes(self, limite: int = 50) -> list[Operacao]:
        rows = self.conn.execute(
            "SELECT seq, id, operacao, payload, tentativas FROM outbox "
            "WHERE enviado_em IS NULL AND rejeitada_em IS NULL ORDER BY seq LIMIT ?",
            (limite,),
        ).fetchall()
        return [
            Operacao(r["seq"], r["id"], r["operacao"], json.loads(r["payload"]), r["tentativas"])
            for r in rows
        ]

    @_travado
    def marcar_enviado(self, op_id: str, resultado: dict | None = None) -> None:
        self.conn.execute("UPDATE outbox SET enviado_em = ?, resultado = ? WHERE id = ?",
                          (_agora(), json.dumps(resultado or {}, default=str), op_id))

    @_travado
    def marcar_rejeitada(self, op_id: str, erro: str) -> None:
        self.conn.execute("UPDATE outbox SET rejeitada_em = ?, ultimo_erro = ? WHERE id = ?",
                          (_agora(), erro[:500], op_id))

    @_travado
    def rejeitadas(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, operacao, payload, ultimo_erro, rejeitada_em FROM outbox WHERE rejeitada_em IS NOT NULL "
            "ORDER BY seq DESC LIMIT 100").fetchall()
        return [dict(r) | {"payload": json.loads(r["payload"])} for r in rows]

    @_travado
    def resultado(self, op_id: str) -> dict | None:
        row = self.conn.execute("SELECT resultado FROM outbox WHERE id = ?", (op_id,)).fetchone()
        return json.loads(row[0]) if row and row[0] else None

    # --- chave/valor (sessão, sequências) -------------------------------------
    @_travado
    def ler(self, chave: str, padrao=None):
        row = self.conn.execute("SELECT valor FROM kv WHERE chave = ?", (chave,)).fetchone()
        return json.loads(row[0]) if row else padrao

    @_travado
    def gravar(self, chave: str, valor) -> None:
        self.conn.execute("INSERT INTO kv (chave, valor) VALUES (?, ?) ON CONFLICT (chave) DO UPDATE SET "
                          "valor = excluded.valor", (chave, json.dumps(valor, default=str)))

    @_travado
    def proximo(self, chave: str) -> int:
        n = int(self.ler(chave, 0)) + 1
        self.gravar(chave, n)
        return n

    @_travado
    def marcar_falha(self, op_id: str, erro: str) -> None:
        self.conn.execute(
            "UPDATE outbox SET tentativas = tentativas + 1, ultimo_erro = ? WHERE id = ?",
            (erro[:500], op_id),
        )

    @_travado
    def total_pendentes(self) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) FROM outbox WHERE enviado_em IS NULL AND rejeitada_em IS NULL").fetchone()[0]

    # --- cache --------------------------------------------------------------
    @_travado
    def aplicar_pull(self, entidade: str, registros: list[dict]) -> None:
        """Grava registros vindos da API e avança o cursor da entidade."""
        if not registros:
            return
        with self.conn:
            self.conn.execute("BEGIN")
            for r in registros:
                self.conn.execute(
                    "INSERT INTO cache (entidade, id, dados, atualizado_em, excluido) "
                    "VALUES (?, ?, ?, ?, ?) ON CONFLICT (entidade, id) DO UPDATE SET "
                    "dados = excluded.dados, atualizado_em = excluded.atualizado_em, "
                    "excluido = excluded.excluido",
                    (
                        entidade,
                        str(r["id"]),
                        json.dumps(r, default=str),
                        r["atualizado_em"],
                        1 if r.get("excluido_em") else 0,
                    ),
                )
            maior = max(r["atualizado_em"] for r in registros)
            self.conn.execute(
                "INSERT INTO cursor_sync (entidade, atualizado_em) VALUES (?, ?) "
                "ON CONFLICT (entidade) DO UPDATE SET atualizado_em = "
                "MAX(cursor_sync.atualizado_em, excluded.atualizado_em)",
                (entidade, maior),
            )

    @_travado
    def cursor(self, entidade: str) -> str | None:
        row = self.conn.execute(
            "SELECT atualizado_em FROM cursor_sync WHERE entidade = ?", (entidade,)
        ).fetchone()
        return row[0] if row else None

    @_travado
    def obter(self, entidade: str, id_: str) -> dict | None:
        row = self.conn.execute("SELECT dados FROM cache WHERE entidade = ? AND id = ? AND excluido = 0",
                                (entidade, str(id_))).fetchone()
        return json.loads(row[0]) if row else None

    @_travado
    def listar(self, entidade: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT dados FROM cache WHERE entidade = ? AND excluido = 0", (entidade,)
        ).fetchall()
        return [json.loads(r[0]) for r in rows]
