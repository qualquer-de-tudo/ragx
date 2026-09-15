# RAGX-0092 — Scheduler, worker e eventos

| | |
|---|---|
| **Fase** | 13 — Task Analyzer + Orquestração |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 1d |
| **Depende de** | `RAGX-0091` |
| **Bloqueia** | `RAGX-0093` |
| **Documentação** | [21-orquestracao-de-tarefas.md](../../docs/21-orquestracao-de-tarefas.md) |
| **Status** | `todo` |

## Objetivo

Manter a fila correta sozinho: expirar lease, promover o que ficou pronto, aplicar retry vencido e disparar agendamentos.

## Entregáveis

- [ ] `ragx worker` com os 6 passos do ciclo, `--once` para cron
- [ ] `schedules` com `once`, `cron`, `interval`, `dependency`, `event`, `manual`
- [ ] Parser de cron mínimo (5 campos), sem dependência nova
- [ ] Eventos: TASK_COMPLETED, TASK_FAILED, TASK_BLOCKED, KNOWLEDGE_UPDATED, DOCUMENT_UPDATED, GIT_MERGED, AGENT_FINISHED
- [ ] `task_events` append-only como trilha de auditoria
- [ ] `max_concurrency` por projeto

## Fora de escopo

- Daemon do sistema operacional — o cron acorda, o worker decide
- Executar tarefa (ADR-0015)

## Critérios de aceite

- [ ] `ragx worker --once` é idempotente: rodar duas vezes seguidas não muda nada na segunda
- [ ] Worker NUNCA executa tarefa
- [ ] Lease vencido é recuperado no ciclo
- [ ] Agendamento vencido dispara uma vez, não em laço
- [ ] Falha num passo não derruba o ciclo inteiro

## Testes

- [ ] Ciclo completo com fila real: tarefas, dependências, uma falha, um lease vencido
- [ ] Parser de cron: expressões válidas e inválidas
- [ ] Idempotência do `--once`

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes
- [ ] `ruff` limpo
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
