# RAGX-0071 — Quantização de embeddings e busca em dois estágios

| | |
|---|---|
| **Fase** | 2 — Semantic + Hybrid Search |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 1d |
| **Depende de** | `RAGX-0027`, `RAGX-0070` |
| **Bloqueia** | `RAGX-0059` |
| **Documentação** | [16-orcamento-de-tamanho.md](../../docs/16-orcamento-de-tamanho.md) · [05-busca.md](../../docs/05-busca.md) · [adr/ADR-0010-conteudo-nao-versionado-e-embeddings-quantizados.md](../../docs/adr/ADR-0010-conteudo-nao-versionado-e-embeddings-quantizados.md) |
| **Status** | `todo` |

## Objetivo

Reduzir o vetor versionado de 3.072 para 256 bytes por chunk sem perder qualidade de busca onde os vetores completos existirem.

## Entregáveis

- [ ] Truncagem Matryoshka para `versioned_dim` com **renormalização** após truncar
- [ ] Quantização escalar int8 por vetor, com `scale` e `offset` próprios de cada vetor
- [ ] Persistência em `vector` (float32, local) e `vector_q` (int8, versionado)
- [ ] Busca em dois estágios: grosseira em int8 (top-100) → rescoring em float32 (top-K)
- [ ] Degradação automática quando `vector` é NULL (logo após um clone): só o estágio 1
- [ ] `[embedding] versioned_dim`, `versioned_quant`, `rescore` configuráveis; `versioned_dim = 0` desliga
- [ ] `ragx eval` reporta as duas condições: `int8 apenas` e `com rescoring`

## Fora de escopo

- Quantização binária — registrada como opção pós-MVP

## Critérios de aceite

- [ ] Vetor versionado ocupa exatamente `versioned_dim` bytes + escala e offset
- [ ] Renormalização após truncagem está presente — sem ela o produto escalar deixa de aproximar cosseno
- [ ] Rescoring recupera a precisão: `hybrid com rescoring` >= `hybrid int8 apenas`
- [ ] Perda no modo `int8 apenas` não passa de 5 pontos de Recall@5
- [ ] Busca funciona com `vector` NULL em 100% dos chunks, sem exceção e sem rede
- [ ] Quantizar 10k vetores leva menos de 1 s (operação vetorizada)

## Testes

- [ ] Round-trip quantizar/desquantizar com erro medido
- [ ] `ragx eval` nas duas condições
- [ ] Busca com vetores locais ausentes

## Notas

A meta de perda <= 5 pontos é o que valida `versioned_dim = 256`. Se não for atingida, a decisão do ADR-0010 precisa ser revista antes da Fase 9.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
