-- Geração dos vetores: o cache de `load_index` (storage/vectors.py) se invalida por
-- ela, e não por `mtime` do banco, que não é confiável sob WAL.
--
-- Gatilhos, e não código nos escritores, porque há vários (`store_vectors`, a
-- limpeza de modelo antigo em `indexing/embed.py`, a exclusão em cascata por
-- `chunks`/`documents`, o importador `.rag`, a manutenção). Qualquer um deles que
-- toque `embeddings` incrementa a geração.

INSERT OR IGNORE INTO meta(key, value) VALUES ('vec_gen', '0');

CREATE TRIGGER trg_embeddings_vec_gen_ins AFTER INSERT ON embeddings
BEGIN
  UPDATE meta SET value = CAST(value AS INTEGER) + 1 WHERE key = 'vec_gen';
END;

CREATE TRIGGER trg_embeddings_vec_gen_upd AFTER UPDATE ON embeddings
BEGIN
  UPDATE meta SET value = CAST(value AS INTEGER) + 1 WHERE key = 'vec_gen';
END;

CREATE TRIGGER trg_embeddings_vec_gen_del AFTER DELETE ON embeddings
BEGIN
  UPDATE meta SET value = CAST(value AS INTEGER) + 1 WHERE key = 'vec_gen';
END;
