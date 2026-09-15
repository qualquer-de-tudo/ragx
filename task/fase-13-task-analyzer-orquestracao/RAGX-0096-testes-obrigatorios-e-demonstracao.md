# RAGX-0096 — Testes obrigatórios e demonstração ponta a ponta

| | |
|---|---|
| **Fase** | 13 — Task Analyzer + Orquestração |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 1,5d |
| **Depende de** | `RAGX-0093`, `RAGX-0094`, `RAGX-0095` |
| **Bloqueia** | — |
| **Documentação** | [20-task-analyzer.md](../../docs/20-task-analyzer.md) · [21-orquestracao-de-tarefas.md](../../docs/21-orquestracao-de-tarefas.md) |
| **Status** | `todo` |

## Objetivo

Provar, com um projeto real, que o ciclo completo funciona — e cobrir os 8 cenários que a §35 do pedido exige.

## Entregáveis

- [ ] Os 8 cenários obrigatórios da §35, cada um num teste nomeado
- [ ] Demonstração ponta a ponta: solicitação → análise → documentação → knowledge → decomposição → SQLite → dependências → cron → agente → validação → knowledge update → próxima tarefa
- [ ] Teste de concorrência com threads reais
- [ ] Teste de recuperação após falha
- [ ] Medição honesta: quantas tarefas, quanto tempo, o que NÃO funcionou

## Fora de escopo

- Benchmark comparativo com outras ferramentas

## Critérios de aceite

- [ ] **Segredo NÃO chega ao agente** — verificado no contexto de tarefa
- [ ] **Tarefa bloqueada NÃO executa**
- [ ] **Dependência incompleta NÃO executa**
- [ ] **Dependência concluída LIBERA a próxima**
- [ ] **Worker duplicado NÃO executa a mesma tarefa**
- [ ] **Tarefa falha faz retry conforme a política**
- [ ] **Solicitação complexa documenta antes de executar**
- [ ] **Solicitação simples NÃO cria burocracia**

## Testes

- [ ] Os 8 acima, mais: DAG, estados, locking, scheduler, cron, worker, dispatcher, contexto, knowledge update, SQLite, MCP, ignore rules

## Notas

A demonstração precisa ser reproduzível por quem nunca viu o projeto, e o relatório precisa dizer o que NÃO funcionou. Demonstração que só mostra o caminho feliz não prova nada.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes
- [ ] `ruff` limpo
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
