# RAGX-0104 — Prefixos de consulta e documento no provider fastembed

| | |
|---|---|
| **Fase** | 14 — Evolução do RAG |
| **Onda** | 3 — braço semântico |
| **Prioridade** | P1 — alta |
| **Estimativa** | 0,5d |
| **Depende de** | `RAGX-0103` |
| **Documentação** | [23-auditoria-e-evolucao-do-rag.md](../../docs/23-auditoria-e-evolucao-do-rag.md) · [adr/ADR-0004-embeddings.md](../../docs/adr/ADR-0004-embeddings.md) |
| **Status** | `todo` |

## Objetivo

A interface `Embedder` já separa `embed_query` de `embed_documents`, mas o provider `fastembed` não aplica prefixo nenhum. Modelos assimétricos (`nomic`, `e5`) dependem desses prefixos para saber qual lado da assimetria estão codificando.

## Entregáveis

- [ ] `FastEmbedEmbedder` aplica o prefixo correto por modelo (`search_query:`/`search_document:` no nomic; `query:`/`passage:` no e5)
- [ ] O mapa de prefixos é declarado, não adivinhado por heurística de nome
- [ ] Modelo sem prefixo conhecido continua funcionando, sem prefixo
- [ ] O prefixo entra no `model_id`, para que trocar prefixo invalide os vetores

## Fora de escopo

- Prefixos no provider `ollama`, que já os aplica

## Critérios de aceite

- [ ] Consultas e documentos são embutidos com prefixos diferentes, verificável no teste
- [ ] Ganho (ou ausência de ganho) medido no conjunto ampliado e publicado
- [ ] Trocar o prefixo invalida o cache de embeddings

## Testes

- [ ] Teste de que `embed_query` e `embed_documents` produzem vetores diferentes para o MESMO texto
- [ ] Teste do mapa de prefixos por modelo

## Notas

Sem isto, metade do benefício de um modelo assimétrico se perde — ele passa a ser usado como se fosse simétrico.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux, macOS e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] CHANGELOG atualizado na MESMA alteração
- [ ] Documentação confere com o comportamento implementado
