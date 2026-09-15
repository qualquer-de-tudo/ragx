# RAGX-0089 — Task Decomposer e DAG

| | |
|---|---|
| **Fase** | 13 — Task Analyzer + Orquestração |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 1,5d |
| **Depende de** | `RAGX-0088` |
| **Bloqueia** | `RAGX-0090` |
| **Documentação** | [21-orquestracao-de-tarefas.md](../../docs/21-orquestracao-de-tarefas.md) |
| **Status** | `todo` |

## Objetivo

Transformar plano em tarefas executáveis, com dependências, prioridade e critérios de aceite — e garantir que o grafo seja acíclico por construção.

## Entregáveis

- [ ] `TaskDecomposer`: plano → tarefas com todos os campos da §9 do pedido
- [ ] Trilhas: análise, documentação, banco, backend, frontend, integração, testes, segurança, performance, deploy, monitoramento
- [ ] `DependencyResolver`: `depends_on`, `blocks`, `blocked_by`, `parent`, `child`, `related_to`
- [ ] Detecção de ciclo NA CRIAÇÃO, com o caminho completo na mensagem
- [ ] Ordem topológica e cálculo de prontidão
- [ ] `files_scope` derivado do grafo — que arquivos a tarefa provavelmente toca

## Fora de escopo

- Estimar prazo
- Decompor tarefa simples — DIRECT_EXECUTION não vira projeto

## Critérios de aceite

- [ ] Solicitação complexa vira várias tarefas com dependências coerentes
- [ ] Dependência que fecharia ciclo é recusada com o caminho completo
- [ ] Toda tarefa nasce com ao menos um critério de aceite
- [ ] DIRECT_EXECUTION NÃO cria projeto nem tarefas

## Testes

- [ ] Ciclo de 2, de 3 e auto-dependência — todos recusados
- [ ] Ordem topológica estável com muitas tarefas
- [ ] Tarefa sem critério de aceite é recusada

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes
- [ ] `ruff` limpo
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
