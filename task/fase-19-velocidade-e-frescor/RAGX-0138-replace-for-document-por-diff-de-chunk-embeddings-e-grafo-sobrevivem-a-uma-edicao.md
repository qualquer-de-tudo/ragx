# RAGX-0138 — `replace_for_document` por diff de chunk: embeddings e grafo sobrevivem a uma edição

| | |
|---|---|
| **Fase** | 19 — Velocidade e frescor |
| **Prioridade** | P1 — alta |
| **Estimativa** | 1d |
| **Depende de** | — |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (C-06, I-07) · [25-spec-v2.md](../../docs/25-spec-v2.md) (R-V6) · [03-modelo-de-dados.md](../../docs/03-modelo-de-dados.md) · [04-indexacao.md](../../docs/04-indexacao.md) · [06-grafo.md](../../docs/06-grafo.md) |
| **Status** | `done` |

## Objetivo

`ChunkRepo.replace_for_document` (`storage/repositories.py:87-105`) apaga todos os chunks do documento e reinsere. Como `embeddings.chunk_id` é `ON DELETE CASCADE` (`0003_embeddings.sql`) e `entities.chunk_id` e `relations.evidence_chunk_id` são `ON DELETE SET NULL` (`0004_graph.sql:9,28`), editar um arquivo derruba tudo que dependia dos chunks, mesmo dos que não mudaram. Medido: 19 chunks idênticos reinseridos levaram os embeddings de 19 para 0 e as pontes entidade→chunk de 18 para 0 até a próxima consolidação; editar uma linha reescreveu 9 chunks, dos quais só 1 texto foi ao embedder. Como o `chunk.id` é hash de (caminho, conteúdo normalizado, versão), o id **já é** o diff.

## Entregáveis

- [x] **Reproduzir primeiro** (teste vermelho): reinserir os mesmos chunks e contar embeddings e pontes antes/depois; registrar 19 → 0 e 18 → 0.
- [x] `replace_for_document` por diff de id. Sobreviventes = ids nos dois conjuntos; removidos e novos pela diferença. Ordem obrigatória, por causa de `UNIQUE (document_id, ordinal)` e de `parent_id ... ON DELETE CASCADE` (`0002_documents.sql`):
  1. sobrevivente cujo pai está entre os removidos: `parent_id = NULL` antes de apagar (senão o cascade apaga o filho e seus vetores);
  2. `DELETE` dos removidos;
  3. sobreviventes com `ordinal` diferente vão para um valor temporário negativo (`-(ordinal+1)`);
  4. `INSERT` dos novos, na ordem do chunker (pai antes do filho);
  5. `UPDATE` final **só** dos sobreviventes cuja linha mudou (`ordinal`, `parent_id`, `start_line`, `end_line`, `symbol`, `heading_path`, `kind`, `content`, `token_count`). O gatilho `chunks_au` reescreve o FTS por linha, então não atualizar quem não mudou.
- [x] Sobrevivente cujo `symbol`, `heading_path` ou `kind` mudou perde o embedding (`DELETE FROM embeddings WHERE chunk_id = ?`): o prefixo de contexto entra no texto embutido (`chunkers/__init__.py:268-275`), então o vetor ficou velho.
- [x] Devolver um `ReplaceStats(kept, added, removed, updated)` em vez de `int`; o único chamador é `pipeline.py:261`. Somar em `IndexReport` (campos novos `chunks_kept`, `chunks_removed`) e mostrar no `index --json`.
- [x] `docs/03-modelo-de-dados.md` e `docs/04-indexacao.md`: "chunk com o mesmo id sobrevive à edição".
- [x] CHANGELOG com o número antes/depois.

## Fora de escopo

- Reconstruir o grafo por documento (símbolo novo ainda só entra no `sync`): RAGX-0151.
- `index_paths`: RAGX-0140. Cache de embedding por `content_hash`: RAGX-0146.
- `portability/importer.py:192` (`INSERT OR REPLACE`): não mexer.
- O cache de embedding (`EmbeddingCache`) é chaveado só por `content_hash` e pode devolver o vetor sem o prefixo novo; é anterior a esta tarefa. Anotar, não consertar aqui.

## Critérios de aceite

- [x] Reinserir os mesmos chunks: 0 `INSERT`, 0 `DELETE`, 0 `UPDATE` (`conn.total_changes` não muda), embeddings 19 → 19 e pontes 18 → 18.
- [x] Editar um chunk de 19: só ele sai e entra; os outros 18 mantêm `created_at`, embedding e pontes; só o chunk novo vai ao embedder.
- [x] Inserir um chunk no meio desloca ordinais sem violar `UNIQUE`; trocar dois de lugar idem.
- [x] Remover um chunk-pai deixando o filho: o filho **sobrevive** com o novo `parent_id`.
- [x] Estado final de `chunks` (todas as colunas menos `created_at`) idêntico ao de apagar e reinserir, para 200 sequências de edição sorteadas (semente fixa); `INSERT INTO chunks_fts(chunks_fts) VALUES('integrity-check')` ok.

## Medição

| Métrica | Antes | Depois |
|---|---|---|
| Embeddings após reinserir 19 chunks idênticos | 19 → 0 | **19 → 19**, `conn.total_changes` não muda (0 escritas) |
| Pontes entidade→chunk após reinserir | 18 → 0 | **19 → 19** |
| Chunks reescritos ao editar 1 linha | 9 | **1** (1 sai, 1 entra; os demais intactos) |
| Textos enviados ao embedder nessa edição | 1 | **1** (igual: a economia aqui é de vetores e pontes preservados, não de embedder) |

Comando: `uv run pytest tests/integration/test_replace_for_document.py -q` (o teste imprime os contadores com `-s`).

## Testes

- [x] `tests/integration/test_replace_for_document.py` (novo): idempotência, edição de um chunk, inserção no meio, troca de ordem, pai removido com filho vivo, remoção de documento (cascata continua limpando tudo), mudança de `heading_path` apaga só o embedding daquele chunk, equivalência com apagar-e-reinserir em 200 sequências sorteadas, `integrity-check` do FTS e busca FTS por termo removido sem resultado.
- [x] `tests/integration/test_pipeline.py`: `test_modificacao_reindexa_so_o_arquivo` e `test_mudanca_so_de_indentacao_final_nao_gera_chunk_novo` continuam verdes; reindexar após editar uma linha embute só o chunk novo.
- [x] `tests/integration/test_graph.py`: depois de `rebuild` e de uma edição de uma linha, as pontes `entities.chunk_id` dos chunks intactos continuam preenchidas.
- [x] `tests/security/test_surfaces.py` (ou arquivo novo): arquivo com chunk limpo ganha um segredo em outro trecho e a política é `strict`: o documento é bloqueado e removido, com 0 chunks e 0 embeddings dele no banco (nada sobrevive pelo diff); `leaked` não acha o valor em nenhuma tabela.

## Notas

- Confirmado em `repositories.py:87-105`, `0004_graph.sql:9,28` e `pipeline.py:261`. O único chamador de `replace_for_document` no código é o pipeline.
- O `UNIQUE (document_id, ordinal)` do SQLite é checado a cada instrução, não no fim da transação: por isso o desvio para ordinais negativos.
- `_dedupe_ids` (`chunkers/__init__.py:278+`) dá sufixo a chunks de conteúdo idêntico no mesmo arquivo; esses ids também participam do diff sem tratamento especial.
- Quem passa pelo caminho `BLOCK` continua em `docs.delete_many` (`pipeline.py:202`), não aqui; o teste de segurança acima prova que o diff não o contorna.
- Windows/SQLite: tudo na mesma transação do lote; nada de `executescript` (comita implicitamente).

## Definition of Done

- [x] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [x] Testes escritos e verdes (Windows rodado aqui; Linux e macOS pelo CI)
- [x] `ruff` e `mypy` limpos
- [x] Suíte `security/` continua verde
- [x] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [x] Documentação confere com o comportamento implementado
- [x] Commit `tipo(escopo): descrição (RAGX-0138)` na branch `feat/v2`

## Andamento

2026-10-01. Reproduzido primeiro: `tests/integration/test_replace_for_document.py` (novo, 8 testes) vermelho. Implementado `ChunkRepo.replace_for_document` por diff de id, na ordem pedida (órfãos -> NULL; DELETE dos removidos; ordinal
provisório `-(ordinal+1)` dos que mudam de lugar; INSERT dos novos; UPDATE só do que mudou) e `ReplaceStats(kept, added, removed, updated)`; ids repetidos (que o chunker não produz) caem no caminho antigo `_replace_all`. Se `symbol`, `heading_path` ou `kind`
de um sobrevivente muda, o vetor dele é descartado (o prefixo de contexto entra no texto embutido). `IndexReport.chunks_kept`/`chunks_removed` e as chaves no `ragx index --json`.
Verificado: reinserir 19 idênticos = 0 escritas e 19/19 vetores e pontes; editar um chunk = 1 sai e 1 entra, 18 mantêm `created_at`, vetor e ponte; inserção no meio e troca de ordem sem violar `UNIQUE`; pai removido com filho vivo (o filho
sobrevive com o novo pai, com o vetor); equivalência com apagar-e-reinserir em 200 sequências sorteadas (semente 20260930), estado de `chunks` idêntico e `integrity-check` do FTS ok; cascata ao apagar o documento intacta;
pipeline: editar uma linha de um arquivo de 12 funções reaproveita os chunks, 0 vetores perdidos e só 1 texto vai ao embedder; grafo: depois de `rebuild` e da edição, só a ponte do chunk editado fica sem chunk. Segurança: arquivo que ganha um segredo em OUTRO trecho é bloqueado e removido, sem sobrar chunk nem vetor dele.
Observação: o "Textos enviados ao embedder" já era 1 antes (o cache por `content_hash` poupava os demais); o ganho desta tarefa é de VETORES E PONTES preservados, e de menos escrita/FTS. O cache de embedding por `content_hash` continua podendo devolver vetor sem o prefixo novo (anterior a esta tarefa, fora de escopo, anotado).
Fast suite, `tests/security`, `ruff`, `mypy` verdes.
