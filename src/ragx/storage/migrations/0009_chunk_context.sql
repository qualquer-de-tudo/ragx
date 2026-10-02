-- Prefixo de contexto determinístico por chunk (RAGX-0166).
--
-- `context` (caminho, tipo e símbolo, palavras do símbolo, assinatura, primeira frase do docstring) entra no FTS como
-- 4ª coluna e no texto que vai ao embedder. `content` NÃO muda: o agente continua lendo o código sem prefixo, e o
-- `chunk_id` continua sendo o hash do conteúdo. A coluna é anulável: chunk anterior à migração (ou importado) fica com
-- `context` nulo até ser reindexado, e a busca por palavra-chave trata nulo como texto vazio.
ALTER TABLE chunks ADD COLUMN context TEXT;

DROP TRIGGER IF EXISTS chunks_ai;
DROP TRIGGER IF EXISTS chunks_ad;
DROP TRIGGER IF EXISTS chunks_au;
DROP TABLE IF EXISTS chunks_fts;

CREATE VIRTUAL TABLE chunks_fts USING fts5(
  content,
  symbol,
  heading_path,
  context,
  content = 'chunks',
  content_rowid = 'rowid',
  tokenize = 'unicode61 remove_diacritics 2'
);

CREATE TRIGGER chunks_ai AFTER INSERT ON chunks BEGIN
  INSERT INTO chunks_fts(rowid, content, symbol, heading_path, context)
  VALUES (new.rowid, new.content, new.symbol, new.heading_path, new.context);
END;

CREATE TRIGGER chunks_ad AFTER DELETE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rowid, content, symbol, heading_path, context)
  VALUES ('delete', old.rowid, old.content, old.symbol, old.heading_path, old.context);
END;

CREATE TRIGGER chunks_au AFTER UPDATE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rowid, content, symbol, heading_path, context)
  VALUES ('delete', old.rowid, old.content, old.symbol, old.heading_path, old.context);
  INSERT INTO chunks_fts(rowid, content, symbol, heading_path, context)
  VALUES (new.rowid, new.content, new.symbol, new.heading_path, new.context);
END;

INSERT INTO chunks_fts(chunks_fts) VALUES ('rebuild');
