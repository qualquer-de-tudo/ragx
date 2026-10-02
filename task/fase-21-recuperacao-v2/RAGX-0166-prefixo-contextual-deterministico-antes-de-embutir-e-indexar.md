# RAGX-0166 — Prefixo contextual determinístico antes de embutir e indexar

| | |
|---|---|
| **Fase** | 21 — Recuperação v2 |
| **Prioridade** | P1 — alta |
| **Estimativa** | 1d |
| **Depende de** | `RAGX-0104` |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (7.2 #6) · [04-indexacao.md](../../docs/04-indexacao.md) · [05-busca.md](../../docs/05-busca.md) · [03-modelo-de-dados.md](../../docs/03-modelo-de-dados.md) |
| **Status** | `done` |

## Objetivo

O prefixo de contexto que o `docs/04-indexacao.md` promete existe só pela metade. `context_prefix()` (`src/ragx/indexing/chunkers/__init__.py:268`) junta o caminho e o `heading_path`/símbolo, mas é aplicado **só no embedding** (`indexing/embed.py:109`), e o FTS indexa só `content`, `symbol` e `heading_path` (`0002_documents.sql`): o caminho do arquivo, a assinatura e a docstring nunca entram na busca por palavra-chave. A aposta 6 da auditoria (Contextual Retrieval da Anthropic: −49% de falhas no top-20, com o contexto gerado por LLM) pede o mesmo prefixo dos dois lados, mas **determinístico e sem LLM**; o ganho aqui é uma hipótese a medir, não uma promessa. Linha de base: `ragx eval` no conjunto atual de 26 consultas (o número entra em Andamento antes de mexer em código).

## Entregáveis

- [x] **Medir primeiro**: rodar `uv run ragx eval --mode all --json` no índice atual e registrar recall@5, MRR e nDCG@10 de `keyword`, `semantic` e `hybrid` na tabela de Medição
- [x] `Chunk` (`core/models.py:101`) ganha `context: str | None = None`; `chunk_document` o preenche com a função pura `build_context_text(rel_path, kind, symbol, heading_path, signature, doc_line)` em `indexing/chunkers/__init__.py`: caminho com identificadores separados (`ignore_engine.py` vira `ignore engine`), `kind symbol` (o símbolo já é qualificado, ex. `AuthService.login`), primeira linha de assinatura (primeira linha não-decorator do chunk, até 160 caracteres) e a primeira frase da docstring (Python, via `ParseNode.meta["docstring"]` de `parsers/python_ast.py:81,93`)
- [x] `_merge_tiny` (`chunkers/__init__.py:221`) e `_dedupe_ids` (`:278`) reconstroem `Chunk` campo a campo: os dois passam a copiar `context` (sem isso o contexto some em silêncio nos chunks fundidos)
- [x] Migração `NNNN_chunk_context.sql` (próximo número livre: confira `src/ragx/storage/migrations/`; hoje o último é `0006`): `ALTER TABLE chunks ADD COLUMN context TEXT`, recria `chunks_fts` com a 4ª coluna `context` e os três gatilhos (`chunks_ai/ad/au`), e `INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild')`. Sobe `SCHEMA_VERSION` em `core/ids.py:19` (o teste `test_schema_version_bate_com_a_migracao_mais_recente` cobra)
- [x] `ChunkRepo.replace_for_document` (`storage/repositories.py:87`) grava `context`; `portability/importer.py:193` continua válido (coluna anulável: chunk importado cai no prefixo antigo)
- [x] `search/keyword.py`: `BM25_WEIGHTS` (linha 17) ganha o 4º peso (`context`); partir de 0,5 e ajustar pelo `ragx eval`, registrando o valor escolhido e o motivo
- [x] `indexing/embed.py`: `_prefixed` (linha 144) passa a usar `chunks.context` quando existe (o `SELECT` por chunk vira um só, junto de `_paths_for`); a chave do `EmbeddingCache` deixa de ser `content_hash` do chunk e passa a ser o hash do **texto embutido**, senão um prefixo novo reaproveita vetor velho
- [x] Invalidação dos vetores já gravados: constante `CONTEXT_VERSION` e chave `meta.context_version`; `embed_pending` (como no ramo `stale`, linhas 69–82) apaga os embeddings do modelo atual quando a chave difere, e o pipeline trata o primeiro índice depois da troca como `full` para repreencher `context` nos documentos "unchanged"
- [x] Documentar em `docs/04-indexacao.md`, `docs/05-busca.md` e `docs/03-modelo-de-dados.md` (coluna e FTS novos)

## Fora de escopo

- Contextual Retrieval **com LLM** (custo de nuvem; vai contra "local-first", auditoria 24 seção 7.3)
- Trocar o modelo de embedding ou os prefixos `search_query:`/`search_document:` (`RAGX-0103`, `RAGX-0104`)
- Bump de `CHUNKER_VERSION`: os IDs de chunk **não** mudam (o contexto não entra no `chunk_id`), então `knowledge/` não é reescrito
- Assinatura e docstring para TS/JS/PHP: hoje esses arquivos caem em `TextParser`; o AST é da `RAGX-0114`

## Critérios de aceite

- [x] `chunks.content` é **idêntico** antes e depois (o agente continua lendo o código sem prefixo); teste compara o conteúdo de um projeto fixture
- [x] `ragx eval`: recall@5 e MRR de `keyword` e `hybrid` **não pioram** e o ganho (ou a falta dele) fica registrado com o IC95% da tabela de Medição; sem ganho, o contexto entra só no embedding e a tarefa termina com essa conclusão escrita em Notas
- [x] Consulta `ignore engine` acha `src/ragx/security/ignore_engine.py` no top-5 em `--mode keyword` (hoje o caminho não está no FTS)
- [x] Segundo `ragx index` sem mudança reembute **0** chunks e leva o mesmo tempo de antes (±10%)

### Medição

| Métrica | Antes | Depois |
|---|---|---|
| recall@5 keyword / semantic / hybrid (152 consultas, 132 respondidas) | 0,689 / 0,538 / 0,621 | **0,697 / 0,576 / 0,621** (IC95% ±0,08 em todos) |
| MRR hybrid (e keyword) | 0,490 (0,474) | **0,521 (0,503)** |
| nDCG@10 hybrid (e keyword) | 0,431 (0,453) | **0,453 (0,472)** |
| Custo do reembed total (~9 mil chunks, MiniLM, fastembed) | 118 s (índice a frio, medido na 0170) | **113 s** (todos os chunks reembutidos uma vez, depois da migração); `ragx index` sem mudança: 0 reembutidos, 203 ms |

Comando: `uv run ragx index . --embed-only && uv run ragx eval --mode all --json`

## Testes

- [x] `tests/unit/test_chunkers.py`: `build_context_text` é determinística (mesma entrada, mesma saída), separa identificadores e trunca a assinatura; `chunk.context` sobrevive a `_merge_tiny` e `_dedupe_ids`
- [x] `tests/integration/test_search.py`: busca keyword por termo que só existe no caminho do arquivo devolve o chunk (falha antes da migração)
- [x] `tests/unit/test_embedder_cache.py` ou novo `tests/integration/test_embed_context.py`: trocar `CONTEXT_VERSION` apaga os vetores e reembute; mesma versão reembute 0
- [x] `tests/security/test_gate.py`: o contexto é derivado do conteúdo **já liberado pelo gate** (arquivo com segredo redigido não vaza o valor pelo prefixo)

## Notas

Armadilhas: o FTS é `content=chunks` (tabela externa), então esquecer os gatilhos na migração deixa o índice divergir (`ragx doctor` confere a contagem, `cli/commands/doctor.py:227`). O prefixo atual **já** inclui o caminho no embedding, mas o cache por `content_hash` reaproveita vetor de arquivo renomeado com o caminho antigo; a nova chave por texto embutido corrige isso ao custo de reembutir os chunks de um arquivo renomeado (decisão aceita, registrar o custo medido). A migração e a mudança de `replace_for_document` colidem com `RAGX-0138` e com as tarefas que criam `0007`; quem entrar depois renumera. Se o recall não mexer, não force: a evidência pública é de Contextual Retrieval com LLM, e esta é a versão barata dele.

## Definition of Done

- [x] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes em Linux, macOS e Windows (verdes no Windows; Linux e macOS só a CI)
- [x] `ruff` e `mypy` limpos
- [x] Suíte `security/` continua verde
- [x] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [x] Documentação confere com o comportamento implementado
- [x] Commit `tipo(escopo): descrição (RAGX-0166)` na branch `feat/v2`

## Andamento

- 2026-10-02 — **`blocked`, nada implementado.** depende da RAGX-0104 (fase 14, prefixos no provider fastembed), que continua `todo`; o roteiro proíbe o loop de pegar a fase 14 por conta própria (a 0103 troca o modelo e muda o formato do índice: decisão humana). Verificado nos arquivos das dependências (todas ainda com `Status = todo`/`review`). Quando a dependência fechar, voltar o status para `todo` e retomar daqui.

## Andamento

- 2026-10-02 — **Desbloqueada** (a RAGX-0104 fechou e a 0099 deu um conjunto de 152 consultas que torna a medição legível). **Medi primeiro**, com o MESMO conjunto e o MESMO índice (`tests/eval/queries.yaml` fora do índice, ver abaixo), num worktree em HEAD sem as mudanças: keyword 0,689, semantic 0,538, hybrid 0,621 de recall@5; MRR 0,474, 0,429, 0,490; nDCG@10 0,453, 0,378, 0,431.
- **Feito**: `Chunk.context`; `build_context_text(rel_path, chunk)` (pura; caminho, título ou `tipo símbolo`, palavras do símbolo quando há CamelCase, assinatura até 160, primeira frase do docstring até 200, por `ast`) aplicada ao chunk FINAL em `chunk_document`, então `_merge_tiny` e `_dedupe_ids` não precisaram mudar; migração `0009_chunk_context.sql` (coluna, `chunks_fts` com 4ª coluna, os três gatilhos e `rebuild`) e `SCHEMA_VERSION = 9`; `ChunkRepo` grava e compara `context` (contexto novo apaga o vetor do sobrevivente); `BM25_WEIGHTS` com 4º peso 0,5; `_prefixed` usa `chunks.context`; chave do `EmbeddingCache` = hash do texto embutido; `indexing/context.py` com `CONTEXT_VERSION` e `ensure_context`.
- **Desvio da especificação, e por quê**: a tarefa mandava invalidar os vetores e tratar o primeiro índice depois da troca como `full` para repreencher o contexto. Como o contexto é função pura de dados que já estão no banco, `ensure_context` o recalcula direto do banco (sem reler arquivo, sem reindexar), apaga os vetores e grava a versão; isso evita ler o projeto de novo e vale também para `index_paths` e `--embed-only`.
- **Medido depois**: keyword 0,697 / MRR 0,503 / nDCG 0,472; semantic 0,576 / 0,443 / 0,392; hybrid 0,621 / 0,521 / 0,453. Nenhum modo piorou em recall@5 nem em MRR (critério cumprido), mas os ganhos (0 a +0,04 de recall, +0,015 a +0,03 de MRR) cabem dentro do IC95% de ±0,08: **é uma melhora provável e pequena, não uma prova**. Por classe: depuração do keyword 14 → 16 de 19, relacionamento do semantic 4 → 6 de 20; relacionamento do keyword 11 → 10 de 20 (piorou 1 consulta). Falsos positivos das sem resposta: hybrid 3 → 0, semantic 1 → 2 de 20.
- **Peso do contexto** (varredura em 152 consultas, keyword recall@5 / MRR): 0 → 0,705 / 0,473; 0,25 → 0,697 / 0,489; 0,5 → 0,697 / 0,503; 1,0 → 0,682 / 0,508; 2,0 → 0,705 / 0,523. Indistinguíveis dentro do IC; ficou 0,5. Critério `ignore engine` em `--mode keyword`: `src/ragx/security/ignore_engine.py` em 1º lugar (antes o caminho não estava no FTS).
- **Mudança de configuração do repositório**: `ragx.toml` passou a excluir `tests/eval/queries.yaml` do índice. O gabarito indexado deixa a busca achar a PERGUNTA em vez da resposta e contamina o `ragx eval` (as duas medições acima já o excluem). Não afeta a indexação de outros projetos.
- Testes (`tests/integration/test_chunk_context.py`, 14): função pura determinística, identificadores separados, truncamentos, seção sem assinatura, contexto em todo chunk, `content` sem prefixo, busca por palavra só do caminho e por palavras de CamelCase, segundo `index` reembute 0, a chave do cache é o texto embutido, subir a versão refaz o contexto e apaga os vetores, FTS com a mesma contagem e 4 colunas, pesos e colunas alinhados, e segredo no docstring que não vaza pelo contexto. Suíte `-m "not slow"` verde.
- **Efeito colateral a saber**: o worktree de medição baixou o modelo do fastembed para `~/.ragx/models` (a pasta por usuário da RAGX-0153), 240 MB, porque um worktree novo não tem `.ragx/cache/models` legado.
- **Não verificado**: Linux e macOS; migração `0009` aplicada sobre um banco grande real é este repositório (9 mil chunks, funcionou), não testei um de 100 mil.
