# RAGX-0146 — Cache de embedding em SQLite, em lote

| | |
|---|---|
| **Fase** | 19 — Velocidade e frescor |
| **Prioridade** | P2 — média |
| **Estimativa** | 0,75d |
| **Depende de** | RAGX-0130 |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (I-09) · [25-spec-v2.md](../../docs/25-spec-v2.md) · [04-indexacao.md](../../docs/04-indexacao.md) · [ADR-0004](../../docs/adr/ADR-0004-embeddings.md) · [22-vscode-e-desempenho.md](../../docs/22-vscode-e-desempenho.md) |
| **Status** | `todo` |

## Objetivo

O cache de embedding guarda **um arquivo por chunk** (`mkdir` + `open` + `write` em `emb/<modelo>/<hh>/<hash>.f32`); `_prefixed` faz um `SELECT` por chunk; e `store_vectors` só grava no fim, então um processo morto no meio perde tudo que não chegou ao cache (I-09). No primeiro índice de 3.614 chunks, o `put` custou **10,4 s dos 30,5 s (34%), 2,9 ms por chunk**; o SQL, só ~5%. No Windows cada `open` custa ~2,7 ms (provável antivírus). A tarefa troca o cache por SQLite com leitura e escrita em lote, junta as consultas por chunk numa só e passa a gravar por checkpoint.

## Entregáveis

- [ ] **Medir primeiro**: script que gera um projeto sintético (400 arquivos, ~3,6 mil chunks), roda o primeiro `index` com provider `hashing` (isola o cache do modelo) e imprime o tempo por fase do `embed_pending` (`get`, `_prefixed`, `embed_documents`, `put`, `store_vectors`); registrar em Medição
- [ ] `src/ragx/embeddings/base.py:73-105`: `EmbeddingCache` passa a ser SQLite em `.ragx/cache/emb/<modelo>.sqlite` (`content_hash TEXT PRIMARY KEY, vec BLOB NOT NULL` `WITHOUT ROWID`; `journal_mode=WAL`, `busy_timeout=5000`); API em lote `get_many(hashes) -> dict[str, np.ndarray]` (janelas de 500 variáveis, como `_paths_for`) e `put_many(items)` numa transação; `get`/`put` ficam como invólucros finos; `close()` e uso como gerenciador de contexto
- [ ] Leitura de passagem do cache antigo: `get_many` que não acha no SQLite procura em `emb/<modelo>/<hh>/<hash>.f32` e **importa** o que achar; nada de migração em massa e a pasta antiga não é apagada
- [ ] Cache ilegível ou travado nunca derruba a indexação (como hoje, `except OSError: pass`): banco corrompido é renomeado para `.corrupt` e recriado; erro de escrita vira "sem cache" naquela rodada
- [ ] `src/ragx/storage/vectors.py:151-161`: `pending_for_embedding(conn, model_id)` devolve `(chunk_id, content_hash, content, rel_path, kind, symbol, heading_path)` num **único** `SELECT` com `JOIN documents`; `missing_chunk_ids` continua existindo para quem já o usa
- [ ] `src/ragx/indexing/embed.py:84-125`: usar `pending_for_embedding`; apagar `_paths_for` (128-141) e o `SELECT` por chunk de `_prefixed` (144-157, chamado na linha 110), montando o prefixo com `context_prefix` a partir da linha já lida; trocar o laço `cache.get` (95-101) por `get_many` e o `cache.put` por chunk (114) por `put_many` por lote
- [ ] Checkpoint: a cada `checkpoint_every` lotes (padrão 10, constante em `embed.py`) grava `store_vectors` e dá `commit`, em vez de só no fim (122-123). `ragx index` morto no meio retoma do ponto em que parou
- [ ] `docs/04-indexacao.md` (cache de embedding, onde fica e como é retomado) e `docs/22-vscode-e-desempenho.md`, se citarem o cache por arquivo

## Fora de escopo

- Pool de processos no primeiro índice (RAGX-0152, que depende desta)
- Incluir o prefixo de contexto (caminho) na chave do cache: hoje a chave é `content_hash`, mas o texto embutido leva o caminho (`context_prefix`, `chunkers/__init__.py:268`), então chunk movido reaproveita vetor calculado com o caminho velho. É da RAGX-0166 (prefixo contextual); ver Notas
- Despejo/limite de tamanho do cache e `ragx vacuum` do cache
- Mudar `embedding.batch` ou o tamanho do lote do provider

## Critérios de aceite

- [ ] Primeiro índice de ~3,6 mil chunks: soma de `get` + `_prefixed` + `put` **≤ 1,5 s** (antes: só o `put` = 10,4 s), com `hashing`
- [ ] Segunda rodada sem mudança: 0 chamadas a `embed_documents` e 0 arquivos criados em `.ragx/cache/emb/` além do `.sqlite` (e `-wal`/`-shm`)
- [ ] Matar o processo no meio do embedding e rodar de novo: o que já tinha lote concluído **não** é reembedado (contador do embedder falso)
- [ ] Mesmo conjunto de chunks, mesmos vetores e mesmos `embeddings` com cache novo, com cache antigo (passagem) e sem cache
- [ ] Windows: nenhum teste deixa arquivo preso (`.sqlite` fechado antes de o `tmp_path` ser limpo)

### Medição

| Métrica | Antes | Depois |
|---|---|---|
| `put` em 3.614 chunks | 10,4 s (2,9 ms/chunk) | |
| Primeiro índice, 400 arquivos / 3,6 mil chunks | 30,5 s | |
| Criação de arquivos no cache | 1 por chunk | |
| `SELECT` por chunk em `_prefixed` | 1 por chunk | |

Comando: `uv run python scripts/medir_indice_inicial.py --arquivos 400 --provider hashing` (criar).

## Testes

- [ ] `tests/unit/test_embedding_cache.py` (novo; hoje nenhum teste fala de `EmbeddingCache`): `put_many`/`get_many` ida e volta, vetor igual bit a bit, dimensão errada ignorada pelo chamador, janelas de 500, passagem do cache antigo importa e conta, banco corrompido recriado
- [ ] `tests/integration/test_pipeline.py`: segundo `index` não chama o embedder; `kill` simulado (exceção no 3º lote) e nova rodada só embute o resto
- [ ] `tests/integration/test_pipeline.py`: contagem de consultas SQL de `embed_pending` não cresce com o número de chunks (espiar `conn.set_trace_callback`)
- [ ] `tests/unit/test_embeddings.py`: `EmbeddingCache` desligado (`cache=false`) continua sem criar nada
- [ ] Regressão: o texto que vai ao embedder para cada chunk é idêntico ao de antes (`context_prefix`), caso de arquivo com `heading_path`, com `symbol` e sem nenhum dos dois

## Notas

- Confirmado em `src/ragx/embeddings/base.py:73-105` (cache por arquivo), `src/ragx/indexing/embed.py:90-101,110,114,122-123,128-157` e `src/ragx/storage/vectors.py:151-161`. Nenhum teste referencia `EmbeddingCache` diretamente (busca em `tests/`).
- Um arquivo SQLite por modelo, em vez de uma tabela no `knowledge.db`: o cache pode ser apagado sem tocar o índice, não incha o banco que o painel e o MCP leem e não disputa a trava de escrita do índice.
- `embedder.available()` (sondagem de 2 s do Ollama, `embed.py:54-61`) e o carregamento preguiçoso do modelo são da RAGX-0130; esta tarefa parte do `embed_pending` já como ela o deixar.
- Windows: SQLite em WAL deixa `-wal` e `-shm` ao lado; fechar a conexão sempre (`finally`/`with`), senão o `tmp_path` do pytest não limpa. O diretório do projeto pode estar sob antivírus: o ganho vem de tirar milhares de `open`, não de SQLite ser mais rápido que o disco.
- A chave continua `content_hash` + modelo: nada muda no que é considerado "o mesmo chunk". Se alguém quiser incluir o caminho, é decisão da RAGX-0166 (e invalida o cache de todo mundo).
- Se a medição mostrar que o `put` já não era o gargalo (por exemplo, antivírus desligado), registrar em Andamento e manter só o que o teste de regressão justificar.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes em Linux, macOS e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [ ] Documentação confere com o comportamento implementado
- [ ] Commit `tipo(escopo): descrição (RAGX-0146)` na branch `feat/v2`

## Andamento

_(o loop registra aqui o que fez, com datas e medições)_
