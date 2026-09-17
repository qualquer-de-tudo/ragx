# Fase 14 — Evolução do RAG

18 tarefas · ~20d · a partir da auditoria em
[docs/23-auditoria-e-evolucao-do-rag.md](../../docs/23-auditoria-e-evolucao-do-rag.md).

Toda tarefa desta fase nasceu de um número medido, e cada arquivo cita o número
que a justifica. Nenhuma nasceu de "seria bom ter".

## A ordem importa

As ondas não são agrupamento temático — são **dependência de evidência**.

```text
Onda 1  instrumento de medida + caminho quente
   ↓    sem ela, nada abaixo é verificável
Onda 2  composição do corpus
   ↓    maior ganho por linha alterada, e independe de modelo
Onda 3  braço semântico
   ↓    já medido; precisa da onda 1 para confirmar
Onda 4  recuperação adaptativa e reranking
Onda 5  conhecimento hierárquico
Onda 6  confiança e evidência
```

A onda 1 vem primeiro por um motivo específico: hoje o conjunto de avaliação
tem 26 consultas, e o intervalo de confiança de 95% tem largura ~0,33. **Uma
melhoria real de 5 pontos é indistinguível de ruído.** Executar a onda 3 antes
da 1 produz um número que ninguém pode confirmar.

## Tarefas

| ID | Tarefa | Onda | Prio | Est. | Depende de |
|---|---|---|---|---|---|
| [RAGX-0097](RAGX-0097-cachear-o-embedder-por-processo.md) | Cachear o embedder por processo | 1 | P0 | 0,5d | — |
| [RAGX-0098](RAGX-0098-corrigir-a-metrica-ndcg.md) | Corrigir a métrica nDCG | 1 | P0 | 0,5d | — |
| [RAGX-0099](RAGX-0099-ampliar-o-conjunto-de-avaliacao-para-150-consultas.md) | Ampliar o conjunto de avaliação | 1 | P0 | 3d | 0098 |
| [RAGX-0100](RAGX-0100-reportar-intervalo-de-confianca-no-ragx-eval.md) | Intervalo de confiança no `ragx eval` | 1 | P1 | 0,5d | 0098 |
| [RAGX-0101](RAGX-0101-separar-score-bruto-de-relevance-normalizado.md) | Separar `score` de `relevance` | 1 | P1 | 1d | — |
| [RAGX-0102](RAGX-0102-separar-conhecimento-de-registro-de-trabalho-no-indice.md) | Separar conhecimento de registro de trabalho | 2 | P0 | 1,5d | — |
| [RAGX-0103](RAGX-0103-trocar-o-modelo-de-embedding-para-retrieval-assimetrico.md) | Trocar o modelo de embedding | 3 | P0 | 1,5d | 0097, 0099 |
| [RAGX-0104](RAGX-0104-prefixos-de-consulta-e-documento-no-provider-fastembed.md) | Prefixos de consulta/documento | 3 | P1 | 0,5d | 0103 |
| [RAGX-0105](RAGX-0105-recalibrar-a-fusao-rrf.md) | Recalibrar a fusão RRF | 3 | P1 | 0,5d | 0099 |
| [RAGX-0106](RAGX-0106-estrategia-de-recuperacao-por-intencao.md) | Estratégia de recuperação por intenção | 4 | P1 | 2d | 0099, 0101 |
| [RAGX-0107](RAGX-0107-conter-a-expansao-do-grafo-por-orcamento.md) | Conter a expansão do grafo | 4 | P1 | 1d | — |
| [RAGX-0108](RAGX-0108-reranking-com-cross-encoder-opcional.md) | Reranking com cross-encoder | 4 | P2 | 2d | 0097, 0099, 0101 |
| [RAGX-0109](RAGX-0109-popular-os-resumos-do-dicionario-sem-llm.md) | Popular os resumos sem LLM | 5 | P1 | 1,5d | — |
| [RAGX-0110](RAGX-0110-enxugar-o-dicionario.md) | Enxugar o dicionário | 5 | P1 | 1d | 0109 |
| [RAGX-0111](RAGX-0111-get-dictionary-em-niveis.md) | `get_dictionary` em níveis | 5 | P1 | 1d | 0110 |
| [RAGX-0112](RAGX-0112-confianca-e-procedencia-no-resultado-de-busca.md) | Confiança e procedência na busca | 6 | P2 | 1d | 0101 |
| [RAGX-0113](RAGX-0113-marcar-frescor-do-indice-no-resultado.md) | Marcar frescor do índice | 6 | P2 | 1d | — |
| [RAGX-0114](RAGX-0114-chunking-ast-para-typescript-javascript-e-php.md) | Chunking AST para TS/JS/PHP | — | P1 | 3d | — |

## Se só houver espaço para três

1. **RAGX-0097** — cachear o embedder. Hoje ~99% da latência da busca semântica
   é carregar o modelo ONNX (2537–3638 ms contra 6–27 ms para embutir). Nenhum
   resultado muda; só o tempo. Risco quase zero.
2. **RAGX-0098 + RAGX-0099** — consertar a métrica e ampliar o conjunto. O
   `nDCG` mede 2,131 numa escala cujo teto é 1,0, e n=26 não distingue os modos.
3. **RAGX-0102** — separar `task/` do conhecimento. `task/` é 22% do corpus e
   vence o código na busca.

E logo depois a **RAGX-0103**, que já está medida: o híbrido vai de 0,62 para
0,77 de recall@5 e de 0,51 para 0,58 de MRR.

## Uma observação sobre esta própria fase

Estas 18 tarefas acrescentam ~18 arquivos a `task/`, que a auditoria identificou
como **22% do corpus e fonte de falso positivo na busca**. A fase piora, um
pouco, o problema que a `RAGX-0102` existe para corrigir.

Não é motivo para não escrevê-las — é motivo para a `RAGX-0102` vir cedo.
