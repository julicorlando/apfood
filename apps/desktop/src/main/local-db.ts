import Database from 'better-sqlite3';

/**
 * Banco local do PDV (SQLite, modo WAL). Não é uma réplica completa do
 * PostgreSQL: guarda apenas o necessário para operar sem internet.
 *
 *  cache_*   → espelho somente-leitura do catálogo/clientes (pull do servidor)
 *  outbox    → operações feitas offline, enviadas em ordem quando voltar a rede
 *  sync_meta → cursores de pull por entidade
 */
const SCHEMA = `
CREATE TABLE IF NOT EXISTS sync_meta (
  entidade    TEXT PRIMARY KEY,
  cursor      TEXT NOT NULL            -- updatedAt ISO do último registro recebido
);

CREATE TABLE IF NOT EXISTS cache_registros (
  entidade    TEXT NOT NULL,           -- 'produto' | 'categoria' | 'grupo_adicional' | 'cliente' | ...
  id          TEXT NOT NULL,
  dados       TEXT NOT NULL,           -- JSON
  updated_at  TEXT NOT NULL,
  deleted     INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (entidade, id)
);

CREATE TABLE IF NOT EXISTS outbox (
  seq          INTEGER PRIMARY KEY AUTOINCREMENT,
  id           TEXT NOT NULL UNIQUE,   -- UUID da operação (idempotência no servidor)
  tipo         TEXT NOT NULL,          -- 'pedido.criar' | 'turno.abrir' | 'caixa.sangria' | ...
  payload      TEXT NOT NULL,          -- JSON validado pelos schemas do @apfood/shared
  criado_em    TEXT NOT NULL,
  tentativas   INTEGER NOT NULL DEFAULT 0,
  ultimo_erro  TEXT,
  enviado_em   TEXT                    -- NULL = pendente
);
CREATE INDEX IF NOT EXISTS outbox_pendentes ON outbox (enviado_em, seq);
`;

let db: Database.Database | null = null;

export function abrirBancoLocal(caminho: string) {
  db = new Database(caminho);
  db.pragma('journal_mode = WAL');
  db.pragma('foreign_keys = ON');
  db.exec(SCHEMA);
  return db;
}

export function bancoLocal(): Database.Database {
  if (!db) throw new Error('Banco local não inicializado');
  return db;
}
