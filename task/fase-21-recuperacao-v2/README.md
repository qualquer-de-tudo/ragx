# Fase 21: Recuperação v2

5 tarefas, derivadas da [auditoria 24](../../docs/24-auditoria-v2.md) (seção 7, pesquisa de mercado) e da [spec 25](../../docs/25-spec-v2.md) (seção 5.3). A fase 14 tratou de **corrigir** a recuperação (cache do embedder, nDCG, fusão RRF, modelo, dicionário em níveis). Esta fase acrescenta o que a pesquisa trouxe depois: prefixo contextual determinístico antes de embutir, um conjunto-ouro derivado do próprio git para medir recuperação sem depender de consultas escritas à mão, um mapa compacto do repositório (PageRank sobre o grafo) como nível 0, um benchmark local de modelos e um índice por worktree/branch.

O motivo é de produto: o Claude Code não usa índice vetorial por padrão, então o RAGX só ganha se devolver contexto **mais preciso e mais barato** que o loop de Grep e Read do agente (auditoria 24, 7.1). Busca ruidosa piora o agente: no CodeGrep, um BM25 de precisão 0,375 degradou a resolução, e um retriever de precisão 0,677 cortou 19% dos tokens. Hoje o híbrido com MiniLM não supera o keyword (recall@5 0,65 contra 0,77, `docs/05-busca.md`), e num clone novo, sem vetores locais, a busca perde 26% do top-10 (C-10). Medir antes de adotar um modelo ou um reranker é o ponto, e por isso o conjunto-ouro (0167) vem antes do benchmark (0169).

## Herda as 14 tarefas pendentes da fase 14

A fase 21 **não copia** as tarefas da [fase 14](../fase-14-evolucao-do-rag/): ela as herda como pré-requisito de qualidade. Das 18 tarefas da fase 14, 4 estão feitas (0097, 0098, 0100, 0102) e 14 continuam `todo` e válidas:

| ID | Tarefa (na pasta da fase 14) |
|---|---|
| RAGX-0099 | Ampliar o conjunto de avaliação para 150 consultas |
| RAGX-0101 | Separar score bruto de `relevance` normalizado |
| RAGX-0103 | Trocar o modelo de embedding para retrieval assimétrico |
| RAGX-0104 | Prefixos de consulta e documento no provider fastembed |
| RAGX-0105 | Recalibrar a fusão RRF |
| RAGX-0106 | Estratégia de recuperação por intenção |
| RAGX-0107 | Conter a expansão do grafo por orçamento |
| RAGX-0108 | Reranking com cross-encoder opcional |
| RAGX-0109 | Popular os resumos do dicionário sem LLM |
| RAGX-0110 | Enxugar o dicionário |
| RAGX-0111 | `get_dictionary` em níveis |
| RAGX-0112 | Confiança e procedência no resultado de busca |
| RAGX-0113 | Marcar frescor do índice no resultado |
| RAGX-0114 | Chunking AST para TypeScript, JavaScript e PHP |

Os arquivos estão em [`task/fase-14-evolucao-do-rag/`](../fase-14-evolucao-do-rag/). **O loop não pega a fase 14 por conta própria**: a 0103 troca o modelo e muda o formato do índice, e isso precisa de decisão humana (roteiro, "Ordem de execução"). Na prática, 0166 (depende da 0104), 0167 (0099) e 0168 (0111) ficam bloqueadas até uma pessoa fechar essas três tarefas da fase 14, e a 0169 fica bloqueada junto com a 0167.

## Tarefas

| ID | Tarefa | Prio | Est. | Status |
|---|---|---|---|---|
| [RAGX-0166](RAGX-0166-prefixo-contextual-deterministico-antes-de-embutir-e-indexar.md) | Prefixo contextual determinístico antes de embutir e indexar | P1 | 1d | `done` |
| [RAGX-0167](RAGX-0167-conjunto-ouro-derivado-do-git-para-avaliar-recuperacao.md) | Conjunto-ouro derivado do git para avaliar recuperação | P2 | 2d | `blocked` |
| [RAGX-0168](RAGX-0168-repo-map-compacto-pagerank-sobre-o-grafo-como-nivel-0.md) | Repo map compacto (PageRank sobre o grafo) como nível 0 | P2 | 2d | `blocked` |
| [RAGX-0169](RAGX-0169-benchmark-local-de-modelos-de-embedding-e-reranker-de-codigo.md) | Benchmark local de modelos de embedding e reranker de código | P2 | 1d | `blocked` |
| [RAGX-0170](RAGX-0170-indice-por-worktree-branch-com-chunks-compartilhados-por-hash.md) | Índice por worktree/branch com chunks compartilhados por hash | P3 | 2d | `review` |

## Dependências

```text
fase 14: 0104 ──────────────> 0166
fase 14: 0099 ──> 0167 ─────> 0169 (também depende de 0132, fase 19)
fase 14: 0111 ──┐
fase 19: 0145 ──┴──────────> 0168
fase 19: 0138 ──────────────> 0170
```

## Ordem sugerida

Trecho do [ROTEIRO-V2.md](../ROTEIRO-V2.md). As cinco tarefas desta fase são as últimas do bloco:

**Bloco 8 — o que sobra do core e a recuperação** (≈ 11 d)
0146 · 0147 · 0148 · 0150 · 0151 · 0152 · 0153 · 0166 · 0167 · 0168 · 0169 · 0170

**Fecho**: 0195.

Dentro do bloco, a ordem é a da lista. **Nunca inicie uma tarefa com dependência aberta**; se a próxima da lista estiver bloqueada, pule para a seguinte. A 0169 só entrega o harness e roda o que já está em disco: baixar modelos grandes é decisão de uma pessoa.
