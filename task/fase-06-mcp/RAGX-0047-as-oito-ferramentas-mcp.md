# RAGX-0047 — As oito ferramentas MCP

| | |
|---|---|
| **Fase** | 6 — MCP |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 1d |
| **Depende de** | `RAGX-0046` |
| **Bloqueia** | `RAGX-0048` |
| **Documentação** | [09-mcp.md](../../docs/09-mcp.md) |
| **Status** | `todo` |

## Objetivo

Expor o núcleo ao agente, cada ferramenta como tradução direta de um serviço existente.

## Entregáveis

- [ ] `get_dictionary`, `search_knowledge`, `search_hybrid`, `get_document`, `get_chunk`, `get_entity`, `search_graph`, `build_context`
- [ ] Descrições que ensinam a ordem de uso recomendada (dictionary → search → context → chunk)
- [ ] `get_document` consulta o store por caminho relativo; caminho não indexado → `not_found`
- [ ] Zero lógica de negócio: cada ferramenta é validar → chamar serviço → serializar

## Fora de escopo

- Ferramenta de reindexação — fica atrás de `--allow-index`, desligada por padrão

## Critérios de aceite

- [ ] Agente externo consulta dicionário, busca, navega o grafo e monta contexto usando só MCP
- [ ] Nenhuma ferramenta aceita caminho absoluto ou `..`
- [ ] `search_hybrid` responde em menos de 300 ms em índice de 10k chunks
- [ ] Comportamento idêntico ao da CLI equivalente (mesmo serviço por baixo)

## Testes

- [ ] Contrato por ferramenta
- [ ] Comparação CLI × MCP para a mesma consulta

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
