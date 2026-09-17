# RAGX-0101 — Separar score bruto de relevance normalizado

| | |
|---|---|
| **Fase** | 14 — Evolução do RAG |
| **Onda** | 1 — instrumento e caminho quente |
| **Prioridade** | P1 — alta |
| **Estimativa** | 1d |
| **Depende de** | — |
| **Documentação** | [23-auditoria-e-evolucao-do-rag.md](../../docs/23-auditoria-e-evolucao-do-rag.md) · [09-mcp.md](../../docs/09-mcp.md) |
| **Status** | `todo` |

## Objetivo

O campo `score` tem **três escalas incompatíveis**: BM25 invertido (~17,8), cosseno (~0,88) e RRF (~0,029). Sai com o mesmo nome em toda resposta MCP. O agente não consegue calibrar, e `min_score` é inutilizável em híbrido — o teto é ~0,03, então `min_score=0.5` zera o resultado.

## Entregáveis

- [ ] `SearchResult` ganha `relevance` em `[0,1]`, comparável entre modos
- [ ] `score` bruto continua exposto, para depuração, com `score_scale` dizendo o motor (`bm25` | `cosine` | `rrf`)
- [ ] `min_score` passa a operar sobre `relevance`; o comportamento antigo fica documentado como quebra
- [ ] `_hit()` do MCP expõe os três campos
- [ ] `rerank()` deixa de multiplicar sobre escala variável — hoje ×1,5 sobre RRF salta dezenas de posições e sobre BM25 quase não mexe

## Fora de escopo

- Cross-encoder (é a `RAGX-0108`)
- Mudar a ordenação dos resultados — a normalização é monótona por construção

## Critérios de aceite

- [ ] `min_score=0.5` devolve um subconjunto coerente e comparável nos três modos
- [ ] `relevance` do primeiro resultado fica próximo de 1,0 nos três modos
- [ ] A ordem dos resultados **não muda** com a introdução de `relevance`
- [ ] `docs/09-mcp.md` documenta as três escalas e qual usar

## Testes

- [ ] Teste de que a normalização preserva a ordem, nos três modos
- [ ] Teste de que `min_score` corta proporcionalmente o mesmo nos três modos
- [ ] Teste de contrato do plugin: a UI mostra `relevance`, não `score`

## Notas

O playbook manda o agente desconfiar de 'um resultado só semântico com score baixo'. Hoje ele não tem como saber o que é baixo — a escala muda por baixo dele, sem aviso.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux, macOS e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] CHANGELOG atualizado na MESMA alteração
- [ ] Documentação confere com o comportamento implementado
