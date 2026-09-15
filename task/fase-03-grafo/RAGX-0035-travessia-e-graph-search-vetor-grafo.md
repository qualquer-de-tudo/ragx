# RAGX-0035 — Travessia e graph-search (vetor + grafo)

| | |
|---|---|
| **Fase** | 3 — Graph Knowledge |
| **Prioridade** | P1 — alta |
| **Estimativa** | 1d |
| **Depende de** | `RAGX-0034`, `RAGX-0029` |
| **Bloqueia** | `RAGX-0036`, `RAGX-0041` |
| **Documentação** | [06-grafo.md](../../docs/06-grafo.md) |
| **Status** | `todo` |

## Objetivo

Fazer o grafo pagar o próprio custo: encontrar conhecimento relacionado que a busca híbrida pura não encontra.

## Entregáveis

- [ ] `graph/traversal.py`: BFS com `max_depth`, `max_nodes`, `max_fanout`
- [ ] Decaimento por salto (`decay = 0.6`) e penalidade de grau (`weight /= log(1 + grau)`)
- [ ] `graph-search`: híbrida → entidades âncora → expansão → chunks representativos → RRF

## Fora de escopo

- Uso pelo Context Engine (RAGX-0041)

## Critérios de aceite

- [ ] Pelo menos 3 casos do conjunto de avaliação são resolvidos só com vetor+grafo
- [ ] Limites respeitados; expansão termina em menos de 100 ms
- [ ] Nó de altíssimo grau não domina o resultado

## Testes

- [ ] Casos de avaliação dedicados ao grafo
- [ ] Teste de explosão com nó de grau 500

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
