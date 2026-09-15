-- Fase 1 — documentos, chunks e busca por palavra-chave.

CREATE TABLE documents (
  id              TEXT PRIMARY KEY,
  rel_path        TEXT NOT NULL UNIQUE,
  lang            TEXT,
  doc_kind        TEXT NOT NULL,
  size_bytes      INTEGER NOT NULL,
  mtime_ns        INTEGER NOT NULL,
  content_hash    TEXT NOT NULL,
  redacted        INTEGER NOT NULL DEFAULT 0,
  title           TEXT,
  summary         TEXT,
  indexed_at      TEXT NOT NULL,
  chunker_version TEXT NOT NULL
);
CREATE INDEX idx_documents_hash ON documents(content_hash);
CREATE INDEX idx_documents_lang ON documents(lang);

CREATE TABLE chunks (
  id           TEXT PRIMARY KEY,
  document_id  TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  ordinal      INTEGER NOT NULL,
  parent_id    TEXT REFERENCES chunks(id) ON DELETE CASCADE,
  kind         TEXT NOT NULL,
  symbol       TEXT,
  heading_path TEXT,
  start_line   INTEGER NOT NULL,
  end_line     INTEGER NOT NULL,
  content      TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  token_count  INTEGER NOT NULL,
  created_at   TEXT NOT NULL,
  UNIQUE (document_id, ordinal)
);
CREATE INDEX idx_chunks_doc    ON chunks(document_id);
CREATE INDEX idx_chunks_hash   ON chunks(content_hash);
CREATE INDEX idx_chunks_symbol ON chunks(symbol);

-- remove_diacritics 2: a base é em português; 'autenticacao' precisa casar
-- com 'autenticação'.
CREATE VIRTUAL TABLE chunks_fts USING fts5(
  content,
  symbol,
  heading_path,
  content = 'chunks',
  content_rowid = 'rowid',
  tokenize = 'unicode61 remove_diacritics 2'
);

CREATE TRIGGER chunks_ai AFTER INSERT ON chunks BEGIN
  INSERT INTO chunks_fts(rowid, content, symbol, heading_path)
  VALUES (new.rowid, new.content, new.symbol, new.heading_path);
END;

CREATE TRIGGER chunks_ad AFTER DELETE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rowid, content, symbol, heading_path)
  VALUES ('delete', old.rowid, old.content, old.symbol, old.heading_path);
END;

CREATE TRIGGER chunks_au AFTER UPDATE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rowid, content, symbol, heading_path)
  VALUES ('delete', old.rowid, old.content, old.symbol, old.heading_path);
  INSERT INTO chunks_fts(rowid, content, symbol, heading_path)
  VALUES (new.rowid, new.content, new.symbol, new.heading_path);
END;
