# RAGX-0145 — Expansão do grafo: semeadura pelo topo, filtros e grau só dos visitados

| | |
|---|---|
| **Fase** | 19 — Velocidade e frescor |
| **Prioridade** | P1 — alta |
| **Estimativa** | 1d |
| **Depende de** | — |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (C-03, seção 2) · [25-spec-v2.md](../../docs/25-spec-v2.md) (R-V12) · [06-grafo.md](../../docs/06-grafo.md) · [07-context-engine.md](../../docs/07-context-engine.md) · [15-configuracao.md](../../docs/15-configuracao.md) |
| **Status** | `todo` |

## Objetivo

A expansão do grafo semeia **todas** as entidades dos documentos dos 100 melhores chunks e ignora `SearchFilters` (C-03). Medido em 12 consultas: **158–533 sementes**, `truncated` em todas, no máximo 6 nós visitados (com `max_nodes=200`, as próprias sementes já estouram o teto antes de a BFS andar), chunks acrescentados pelo grafo **0** em 9 consultas e 1–3 nas outras 3; com `path_glob`, **27 de 50** resultados ficavam fora do filtro; ~160 ms de custo por `build_context`. O grafo hoje gasta tempo para quase não contribuir. A tarefa conserta a semeadura, o filtro e o cálculo de grau, **sem** mexer em orçamento de tokens.

## Entregáveis

- [ ] **Medir primeiro**: script que roda `graph_search` em 12 consultas do próprio repo (as de `tests/eval/queries.yaml`) e imprime sementes, `visited`, `truncated`, chunks vindos do grafo, resultados fora do filtro (com `--path`) e o tempo do grafo excluindo a busca base; registrar em Medição
- [ ] Semeadura pelo topo (`src/ragx/graph/service.py:99-116`): sementes só das entidades cujo `chunk_id` está nos `cfg.graph.seed_top_k` primeiros chunks (padrão 10; ajustar depois de medir) mais, para chunk sem entidade (prosa), **uma** entidade de arquivo por documento. A nota de âncora é a do melhor chunk do documento, não `1.0` (linhas 112-115 dão `1.0` às sementes de documento, mais que ao chunk de topo). `ORDER BY` determinístico: `score DESC, id`
- [ ] `src/ragx/config.py:87-93`: `GraphCfg.seed_top_k: int = 10`; documentar em `docs/15-configuracao.md` e `docs/06-grafo.md`
- [ ] `src/ragx/graph/traversal.py:57-83`: as sementes não contam contra `max_nodes`; o teto vale para nós **expandidos**. Desempate das arestas determinístico (`weight DESC, other_id`) em vez da ordem de retorno do SQLite
- [ ] Grau só dos visitados: `GraphStore.degrees_for(ids)` em `src/ragx/graph/store.py` (consulta agrupada por `src_id`/`dst_id` sobre os índices `idx_relations_src` e `idx_relations_dst`, com memo dentro de `expand`); `degrees()` (linhas 241-248, subconsulta correlacionada sobre **todas** as entidades) deixa de ser chamado em `traversal.py:49`
- [ ] Filtros honrados: extrair o predicado de `_filter_mask` (`src/ragx/search/service.py:132-150`) para `filter_chunk_ids(conn, ids, filters)`, com a **mesma** semântica de `LIKE` (`*` vira `%`), e aplicá-lo aos chunks vindos do grafo antes de `_hydrate` (`graph/service.py:149-154`) e às sementes
- [ ] `ragx context --lang/--path` (`src/ragx/cli/commands/context_cmd.py:45`) já entrega `SearchFilters(lang, path_glob)` a `graph_search`: passa a valer também para o que vem do grafo. `ragx graph-search` só tem `--lang` (`graph_cmd.py:149`) e o MCP `search_graph` só repassa `lang` (`server.py:402-405`): os contratos ficam como estão (o do MCP é revisto na RAGX-0157)
- [ ] `--explain` e `pack.stats` (`src/ragx/context/engine.py:199-203`) passam a mostrar sementes, nós expandidos, truncado e quantos chunks vieram **só** do grafo
- [ ] `docs/06-grafo.md`: descrever a semeadura e o filtro; corrigir qualquer número de "209 nós de expansão" que sobrar

## Fora de escopo

- Orçamento de **tokens** da expansão, teto de fragmentos, união de fragmentos vizinhos (RAGX-0107, fase 14; o diagnóstico dela foi corrigido pela auditoria 24, seção 2: os 209 eram sementes)
- Estratégia de recuperação por intenção (RAGX-0106) e pesos da fusão RRF do grafo (`0.7`)
- Camada semântica do grafo (`graph.semantic`)
- Grafo incremental (RAGX-0151) e o cache de `build_context` (RAGX-0135)

## Critérios de aceite

- [ ] Nas 12 consultas: `graph_seeds` **≤ 3 × seed_top_k** (antes 158–533) e `truncated` falso em ao menos 10 delas
- [ ] Com `path_glob`, **0 de 50** resultados fora do filtro (antes 27 de 50); falha hoje, passa depois
- [ ] Custo do grafo (sem a busca base) **menos da metade** do medido (~160 ms); meta provisória, confirmada ou ajustada após "medir primeiro"
- [ ] `ragx eval` (tests/eval): recall e nDCG **não pioram** frente ao antes, e o número de consultas com chunk vindo só do grafo não cai (antes 3 de 12)
- [ ] Mesma consulta, mesma ordem de IDs em duas execuções seguidas (determinismo)

### Medição

| Métrica | Antes | Depois |
|---|---|---|
| Sementes por consulta (12 consultas) | 158–533 | |
| Nós visitados | ≤ 6 | |
| Consultas com `truncated` | 12 de 12 | |
| Chunks acrescentados só pelo grafo | 0 em 9, 1–3 em 3 | |
| Resultados fora do `path_glob` | 27 de 50 | |
| Custo do grafo por `build_context` | ~160 ms | |

Comando: `uv run python scripts/medir_grafo.py --consultas tests/eval/queries.yaml --n 12` (criar, imprimindo a tabela); recall: `uv run ragx eval`.

## Testes

- [ ] `tests/integration/test_graph.py`: com projeto de fixture grande o bastante, sementes ≤ `3 × seed_top_k` e a BFS passa de 1 nó visitado; `truncated` só quando os nós **expandidos** estouram `max_nodes`
- [ ] `tests/integration/test_graph.py`: `path_glob`, `lang` e `kind` valem para os chunks vindos do grafo (regressão que falha hoje)
- [ ] `tests/unit/test_graph_units.py`: `degrees_for(ids)` igual ao recorte de `degrees()`; empate de peso desempatado por `other_id`; 300 sementes não estouram `max_nodes` no nível 0
- [ ] `tests/unit/test_search_units.py`: `filter_chunk_ids` tem o mesmo resultado que `_filter_mask` para `*`, `%` e maiúsculas
- [ ] `tests/integration/test_context.py`: `stats` traz sementes/expandidos/truncado; `--explain` mostra a origem
- [ ] Não toca leitura de arquivo nem o gate (só lê o banco): sem teste novo em `tests/security`; rodar a suíte inteira mesmo assim

## Notas

- Confirmado em `src/ragx/graph/service.py:99-125` (sementes de `chunk_id IN (...) OR document_id IN (SELECT document_id FROM chunks WHERE id IN (...))`), `:153` (`_hydrate` sem filtro), `src/ragx/graph/traversal.py:49,62,66,77` e `src/ragx/graph/store.py:241-248`. `build_context` chama `graph_search(limit=want)` com `want = max(limit*5, 25)` e esta pede à busca base `max(limit*2, 20)` chunks (`service.py:91`): é de lá que vêm os "100 melhores".
- O fallback do motor (`engine._retrieve`) só cai para a busca híbrida se o grafo devolver **vazio**; com sementes melhores o grafo passa a devolver menos ruído, não menos resultados.
- `neighbors()` faz `UNION ALL` das duas direções; o grau de um vizinho conta relações de entrada **e** saída (mesma definição de `degrees()`): o teste de equivalência cobre isso.
- `LIKE` do SQLite ignora maiúsculas em ASCII e `fnmatch` do Python não: por isso o filtro do grafo reutiliza o SQL, não reimplementa em Python.
- Se, depois do conserto, o grafo continuar sem acrescentar chunks úteis (recall igual e 0 de 12 com chunk só do grafo), registrar em Andamento com os números e propor desligar `include_graph` por padrão em outra tarefa; não decidir aqui.
- Mudança no que o grafo devolve muda o conteúdo do `build_context`: avisar no CHANGELOG, e lembrar que o cache do contexto (RAGX-0135) invalida pela versão do índice, não pelo código.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes em Linux, macOS e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [ ] Documentação confere com o comportamento implementado
- [ ] Commit `tipo(escopo): descrição (RAGX-0145)` na branch `feat/v2`

## Andamento

_(o loop registra aqui o que fez, com datas e medições)_
