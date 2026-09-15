-- Fase 11 — superfície pública do projeto. Ver docs/17-multiprojeto-e-federacao.md.

CREATE TABLE federation_surface (
  id          TEXT PRIMARY KEY,
  direction   TEXT NOT NULL,          -- provides | consumes
  kind        TEXT NOT NULL,          -- http | event | package | table
  normalized  TEXT NOT NULL,
  raw         TEXT NOT NULL,
  handler     TEXT,
  contract    TEXT,
  source_ref  TEXT NOT NULL,
  confidence  REAL NOT NULL DEFAULT 1.0,
  detected_by TEXT NOT NULL,
  manual      INTEGER NOT NULL DEFAULT 0,
  UNIQUE (direction, kind, normalized)
);
CREATE INDEX idx_fedsurf_dir ON federation_surface(direction, kind);
