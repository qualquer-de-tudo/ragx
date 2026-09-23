# 03 — Modelo de dados

Dois bancos SQLite, com papéis distintos ([ADR-0002](adr/ADR-0002-sqlite-como-store-unico.md),
[ADR-0009](adr/ADR-0009-tres-camadas-de-conhecimento.md)):

| Banco | Escopo | Conteúdo |
|-------|--------|----------|
| `.ragx/knowledge.db` | um projeto | documentos, chunks, embeddings, grafo — fidelidade total |
| `~/.ragx/hub/hub.db` | a máquina | registro de projetos, fatias de federação, vínculos cross-project |

Ambos derivados, ambos descartáveis, nenhum versionado.

## Pragmas de abertura

```sql
PRAGMA journal_mode = WAL;        -- leitura concorrente (CLI + MCP)
PRAGMA synchronous  = NORMAL;     -- durabilidade suficiente para dado derivável
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;
PRAGMA temp_store   = MEMORY;
PRAGMA mmap_size    = 268435456;  -- 256 MB
```

## Migrações

Arquivos `src/ragx/storage/migrations/NNNN_nome.sql`, aplicados em ordem dentro de
uma transação, controlados por `PRAGMA user_version`. Sem ORM, sem Alembic:
o schema é pequeno e explícito.

| Migração | Fase | Conteúdo |
|----------|------|----------|
| `0001_init.sql` | 0 | `meta`, `index_runs`, `security_events` |
| `0002_documents.sql` | 1 | `documents`, `chunks`, `chunks_fts` |
| `0003_embeddings.sql` | 2 | `embeddings`, `embedding_models` |
| `0004_graph.sql` | 3 | `entities`, `relations` |
| `0005_dictionary.sql` | 5 | `dictionary_artifacts` |
| `0006_agents.sql` | 7 | `agent_profiles`, `agent_evaluations` |
| `0007_sync.sql` | 9 | `sync_state` |
| `0008_federation.sql` | 11 | `federation_surface` (no banco do projeto) |

Migrações do hub ficam em `migrations/hub/NNNN_*.sql`, com `user_version` próprio.

## Schema

### `meta` / `index_runs`

```sql
CREATE TABLE meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
-- chaves: schema_version, ragx_version, project_id, project_name, chunker_version,
--         ruleset_version, embedding_model, embedding_dim, versioned_dim,
--         visibility, last_sync_commit, created_at

CREATE TABLE index_runs (
  id           INTEGER PRIMARY KEY,
  started_at   TEXT NOT NULL,
  finished_at  TEXT,
  mode         TEXT NOT NULL,          -- full | incremental | sync | embed-only
  files_seen   INTEGER NOT NULL DEFAULT 0,
  indexed      INTEGER NOT NULL DEFAULT 0,
  skipped      INTEGER NOT NULL DEFAULT 0,
  blocked      INTEGER NOT NULL DEFAULT 0,
  removed      INTEGER NOT NULL DEFAULT 0,
  chunks       INTEGER NOT NULL DEFAULT 0,
  embedded     INTEGER NOT NULL DEFAULT 0,
  duration_ms  INTEGER,
  error        TEXT,
  git_branch   TEXT,                  -- null sem git ou com HEAD destacado
  git_commit   TEXT,                  -- null sem git
  git_dirty    INTEGER,               -- 0/1, null sem git
  source       TEXT NOT NULL DEFAULT 'cli'  -- cli | panel | watch | sync | mcp:* | hook:*
);
```

`git_branch`, `git_commit`, `git_dirty` e `source` vieram da migração
`0006_run_provenance.sql`, que faz só `ALTER TABLE ADD COLUMN` (sem `NOT NULL`
nas três de git, porque um projeto sem repositório Git nunca as preenche).
`mode` ganhou o valor `embed-only`, de `ragx index --embed-only` (só gera
vetores faltantes, sem varrer o projeto de novo).

### `.ragx/status.json`

Não é tabela: é um arquivo JSON derivado de `index_runs`, `embeddings` e da
trava (`index.lock`/`index.pending`), pensado para quem quer o estado do
índice sem abrir o SQLite (o painel, por exemplo).

```json
{
  "schema_version": 1,
  "written_at": "2026-09-23T12:00:00Z",
  "project": {"id": "t", "name": "t", "root": "C:/x/t"},
  "index": {"finished_at": "...", "mode": "incremental", "source": "cli",
            "branch": "main", "commit": "abc...", "dirty": false},
  "counts": {"documents": 4, "chunks": 10, "embeddings": 10, "pending_embeddings": 0},
  "embedding": {"provider": "ollama", "model": "nomic-embed-text"},
  "hooks": {"installed": null},
  "running": null,
  "pending": false,
  "last_error": null
}
```

Regras:

- Escrita atômica: grava num temporário e faz `os.replace` no lugar do arquivo
  final, para ninguém ler JSON pela metade.
- Só contagens e metadados, nenhum caminho de arquivo do projeto.
- Reescrito no início e no fim de cada indexação (e também quando a trava fica
  ocupada, para `pending` aparecer na hora) e ao instalar ou remover hooks.
- `index` é o último run com `finished_at` (`null` se não houver nenhum).
  `running` é o dono da trava quando o processo está vivo, senão `null`.
  `hooks.installed` é `null` quando o projeto não está dentro de um
  repositório Git.

### `security_events` — sem segredo, só prova

```sql
CREATE TABLE security_events (
  id          INTEGER PRIMARY KEY,
  run_id      INTEGER REFERENCES index_runs(id) ON DELETE SET NULL,
  path        TEXT NOT NULL,           -- caminho relativo à raiz
  rule_id     TEXT NOT NULL,
  severity    TEXT NOT NULL,           -- critical | high | medium | low
  action      TEXT NOT NULL,           -- block | redact | warn
  line        INTEGER,
  digest      TEXT,                    -- sha256(valor)[:16] — NUNCA o valor
  preview     TEXT,                    -- "sk-a…5f2c"
  detected_at TEXT NOT NULL
);
CREATE INDEX idx_secev_path ON security_events(path);
CREATE INDEX idx_secev_rule ON security_events(rule_id, severity);
```

> Invariante testável: nenhuma coluna desta tabela pode conter o valor original.
> Teste de segurança faz `SELECT` em todas as colunas TEXT e procura os segredos
> da fixture.

### `documents`

```sql
CREATE TABLE documents (
  id            TEXT PRIMARY KEY,      -- sha256(rel_path)[:32]
  rel_path      TEXT NOT NULL UNIQUE,
  lang          TEXT,                  -- python | markdown | php | ...
  doc_kind      TEXT NOT NULL,         -- code | doc | config | data
  size_bytes    INTEGER NOT NULL,
  mtime_ns      INTEGER NOT NULL,
  content_hash  TEXT NOT NULL,         -- sha256 do conteúdo normalizado
  redacted      INTEGER NOT NULL DEFAULT 0,
  title         TEXT,
  summary       TEXT,                  -- preenchido na Fase 5
  indexed_at    TEXT NOT NULL,
  chunker_version TEXT NOT NULL
);
CREATE INDEX idx_documents_hash ON documents(content_hash);
CREATE INDEX idx_documents_lang ON documents(lang);
```

### `chunks`

```sql
CREATE TABLE chunks (
  id            TEXT PRIMARY KEY,      -- ID determinístico, ver abaixo
  document_id   TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  ordinal       INTEGER NOT NULL,      -- ordem dentro do documento
  parent_id     TEXT REFERENCES chunks(id) ON DELETE CASCADE,  -- classe -> método
  kind          TEXT NOT NULL,         -- file | class | function | method | section | block
  symbol        TEXT,                  -- "AuthService.login"
  heading_path  TEXT,                  -- "Arquitetura > Autenticação > SSO"
  start_line    INTEGER NOT NULL,
  end_line      INTEGER NOT NULL,
  content       TEXT NOT NULL,
  content_hash  TEXT NOT NULL,
  token_count   INTEGER NOT NULL,
  created_at    TEXT NOT NULL,
  UNIQUE (document_id, ordinal)
);
CREATE INDEX idx_chunks_doc    ON chunks(document_id);
CREATE INDEX idx_chunks_hash   ON chunks(content_hash);
CREATE INDEX idx_chunks_symbol ON chunks(symbol);
```

### `chunks_fts` — busca keyword

FTS5 com *external content* (não duplica o texto):

```sql
CREATE VIRTUAL TABLE chunks_fts USING fts5(
  content,
  symbol,
  heading_path,
  content = 'chunks',
  content_rowid = 'rowid',
  tokenize = 'unicode61 remove_diacritics 2'
);
-- + triggers AFTER INSERT/UPDATE/DELETE em chunks para manter sincronizado
```

`tokenize = unicode61 remove_diacritics 2` é deliberado: a base é em português e
`autenticacao` precisa casar com `autenticação`.

### `embeddings`

```sql
CREATE TABLE embedding_models (
  id            TEXT PRIMARY KEY,      -- "ollama:nomic-embed-text"
  dim           INTEGER NOT NULL,      -- dimensão nativa (768)
  versioned_dim INTEGER NOT NULL,      -- dimensão truncada para o Git (256)
  quant         TEXT NOT NULL,         -- none | int8
  normalized    INTEGER NOT NULL DEFAULT 1,
  created_at    TEXT NOT NULL
);

CREATE TABLE embeddings (
  chunk_id   TEXT NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
  model_id   TEXT NOT NULL REFERENCES embedding_models(id),
  vector     BLOB,                     -- float32 LE, dim*4 — LOCAL, pode ser NULL
  vector_q   BLOB NOT NULL,            -- int8, versioned_dim bytes — versionado
  q_scale    REAL NOT NULL,            -- desquantização: v ≈ q * scale + offset
  q_offset   REAL NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (chunk_id, model_id)
);
CREATE INDEX idx_emb_model ON embeddings(model_id);
```

Duas representações por chunk, por decisão de orçamento
([ADR-0010](adr/ADR-0010-conteudo-nao-versionado-e-embeddings-quantizados.md)):

| Coluna | Formato | Bytes | Onde vive | Papel |
|--------|---------|-------|-----------|-------|
| `vector` | float32 @ 768d | 3.072 | só `.ragx/` | rescoring exato |
| `vector_q` | int8 @ 256d | 256 | vai para `knowledge/` | busca grosseira |

`vector` é `NULL` logo após um `git clone` — a busca funciona só com `vector_q`,
com qualidade um pouco menor, e `ragx sync` preenche quando houver embedder.

Vetores são gravados **já normalizados** (norma L2 = 1), então similaridade de
cosseno vira produto escalar. Ver [ADR-0003](adr/ADR-0003-busca-vetorial.md).

Quantização por vetor (escala e offset próprios de cada vetor, não globais):

```python
def quantize(v: np.ndarray, dim: int) -> tuple[bytes, float, float]:
    t = v[:dim]                          # truncagem Matryoshka
    t = t / np.linalg.norm(t)            # renormaliza após truncar
    lo, hi = float(t.min()), float(t.max())
    scale = (hi - lo) / 255.0 or 1e-8
    q = np.round((t - lo) / scale).astype(np.uint8)
    return q.tobytes(), scale, lo
```

A renormalização depois da truncagem não é detalhe: sem ela o produto escalar deixa
de aproximar cosseno e o ranking degrada de forma silenciosa.

### `entities` / `relations` (Fase 3)

```sql
CREATE TABLE entities (
  id             TEXT PRIMARY KEY,     -- sha256(type + "\0" + qualified_name)[:32]
  type           TEXT NOT NULL,        -- file|class|function|service|technology|concept|endpoint|table
  name           TEXT NOT NULL,
  qualified_name TEXT NOT NULL,
  document_id    TEXT REFERENCES documents(id) ON DELETE CASCADE,
  chunk_id       TEXT REFERENCES chunks(id) ON DELETE SET NULL,
  summary        TEXT,
  confidence     REAL NOT NULL DEFAULT 1.0,
  source         TEXT NOT NULL,        -- structural | reference | semantic
  UNIQUE (type, qualified_name)
);
CREATE INDEX idx_entities_name ON entities(name);

CREATE TABLE relations (
  id          TEXT PRIMARY KEY,        -- sha256(src + type + dst)[:32]
  src_id      TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  dst_id      TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  type        TEXT NOT NULL,           -- contains|calls|imports|uses|implements|documented_by|depends_on
  weight      REAL NOT NULL DEFAULT 1.0,
  confidence  REAL NOT NULL DEFAULT 1.0,
  source      TEXT NOT NULL,
  evidence_chunk_id TEXT REFERENCES chunks(id) ON DELETE SET NULL,
  UNIQUE (src_id, dst_id, type)
);
CREATE INDEX idx_relations_src ON relations(src_id, type);
CREATE INDEX idx_relations_dst ON relations(dst_id, type);
```

### `sync_state` (Fase 9)

```sql
CREATE TABLE sync_state (
  rel_path      TEXT PRIMARY KEY,
  content_hash  TEXT NOT NULL,
  git_blob_sha  TEXT,
  rehydrated_at TEXT,                  -- última reidratação bem-sucedida
  rehydrate_status TEXT,               -- ok | hash_mismatch | file_missing
  last_seen_run INTEGER NOT NULL REFERENCES index_runs(id)
);
```

### `federation_surface` (Fase 11, banco do projeto)

Superfície pública derivada do grafo, materializada para gerar a fatia:

```sql
CREATE TABLE federation_surface (
  id          TEXT PRIMARY KEY,        -- sha256(direction + kind + normalized)[:32]
  direction   TEXT NOT NULL,           -- provides | consumes
  kind        TEXT NOT NULL,           -- http | event | package | table
  normalized  TEXT NOT NULL,           -- "POST /api/payments" | "payment.captured"
  raw         TEXT NOT NULL,           -- forma original, antes da normalização
  handler     TEXT,                    -- símbolo que serve/consome
  contract    TEXT,                    -- caminho do schema, quando existir
  source_ref  TEXT NOT NULL,           -- "routes/api.php:42"
  confidence  REAL NOT NULL DEFAULT 1.0,
  detected_by TEXT NOT NULL,
  manual      INTEGER NOT NULL DEFAULT 0,   -- 1 = curado à mão, vence o derivado
  UNIQUE (direction, kind, normalized)
);
```

## Schema do hub (`~/.ragx/hub/hub.db`)

```sql
CREATE TABLE projects (
  id              TEXT PRIMARY KEY,    -- project_id do projeto
  name            TEXT NOT NULL UNIQUE,
  path            TEXT,                -- NULL quando só-federação
  cloned          INTEGER NOT NULL DEFAULT 0,
  remote_hash     TEXT,
  embedding_model TEXT,
  embedding_dim   INTEGER,
  versioned_dim   INTEGER,
  visibility      TEXT NOT NULL DEFAULT 'workspace',  -- workspace | private
  status          TEXT NOT NULL DEFAULT 'ok',         -- ok | missing | stale | degraded
  chunks          INTEGER NOT NULL DEFAULT 0,
  last_sync       TEXT,
  manifest_hash   TEXT                 -- para sync incremental do hub
);

CREATE TABLE federation_items (
  id          TEXT NOT NULL,
  project_id  TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  direction   TEXT NOT NULL,
  kind        TEXT NOT NULL,
  normalized  TEXT NOT NULL,
  raw         TEXT NOT NULL,
  handler     TEXT,
  contract_body TEXT,                  -- POR VALOR: funciona sem o repo clonado
  source_ref  TEXT NOT NULL,
  confidence  REAL NOT NULL DEFAULT 1.0,
  PRIMARY KEY (project_id, id)
);
CREATE INDEX idx_fed_norm ON federation_items(kind, normalized, direction);

CREATE TABLE cross_links (
  id           TEXT PRIMARY KEY,       -- sha256(src_project + dst_project + normalized)[:32]
  src_project  TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  dst_project  TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  kind         TEXT NOT NULL,          -- http | event | package | table
  normalized   TEXT NOT NULL,
  relation     TEXT NOT NULL,          -- consumes | publishes | subscribes | depends_on
  confidence   REAL NOT NULL,
  evidence     TEXT NOT NULL,          -- "contract" | "method+path" | "name"
  resolved_at  TEXT NOT NULL
);

CREATE TABLE unresolved (
  id          TEXT PRIMARY KEY,
  src_project TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  kind        TEXT NOT NULL,
  normalized  TEXT NOT NULL,
  reason      TEXT NOT NULL,           -- no_provider | method_mismatch | ambiguous
  detail      TEXT,
  detected_at TEXT NOT NULL
);
```

`unresolved` é tabela de primeira classe, não log: consumo sem provedor e divergência
de método são os achados mais úteis da federação (ver
[17 — Multiprojeto](17-multiprojeto-e-federacao.md)).

O hub **não** guarda chunks nem embeddings de outros projetos. Para projeto clonado,
ele consulta o `.ragx/knowledge.db` daquele projeto sob demanda; para projeto
só-federação, usa `federation_items.contract_body`.

## IDs determinísticos

Requisito duro: **mesmo input + mesma versão do chunker = mesmo ID**, em qualquer
máquina e qualquer sistema operacional. Sem isso, indexação incremental e merge no
Git não funcionam.

```python
CHUNKER_VERSION = "1"   # bump obrigatório em qualquer mudança de fatiamento

def normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    return text.strip("\n")

def chunk_id(rel_path: str, content: str, chunker_version: str) -> str:
    payload = "\0".join((
        rel_path.replace("\\", "/"),      # separador POSIX sempre
        normalize(content),
        chunker_version,
    ))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]
```

Cuidados obrigatórios (cada um vira um teste unitário):

1. `rel_path` sempre com `/`, sempre relativo à raiz do projeto — nunca absoluto.
   Caminho absoluto no ID vazaria o nome do usuário no `.rag` exportado.
2. CRLF normalizado — senão Windows e Linux produzem IDs diferentes.
3. Trailing whitespace removido por linha.
4. `CHUNKER_VERSION` no payload — mudar o chunker invalida os IDs *de propósito*,
   forçando reindexação em vez de corromper o índice silenciosamente.
5. Sem `mtime`, sem `uuid`, sem `random`. Nada que varie entre execuções.

`document.id = sha256(rel_path)[:32]` — não inclui conteúdo, porque a identidade
do documento é o caminho; o conteúdo vive em `content_hash`.

## Ciclo de vida e limpeza

```text
arquivo modificado  → content_hash muda → chunks antigos DELETE (cascade em embeddings)
                                        → novos chunks INSERT
arquivo removido    → documents DELETE  → cascade em chunks/embeddings/entities
arquivo vira sensível → BLOCK           → documents DELETE + security_event
```

`ragx vacuum` (Fase 10) roda `VACUUM` + `PRAGMA optimize` e remove órfãos:
embeddings sem chunk, entidades sem documento, relações sem entidade.

## Convenções

- Timestamps: ISO-8601 UTC com sufixo `Z` (`2026-09-15T12:29:04Z`), como TEXT.
- Booleans: `INTEGER` 0/1.
- Hashes: hex minúsculo.
- Nenhum `BLOB` além de `embeddings.vector` e `embeddings.vector_q`.
- Nenhuma coluna guarda caminho absoluto — **exceto** `projects.path` no hub, que é
  por natureza local da máquina e nunca sai dela (não é versionado, não é exportado).
- Toda tabela do hub referencia `projects(id)`, para que nenhum dado cross-project
  circule sem atribuição de origem.
