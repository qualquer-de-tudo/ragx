# RAGX-0113 — Marcar frescor do índice no resultado

| | |
|---|---|
| **Fase** | 14 — Evolução do RAG |
| **Onda** | 6 — confiança e evidência |
| **Prioridade** | P2 — media |
| **Estimativa** | 1d |
| **Depende de** | — |
| **Documentação** | [23-auditoria-e-evolucao-do-rag.md](../../docs/23-auditoria-e-evolucao-do-rag.md) · [19-watch-e-autonomia-do-agente.md](../../docs/19-watch-e-autonomia-do-agente.md) |
| **Status** | `todo` |

## Objetivo

Um agente que recebe um chunk não sabe se ele corresponde ao disco de agora. O chunk guarda `content_hash`; comparar com o arquivo diz se o índice está atrás. Hoje o agente raciocina sobre código velho sem saber.

## Entregáveis

- [ ] `stale: true` no resultado quando o `content_hash` do chunk não bate com o arquivo
- [ ] A verificação é barata: `mtime`/tamanho primeiro, hash só quando muda
- [ ] `stale` também no `ContextPack`, agregado
- [ ] O playbook orienta: com `stale`, chamar `refresh` antes de concluir

## Fora de escopo

- Reindexar automaticamente durante a busca — o agente decide, a busca informa
- Verificar o disco dentro do `ragx.mcp` (ADR-0006 proíbe; a verificação vive na camada abaixo)

## Critérios de aceite

- [ ] Editar um arquivo sem reindexar faz o resultado vir com `stale: true`
- [ ] O custo da verificação fica abaixo de 20 ms para 50 resultados
- [ ] Sem acesso ao arquivo (índice importado de outra máquina), `stale` vem ausente, não `false`

## Testes

- [ ] Teste de que editar o arquivo marca stale
- [ ] Teste de que o índice importado não afirma frescor que não pode verificar

## Notas

Cuidado com a fronteira do ADR-0006: `ragx.mcp` não pode tocar o filesystem. A verificação pertence à camada de busca, que já lê o banco.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux, macOS e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] CHANGELOG atualizado na MESMA alteração
- [ ] Documentação confere com o comportamento implementado
