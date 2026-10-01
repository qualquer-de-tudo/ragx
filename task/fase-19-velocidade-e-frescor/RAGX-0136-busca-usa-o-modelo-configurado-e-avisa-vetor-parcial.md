# RAGX-0136 — Busca usa o modelo configurado e avisa vetor parcial

| | |
|---|---|
| **Fase** | 19 — Velocidade e frescor |
| **Prioridade** | P1 — alta |
| **Estimativa** | 0,5d |
| **Depende de** | RAGX-0134 |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (C-07, I-10) · [25-spec-v2.md](../../docs/25-spec-v2.md) (R-V7) · [05-busca.md](../../docs/05-busca.md) · [ADR-0004](../../docs/adr/ADR-0004-embeddings.md) |
| **Status** | `todo` |

## Objetivo

`load_index` escolhe o modelo **mais recente do banco**, não o configurado (`storage/vectors.py:102-109`, `ORDER BY created_at DESC LIMIT 1`, com resolução de 1 s), e `_semantic` (`search/service.py:115-129`) carrega o índice antes de construir o embedder. Medido: `hashing dim=64` contra índice 192d dá `ValueError: matmul` (a falha estoura **fora** do `try` que só cobre o embedder); com outro modelo da mesma dimensão o resultado é aleatório e silencioso. Vetor parcial (embedder caiu no meio) também degrada a busca sem aviso: `degraded` só marca "0 embeddings".

## Entregáveis

- [ ] **Reproduzir primeiro:** os dois casos acima como testes vermelhos.
- [ ] `_semantic` usa `embedder_id(cfg)` (criada na RAGX-0130, `embeddings/__init__.py`) e chama `load_index(conn, model_id)`; o cache da RAGX-0134 já é por `(banco, modelo)`.
- [ ] Índice vazio para o modelo configurado: se existem vetores de **outro** modelo (`SELECT model_id, COUNT(*) FROM embeddings GROUP BY model_id`), `degraded` diz quais e o comando (`índice vetorial é de X, a configuração pede Y — rode: ragx index --embed-only`); sem vetor nenhum, mantém a mensagem atual (`service.py:120`). Nos dois casos a busca híbrida segue só com keyword.
- [ ] Guarda de dimensão: `qvec.size < index.versioned_dim` (ou diferente da dimensão registrada) vira `degraded` em vez de `ValueError`.
- [ ] Vetor parcial: `SearchOutcome` (`service.py:35-40`) ganha `partial: str | None`, preenchido quando `index.size < COUNT(*) FROM chunks` (`vetores parciais: N de M chunks`). `degraded` mantém o significado "o semântico não rodou"; com `partial` a busca semântica **roda**.
- [ ] Propagar `partial`: `KnowledgeAPI.search` (`mcp/server.py:184-210`, só serializa), `ragx search` (`search_cmd.py`) e `stats` do `ContextPack` (`partial_vectors`).
- [ ] `context/engine._vectors_for` (`engine.py:264-300`) troca `ORDER BY created_at DESC LIMIT 1` (275-277) por `embedder_id(cfg)`; modelo configurado sem vetores devolve `({}, None)`. `_resolve_model` (`vectors.py:106-108`) ganha desempate `rowid DESC` para o caso sem `model_id`.
- [ ] `docs/05-busca.md`: seção "degradação" com os três motivos (sem vetores, modelo diferente, parcial).
- [ ] CHANGELOG.

## Fora de escopo

- Reembutir ou migrar o índice para outro modelo: `ragx index --embed-only` existe; trocar o modelo é a RAGX-0103.
- Busca federada com modelos diferentes (já tem regra própria em `federation/search.py:128-136`).
- Clone novo usando os embeddings versionados: RAGX-0144. `serialize` escolher o modelo (`sync/serialize.py:140-142`): mesmo assunto, tarefa própria se aparecer.
- Cache da matriz: RAGX-0134 (dependência).

## Critérios de aceite

- [ ] Índice 192d com `hashing dim=64` configurado: sem exceção, `degraded` preenchido, resultados só de keyword.
- [ ] Dois modelos com a mesma dimensão no banco: a busca usa o configurado; se o configurado não tem vetor, `degraded` cita os dois e **nenhum** resultado traz `semantic` em `matched_by`.
- [ ] Com 50% dos chunks embutidos: `partial` preenchido e a busca devolve hits semânticos.
- [ ] Busca com tudo correto: sem `degraded` nem `partial`, ids idênticos aos de hoje nas 26 consultas de `tests/eval/queries.yaml`.
- [ ] A resposta MCP só ganha o campo `partial` quando ele existe (não acrescenta `null` ao fio; ver RAGX-0155).

## Testes

- [ ] `tests/integration/test_search.py`: modelo diferente com mesma dimensão e com dimensão diferente (`ValueError` hoje, **falha antes**); índice parcial; índice sem vetores.
- [ ] `tests/integration/test_search.py`: `test_embedder_fora_do_ar_degrada_para_keyword` (linha 156) continua verde.
- [ ] `tests/integration/test_mcp.py`: `test_dedup_nao_mistura_modelos_de_embedding` (linha 413) continua verde com `_vectors_for` pelo modelo configurado; resposta de `search_hybrid` traz `partial` só quando aplicável.
- [ ] `tests/unit/test_search_units.py`: `_resolve_model` determinístico com dois modelos de mesmo `created_at`.
- [ ] `tests/security/`: nenhuma alteração; confirmar que a suíte segue verde (nenhum caminho de leitura de arquivo foi tocado).

## Notas

- Confirmado em `vectors.py:102-109`, `service.py:118-129` (o `try` das linhas 121-125 cobre só o embedder), `engine.py:275-277`.
- Dependência prática: `embedder_id` nasce na RAGX-0130. Se por alguma razão ela ainda não estiver `done`, criar a função aqui com o contrato descrito lá (sem construir o provider; `build_embedder(cfg).id == embedder_id(cfg)`), em vez de duplicar a lógica.
- O custo extra é um `COUNT(*)` em `chunks` e um `GROUP BY` só quando o índice do modelo vem vazio; ambos em milissegundos.
- `pipeline.status()` (`pipeline.py:406-408`) e o painel mostram "o último modelo registrado"; isso é informativo e fica como está.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes em Linux, macOS e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [ ] Documentação confere com o comportamento implementado
- [ ] Commit `tipo(escopo): descrição (RAGX-0136)` na branch `feat/v2`

## Andamento

_(o loop registra aqui o que fez, com datas e medições)_
