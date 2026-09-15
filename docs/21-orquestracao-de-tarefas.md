# 21 — Orquestração de tarefas

> Da decomposição à conclusão: banco, DAG, estados, lease, retry, scheduler.
> Ver [20 — Task Analyzer](20-task-analyzer.md),
> [ADR-0014](adr/ADR-0014-orquestracao-local-e-o-que-e-versionavel.md) e
> [ADR-0015](adr/ADR-0015-quem-executa-a-tarefa.md).

## Componentes

Nenhum agente monolítico. Cada peça faz uma coisa:

| Componente | Responsabilidade |
|---|---|
| `TaskAnalyzer` | classifica a solicitação ([20](20-task-analyzer.md)) |
| `DocumentationPlanner` | decide **quais** documentos, com que contexto |
| `TaskDecomposer` | transforma o plano em tarefas e dependências |
| `TaskRepository` | persistência; a única coisa que fala SQL de tarefas |
| `DependencyResolver` | DAG, ciclos, quem está pronto |
| `TaskContextBuilder` | monta o contexto por tarefa (Context Engine) |
| `TaskDispatcher` | reivindica com lease, entrega, recebe resultado |
| `TaskValidator` | checagens determinísticas sobre o resultado |
| `ResultProcessor` | persiste, promove conhecimento, libera dependentes |
| `Scheduler` | cron, intervalo, evento |
| `Worker` | acorda, faz transições, sai |
| `AgentSelector` | escolhe o perfil de agente pela tarefa |

Todos consomem o RAGX existente — busca, grafo, contexto, dicionário, gate.
Nada é duplicado.

## O banco

`.ragx/ragx.sqlite`, separado do `knowledge.db`
([ADR-0014](adr/ADR-0014-orquestracao-local-e-o-que-e-versionavel.md)).

```text
projects              projeto = uma solicitação analisada
tasks                 unidade de trabalho
task_dependencies     arestas do DAG
task_runs             uma execução (claim → result)
task_attempts         tentativa dentro de um run
task_logs             linhas de log por tarefa
task_artifacts        arquivos produzidos
task_context          contexto montado (hash + tokens)
task_results          resultado estruturado
task_errors           falhas com causa
task_events           trilha append-only
agents                perfis disponíveis
agent_runs            execução por agente
schedules             agendamentos
knowledge_documents   documentos planejados/gerados
knowledge_versions    versões de documento
decisions             decision records
approvals             aprovações humanas
```

Índices onde as consultas quentes batem:

```sql
tasks(status, priority)             -- a fila
tasks(project_id, status)
tasks(parent_task_id)
tasks(lock_expires_at)              -- expiração de lease
task_dependencies(task_id)
task_dependencies(depends_on_task_id)
task_runs(task_id, status)
task_events(task_id, created_at)
```

A fila é **uma consulta**, não N+1: um `LEFT JOIN` contra dependências
pendentes devolve as tarefas prontas de uma vez.

## O que viaja no Git

```text
knowledge/tasks/projects/*.json     definição do projeto
knowledge/tasks/tasks/*.json        tarefa, dependências, aceite
knowledge/decisions/*.md            decision records
```

Execução (runs, tentativas, logs, locks, retry) **nunca** é versionada. Depois
de `git pull && ragx sync`, o board volta íntegro e o histórico local não volta
— e a saída diz isso, em vez de fingir.

Conflito em `status` resolve por precedência declarada:

```text
cancelled > completed > failed > blocked > running > ready > pending
```

`running` vindo do Git vira `pending` na reidratação: não existe execução de
outra máquina que valha para esta.

## Estados

```text
                 ┌──────────┐
                 │ PENDING  │  criada; dependências abertas
                 └────┬─────┘
       dependências fecham
                 ┌────▼─────┐
                 │  READY   │  pode ser reivindicada
                 └────┬─────┘
                 claim_task
                 ┌────▼─────┐
                 │  QUEUED  │  reivindicada, lease ativo
                 └────┬─────┘
                 ┌────▼─────┐      ┌──────────────────┐
                 │ RUNNING  ├─────►│ WAITING_APPROVAL │
                 └────┬─────┘      └──────────────────┘
        ┌─────────────┼─────────────┐
        ▼             ▼             ▼
  ┌───────────┐ ┌──────────┐  ┌─────────┐
  │ COMPLETED │ │  FAILED  │  │ BLOCKED │
  └───────────┘ └────┬─────┘  └─────────┘
                     │ retry_count < max
                ┌────▼─────┐
                │ RETRYING │ ──► READY (após next_retry_at)
                └──────────┘

  CANCELLED e SKIPPED são terminais, alcançáveis de qualquer estado por
  decisão humana.
```

Transições inválidas são **recusadas pelo repositório**, não evitadas por
convenção. `COMPLETED → RUNNING` levanta erro.

## DAG

```text
TASK-001 analisar
    ↓
TASK-002 documentar
    ↓
TASK-003 banco ────────┐
                       ↓
TASK-004 backend ──────┤
                       ↓
TASK-005 frontend      │
                       ↓
TASK-006 integração ◄──┘
```

Relações suportadas: `depends_on`, `blocks`, `blocked_by`, `parent`, `child`,
`related_to`. As quatro primeiras afetam a prontidão; `related_to` é só
navegação.

**Ciclo é recusado na criação**, não descoberto na execução. Uma dependência
que fecharia um ciclo levanta erro com o caminho completo:

```
ciclo: TASK-003 → TASK-005 → TASK-004 → TASK-003
```

## Lease e concorrência

Dois workers não podem executar a mesma tarefa. Não basta `SELECT` e depois
`UPDATE` — entre os dois, outro processo passa.

A reivindicação é **uma instrução condicional**, e quem ganhou é quem viu
`rowcount == 1`:

```sql
UPDATE tasks
   SET status = 'queued',
       locked_by = :worker,
       locked_at = :now,
       lock_expires_at = :now_plus_lease
 WHERE id = :task
   AND status = 'ready'
   AND (lock_expires_at IS NULL OR lock_expires_at < :now);
```

`IMMEDIATE` na transação, para que o bloqueio de escrita seja adquirido no
começo e não no commit — é o que evita `SQLITE_BUSY` em escalada.

**Lease expirado é recuperado, não abandonado.** Agente que morreu no meio
deixa a tarefa presa em `QUEUED` com lease vencido; o worker a devolve para
`READY` e registra o evento. Sem isso, uma queda trava a fila para sempre.

## Retry

```text
retry_count  max_retries  next_retry_at  last_error
```

Backoff configurável, padrão `30s · 1m · 5m · 15m · 30m`. Esgotado, a tarefa
fica `FAILED` e para. **Nunca infinito.**

Falha de validação e falha de execução contam igual, mas registram causas
diferentes em `task_errors` — retry de resultado inválido normalmente não
adianta, e o motivo precisa aparecer.

## Scheduler e worker

O cron **só acorda** o RAGX. A inteligência está no worker.

```cron
*/5 * * * * cd /caminho/do/projeto && ragx worker
```

Cada ciclo:

```text
1. expira leases vencidos            QUEUED/RUNNING presos → READY
2. promove PENDING → READY           dependências fechadas
3. aplica retry vencido              RETRYING → READY
4. dispara agendamentos vencidos     schedules.next_run_at <= agora
5. emite eventos pendentes
6. reporta e sai
```

O worker **não executa tarefa** ([ADR-0015](adr/ADR-0015-quem-executa-a-tarefa.md)).
Ele mantém a fila correta para que o agente encontre trabalho pronto.

Tipos de agendamento: `once`, `cron`, `interval`, `dependency`, `event`,
`manual`.

## Eventos

Polling resolve o caso geral; evento resolve a latência.

```text
TASK_COMPLETED · TASK_FAILED · TASK_BLOCKED
KNOWLEDGE_UPDATED · DOCUMENT_UPDATED · GIT_MERGED · AGENT_FINISHED
```

```text
TASK-003 COMPLETED
    ↓ evento
TASK-004 fica READY imediatamente
    ↓
o agente encontra trabalho no próximo claim_task
```

`task_events` é append-only e é a trilha de auditoria: por que uma tarefa
mudou de estado, quando, e por quem.

## Contexto por tarefa

O agente **não recebe o projeto inteiro**.

```text
tarefa (título, descrição, aceite, escopo)
   ↓
Context Engine (docs/07)  ── orçamento de tokens
   ↓
resultados das dependências já concluídas
   ↓
decisões registradas que tocam o assunto
   ↓
conhecimento base (@base/...) filtrado pelo tipo da tarefa
   ↓
pacote entregue no claim_task
```

O contexto é gravado em `task_context` com hash e contagem de tokens — dá para
saber depois com o que o agente trabalhou.

## Validação

Determinística, sem juízo sobre qualidade
([ADR-0015](adr/ADR-0015-quem-executa-a-tarefa.md)):

- todo critério de aceite marcado, com evidência
- `files_changed` existem e estão indexados
- arquivos tocados dentro de `files_scope`
- nenhum arquivo tocado bloqueado pelo Security Gate
- teste declarado quando `test_requirements` exige
- `summary` não vazio

Falhou → `FAILED` com o motivo. O RAGX não sabe julgar se o código é bom, e um
validador que finge saber aprova o errado com autoridade.

## Feedback

```text
TASK-001 descobre uma restrição arquitetural
    ↓
decisão registrada (decisions/)
    ↓
indexada pelo pipeline normal
    ↓
TASK-004 recebe a restrição no contexto, sem ninguém lembrar de contar
```

É o que faz o projeto ficar mais barato à medida que avança.

## Segurança

O Security Gate roda **antes** de parse, chunk, embedding, grafo, contexto,
tarefa, agente, export e MCP — sem exceção nova nesta fase.

Consequências concretas para a orquestração:

- documento gerado entra pelo pipeline normal; se contiver segredo, é bloqueado
- contexto de tarefa vem do índice, que não contém segredo
- `files_scope` bloqueado pelo gate faz a tarefa falhar na validação
- nenhuma ferramenta MCP de tarefa lê o filesystem

## Comandos

```bash
ragx task analyze "<pedido>"        classifica; não escreve nada
ragx task plan "<pedido>" --apply   cria projeto, documentos e tarefas
ragx task list [--status --project]
ragx task show TASK-001
ragx task next                      a próxima executável
ragx task context TASK-001          o contexto que o agente receberia
ragx task run TASK-001              imprime tarefa + contexto (manual)
ragx task result TASK-001 --file r.json
ragx task validate TASK-001
ragx task retry|cancel|block|unblock TASK-001
ragx task dependencies TASK-001
ragx task graph [--project P]
ragx task status                    painel
ragx task logs TASK-001

ragx worker [--once]                transições de estado
ragx schedule list|add|remove|enable|disable
```

## Ver também

- [20 — Task Analyzer](20-task-analyzer.md)
- [07 — Context Engine](07-context-engine.md)
- [09 — MCP](09-mcp.md)
- [ADR-0014](adr/ADR-0014-orquestracao-local-e-o-que-e-versionavel.md) · [ADR-0015](adr/ADR-0015-quem-executa-a-tarefa.md)
