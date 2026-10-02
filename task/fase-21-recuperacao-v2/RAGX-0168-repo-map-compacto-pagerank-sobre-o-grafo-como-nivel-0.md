# RAGX-0168 — Repo map compacto (PageRank sobre o grafo) como nível 0

| | |
|---|---|
| **Fase** | 21 — Recuperação v2 |
| **Prioridade** | P2 — média |
| **Estimativa** | 2d |
| **Depende de** | `RAGX-0111` (fase 14) · `RAGX-0145` |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (7.2 #9) · [06-grafo.md](../../docs/06-grafo.md) · [08-dictionary.md](../../docs/08-dictionary.md) · [09-mcp.md](../../docs/09-mcp.md) |
| **Status** | `doing` |

## Objetivo

O agente que chega num repositório não sabe quais arquivos importam. `get_dictionary` entrega 8.660 tokens indentados (7.098 compactos; `services` sozinho = 3.031) e **nenhum** deles ordena os arquivos por importância. O repo map do Aider (PageRank sobre o grafo de referências, ~1k tokens) teve o melhor rendimento a 8K tokens no Agent Retrieval Bench (arxiv 2607.24882). Este repo tem o insumo pronto: 598 arquivos e relações no grafo (`calls` 7.947, `imports` 97, `uses` 7, medido no `.ragx/knowledge.db`). A meta é um mapa de **≤ 600 tokens** que cabe no nível 0 do dicionário (S3: ≤ 800 tokens no total).

## Entregáveis

- [ ] **Medir primeiro**: com SQL somente leitura sobre `.ragx/knowledge.db`, contar arestas arquivo→arquivo distintas **por tipo** (`calls`, `imports`, `extends`, `uses`) e o desvio das 20 entidades com maior grau; registrar em Andamento. As 7.759 arestas distintas já medidas incluem `documented_by` (4.578) e `mentions`, que são prosa e **não** devem pesar no mapa
- [ ] `src/ragx/graph/rank.py`: `file_rank(conn, damping=0.85, iters=50)` projeta `relations` para o nível de arquivo (`entities.document_id`), peso = `weight * confidence` somado por par, só tipos de código; descarta aresta cujo destino tem **nome ambíguo** (mais de 5 entidades com o mesmo `name`; o extrator `graph/extractors/reference.py` casa chamadas por nome e gera hubs falsos com `get`, `build`, `run`). Iteração de potência em NumPy sobre listas de arestas (`np.bincount`), massa de nó sem saída redistribuída; sem dependência nova (numpy já é obrigatório em `pyproject.toml`)
- [ ] Desempate determinístico (rank arredondado a 6 casas, depois caminho) e nenhum timestamp: a saída entra no `knowledge/` versionado e não pode sujar o git (`I-12`)
- [ ] `repo_map(cfg, tokens=600, files=None)` em `graph/rank.py`: os N melhores arquivos de código (camada `knowledge` de `ragx.tiers`; fora `task/`, `knowledge/`, testes), cada um com até 3 símbolos (classes e funções de maior grau de entrada), uma linha por arquivo no formato `caminho: Simbolo1, Simbolo2`; corta pelo orçamento com `ragx.tokens.count_tokens`
- [ ] `dictionary/builder.py`: nova seção `repo_map` (lista de `{path, rank, symbols}`) calculada em `build` (linhas 46–80) e contada por `_fit_budget` (linha 386), que hoje só sabe aparar seções antigas
- [ ] `get_dictionary(level=0)` (entregue pela `RAGX-0111`) passa a incluir `repo_map`; confirmar o nome real da função/seção no código da 0111 antes de editar e, se a 0111 tiver escolhido outro formato, adaptar em vez de duplicar
- [ ] `ragx graph rank [--top N]` (comando em `cli/commands/graph_cmd.py`) imprime o mapa e a posição dos arquivos para inspeção humana; documentar em `docs/14-cli.md`
- [ ] Atualizar `docs/06-grafo.md` (o algoritmo e o filtro de nome ambíguo), `docs/08-dictionary.md` e `docs/09-mcp.md` (nível 0 com mapa)

## Fora de escopo

- Injetar o mapa no hint do SessionStart: o tamanho do hint é da `RAGX-0164`; esta tarefa só expõe `repo_map()` para ela
- Mudar o extrator do grafo ou criar relações novas (`RAGX-0145` cuida da expansão; o filtro de ambiguidade aqui é só do ranking)
- Qualquer dependência de grafo externa (networkx, scipy) e ANN
- Mapa por símbolo ou por linha (o nível é o arquivo)

## Critérios de aceite

- [ ] `repo_map(tokens=600)` devolve **≤ 600 tokens** (`count_tokens`) e é **idêntico** em duas execuções seguidas, e depois de `ragx graph rebuild` sem mudança de código
- [ ] Cobertura medida: fração dos `relevant_paths` de `tests/eval/queries.yaml` que aparece no mapa, comparada com o controle "top-N por quantidade de chunks"; o PageRank deve **igualar ou superar** o controle. Se não superar, registrar o número em Notas e **não** ligar o mapa no nível 0
- [ ] Os 10 primeiros arquivos do mapa deste repo incluem pelo menos 5 dos 8 núcleos conhecidos (`security/gate.py`, `indexing/pipeline.py`, `search/service.py`, `context/engine.py`, `mcp/server.py`, `storage/db.py`, `config.py`, `graph/service.py`); a lista fixa e o resultado vão em Andamento
- [ ] `file_rank` roda em menos de **100 ms** no grafo deste repo (15 mil relações) e a seção não leva `dictionary generate` acima de 1,3 s (hoje 1,0 s)
- [ ] `get_dictionary(level=0)` continua ≤ 800 tokens com o mapa dentro (S3)

### Medição

| Métrica | Antes | Depois |
|---|---|---|
| Tokens de `get_dictionary` (visão geral, indentado) | 8.660 | (medir nível 0) |
| Cobertura dos arquivos relevantes no mapa (controle por chunks / PageRank) | n/a | (medir) |
| Tempo de `dictionary.build` | 1,0 s | (medir) |

Comando: `uv run ragx graph rank --top 40` e `uv run ragx dictionary generate` com `time`

## Testes

- [ ] `tests/unit/test_graph_rank.py`: grafo de brinquedo em memória com resultado conhecido (A chamado por B e C ganha de B); nó sem saída não vaza massa; aresta para nome ambíguo é ignorada; saída determinística entre duas chamadas
- [ ] `tests/integration/test_dictionary.py`: a seção `repo_map` existe, respeita o orçamento e não contém caminho de `task/` nem de `knowledge/`
- [ ] `tests/integration/test_mcp.py`: `get_dictionary(level=0)` inclui o mapa; o teste que compara ferramentas registradas com `docs/09-mcp.md` segue verde
- [ ] `tests/security/test_gate.py`: arquivo bloqueado pelo gate não aparece no mapa (o grafo só conhece documentos liberados)

## Notas

Armadilha principal: as 7.947 relações `calls` vêm de casar o **nome** da chamada com qualquer entidade homônima (confiança 0,75); sem o filtro de ambiguidade o PageRank premia nomes genéricos, não arquivos centrais. O mapa só vale com o grafo reconstruído (`ragx graph rebuild`); se o grafo estiver vazio, `repo_map` devolve lista vazia e o nível 0 omite a seção. Se a premissa de ganho não se confirmar na cobertura, entregar `ragx graph rank` como ferramenta de inspeção e deixar o nível 0 como está.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes em Linux, macOS e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [ ] Documentação confere com o comportamento implementado
- [ ] Commit `tipo(escopo): descrição (RAGX-0168)` na branch `feat/v2`

## Andamento

- 2026-10-02 — **`blocked`, nada implementado.** depende da RAGX-0111 (fase 14, `get_dictionary` em níveis), que continua `todo`, e da RAGX-0145, que está em `review` (queda do MRR do grafo, decisão humana). Verificado nos arquivos das dependências (todas ainda com `Status = todo`/`review`). Quando a dependência fechar, voltar o status para `todo` e retomar daqui.
