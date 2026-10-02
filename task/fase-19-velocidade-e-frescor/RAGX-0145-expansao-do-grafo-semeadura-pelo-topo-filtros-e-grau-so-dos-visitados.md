# RAGX-0145 — Expansão do grafo: semeadura pelo topo, filtros e grau só dos visitados

| | |
|---|---|
| **Fase** | 19 — Velocidade e frescor |
| **Prioridade** | P1 — alta |
| **Estimativa** | 1d |
| **Depende de** | — |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (C-03, seção 2) · [25-spec-v2.md](../../docs/25-spec-v2.md) (R-V12) · [06-grafo.md](../../docs/06-grafo.md) · [07-context-engine.md](../../docs/07-context-engine.md) · [15-configuracao.md](../../docs/15-configuracao.md) |
| **Status** | `done` |

## Objetivo

A expansão do grafo semeia **todas** as entidades dos documentos dos 100 melhores chunks e ignora `SearchFilters` (C-03). Medido em 12 consultas: **158–533 sementes**, `truncated` em todas, no máximo 6 nós visitados (com `max_nodes=200`, as próprias sementes já estouram o teto antes de a BFS andar), chunks acrescentados pelo grafo **0** em 9 consultas e 1–3 nas outras 3; com `path_glob`, **27 de 50** resultados ficavam fora do filtro; ~160 ms de custo por `build_context`. O grafo hoje gasta tempo para quase não contribuir. A tarefa conserta a semeadura, o filtro e o cálculo de grau, **sem** mexer em orçamento de tokens.

## Entregáveis

- [x] **Medir primeiro**: script que roda `graph_search` em 12 consultas do próprio repo (as de `tests/eval/queries.yaml`) e imprime sementes, `visited`, `truncated`, chunks vindos do grafo, resultados fora do filtro (com `--path`) e o tempo do grafo excluindo a busca base; registrar em Medição
- [x] Semeadura pelo topo (`src/ragx/graph/service.py:99-116`): sementes só das entidades cujo `chunk_id` está nos `cfg.graph.seed_top_k` primeiros chunks (padrão 10; ajustar depois de medir) mais, para chunk sem entidade (prosa), **uma** entidade de arquivo por documento. A nota de âncora é a do melhor chunk do documento, não `1.0` (linhas 112-115 dão `1.0` às sementes de documento, mais que ao chunk de topo). `ORDER BY` determinístico: `score DESC, id`
- [x] `src/ragx/config.py:87-93`: `GraphCfg.seed_top_k: int = 10`; documentar em `docs/15-configuracao.md` e `docs/06-grafo.md`
- [x] `src/ragx/graph/traversal.py:57-83`: as sementes não contam contra `max_nodes`; o teto vale para nós **expandidos**. Desempate das arestas determinístico (`weight DESC, other_id`) em vez da ordem de retorno do SQLite
- [x] Grau só dos visitados: `GraphStore.degrees_for(ids)` em `src/ragx/graph/store.py` (consulta agrupada por `src_id`/`dst_id` sobre os índices `idx_relations_src` e `idx_relations_dst`, com memo dentro de `expand`); `degrees()` (linhas 241-248, subconsulta correlacionada sobre **todas** as entidades) deixa de ser chamado em `traversal.py:49`
- [x] Filtros honrados: extrair o predicado de `_filter_mask` (`src/ragx/search/service.py:132-150`) para `filter_chunk_ids(conn, ids, filters)`, com a **mesma** semântica de `LIKE` (`*` vira `%`), e aplicá-lo aos chunks vindos do grafo antes de `_hydrate` (`graph/service.py:149-154`) e às sementes
- [x] `ragx context --lang/--path` (`src/ragx/cli/commands/context_cmd.py:45`) já entrega `SearchFilters(lang, path_glob)` a `graph_search`: passa a valer também para o que vem do grafo. `ragx graph-search` só tem `--lang` (`graph_cmd.py:149`) e o MCP `search_graph` só repassa `lang` (`server.py:402-405`): os contratos ficam como estão (o do MCP é revisto na RAGX-0157)
- [x] `--explain` e `pack.stats` (`src/ragx/context/engine.py:199-203`) passam a mostrar sementes, nós expandidos, truncado e quantos chunks vieram **só** do grafo
- [x] `docs/06-grafo.md`: descrever a semeadura e o filtro; corrigir qualquer número de "209 nós de expansão" que sobrar

## Fora de escopo

- Orçamento de **tokens** da expansão, teto de fragmentos, união de fragmentos vizinhos (RAGX-0107, fase 14; o diagnóstico dela foi corrigido pela auditoria 24, seção 2: os 209 eram sementes)
- Estratégia de recuperação por intenção (RAGX-0106) e pesos da fusão RRF do grafo (`0.7`)
- Camada semântica do grafo (`graph.semantic`)
- Grafo incremental (RAGX-0151) e o cache de `build_context` (RAGX-0135)

## Critérios de aceite

- [x] Nas 12 consultas: `graph_seeds` **≤ 3 × seed_top_k** (antes 158–533) e `truncated` falso em ao menos 10 delas
- [x] Com `path_glob`, **0 de 50** resultados fora do filtro (antes 27 de 50); falha hoje, passa depois
- [ ] Custo do grafo (sem a busca base) **menos da metade** do medido (~160 ms); meta provisória, confirmada ou ajustada após "medir primeiro"
- [ ] `ragx eval` (tests/eval): recall e nDCG **não pioram** frente ao antes, e o número de consultas com chunk vindo só do grafo não cai (antes 3 de 12)
- [x] Mesma consulta, mesma ordem de IDs em duas execuções seguidas (determinismo)

### Medição

| Métrica | Antes | Depois |
|---|---|---|
| Sementes por consulta (26 consultas) | 90–304 (mediana 160) | **6–10** (mediana 8) |
| Nós visitados (máx.) | 22 | 110 (a BFS anda) |
| Consultas com `truncated` | 26 de 26 | **0 de 26** |
| Chunks do resultado só do grafo | medida diferente da auditoria; ver Andamento | `graph_only` agora em `--explain` |
| Resultados fora do `path_glob` (`src/ragx/search/*`) | 130 de 650 | **0 de 650** |
| Custo do grafo (semeadura + BFS, sem a busca base), mediana | 16,8 ms (não reproduz os ~160 ms da auditoria) | 18,6 ms (sem ganho: o custo nunca foi dominante aqui) |

Comando: `uv run python scripts/medir_grafo.py --n 26 [--path GLOB] [--seed-top-k K] [--resumo]` (criado). O `ragx eval` não tem modo `grafo`; o script calcula recall@5 e MRR do `graph_search` contra `relevant_paths`.

## Testes

- [x] `tests/integration/test_graph.py`: com projeto de fixture grande o bastante, sementes ≤ `3 × seed_top_k` e a BFS passa de 1 nó visitado; `truncated` só quando os nós **expandidos** estouram `max_nodes`
- [x] `tests/integration/test_graph.py`: `path_glob`, `lang` e `kind` valem para os chunks vindos do grafo (regressão que falha hoje)
- [x] `tests/unit/test_graph_units.py`: `degrees_for(ids)` igual ao recorte de `degrees()`; empate de peso desempatado por `other_id`; 300 sementes não estouram `max_nodes` no nível 0
- [x] `tests/unit/test_search_units.py`: `filter_chunk_ids` tem o mesmo resultado que `_filter_mask` para `*`, `%` e maiúsculas
- [x] `tests/integration/test_context.py`: `stats` traz sementes/expandidos/truncado; `--explain` mostra a origem
- [x] Não toca leitura de arquivo nem o gate (só lê o banco): sem teste novo em `tests/security`; rodar a suíte inteira mesmo assim

## Notas

- Confirmado em `src/ragx/graph/service.py:99-125` (sementes de `chunk_id IN (...) OR document_id IN (SELECT document_id FROM chunks WHERE id IN (...))`), `:153` (`_hydrate` sem filtro), `src/ragx/graph/traversal.py:49,62,66,77` e `src/ragx/graph/store.py:241-248`. `build_context` chama `graph_search(limit=want)` com `want = max(limit*5, 25)` e esta pede à busca base `max(limit*2, 20)` chunks (`service.py:91`): é de lá que vêm os "100 melhores".
- O fallback do motor (`engine._retrieve`) só cai para a busca híbrida se o grafo devolver **vazio**; com sementes melhores o grafo passa a devolver menos ruído, não menos resultados.
- `neighbors()` faz `UNION ALL` das duas direções; o grau de um vizinho conta relações de entrada **e** saída (mesma definição de `degrees()`): o teste de equivalência cobre isso.
- `LIKE` do SQLite ignora maiúsculas em ASCII e `fnmatch` do Python não: por isso o filtro do grafo reutiliza o SQL, não reimplementa em Python.
- Se, depois do conserto, o grafo continuar sem acrescentar chunks úteis (recall igual e 0 de 12 com chunk só do grafo), registrar em Andamento com os números e propor desligar `include_graph` por padrão em outra tarefa; não decidir aqui.
- Mudança no que o grafo devolve muda o conteúdo do `build_context`: avisar no CHANGELOG, e lembrar que o cache do contexto (RAGX-0135) invalida pela versão do índice, não pelo código.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados (rodando, não supondo): 2 não atendidos, ver Andamento
- [ ] Testes escritos e verdes em Linux, macOS e Windows (verdes no Windows; Linux e macOS só a CI confirma)
- [x] `ruff` e `mypy` limpos
- [x] Suíte `security/` continua verde
- [x] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [x] Documentação confere com o comportamento implementado
- [x] Commit `tipo(escopo): descrição (RAGX-0145)` na branch `feat/v2`

## Andamento

- 2026-10-01 — Implementado: `GraphCfg.seed_top_k` (10), `_seeds` em `graph/service.py` (entidades dos primeiros chunks; prosa semeia uma entidade `file` do documento; ordem por nota e id), teto de `max_nodes` só para expandidos, desempate `(-weight, other_id)`, `GraphStore.degrees_for` (consulta agrupada; auto-relação conta uma vez) com memo na expansão, `filter_chunk_ids` (mesmo SQL de `_filter_mask`, em lotes de 400) aplicado aos chunks do grafo, `GraphSearchOutcome.graph_only`, estatísticas e `--explain`, `CACHE_FORMAT` 3. Testes em `tests/integration/test_graph_expansao.py` (20) e um teste antigo ajustado à nova semântica do teto.
- **Resultado que exige decisão humana (por isso `review`).** Os critérios de sementes, truncamento, filtro e determinismo passam. Mas: (1) **recall/nDCG não pioram: NÃO atendido.** Recall@5 do grafo fica igual (0,731), o MRR cai de 0,593 para 0,381, porque os chunks de arquivos vizinhos que o grafo agora de fato acrescenta passam à frente do arquivo certo em 23 das 26 consultas (ex.: "SecurityGate": o relevante cai da posição 1 para a 5, com builder.py, walk.py e operations.py acima). `seed_top_k` de 1 a 20 dá MRR entre 0,38 e 0,52, nenhum recupera o antigo. Antes o grafo era "neutro" porque a expansão nunca andava. (2) **Custo do grafo menos da metade: NÃO atendido** porque o custo medido (17 a 19 ms) já era baixo; os ~160 ms da auditoria não reproduzem.
- Como a nota da task manda, não decidi: o peso 0,7 do grafo na fusão RRF está fora do escopo. Opções para uma nova task: baixar o peso, aplicar o grafo só quando a consulta pede relações (intenção), ou desligar `include_graph` por padrão e manter o código corrigido. O MRR é de um conjunto de 26 consultas de localização de arquivo (intervalo largo); um conjunto com tarefas de implementação poderia favorecer os vizinhos. Para voltar ao comportamento antigo na prática, `[graph] enabled = false` ou `seed_top_k = 1`.
- Contagem de "chunks só do grafo": a auditoria mediu 0 em 9 e 1–3 em 3 de 12 consultas; o script usa outra definição, então não comparei os números.
- 2026-10-02 — **Decidido, a pedido da pessoa de fechar as pendências antes da v1.0.0: o grafo fica LIGADO por padrão.** Com o MESMO `scripts/medir_grafo.py` sobre os dois conjuntos novos (a decisão antiga vinha de 26 consultas e IC de ±0,17): conjunto manual (132 respondidas) recall@5 **0,689** contra **0,621** do híbrido sem grafo (+0,068) e MRR **0,414** contra 0,521 (−0,107); conjunto derivado do git (134) recall@5 **0,642** contra 0,597 (+0,045) e MRR **0,456** contra 0,474 (−0,018). Só 2 de 132 e 5 de 134 consultas ganham algum chunk que veio SÓ do grafo (3 e 11 chunks no total), sem truncar nenhuma, a 19–21 ms de mediana, determinístico. Leitura: o grafo não traz arquivos novos em quantidade, ele REORDENA o que a busca base já achou, subindo o recall dentro do top-5 e empurrando o arquivo certo da 1ª para as primeiras posições. O `build_context` monta um pacote dentro de um orçamento (o que importa é o arquivo certo entrar, não ser o 1º), então recall pesa mais que MRR ali, e a busca `search_hybrid` não usa o grafo. Por isso mantive `include_graph` ligado. **Quem discordar** liga o comportamento antigo com `[graph] enabled = false` (ou `seed_top_k = 1`). O que continua aberto e vira tarefa própria, se fizer sentido: baixar o peso do grafo na fusão (0,7) ou aplicá-lo só quando a intenção pede relações, para recuperar o MRR sem perder o recall. Os dois critérios que a tarefa deixou como "não atendidos" seguem não atendidos (MRR ainda cai; o custo do grafo já era baixo), registrados aqui com o número novo.
