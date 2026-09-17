# RAGX-0098 — Corrigir a métrica nDCG

| | |
|---|---|
| **Fase** | 14 — Evolução do RAG |
| **Onda** | 1 — instrumento e caminho quente |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 0,5d |
| **Depende de** | — |
| **Documentação** | [23-auditoria-e-evolucao-do-rag.md](../../docs/23-auditoria-e-evolucao-do-rag.md) · [13-testes-hardening.md](../../docs/13-testes-hardening.md) |
| **Status** | `done` |

## Objetivo

`search/evaluation.py:_ndcg()` conta caminhos duplicados como ganhos separados, com denominador ideal em número de arquivos. Medido: **2,131** numa métrica cujo teto é 1,0. O erro tem direção — **premia devolver vários chunks do mesmo arquivo**, que é o oposto de um contexto bom.

## Entregáveis

- [x] `_ndcg` deduplica caminhos antes de calcular ganhos, OU passa a medir em chunks com ideal em chunks — a escolha fica registrada no docstring
- [x] `recall@5` documenta explicitamente que mede **caminhos distintos**, não chunks
- [x] Teste que falha se `nDCG > 1.0` para qualquer entrada

## Fora de escopo

- Mudar as métricas reportadas (recall@5, MRR, nDCG continuam sendo as três)
- Ampliar o conjunto de consultas (é a `RAGX-0099`)

## Critérios de aceite

- [x] `_ndcg(['a','a','a'], ('a',)) <= 1.0` — era 2,131, agora 1,0
- [x] `_ndcg` com resultado perfeito devolve exatamente 1,0
- [x] `_ndcg` com nenhum acerto devolve 0,0
- [x] Os valores de `ragx eval` são recalculados: **nDCG cai de 0,76 para 0,48** (keyword), 0,66→0,44 (semantic), 0,76→0,49 (hybrid). A série histórica quebra — os valores antigos estavam inflados

## Testes

- [x] Propriedade: para qualquer entrada, `0.0 <= ndcg <= 1.0`
- [x] Caso com caminhos duplicados, fixando o valor esperado
- [x] Caso com mais caminhos relevantes que `k`

## Notas

Enquanto isto não estiver feito, **o nDCG não deve ser citado em lugar nenhum** — inclusive o salto de 0,76 para 0,87 medido na troca de modelo (`RAGX-0103`), que está medido com o instrumento quebrado.

O mesmo defeito faz `max_per_document=1` 'melhorar' o recall em 7 pontos, por artefato: o top-5 passa a ter 5 caminhos distintos em vez de 2 ou 3.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux, macOS e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] CHANGELOG atualizado na MESMA alteração
- [ ] Documentação confere com o comportamento implementado
