# RAGX-0086 — Banco de orquestração

| | |
|---|---|
| **Fase** | 13 — Task Analyzer + Orquestração |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 1,5d |
| **Depende de** | `RAGX-0009` |
| **Bloqueia** | `RAGX-0087` .. `RAGX-0096` |
| **Documentação** | [21-orquestracao-de-tarefas.md](../../docs/21-orquestracao-de-tarefas.md) · [ADR-0014](../../docs/adr/ADR-0014-orquestracao-local-e-o-que-e-versionavel.md) |
| **Status** | `todo` |

## Objetivo

Dar à orquestração um store próprio, com esquema explícito e migrações versionadas — separado do `knowledge.db` pelas razões do ADR-0014.

## Entregáveis

- [ ] `.ragx/ragx.sqlite` com runner de migração próprio (`PRAGMA user_version` independente)
- [ ] As 18 tabelas da §12 do pedido, com `FOREIGN KEY` e `CHECK` de estado
- [ ] Índices: `tasks(status, priority)`, `tasks(project_id, status)`, `tasks(parent_task_id)`, `tasks(lock_expires_at)`, `task_dependencies(task_id)`, `task_dependencies(depends_on_task_id)`, `task_runs(task_id, status)`, `task_events(task_id, created_at)`
- [ ] `TaskRepository` — o ÚNICO módulo que escreve SQL de tarefa
- [ ] Fila resolvida em UMA consulta (LEFT JOIN contra dependências abertas), sem N+1
- [ ] `ragx.toml` `[tasks]`: `lease_seconds`, `max_retries`, `backoff`, `max_concurrency`

## Fora de escopo

- Qualquer lógica de decisão — aqui é só persistência
- Versionamento em `knowledge/` (é a RAGX-0095)

## Critérios de aceite

- [ ] Dois bancos coexistem; `ragx vacuum` no `knowledge.db` não toca no `ragx.sqlite`
- [ ] `ragx reset` avisa que o histórico de execução será perdido
- [ ] Transição de estado inválida é RECUSADA pelo repositório, não evitada por convenção
- [ ] Listar a fila de 500 tarefas com dependências faz poucas consultas, não uma por tarefa

## Testes

- [ ] Migração idempotente; aplicar duas vezes não muda nada
- [ ] `COMPLETED → RUNNING` levanta erro
- [ ] Contagem de queries na listagem da fila (prova de ausência de N+1)

## Notas

O [ADR-0014](../../docs/adr/ADR-0014-orquestracao-local-e-o-que-e-versionavel.md) abre exceção explícita ao ADR-0002. A justificativa (VACUUM contra o worker, `reset` apagando histórico) precisa estar no código, não só no ADR.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes
- [ ] `ruff` limpo
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
