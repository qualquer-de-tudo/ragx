-- Veredito guardado de arquivo que NÃO entra no índice (RAGX-0139).
--
-- Arquivo `blocked`, `unsupported`, binário ou indecodável nunca vira linha em `documents`,
-- então o atalho de tamanho+mtime nunca valia para ele: toda rodada o relia inteiro e o passava
-- de novo pelo Security Gate. Aqui fica só o RESULTADO (nunca um trecho do arquivo): com
-- tamanho e mtime iguais, e as mesmas regras (`meta.verdict_ctx`), o veredito vale.
-- O cache só pode manter um arquivo FORA do índice; nada entra no índice por causa dele.
-- É estado local e derivado: não vai para `knowledge/` e `ragx index --full` o refaz.

CREATE TABLE file_verdicts (
  rel_path   TEXT PRIMARY KEY,
  verdict    TEXT NOT NULL CHECK (verdict IN ('blocked','unsupported','binary','undecodable')),
  rule_id    TEXT,
  size_bytes INTEGER NOT NULL,
  mtime_ns   INTEGER NOT NULL,
  checked_at TEXT NOT NULL
);
