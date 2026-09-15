-- Fase 0 — fundação. Ver docs/03-modelo-de-dados.md.

CREATE TABLE meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE index_runs (
  id          INTEGER PRIMARY KEY,
  started_at  TEXT NOT NULL,
  finished_at TEXT,
  mode        TEXT NOT NULL,
  files_seen  INTEGER NOT NULL DEFAULT 0,
  indexed     INTEGER NOT NULL DEFAULT 0,
  skipped     INTEGER NOT NULL DEFAULT 0,
  blocked     INTEGER NOT NULL DEFAULT 0,
  removed     INTEGER NOT NULL DEFAULT 0,
  chunks      INTEGER NOT NULL DEFAULT 0,
  embedded    INTEGER NOT NULL DEFAULT 0,
  duration_ms INTEGER,
  error       TEXT
);

-- Invariante testável: NENHUMA coluna desta tabela pode conter o valor do segredo.
CREATE TABLE security_events (
  id          INTEGER PRIMARY KEY,
  run_id      INTEGER REFERENCES index_runs(id) ON DELETE SET NULL,
  path        TEXT NOT NULL,
  rule_id     TEXT NOT NULL,
  severity    TEXT NOT NULL,
  action      TEXT NOT NULL,
  line        INTEGER,
  digest      TEXT,
  preview     TEXT,
  detected_at TEXT NOT NULL
);
CREATE INDEX idx_secev_path ON security_events(path);
CREATE INDEX idx_secev_rule ON security_events(rule_id, severity);
