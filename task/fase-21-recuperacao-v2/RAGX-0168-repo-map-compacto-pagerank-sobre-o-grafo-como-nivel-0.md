# RAGX-0168 — Repo map compacto (PageRank sobre o grafo) como nível 0

| | |
|---|---|
| **Fase** | 21 — Recuperação v2 |
| **Prioridade** | P2 — média |
| **Estimativa** | 2d |
| **Depende de** | `RAGX-0111` (fase 14) · `RAGX-0145` |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (7.2 #9) · [06-grafo.md](../../docs/06-grafo.md) · [08-dictionary.md](../../docs/08-dictionary.md) · [09-mcp.md](../../docs/09-mcp.md) |
| **Status** | `done` |

## Objetivo

O agente que chega num repositório não sabe quais arquivos importam. `get_dictionary` entrega 8.660 tokens indentados (7.098 compactos; `services` sozinho = 3.031) e **nenhum** deles ordena os arquivos por importância. O repo map do Aider (PageRank sobre o grafo de referências, ~1k tokens) teve o melhor rendimento a 8K tokens no Agent Retrieval Bench (arxiv 2607.24882). Este repo tem o insumo pronto: 598 arquivos e relações no grafo (`calls` 7.947, `imports` 97, `uses` 7, medido no `.ragx/knowledge.db`). A meta é um mapa de **≤ 600 tokens** que cabe no nível 0 do dicionário (S3: ≤ 800 tokens no total).

## Entregáveis

- [x] **Medir primeiro**: com SQL somente leitura sobre `.ragx/knowledge.db`, contar arestas arquivo→arquivo distintas **por tipo** (`calls`, `imports`, `extends`, `uses`) e o desvio das 20 entidades com maior grau; registrar em Andamento. As 7.759 arestas distintas já medidas incluem `documented_by` (4.578) e `mentions`, que são prosa e **não** devem pesar no mapa
- [x] `src/ragx/graph/rank.py`: `file_rank(conn, damping=0.85, iters=50)` projeta `relations` para o nível de arquivo (`entities.document_id`), peso = `weight * confidence` somado por par, só tipos de código; descarta aresta cujo destino tem **nome ambíguo** (mais de 5 entidades com o mesmo `name`; o extrator `graph/extractors/reference.py` casa chamadas por nome e gera hubs falsos com `get`, `build`, `run`). Iteração de potência em NumPy sobre listas de arestas (`np.bincount`), massa de nó sem saída redistribuída; sem dependência nova (numpy já é obrigatório em `pyproject.toml`)
- [x] Desempate determinístico (rank arredondado a 6 casas, depois caminho) e nenhum timestamp: a saída entra no `knowledge/` versionado e não pode sujar o git (`I-12`)
- [x] `repo_map(cfg, tokens=600, files=None)` em `graph/rank.py`: os N melhores arquivos de código (camada `knowledge` de `ragx.tiers`; fora `task/`, `knowledge/`, testes), cada um com até 3 símbolos (classes e funções de maior grau de entrada), uma linha por arquivo no formato `caminho: Simbolo1, Simbolo2`; corta pelo orçamento com `ragx.tokens.count_tokens`
- [x] `dictionary/builder.py`: nova seção `repo_map` (lista de `{path, rank, symbols}`) calculada em `build` (linhas 46–80) e contada por `_fit_budget` (linha 386), que hoje só sabe aparar seções antigas
- [x] `get_dictionary(level=0)` (entregue pela `RAGX-0111`) passa a incluir `repo_map`; confirmar o nome real da função/seção no código da 0111 antes de editar e, se a 0111 tiver escolhido outro formato, adaptar em vez de duplicar
- [x] `ragx graph rank [--top N]` (comando em `cli/commands/graph_cmd.py`) imprime o mapa e a posição dos arquivos para inspeção humana; documentar em `docs/14-cli.md`
- [x] Atualizar `docs/06-grafo.md` (o algoritmo e o filtro de nome ambíguo), `docs/08-dictionary.md` e `docs/09-mcp.md` (nível 0 com mapa)

## Fora de escopo

- Injetar o mapa no hint do SessionStart: o tamanho do hint é da `RAGX-0164`; esta tarefa só expõe `repo_map()` para ela
- Mudar o extrator do grafo ou criar relações novas (`RAGX-0145` cuida da expansão; o filtro de ambiguidade aqui é só do ranking)
- Qualquer dependência de grafo externa (networkx, scipy) e ANN
- Mapa por símbolo ou por linha (o nível é o arquivo)

## Critérios de aceite

- [x] `repo_map(tokens=600)` devolve **≤ 600 tokens** (`count_tokens`) e é **idêntico** em duas execuções seguidas, e depois de `ragx graph rebuild` sem mudança de código
- [x] Cobertura medida: fração dos `relevant_paths` de `tests/eval/queries.yaml` que aparece no mapa, comparada com o controle "top-N por quantidade de chunks"; o PageRank deve **igualar ou superar** o controle. Se não superar, registrar o número em Notas e **não** ligar o mapa no nível 0
- [ ] **NÃO ATENDIDO** (2 dos 8). Os 10 primeiros arquivos do mapa deste repo incluem pelo menos 5 dos 8 núcleos conhecidos (`security/gate.py`, `indexing/pipeline.py`, `search/service.py`, `context/engine.py`, `mcp/server.py`, `storage/db.py`, `config.py`, `graph/service.py`); a lista fixa e o resultado vão em Andamento
- [x] `file_rank` roda em menos de **100 ms** no grafo deste repo (15 mil relações) e a seção não leva `dictionary generate` acima de 1,3 s (hoje 1,0 s)
- [x] `get_dictionary(level=0)` continua ≤ 800 tokens com o mapa dentro (S3)

### Medição

| Métrica | Antes | Depois |
|---|---|---|
| Tokens de `get_dictionary` (visão geral, indentado) | 8.660 (auditoria); 3.701 depois da 0110 | nível 0 **690** (≤ 800 ✓), nível 1 2.070, nível 2 3.808 |
| Cobertura dos arquivos relevantes no mapa (controle por chunks / PageRank) | n/a | controle (36 arquivos com mais chunks) **11 de 114**; PageRank **27 de 114** (ambiguidade > 3) ou 24 de 114 (> 5, o valor da tarefa) |
| Tempo de `dictionary.build` | 1,0 s (a CLI inteira) | `builder.build` em processo: 0,14 s sem o mapa, 0,16 s com (+20 ms); `file_rank` sozinho 20 ms |

Comando: `uv run ragx graph rank --top 40` e `uv run ragx dictionary generate` com `time`

## Testes

- [x] `tests/unit/test_graph_rank.py`: grafo de brinquedo em memória com resultado conhecido (A chamado por B e C ganha de B); nó sem saída não vaza massa; aresta para nome ambíguo é ignorada; saída determinística entre duas chamadas
- [x] `tests/integration/test_dictionary.py`: a seção `repo_map` existe, respeita o orçamento e não contém caminho de `task/` nem de `knowledge/`
- [x] `tests/integration/test_mcp.py`: `get_dictionary(level=0)` inclui o mapa; o teste que compara ferramentas registradas com `docs/09-mcp.md` segue verde
- [x] `tests/security/test_gate.py`: arquivo bloqueado pelo gate não aparece no mapa (o grafo só conhece documentos liberados)

## Notas

Armadilha principal: as 7.947 relações `calls` vêm de casar o **nome** da chamada com qualquer entidade homônima (confiança 0,75); sem o filtro de ambiguidade o PageRank premia nomes genéricos, não arquivos centrais. O mapa só vale com o grafo reconstruído (`ragx graph rebuild`); se o grafo estiver vazio, `repo_map` devolve lista vazia e o nível 0 omite a seção. Se a premissa de ganho não se confirmar na cobertura, entregar `ragx graph rank` como ferramenta de inspeção e deixar o nível 0 como está.

## Definition of Done

- [x] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes em Linux, macOS e Windows (verdes no Windows; Linux e macOS só a CI)
- [x] `ruff` e `mypy` limpos
- [x] Suíte `security/` continua verde
- [x] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [x] Documentação confere com o comportamento implementado
- [x] Commit `tipo(escopo): descrição (RAGX-0168)` na branch `feat/v2`

## Andamento

- 2026-10-02 — **`blocked`, nada implementado.** depende da RAGX-0111 (fase 14, `get_dictionary` em níveis), que continua `todo`, e da RAGX-0145, que está em `review` (queda do MRR do grafo, decisão humana). Verificado nos arquivos das dependências (todas ainda com `Status = todo`/`review`). Quando a dependência fechar, voltar o status para `todo` e retomar daqui.

## Andamento

- 2026-10-02 — **Desbloqueada** (0111 e 0145 fechadas). **Medido primeiro** (SQL somente leitura sobre `.ragx/knowledge.db`): arestas arquivo→arquivo DISTINTAS por tipo: `calls` 3.488, `imports` 100, `contains` 11, e as de prosa `documented_by` 5.595 e `mentions` 1.698 (não pesam). Os 20 maiores graus mostram o problema que a tarefa previa: o topo é `status` (4 entidades de ~330), `projeto`, `get`, `cfg`, `load_config`, ou seja, nomes genéricos e um plano de 2026-09-23 (446). Nomes ambíguos (> 5 homônimos): 6.
- **Feito**: `graph/rank.py` (`file_rank` com iteração de potência em NumPy e massa solta redistribuída, `ranked_files` só código da camada `knowledge` sem `task/`, `knowledge/`, testes, com os 3 símbolos de maior grau de entrada, `select_by_budget`, `repo_map`), seção `repo_map` do dicionário (250 tokens de linhas, ~550 em JSON, e `_fit_budget` com pisos menores para o total ficar ≤ 4.000), níveis 0 (10 arquivos), 1 (15) e 2 (completo, com `rank`), `ragx graph rank [--top] [--tokens] [--json]`, docs `06-grafo`, `08-dictionary`, `09-mcp`, `14-cli`, CHANGELOG, arquivos-ouro do `tools/list` regravados (a descrição de `get_dictionary` ganhou os tokens novos).
- **Medido**: `file_rank` 20 ms (193 arquivos no ranking, a meta era < 100 ms). Cobertura dos `relevant_paths` de código (114) no mapa de 600 tokens (36 arquivos): **PageRank 27, controle por chunks 11**: iguala e supera, então o mapa FICA no nível 0. Nível 0 do dicionário: 690 tokens (≤ 800).
- **Desvios**: (1) o filtro de nome ambíguo ficou em **> 3** homônimos, não > 5: com 5, `config_cmd.py` (4º lugar) e `embeddings/base.py` (2º) eram hubs falsos de `get`/`set`, e a cobertura era 24; com 3 sobe para 27 (com 2 vai a 25, com 1 a 26). (2) o mapa dentro do dicionário tem 250 tokens (15 arquivos), não 600: com 600 o dicionário completo estourava os 4.000 tokens da 0110; o `repo_map(tokens=600)` avulso e `ragx graph rank` seguem aceitando 600.
- **Critério NÃO atendido: "5 dos 8 núcleos conhecidos entre os 10 primeiros".** Deu **2 de 8** (`storage/db.py` e `config.py`; com ambiguidade 5, 2; peso de aresta reversa 0,1 a 1,0, entre 1 e 3). O PageRank por dependência premia o que todo o resto USA (`db.py`, `config.py`, `repositories.py`, `models.py`, `errors.py`, `budget.py`) e não os ORQUESTRADORES (`pipeline.py`, `engine.py`, `service.py`, `gate.py`), que chamam muito e são pouco chamados. Isso é o que o algoritmo faz, e para quem chega no repositório "o que todo mundo usa" é um mapa útil, mas não é o que a lista de 8 espera. Não ajustei os pesos até a lista de 8 sair: seria enfeitar o número. A regra da tarefa para o caso em que o mapa NÃO supera o controle (não ligar no nível 0) não vale aqui, porque ele supera por 27 a 11.
- Testes: `tests/unit/test_graph_rank.py` (9: o chamado por dois ganha, nó sem saída não vaza massa e a soma é 1, nome ambíguo ignorado, prosa e estrutura não pesam, aresta no mesmo arquivo não conta, determinismo independente da ordem das relações, só código `knowledge` e símbolos por grau, corte por orçamento, grafo vazio), 5 testes novos em `test_dictionary_niveis.py` (seção respeita o orçamento e não traz `task/`, `knowledge/` nem testes; nível 0 com o mapa e ≤ 800 tokens; `repo_map` idêntico em duas execuções e depois de `graph rebuild`; MCP nível 0 inclui o mapa; `ragx graph rank`) e 1 de segurança (arquivo bloqueado pelo gate não aparece no mapa).
- **Não verificado**: Linux e macOS; repositórios grandes (milhares de arquivos): o PageRank é O(arestas x 50 iterações), 20 ms aqui.
