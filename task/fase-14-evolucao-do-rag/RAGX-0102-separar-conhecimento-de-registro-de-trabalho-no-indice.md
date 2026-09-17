# RAGX-0102 — Separar conhecimento de registro de trabalho no índice

| | |
|---|---|
| **Fase** | 14 — Evolução do RAG |
| **Onda** | 2 — composição do corpus |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 1,5d |
| **Depende de** | — |
| **Documentação** | [23-auditoria-e-evolucao-do-rag.md](../../docs/23-auditoria-e-evolucao-do-rag.md) · [04-indexacao.md](../../docs/04-indexacao.md) · [15-configuracao.md](../../docs/15-configuracao.md) |
| **Status** | `done` |

## Objetivo

`task/` é **22% do corpus** (543 chunks, mais que toda a documentação) e vence o código na busca. Para *"como o security gate decide bloquear um arquivo"*, o fragmento [1] do `build_context` é o enunciado da TAREFA que pediu para construir o gate — não o `admit()`. Documento de planejamento é quase-duplicata semântica da documentação: mesmo vocabulário, menos informação.

## Entregáveis

- [x] ~~Coluna `tier` em `documents`~~ → **classificação em tempo de LEITURA**, sem coluna e sem migração. Motivo: mudar `work_paths` passa a valer sem reindexar o projeto inteiro. O custo é uma comparação de caminho por resultado. Ver `src/ragx/tiers.py`
- [x] Classificação por caminho, configurável em `ragx.toml`:
  ```toml
  [index]
  knowledge_paths = ["src/", "docs/"]
  work_paths      = ["task/", "adr-drafts/"]
  test_paths      = ["tests/"]
  ```
- [x] Defaults sensatos que funcionem sem configuração (`task/`, `tests/`, `spec/`, `.github/`)
- [x] O ranking pondera `work` e `test` para BAIXO (`weight_tier_work=0.45`, `weight_tier_test=0.7`) — sem excluir, porque às vezes a resposta está mesmo na tarefa
- [x] O peso é configurável e o default fica registrado na documentação
- [x] `matched_by`/metadados expõem o `tier`, para o agente saber o que recebeu
- [x] ~~Migração de schema~~ — desnecessária: não há coluna nova, e nenhum índice existente precisa ser tocado

## Fora de escopo

- Excluir `task/` do índice — a informação é legítima, o PESO é que está errado
- Classificação semântica do conteúdo; a classificação é por caminho, declarada e auditável

## Critérios de aceite

- [ ] Na consulta *"como o security gate decide bloquear um arquivo"*, o fragmento [1] passa a ser `src/ragx/security/gate.py` — **NÃO atingido literalmente**. O arquivo de task saiu do topo (era [1]), e o [1] passou a ser `docs/adr/ADR-0008-security-gate-antes-do-parser.md`, que responde a pergunta. Mas `gate.py` não aparece nem no top-10: as três primeiras posições são três chunks do MESMO ADR. Isso aponta para a `RAGX-0107` (conter fragmentação) e para `max_per_document`, não para esta tarefa
- [x] recall@5 medido antes/depois — mas no conjunto de **26** consultas, não no ampliado:

  | modo | recall@5 | MRR |
  |---|---|---|
  | keyword | 0,77 → **0,81** | 0,47 → **0,62** |
  | semantic | 0,54 → **0,69** | 0,44 → **0,51** |
  | hybrid | 0,62 → **0,77** | 0,51 → **0,59** |

  **Ressalva que não pode sumir:** os `relevant_paths` do conjunto nunca apontam
  para `task/` ou `tests/`. Rebaixar essas camadas melhora esta métrica **por
  construção** — o ganho é real no sentido de que a métrica encoda julgamento
  humano sobre onde a resposta mora, e circular no sentido de que nenhum caso
  poderia ter sido prejudicado. Confirmar na `RAGX-0099`, com casos cuja
  resposta ESTEJA numa tarefa
- [x] Um projeto sem `[index] tier` configurado continua funcionando, com os defaults
- [x] Uma consulta cuja resposta REALMENTE está numa task ainda a encontra — testado

## Testes

- [x] Teste de que o peso muda a ordem, sem remover resultados
- [x] Teste dos defaults de classificação
- [ ] ~~Teste de que `tier` sobrevive a export/import~~ — sem coluna, não há o que sobreviver: o `tier` é recalculado na leitura, sempre a partir da configuração de quem lê

## Notas

Este é o maior ganho de precisão por linha alterada de toda a fase, e não envolve modelo nem algoritmo.

Vale para qualquer projeto: todo repositório tem seu equivalente de `task/` — ADRs em rascunho, RFCs, tickets exportados, notas de sprint.

**Ironia registrada:** a própria Fase 14 acrescenta ~19 arquivos a `task/`, piorando o problema que esta tarefa corrige. Mais um motivo para ela vir cedo.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux, macOS e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] CHANGELOG atualizado na MESMA alteração
- [ ] Documentação confere com o comportamento implementado
