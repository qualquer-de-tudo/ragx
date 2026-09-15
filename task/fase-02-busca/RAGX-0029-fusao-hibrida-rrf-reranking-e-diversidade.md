# RAGX-0029 — Fusão híbrida RRF, reranking e diversidade

| | |
|---|---|
| **Fase** | 2 — Semantic + Hybrid Search |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 0,5d |
| **Depende de** | `RAGX-0027`, `RAGX-0028` |
| **Bloqueia** | `RAGX-0030`, `RAGX-0035` |
| **Documentação** | [05-busca.md](../../docs/05-busca.md) |
| **Status** | `todo` |

## Objetivo

Combinar os dois motores sem precisar calibrar scores heterogêneos.

## Entregáveis

- [ ] `search/hybrid.py` com RRF (`K=60`) e pesos configuráveis
- [ ] Cada motor contribui com `limit × candidate_factor` candidatos
- [ ] `search/ranking.py` com os 5 sinais determinísticos do doc 05
- [ ] Diversidade de fonte: no máximo `max_per_document` chunks do mesmo documento no topo
- [ ] `matched_by` preenchido com os motores que acharam cada chunk

## Fora de escopo

- Rerank com cross-encoder — registrado como evolução pós-MVP

## Critérios de aceite

- [ ] Híbrido supera cada motor isolado em Recall@5 no `ragx eval`
- [ ] Nenhum documento ocupa mais de 3 posições no top-10 quando há alternativa
- [ ] Fusão custa menos de 5 ms para 100 candidatos

## Testes

- [ ] Unitário do RRF com rankings conhecidos
- [ ] Teste de diversidade

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
