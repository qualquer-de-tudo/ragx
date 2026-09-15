# 01 — Arquitetura

## Visão em camadas

```text
┌──────────────────────────────────────────────────────────┐
│  INTERFACES                                              │
│   CLI (Typer)        MCP Server (stdio)      Python API  │
└───────────────┬──────────────┬───────────────────┬───────┘
                │              │                   │
                └──────────────┴───────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────┐
│  APPLICATION  —  casos de uso, orquestração              │
│   IndexService · SearchService · GraphService            │
│   ContextEngine · DictionaryService · AgentService       │
│   ExportService · SyncService                            │
└──────────────────────────────┬───────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────┐
│  DOMAIN  —  regras puras, sem I/O                        │
│   Document · Chunk · Entity · Relation · SecurityFinding │
│   Chunkers · Fusion · Ranking · Budgeting                │
└──────────────────────────────┬───────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────┐
│  INFRASTRUCTURE  —  I/O, tudo substituível               │
│   SQLite · FileWalker · Parsers · EmbeddingProviders     │
│   TokenCounter · Packager                                │
└──────────────────────────────────────────────────────────┘

        ╔══════════════════════════════════════════════╗
        ║  SECURITY GATE — atravessa todas as camadas  ║
        ║  IgnoreEngine · SecurityScanner · Redactor   ║
        ╚══════════════════════════════════════════════╝
```

**Regra de dependência:** de fora para dentro. `domain` não importa nada de `infrastructure`.
`infrastructure` implementa Protocols declarados em `core/protocols.py`.

## Estrutura de pastas

```text
ragx/
├── pyproject.toml
├── ragx.toml                     # config default do próprio repo
├── src/ragx/
│   ├── core/                     # domínio
│   │   ├── models.py             # Document, Chunk, Entity, Relation...
│   │   ├── ids.py                # IDs determinísticos
│   │   ├── errors.py
│   │   └── protocols.py          # interfaces (Embedder, Parser, Store, ...)
│   ├── security/                 # FASE 0 — construído primeiro
│   │   ├── ignore_engine.py
│   │   ├── scanner.py
│   │   ├── rules/                # regras declarativas (YAML)
│   │   ├── entropy.py
│   │   ├── redactor.py
│   │   └── gate.py               # fachada: SecurityGate.admit(path) -> Verdict
│   ├── storage/
│   │   ├── db.py                 # conexão, pragmas, WAL
│   │   ├── migrations/           # 0001_init.sql, 0002_graph.sql, ...
│   │   ├── repositories.py       # DocumentRepo, ChunkRepo, EmbeddingRepo...
│   │   └── vectors.py            # persistência + busca vetorial
│   ├── indexing/
│   │   ├── walker.py
│   │   ├── parsers/              # markdown, python, generic_code, json_yaml, sql
│   │   ├── chunkers/             # code_chunker, doc_chunker, fallback_chunker
│   │   └── pipeline.py
│   ├── embeddings/
│   │   ├── base.py               # Embedder Protocol + cache
│   │   ├── ollama.py             # default: nomic-embed-text
│   │   ├── fastembed.py          # fallback offline
│   │   └── hashing.py            # determinístico, só para testes
│   ├── search/
│   │   ├── semantic.py
│   │   ├── keyword.py            # FTS5
│   │   ├── hybrid.py             # RRF + rerank
│   │   └── ranking.py
│   ├── graph/
│   │   ├── extractors/           # structural, reference, semantic
│   │   ├── store.py
│   │   └── traversal.py
│   ├── context/
│   │   ├── engine.py
│   │   ├── dedup.py              # MMR / near-duplicate
│   │   ├── compress.py
│   │   └── budget.py             # TokenCounter + alocação
│   ├── dictionary/
│   ├── agents/
│   ├── portability/              # exporter, importer, manifest
│   ├── sizing/                   # FASE 1 — orçamento de tamanho
│   │   ├── budget.py             # contagem, projeção, recusa de escrita
│   │   └── sharding.py           # shard por prefixo de ID
│   ├── federation/               # FASE 11 — multiprojeto
│   │   ├── slice.py              # gera knowledge/federation/
│   │   ├── surface.py            # provides / consumes
│   │   ├── normalize.py          # normalização de rotas entre stacks
│   │   ├── linker.py             # resolve consumes ⟷ provides
│   │   ├── hub.py                # ~/.ragx/hub/hub.db
│   │   └── registry.py           # projetos registrados
│   ├── sync/                     # git, incremental, reidratação
│   ├── mcp/
│   │   ├── server.py
│   │   └── tools.py              # casca fina sobre application/
│   ├── cli/
│   └── config.py
├── tests/
│   ├── unit/ integration/ security/ e2e/
│   └── fixtures/secret_project/  # projeto-armadilha da Fase 10
├── docs/
└── task/
```

## Artefatos em disco

Três camadas, com papéis distintos — ver [ADR-0009](adr/ADR-0009-tres-camadas-de-conhecimento.md)
e [17 — Multiprojeto](17-multiprojeto-e-federacao.md).

```text
<projeto-alvo>/
├── .ragx/                        # LOCAL · derivado · NÃO versionado · fidelidade total
│   ├── knowledge.db              # documents, chunks (com conteúdo), float32@768, grafo
│   ├── cache/
│   └── logs/
├── knowledge/                    # REPO · VERSIONADO · leve · orçado (doc 16)
│   ├── manifest.json
│   ├── documents/*.json
│   ├── chunks/*.jsonl            # SEM conteúdo — reidratado do working tree
│   ├── embeddings/               # int8 @ 256d, shardado
│   │   ├── manifest.json
│   │   └── shard-00.i8 … shard-0f.i8
│   ├── entities/shard-*.json
│   ├── relations/shard-*.json
│   ├── dictionary.json
│   └── federation/               # superfície pública — autossuficiente (doc 17)
│       ├── service.json
│       ├── provides.json
│       ├── consumes.json
│       ├── contracts/
│       └── glossary.json
├── agents/<nome>/                # versionado (Fase 7)
├── .ragignore
└── ragx.toml

~/.ragx/hub/                      # MÁQUINA · derivado · NÃO versionado · N projetos
├── hub.db
├── registry.json
└── federation/<projeto>/         # fatias de projetos não clonados
```

Regras que decorrem:

- `.ragx/` é **sempre** reconstruível a partir de `knowledge/` + working tree.
- `knowledge/` é **sempre** reconstruível reindexando o working tree.
- O hub é **sempre** reconstruível a partir dos projetos registrados.
- O fluxo é unidirecional: working tree → `.ragx/` → `knowledge/` → `federation/` → hub.

É isso que torna o merge no Git viável ([12 — Git Sync](12-git-sync.md)) e mantém o
conhecimento versionado dentro do orçamento ([16](16-orcamento-de-tamanho.md)).

## Fluxo principal — indexação

```text
FileWalker
    │  caminha o repo
    ▼
IgnoreEngine ────────► descartado (skipped)
    │  .gitignore + .dockerignore + .ragignore + defaults
    ▼
SecurityScanner ─────► bloqueado (blocked) + SecurityEvent (só hash, nunca o segredo)
    │  nome do arquivo (deny-list) + conteúdo (regex + entropia)
    ▼
Parser              estrutura sintática por linguagem
    ▼
Chunker             classe→método / heading→seção
    ▼
ID determinístico   sha256(rel_path + conteúdo normalizado + versão do chunker)
    ▼
Embedder            cache por content_hash; só o que mudou
    ▼
Quantizador         float32@768 (local)  +  int8@256 (versionado)
    ▼
Orçamento           projeta tamanho; RECUSA a gravação se estourar (doc 16)
    ▼
SQLite              documents · chunks · chunks_fts · embeddings
```

## Fluxo principal — consulta

```text
Query
  │
  ├─► Embedding ──► Vector search (top-K)  ─┐
  │                  int8@256 → rescoring   │
  │                  float32@768 (se local) │
  │                                         ├─► RRF fusion ─► rerank ─► resultados
  └─► FTS5 ───────► Keyword search (top-K) ─┘
                                                     │
                                                     ▼  (Fase 4)
                                       Graph expansion (1–2 saltos)
                                                     ▼
                                       Dedup (MMR) ─► Compress ─► Token budget
                                                     ▼
                                              Context Pack
```

Com `--scope all` (Fase 11), o mesmo fluxo roda em leque sobre os projetos
registrados no hub, e a fusão aplica penalidade a projeto externo — detalhe em
[17 — Multiprojeto](17-multiprojeto-e-federacao.md).

## Stack

| Área | Escolha | Por quê | ADR |
|------|---------|---------|-----|
| Linguagem | Python >= 3.11 (dev em 3.13) | ecossistema de NLP/parsing; `tomllib` na stdlib | [ADR-0001](adr/ADR-0001-python-e-toolchain.md) |
| Packaging | `uv` + `hatchling` | uv já instalado na máquina; resolução rápida | ADR-0001 |
| CLI | `typer` + `rich` | tipagem nativa, saída legível | ADR-0001 |
| Modelos/config | `pydantic` v2 + `pydantic-settings` | valida contratos MCP e config | ADR-0001 |
| Store | SQLite (stdlib) + WAL | um arquivo, zero servidor, transacional | [ADR-0002](adr/ADR-0002-sqlite-como-store-unico.md) |
| Keyword | FTS5 (built-in) | BM25 sem dependência extra | ADR-0002 |
| Vetores | tabela BLOB + NumPy; upgrade p/ `sqlite-vec` | brute force basta até ~200k chunks | [ADR-0003](adr/ADR-0003-busca-vetorial.md) |
| Embeddings | Ollama `nomic-embed-text` (768d) | já existe em `ollama_models/`; roda offline | [ADR-0004](adr/ADR-0004-embeddings.md) |
| Fallback embeddings | `fastembed` (bge-small) | sem daemon; usado em CI | ADR-0004 |
| Ignore | `pathspec` | semântica gitignore correta, sem reimplementar | — |
| Parsing código | `ast` (Python) + `tree-sitter-language-pack` | AST real > regex | [ADR-0005](adr/ADR-0005-parsing-e-chunking.md) |
| Parsing Markdown | `markdown-it-py` | árvore de headings confiável | ADR-0005 |
| Tokens | `tiktoken` (cl100k_base) como estimador | orçamento precisa de contagem estável | — |
| MCP | SDK oficial `mcp` >= 2.0 (`MCPServer`), stdio | contrato padrão de agentes | [ADR-0006](adr/ADR-0006-mcp-casca-fina.md) |
| Camadas de conhecimento | local / repo / hub | Git tem teto; multiprojeto precisa cruzar repos | [ADR-0009](adr/ADR-0009-tres-camadas-de-conhecimento.md) |
| Vetores versionados | int8 @ 256d (Matryoshka) | 24 MB por 100k chunks em vez de 293 MB | [ADR-0010](adr/ADR-0010-conteudo-nao-versionado-e-embeddings-quantizados.md) |
| Cross-project | fatia pública por projeto | funciona sem o outro repo clonado | [ADR-0011](adr/ADR-0011-federacao-entre-projetos.md) |
| Testes | `pytest`, `pytest-cov` | — | — |
| Qualidade | `ruff`, `mypy --strict` em `core/` e `security/` | — | — |

## Fronteiras de segurança

Só existem **dois** pontos do sistema autorizados a ler o filesystem do projeto-alvo:
`indexing/walker.py` e `sync/incremental.py` (este último também faz a reidratação).
Ambos só entregam bytes depois do `SecurityGate`. Isso é verificado por teste
arquitetural (ver [13 — Testes e Hardening](13-testes-hardening.md)).

O hub **não** é uma terceira exceção: ele lê apenas artefatos derivados
(`knowledge/`, `federation/`) de projetos registrados — nunca o código-fonte deles —
e re-escaneia o que lê, porque o ruleset local pode ser mais estrito que o de origem.

Consequência direta, e é a regra mais importante da camada MCP:

```text
    PERMITIDO                         PROIBIDO
    MCP -> KnowledgeAPI -> Store      MCP -> open(path)
```

## Modelo de execução

- **CLI**: processo curto, abre o SQLite, executa, fecha. Sem daemon.
- **MCP**: processo longo via stdio, mantém conexão SQLite em modo WAL (leitura concorrente).
- **Indexação**: paralelismo por *arquivo* com `ThreadPoolExecutor` para I/O e parsing;
  embeddings em lote (batch) contra o provider. Escrita no SQLite é serializada por
  uma única thread escritora (evita `database is locked`).
