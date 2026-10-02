# RAGX-0166 — Prefixo contextual determinístico antes de embutir e indexar

| | |
|---|---|
| **Fase** | 21 — Recuperação v2 |
| **Prioridade** | P1 — alta |
| **Estimativa** | 1d |
| **Depende de** | `RAGX-0104` |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (7.2 #6) · [04-indexacao.md](../../docs/04-indexacao.md) · [05-busca.md](../../docs/05-busca.md) · [03-modelo-de-dados.md](../../docs/03-modelo-de-dados.md) |
| **Status** | `blocked` |

## Objetivo

O prefixo de contexto que o `docs/04-indexacao.md` promete existe só pela metade. `context_prefix()` (`src/ragx/indexing/chunkers/__init__.py:268`) junta o caminho e o `heading_path`/símbolo, mas é aplicado **só no embedding** (`indexing/embed.py:109`), e o FTS indexa só `content`, `symbol` e `heading_path` (`0002_documents.sql`): o caminho do arquivo, a assinatura e a docstring nunca entram na busca por palavra-chave. A aposta 6 da auditoria (Contextual Retrieval da Anthropic: −49% de falhas no top-20, com o contexto gerado por LLM) pede o mesmo prefixo dos dois lados, mas **determinístico e sem LLM**; o ganho aqui é uma hipótese a medir, não uma promessa. Linha de base: `ragx eval` no conjunto atual de 26 consultas (o número entra em Andamento antes de mexer em código).

## Entregáveis

- [ ] **Medir primeiro**: rodar `uv run ragx eval --mode all --json` no índice atual e registrar recall@5, MRR e nDCG@10 de `keyword`, `semantic` e `hybrid` na tabela de Medição
- [ ] `Chunk` (`core/models.py:101`) ganha `context: str | None = None`; `chunk_document` o preenche com a função pura `build_context_text(rel_path, kind, symbol, heading_path, signature, doc_line)` em `indexing/chunkers/__init__.py`: caminho com identificadores separados (`ignore_engine.py` vira `ignore engine`), `kind symbol` (o símbolo já é qualificado, ex. `AuthService.login`), primeira linha de assinatura (primeira linha não-decorator do chunk, até 160 caracteres) e a primeira frase da docstring (Python, via `ParseNode.meta["docstring"]` de `parsers/python_ast.py:81,93`)
- [ ] `_merge_tiny` (`chunkers/__init__.py:221`) e `_dedupe_ids` (`:278`) reconstroem `Chunk` campo a campo: os dois passam a copiar `context` (sem isso o contexto some em silêncio nos chunks fundidos)
- [ ] Migração `NNNN_chunk_context.sql` (próximo número livre: confira `src/ragx/storage/migrations/`; hoje o último é `0006`): `ALTER TABLE chunks ADD COLUMN context TEXT`, recria `chunks_fts` com a 4ª coluna `context` e os três gatilhos (`chunks_ai/ad/au`), e `INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild')`. Sobe `SCHEMA_VERSION` em `core/ids.py:19` (o teste `test_schema_version_bate_com_a_migracao_mais_recente` cobra)
- [ ] `ChunkRepo.replace_for_document` (`storage/repositories.py:87`) grava `context`; `portability/importer.py:193` continua válido (coluna anulável: chunk importado cai no prefixo antigo)
- [ ] `search/keyword.py`: `BM25_WEIGHTS` (linha 17) ganha o 4º peso (`context`); partir de 0,5 e ajustar pelo `ragx eval`, registrando o valor escolhido e o motivo
- [ ] `indexing/embed.py`: `_prefixed` (linha 144) passa a usar `chunks.context` quando existe (o `SELECT` por chunk vira um só, junto de `_paths_for`); a chave do `EmbeddingCache` deixa de ser `content_hash` do chunk e passa a ser o hash do **texto embutido**, senão um prefixo novo reaproveita vetor velho
- [ ] Invalidação dos vetores já gravados: constante `CONTEXT_VERSION` e chave `meta.context_version`; `embed_pending` (como no ramo `stale`, linhas 69–82) apaga os embeddings do modelo atual quando a chave difere, e o pipeline trata o primeiro índice depois da troca como `full` para repreencher `context` nos documentos "unchanged"
- [ ] Documentar em `docs/04-indexacao.md`, `docs/05-busca.md` e `docs/03-modelo-de-dados.md` (coluna e FTS novos)

## Fora de escopo

- Contextual Retrieval **com LLM** (custo de nuvem; vai contra "local-first", auditoria 24 seção 7.3)
- Trocar o modelo de embedding ou os prefixos `search_query:`/`search_document:` (`RAGX-0103`, `RAGX-0104`)
- Bump de `CHUNKER_VERSION`: os IDs de chunk **não** mudam (o contexto não entra no `chunk_id`), então `knowledge/` não é reescrito
- Assinatura e docstring para TS/JS/PHP: hoje esses arquivos caem em `TextParser`; o AST é da `RAGX-0114`

## Critérios de aceite

- [ ] `chunks.content` é **idêntico** antes e depois (o agente continua lendo o código sem prefixo); teste compara o conteúdo de um projeto fixture
- [ ] `ragx eval`: recall@5 e MRR de `keyword` e `hybrid` **não pioram** e o ganho (ou a falta dele) fica registrado com o IC95% da tabela de Medição; sem ganho, o contexto entra só no embedding e a tarefa termina com essa conclusão escrita em Notas
- [ ] Consulta `ignore engine` acha `src/ragx/security/ignore_engine.py` no top-5 em `--mode keyword` (hoje o caminho não está no FTS)
- [ ] Segundo `ragx index` sem mudança reembute **0** chunks e leva o mesmo tempo de antes (±10%)

### Medição

| Métrica | Antes | Depois |
|---|---|---|
| recall@5 keyword / semantic / hybrid | (medir) | |
| MRR hybrid | (medir) | |
| nDCG@10 hybrid | (medir) | |
| Custo do reembed total (6.587 chunks, MiniLM) | (medir) | |

Comando: `uv run ragx index . --embed-only && uv run ragx eval --mode all --json`

## Testes

- [ ] `tests/unit/test_chunkers.py`: `build_context_text` é determinística (mesma entrada, mesma saída), separa identificadores e trunca a assinatura; `chunk.context` sobrevive a `_merge_tiny` e `_dedupe_ids`
- [ ] `tests/integration/test_search.py`: busca keyword por termo que só existe no caminho do arquivo devolve o chunk (falha antes da migração)
- [ ] `tests/unit/test_embedder_cache.py` ou novo `tests/integration/test_embed_context.py`: trocar `CONTEXT_VERSION` apaga os vetores e reembute; mesma versão reembute 0
- [ ] `tests/security/test_gate.py`: o contexto é derivado do conteúdo **já liberado pelo gate** (arquivo com segredo redigido não vaza o valor pelo prefixo)

## Notas

Armadilhas: o FTS é `content=chunks` (tabela externa), então esquecer os gatilhos na migração deixa o índice divergir (`ragx doctor` confere a contagem, `cli/commands/doctor.py:227`). O prefixo atual **já** inclui o caminho no embedding, mas o cache por `content_hash` reaproveita vetor de arquivo renomeado com o caminho antigo; a nova chave por texto embutido corrige isso ao custo de reembutir os chunks de um arquivo renomeado (decisão aceita, registrar o custo medido). A migração e a mudança de `replace_for_document` colidem com `RAGX-0138` e com as tarefas que criam `0007`; quem entrar depois renumera. Se o recall não mexer, não force: a evidência pública é de Contextual Retrieval com LLM, e esta é a versão barata dele.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes em Linux, macOS e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [ ] Documentação confere com o comportamento implementado
- [ ] Commit `tipo(escopo): descrição (RAGX-0166)` na branch `feat/v2`

## Andamento

- 2026-10-02 — **`blocked`, nada implementado.** depende da RAGX-0104 (fase 14, prefixos no provider fastembed), que continua `todo`; o roteiro proíbe o loop de pegar a fase 14 por conta própria (a 0103 troca o modelo e muda o formato do índice: decisão humana). Verificado nos arquivos das dependências (todas ainda com `Status = todo`/`review`). Quando a dependência fechar, voltar o status para `todo` e retomar daqui.
