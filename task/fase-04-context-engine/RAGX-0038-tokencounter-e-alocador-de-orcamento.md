# RAGX-0038 — TokenCounter e alocador de orçamento

| | |
|---|---|
| **Fase** | 4 — Context Engine |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 0,5d |
| **Depende de** | `RAGX-0030` |
| **Bloqueia** | `RAGX-0039` |
| **Documentação** | [07-context-engine.md](../../docs/07-context-engine.md) |
| **Status** | `todo` |

## Objetivo

Ter contagem de tokens estável e uma política de alocação que não concentre todo o orçamento numa única fonte.

## Entregáveis

- [ ] `context/budget.py` com o Protocol `TokenCounter` e implementação `tiktoken` (`cl100k_base`)
- [ ] Knapsack aproximado por densidade `score / token_count`
- [ ] Reserva de ~5% para overhead de formatação
- [ ] Reserva mínima de 1 trecho para cada um dos top-3 documentos distintos
- [ ] Garantia `estimated_tokens <= budget` com margem de 3%

## Fora de escopo

- Contagem exata por modelo de destino — é estimativa declarada

## Critérios de aceite

- [ ] `estimated_tokens <= budget` em 100% dos casos do conjunto de avaliação
- [ ] Nunca devolve 3.000 tokens de um único arquivo quando há 2+ documentos relevantes
- [ ] `token_count` gravado no chunk bate com o contador (tolerância 2%)
- [ ] Contador é trocável sem alterar o engine

## Testes

- [ ] Unitários do knapsack com conjuntos sintéticos
- [ ] Teste de borda: orçamento menor que o menor chunk

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
