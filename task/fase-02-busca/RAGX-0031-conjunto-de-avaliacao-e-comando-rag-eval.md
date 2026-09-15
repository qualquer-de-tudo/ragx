# RAGX-0031 — Conjunto de avaliação e comando ragx eval

| | |
|---|---|
| **Fase** | 2 — Semantic + Hybrid Search |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 0,5d |
| **Depende de** | `RAGX-0030` |
| **Bloqueia** | — |
| **Documentação** | [05-busca.md](../../docs/05-busca.md) |
| **Status** | `partial` — mecanismo validado, qualidade medida e abaixo da meta |

## Objetivo

Medir qualidade de recuperação em vez de discutir sobre ela.

## Entregáveis

- [ ] `tests/eval/queries.yaml` com pelo menos 25 consultas sobre este próprio repositório
- [ ] `ragx eval` reportando Recall@5, MRR e nDCG@10 por modo
- [ ] Job informativo no CI (não bloqueante) registrando a métrica ao longo do tempo

## Fora de escopo

- Avaliação de geração (exigiria LLM-as-judge; pós-MVP)

## Critérios de aceite

- [ ] `hybrid > semantic > keyword` em Recall@5
- [ ] `hybrid` >= 0.80 de Recall@5 no conjunto
- [ ] Consulta que não usa nenhuma palavra do documento-alvo ainda o encontra (prova do semântico)
- [ ] Resultado reproduzível com o provider `hashing` desativado

## Testes

- [ ] O próprio `ragx eval` executado no CI

## Notas

Porta de saída da Fase 2 — fim do MVP vertical.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado

---

## Estado em 2026-09-15 — MEDIDO (critério não atingido)

**Destravado sem Ollama.** `fastembed` roda o modelo localmente via ONNX Runtime,
sem daemon: baixa ~220 MB uma vez para `.ragx/cache/models/` e funciona offline.
Modelo `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` — multilíngue,
porque o corpus é português + código.

### Medição real (26 consultas, 1.929 chunks)

```text
Modo       Recall@5   MRR     nDCG@10
keyword      0.77     0.48     0.79
semantic     0.62     0.44     0.68
hybrid       0.65     0.49     0.78
```

O critério `hybrid > semantic > keyword` com `hybrid >= 0.80` **NÃO foi atingido**.
O híbrido tem o melhor MRR, mas perde em Recall@5.

### Investigação

Rastreando `"quantização int8 dos vetores"`, cada motor acha um alvo rotulado
**diferente** (keyword: `docs/16`, semantic: `embeddings/base.py`) e nenhum dos
dois entra no topo do híbrido. O que sobe é aquilo em que os dois concordam —
um arquivo de task. **É a fraqueza conhecida do RRF: ele premia consenso.**

Agravante: `RAGX-0071` e `ADR-0010`, que o híbrido traz, **são documentos
genuinamente relevantes** sobre quantização e não estão em `relevant_paths`. A
métrica pune o híbrido por achar documentos corretos porém não rotulados.

### Hipóteses testadas e descartadas

| Tentativa | Resultado |
|-----------|-----------|
| Varredura de pesos do RRF (6 combinações) | platô em 0.69 — teto independente do peso |
| Fusão adaptativa por forma da consulta | 0.65 — sem ganho; **código removido** |
| `max_per_document` = 1 ou 2 | 0.65–0.69 — sem ganho |

Nada foi mantido. A diferença entre 0.65 e 0.69 é **uma consulta** em 26 — ruído.
Ajustar contra um conjunto deste tamanho seria ajustar a ruído.

### O que falta, e por quem

- [ ] **Rerrotular `tests/eval/queries.yaml`** — `relevant_paths` lista 1–2 caminhos
      onde há 3–5 genuinamente relevantes. Precisa ser feito por alguém que **não**
      esteja otimizando contra a métrica.
- [ ] Ampliar o conjunto para ~60 consultas, com equilíbrio explícito entre
      consulta lexical (nome de símbolo) e conceitual (pergunta).
- [ ] Só então reavaliar se a meta de 0.80 faz sentido **neste corpus**, que é
      anormalmente autossimilar.
- [ ] Opcional: comparar com `intfloat/multilingual-e5-large` (2,2 GB) para separar
      limitação do modelo de limitação do corpus.

### O que está validado

- [x] Pipeline completo: chunk → embedding → quantização int8 → busca em 2 estágios
- [x] Fusão RRF, reranking e diversidade de fonte
- [x] Degradação para keyword quando o embedder está fora do ar
- [x] Busca só com vetores int8 (simulação de `git clone`)
- [x] Filtros aplicados antes do top-K
- [x] **Embeddings reais, sem daemon** — `ragx eval` produz número auditável
