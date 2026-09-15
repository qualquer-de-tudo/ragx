# RAGX-0094 — MCP de orquestração

| | |
|---|---|
| **Fase** | 13 — Task Analyzer + Orquestração |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 0,5d |
| **Depende de** | `RAGX-0091`, `RAGX-0083` |
| **Bloqueia** | `RAGX-0096` |
| **Documentação** | [ADR-0015](../../docs/adr/ADR-0015-quem-executa-a-tarefa.md) · [09-mcp.md](../../docs/09-mcp.md) |
| **Status** | `todo` |

## Objetivo

Dar ao agente o contrato para reivindicar e reportar trabalho — sem quebrar nenhuma invariante do ADR-0006.

## Entregáveis

- [ ] `analyze_request`, `plan_work`, `list_tasks`, `get_task`, `task_graph` (leitura)
- [ ] `next_task`, `claim_task`, `report_task_result`, `release_task` (escrita)
- [ ] `claim_task` devolve tarefa + contexto JÁ MONTADO
- [ ] Playbook atualizado: quando reivindicar, quando reportar, o que não fazer
- [ ] Todas sob `_guarded` e sob o mesmo rate limit

## Fora de escopo

- Qualquer ferramenta que execute comando ou leia arquivo

## Critérios de aceite

- [ ] `ragx.mcp` continua sem `open`, sem `pathlib`, sem rede — teste arquitetural inalterado
- [ ] `claim_task` de tarefa já reivindicada devolve erro estruturado, não exceção
- [ ] Nenhum segredo aparece em contexto de tarefa entregue por MCP
- [ ] Em modo `--read-only`, as ferramentas de escrita respondem `write_disabled`

## Testes

- [ ] Cliente MCP real: analyze → plan → claim → report → validate
- [ ] Duas sessões MCP disputando `claim_task`: uma ganha
- [ ] Teste arquitetural do ADR-0006 continua verde SEM ser relaxado

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes
- [ ] `ruff` limpo
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
