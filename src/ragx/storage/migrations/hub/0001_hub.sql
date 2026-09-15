-- Hub multiprojeto. Derivado, local da máquina, NUNCA versionado.

CREATE TABLE projects (
  id              TEXT PRIMARY KEY,
  name            TEXT NOT NULL UNIQUE,
  path            TEXT,
  cloned          INTEGER NOT NULL DEFAULT 0,
  remote_hash     TEXT,
  embedding_model TEXT,
  embedding_dim   INTEGER,
  versioned_dim   INTEGER,
  visibility      TEXT NOT NULL DEFAULT 'workspace',
  status          TEXT NOT NULL DEFAULT 'ok',
  chunks          INTEGER NOT NULL DEFAULT 0,
  last_sync       TEXT,
  manifest_hash   TEXT
);

CREATE TABLE federation_items (
  id            TEXT NOT NULL,
  project_id    TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  direction     TEXT NOT NULL,
  kind          TEXT NOT NULL,
  normalized    TEXT NOT NULL,
  raw           TEXT NOT NULL,
  handler       TEXT,
  contract_body TEXT,
  source_ref    TEXT NOT NULL,
  confidence    REAL NOT NULL DEFAULT 1.0,
  PRIMARY KEY (project_id, id)
);
CREATE INDEX idx_fed_norm ON federation_items(kind, normalized, direction);

CREATE TABLE cross_links (
  id          TEXT PRIMARY KEY,
  src_project TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  dst_project TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  kind        TEXT NOT NULL,
  normalized  TEXT NOT NULL,
  relation    TEXT NOT NULL,
  confidence  REAL NOT NULL,
  evidence    TEXT NOT NULL,
  resolved_at TEXT NOT NULL
);

CREATE TABLE unresolved (
  id          TEXT PRIMARY KEY,
  src_project TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  kind        TEXT NOT NULL,
  normalized  TEXT NOT NULL,
  reason      TEXT NOT NULL,
  detail      TEXT,
  detected_at TEXT NOT NULL
);
