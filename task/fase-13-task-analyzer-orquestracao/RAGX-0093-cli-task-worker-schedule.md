# RAGX-0093 — CLI `ragx task`, `ragx worker`, `ragx schedule`

| | |
|---|---|
| **Fase** | 13 — Task Analyzer + Orquestração |
| **Prioridade** | P1 — alta |
| **Estimativa** | 1d |
| **Depende de** | `RAGX-0092` |
| **Bloqueia** | `RAGX-0096` |
| **Documentação** | [20-task-analyzer.md](../../docs/20-task-analyzer.md) · [21-orquestracao-de-tarefas.md](../../docs/21-orquestracao-de-tarefas.md) |
| **Status** | `todo` |

## Objetivo

Tornar tudo operável e inspecionável pela linha de comando.

## Entregáveis

- [ ] `ragx task analyze|plan|list|show|next|context|run|result|validate|retry|cancel|block|unblock|dependencies|graph|status|logs`
- [ ] `ragx worker [--once]`
- [ ] `ragx schedule list|add|remove|enable|disable`
- [ ] `--json` em tudo
- [ ] Painel de monitoramento da §31 do pedido
- [ ] Toda saída documentada em `docs/14-cli.md`

## Fora de escopo

- Interface web ou TUI

## Critérios de aceite

- [ ] `ragx task analyze` não escreve nada; `ragx task plan --apply` escreve
- [ ] `ragx task graph` desenha o DAG legível no terminal
- [ ] Todo comando novo passa no teste de documentação existente
- [ ] Nenhuma saída ecoa entrada do usuário sem `safe_echo`

## Testes

- [ ] E2E: analyze → plan --apply → list → next → context → result → validate
- [ ] Teste de documentação (todo comando em `docs/14-cli.md`) continua verde

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes
- [ ] `ruff` limpo
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
