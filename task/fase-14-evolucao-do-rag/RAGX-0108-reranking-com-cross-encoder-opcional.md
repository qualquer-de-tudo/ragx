# RAGX-0108 — Reranking com cross-encoder, opcional

| | |
|---|---|
| **Fase** | 14 — Evolução do RAG |
| **Onda** | 4 — recuperação adaptativa |
| **Prioridade** | P2 — media |
| **Estimativa** | 2d |
| **Depende de** | `RAGX-0097` · `RAGX-0099` · `RAGX-0101` |
| **Documentação** | [23-auditoria-e-evolucao-do-rag.md](../../docs/23-auditoria-e-evolucao-do-rag.md) · [05-busca.md](../../docs/05-busca.md) |
| **Status** | `todo` |

## Objetivo

Não há reranking de modelo — só multiplicadores heurísticos, que é uma escolha defensável para o MVP. O que falta não é o modelo: é o ARRANJO. Hoje o pipeline é `recuperar 30 → fundir → heurística → cortar em 10`. O arranjo que paga é `recuperar muitos → rerankear → ficar com poucos`, e ele só cabe no orçamento de latência depois da `RAGX-0097`.

## Entregáveis

- [ ] Cross-encoder pequeno e local, atrás de flag, **desligado por padrão**
- [ ] Recuperar ~50 e rerankear para ~10
- [ ] Cache de reranking por `(query_hash, chunk_id)`
- [ ] Degradação limpa: sem o modelo, cai na heurística atual sem erro
- [ ] Custo de latência publicado ao lado do ganho

## Fora de escopo

- Reranking remoto ou por API paga — o RAGX é local por princípio
- Ligar por padrão antes de haver número que justifique

## Critérios de aceite

- [ ] Ganho medido no conjunto ampliado (`RAGX-0099`), com latência ao lado
- [ ] **Sem ganho medido, não entra** — a tarefa pode terminar em "avaliado e recusado", com o número
- [ ] Com o reranker ligado, `search` fica abaixo de 500 ms na segunda chamada

## Testes

- [ ] Teste de que a ausência do modelo não quebra a busca
- [ ] Teste do cache de reranking

## Notas

Esta é a única tarefa da fase que pode legitimamente terminar em 'não vale a pena'. Registrar o número negativo é entrega válida.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux, macOS e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] CHANGELOG atualizado na MESMA alteração
- [ ] Documentação confere com o comportamento implementado
