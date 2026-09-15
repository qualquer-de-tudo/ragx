-- Fase 3 — grafo de conhecimento. Ver docs/06-grafo.md.

CREATE TABLE entities (
  id             TEXT PRIMARY KEY,
  type           TEXT NOT NULL,
  name           TEXT NOT NULL,
  qualified_name TEXT NOT NULL,
  document_id    TEXT REFERENCES documents(id) ON DELETE CASCADE,
  chunk_id       TEXT REFERENCES chunks(id) ON DELETE SET NULL,
  summary        TEXT,
  confidence     REAL NOT NULL DEFAULT 1.0,
  source         TEXT NOT NULL,
  UNIQUE (type, qualified_name)
);
CREATE INDEX idx_entities_name   ON entities(name);
CREATE INDEX idx_entities_type   ON entities(type);
CREATE INDEX idx_entities_doc    ON entities(document_id);
CREATE INDEX idx_entities_source ON entities(source);

CREATE TABLE relations (
  id                TEXT PRIMARY KEY,
  src_id            TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  dst_id            TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  type              TEXT NOT NULL,
  weight            REAL NOT NULL DEFAULT 1.0,
  confidence        REAL NOT NULL DEFAULT 1.0,
  source            TEXT NOT NULL,
  evidence_chunk_id TEXT REFERENCES chunks(id) ON DELETE SET NULL,
  UNIQUE (src_id, dst_id, type)
);
CREATE INDEX idx_relations_src ON relations(src_id, type);
CREATE INDEX idx_relations_dst ON relations(dst_id, type);
