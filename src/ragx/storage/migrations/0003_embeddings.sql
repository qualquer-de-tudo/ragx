-- Fase 2 — embeddings em duas representações (ADR-0010):
--   vector   float32 @ dim           -> LOCAL, rescoring exato, pode ser NULL
--   vector_q int8    @ versioned_dim -> VERSIONADO, busca grosseira

CREATE TABLE embedding_models (
  id            TEXT PRIMARY KEY,
  dim           INTEGER NOT NULL,
  versioned_dim INTEGER NOT NULL,
  quant         TEXT NOT NULL,
  normalized    INTEGER NOT NULL DEFAULT 1,
  created_at    TEXT NOT NULL
);

CREATE TABLE embeddings (
  chunk_id   TEXT NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
  model_id   TEXT NOT NULL REFERENCES embedding_models(id),
  vector     BLOB,
  vector_q   BLOB NOT NULL,
  q_scale    REAL NOT NULL,
  q_offset   REAL NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (chunk_id, model_id)
);
CREATE INDEX idx_emb_model ON embeddings(model_id);
