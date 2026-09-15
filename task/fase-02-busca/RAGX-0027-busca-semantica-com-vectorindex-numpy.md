# RAGX-0027 — Busca semântica com VectorIndex NumPy

| | |
|---|---|
| **Fase** | 2 — Semantic + Hybrid Search |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 0,5d |
| **Depende de** | `RAGX-0025` |
| **Bloqueia** | `RAGX-0029`, `RAGX-0071` |
| **Documentação** | [05-busca.md](../../docs/05-busca.md) · [adr/ADR-0003-busca-vetorial.md](../../docs/adr/ADR-0003-busca-vetorial.md) |
| **Status** | `todo` |

## Objetivo

Implementar busca vetorial exata, com filtro aplicado antes do top-K.

## Entregáveis

- [ ] `storage/vectors.py` implementando o Protocol `VectorIndex`
- [ ] Carga da matriz uma vez por processo, cache invalidado pelo `index_runs.id` mais recente
- [ ] Produto escalar sobre vetores normalizados, top-K por `argpartition`
- [ ] Máscara booleana de filtro aplicada ANTES do top-K
- [ ] Aviso automático em `ragx status`/`ragx doctor` acima de 100.000 chunks

## Fora de escopo

- Índice aproximado — só ao ultrapassar o limiar do ADR-0003

## Critérios de aceite

- [ ] Recall exato (100%) — comprovado contra varredura ingênua
- [ ] Filtro restritivo ainda devolve `limit` resultados quando eles existem
- [ ] Busca em 10.000 chunks em menos de 50 ms
- [ ] Memória proporcional ao corpus, medida e reportada em `ragx status`

## Testes

- [ ] Comparação com busca ingênua
- [ ] Benchmark com 10k e 100k vetores sintéticos

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
