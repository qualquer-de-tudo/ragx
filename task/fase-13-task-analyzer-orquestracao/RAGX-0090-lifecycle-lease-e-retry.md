# RAGX-0090 — Lifecycle, lease e retry

| | |
|---|---|
| **Fase** | 13 — Task Analyzer + Orquestração |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 1d |
| **Depende de** | `RAGX-0089` |
| **Bloqueia** | `RAGX-0091` |
| **Documentação** | [21-orquestracao-de-tarefas.md](../../docs/21-orquestracao-de-tarefas.md) |
| **Status** | `todo` |

## Objetivo

Garantir que duas instâncias nunca executem a mesma tarefa, que agente morto não trave a fila, e que falha não gere retry infinito.

## Entregáveis

- [ ] Máquina de estados completa da §13, com transições válidas declaradas
- [ ] Reivindicação ATÔMICA: `UPDATE ... WHERE status='ready' AND lease expirado`; vencedor é quem vê `rowcount == 1`
- [ ] `BEGIN IMMEDIATE` — bloqueio de escrita no começo, não no commit
- [ ] Recuperação de lease vencido: `QUEUED` preso volta a `READY`, com evento
- [ ] Backoff `30s · 1m · 5m · 15m · 30m`, configurável, NUNCA infinito
- [ ] `task_errors` distingue falha de execução de falha de validação

## Fora de escopo

- Fila distribuída entre máquinas — o lease é local

## Critérios de aceite

- [ ] Dois workers concorrentes: exatamente UM obtém a tarefa
- [ ] Lease vencido é recuperado, não abandonado para sempre
- [ ] Retry esgotado para em FAILED
- [ ] `SELECT` seguido de `UPDATE` NÃO é usado para controle de concorrência

## Testes

- [ ] Threads reais disputando a mesma tarefa → 1 vencedor, o resto recusado
- [ ] Agente que morre deixa lease vencido; worker recupera no ciclo seguinte
- [ ] Backoff respeita a sequência e para no limite
- [ ] Toda transição inválida da matriz levanta erro

## Notas

Este é o arquivo onde um bug não aparece em desenvolvimento e aparece em produção sob carga. O teste de concorrência com threads reais não é opcional.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes
- [ ] `ruff` limpo
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
