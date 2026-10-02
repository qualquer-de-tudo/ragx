# RAGX-0104 — Prefixos de consulta e documento no provider fastembed

| | |
|---|---|
| **Fase** | 14 — Evolução do RAG |
| **Onda** | 3 — braço semântico |
| **Prioridade** | P1 — alta |
| **Estimativa** | 0,5d |
| **Depende de** | `RAGX-0103` |
| **Documentação** | [23-auditoria-e-evolucao-do-rag.md](../../docs/23-auditoria-e-evolucao-do-rag.md) · [adr/ADR-0004-embeddings.md](../../docs/adr/ADR-0004-embeddings.md) |
| **Status** | `done` |

## Objetivo

A interface `Embedder` já separa `embed_query` de `embed_documents`, mas o provider `fastembed` não aplica prefixo nenhum. Modelos assimétricos (`nomic`, `e5`) dependem desses prefixos para saber qual lado da assimetria estão codificando.

## Entregáveis

- [x] `FastEmbedEmbedder` aplica o prefixo correto por modelo (`search_query:`/`search_document:` no nomic; `query:`/`passage:` no e5)
- [x] O mapa de prefixos é declarado, não adivinhado por heurística de nome
- [x] Modelo sem prefixo conhecido continua funcionando, sem prefixo
- [x] O prefixo entra no `model_id`, para que trocar prefixo invalide os vetores

## Fora de escopo

- Prefixos no provider `ollama`, que já os aplica

## Critérios de aceite

- [x] Consultas e documentos são embutidos com prefixos diferentes, verificável no teste
- [ ] Ganho (ou ausência de ganho) medido no conjunto ampliado e publicado — **não aplicável hoje**: o modelo padrão é simétrico e não leva prefixo, então não há o que comparar; só passa a existir quando a RAGX-0103 trocar o modelo por um assimétrico (e depois da RAGX-0099)
- [x] Trocar o prefixo invalida o cache de embeddings

## Testes

- [x] Teste de que `embed_query` e `embed_documents` produzem vetores diferentes para o MESMO texto
- [x] Teste do mapa de prefixos por modelo

## Notas

Sem isto, metade do benefício de um modelo assimétrico se perde — ele passa a ser usado como se fosse simétrico.

## Definition of Done

- [x] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux, macOS e Windows (verdes no Windows; Linux e macOS só a CI)
- [x] `ruff` e `mypy` limpos
- [x] Suíte `security/` continua verde
- [x] CHANGELOG atualizado na MESMA alteração
- [x] Documentação confere com o comportamento implementado

## Andamento

- 2026-10-02 — Feito sem trocar o modelo (a 0103 continua `todo`, é decisão de produto): `PREFIXES` declarado (e5 e nomic), `prefixes_for` e `model_id` em `fastembed_provider.py`; o heurístico `"e5" in model` saiu; `embedder_id()` usa o mesmo `model_id` (paridade coberta por teste). O id de um modelo com prefixo muda (`#p<hash>`), o de um sem prefixo não. 5 testes novos em `tests/unit/test_embeddings.py`. Efeito colateral aceito: um índice feito com `e5` antes desta tarefa (que já usava prefixo, sem tag no id) será considerado de outro modelo e reembutido; ninguém neste repositório usa `e5`.
